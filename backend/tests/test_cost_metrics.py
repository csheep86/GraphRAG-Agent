"""M6 §4.3 成本日聚合（P6-V）：**写入去重** 与 **仪表盘口径**。

为什么本文件分两组：

1. **服务层**（:func:`record_answer_usage` / :func:`build_dashboard`）用**真 PG**
   ——去重写在 SQL 与 Python 之间（``ON CONFLICT`` + 行锁），打桩测不出来，
   打桩版只会把实现重述一遍（纪律 R-2：别给影子测 whistle）；
2. **路由层**只验契约组装与默认区间，数据落在真实表里（**不再** monkeypatch 服务
   函数）——占位期那条「恒 501」的判据**已被本批取代**：那时验的是"没实现"，
   实现到位后判据就该换成"真出数"。

每个用例自带 ``org_id`` 并在 finally 里清干净。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.models import CostMetric
from app.db.session import session_scope
from app.services.cost_metrics import build_dashboard, record_answer_usage

DASHBOARD_PATH = "/api/v1/cost/dashboard"
RESPONSE_KEYS = {"token_usage_total", "single_doc_cost", "cost_ratio", "by_date"}


def _usage(prompt: int = 100, completion: int = 50, total: int = 150) -> Any:
    """``TokenUsage`` 形态的最小替身（属性名对齐即可）。"""
    return SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=total
    )


def _cleanup(org_id: uuid.UUID) -> None:
    with session_scope(org_id=org_id) as db:
        db.execute(delete(CostMetric).where(CostMetric.org_id == org_id))
        db.commit()


def _row(org_id: uuid.UUID, day: date) -> CostMetric | None:
    with session_scope(org_id=org_id) as db:
        return db.scalar(
            select(CostMetric).where(
                CostMetric.org_id == org_id,
                CostMetric.metric_date == day,
            )
        )


def test_record_accumulates_tokens_and_dedupes_documents() -> None:
    """同一天多次问答：token 累加、文档**去重**计数（偏离 X-3 的核心断言）。

    同一份文档问两次若不去重 ⇒ ``single_doc_cost`` 随提问次数单调下降，
    指标就成了「多问几次即可刷绿」的数字。
    """
    org_id = uuid.uuid4()
    today = datetime.now(UTC).date()
    doc_a, doc_b, doc_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    try:
        with session_scope(org_id=org_id) as db:
            record_answer_usage(
                org_id=org_id,
                token_usage=_usage(100, 50, 150),
                doc_ids=[doc_a, doc_b],
                db=db,
            )
            record_answer_usage(
                org_id=org_id,
                token_usage=_usage(200, 100, 300),
                doc_ids=[doc_b, doc_c],  # doc_b 重复 ⇒ 不该被数第二次
                db=db,
            )

        row = _row(org_id, today)
        assert row is not None, "当日成本行没有落下来"
        assert row.token_usage_input == 300
        assert row.token_usage_output == 150
        assert row.token_usage_total == 450
        # 3 份而不是 4 份：本批最容易写错的一处
        assert row.doc_count == 3, f"文档去重失效：实读={row.doc_count}（期望 3）"
        assert len(row.counted_doc_ids) == 3
        assert row.single_doc_cost == pytest.approx(450 / 3)
    finally:
        _cleanup(org_id)


def test_record_skips_when_no_usage_or_no_session() -> None:
    """拒答（无 token_usage）/ 无 PG 会话：**跳过**，不许写 0、也不许把主链路拖崩。

    写 0 会让仪表盘看起来"有数据"；抛异常则会让一次好好的问答 500 ——
    记帐是旁路，不该反向拖垮主链路。
    """
    org_id = uuid.uuid4()
    today = datetime.now(UTC).date()
    try:
        assert record_answer_usage(org_id=org_id, token_usage=None) is None
        assert record_answer_usage(org_id=org_id, token_usage=_usage(), db=None) is None
        assert _row(org_id, today) is None, "没有会话却把行建出来了"
    finally:
        _cleanup(org_id)


def test_dashboard_aggregates_range_without_averaging_daily_values() -> None:
    """区间聚合：**先求和再相除**，不是对按天值再取一次平均。"""
    org_id = uuid.uuid4()
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    try:
        with session_scope(org_id=org_id) as db:
            db.add_all(
                [
                    CostMetric(
                        org_id=org_id,
                        metric_date=yesterday,
                        token_usage_input=10,
                        token_usage_output=0,
                        token_usage_total=10,
                        doc_count=1,
                        counted_doc_ids=[str(uuid.uuid4())],
                        single_doc_cost=10.0,
                    ),
                    CostMetric(
                        org_id=org_id,
                        metric_date=today,
                        token_usage_input=900,
                        token_usage_output=90,
                        token_usage_total=990,
                        doc_count=9,
                        counted_doc_ids=[str(uuid.uuid4()) for _ in range(9)],
                        single_doc_cost=110.0,
                        incremental_cost=30.0,
                        full_rebuild_cost=100.0,
                        cost_ratio=0.30,
                    ),
                ]
            )
            db.commit()

            payload = build_dashboard(
                db=db, org_id=org_id, date_from=yesterday, date_to=today
            )

        # 1000 token / 10 文档 = 100；若按「两天均值」则为 (10+110)/2 = 60
        assert payload["token_usage_total"] == 1000
        assert payload["single_doc_cost"] == pytest.approx(100.0)
        assert payload["cost_ratio"] == pytest.approx(0.30)
        assert [item["date"] for item in payload["by_date"]] == [yesterday, today]
    finally:
        _cleanup(org_id)


def test_dashboard_endpoint_returns_real_rows(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """路由层：不再 501，而是真出数（占位期「恒 501」的判据已被本条取代）。"""
    org_id = get_settings().default_org_id  # == dev_headers 的租户
    today = datetime.now(UTC).date()
    try:
        with session_scope(org_id=org_id) as db:
            # ⚠️ **本租户当日必须先清空**（P6-V3 起因起的脆弱性）：自本批起
            # ``incremental_cost`` / ``full_rebuild_cost`` 有了真实写入方，而真图用例
            # （``test_kg_incremental_rebuild.py``）也跑在 default_org 上 ⇒ 区间里可能
            # 已经有别人建的行，"无增量 ⇒ 0.0"这条断言就不再取决于本用例，
            # 而取决于**执行顺序**。⇒ 先清当日，再落自己的那一行。
            db.execute(
                delete(CostMetric).where(
                    CostMetric.org_id == org_id, CostMetric.metric_date == today
                )
            )
            db.add(
                CostMetric(
                    org_id=org_id,
                    metric_date=today,
                    token_usage_input=400,
                    token_usage_output=100,
                    token_usage_total=500,
                    doc_count=5,
                    counted_doc_ids=[str(uuid.uuid4()) for _ in range(5)],
                    single_doc_cost=100.0,
                )
            )
            db.commit()

        response = client.get(
            DASHBOARD_PATH,
            headers=dev_headers,
            params={
                "date_from": today.isoformat(),
                "date_to": today.isoformat(),
            },
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == RESPONSE_KEYS
        assert body["token_usage_total"] == 500
        assert body["single_doc_cost"] == pytest.approx(100.0)
        # 无增量成本 ⇒ 0.0（契约要求 `ge=0` 的 float，不许是 null）
        assert body["cost_ratio"] == pytest.approx(0.0)
        assert [item["date"] for item in body["by_date"]] == [today.isoformat()]
    finally:
        _cleanup(org_id)


def test_dashboard_does_not_see_another_tenants_rows(
    client: TestClient, dev_headers: dict[str, str]
) -> None:
    """跨租户：org B 的成本行在默认租户视野下**一行都看不到**（不报错、不串号）。

    与 G-26 的差异：那条验的是「RLS 策略是否存在」，本条验的是**应用层 org_id
    过滤也守着**（ADR-0003 §4.1 的 T1/T2 精神）——两者是两道独立的防线。
    """
    other_org = uuid.UUID("00000000-0000-4000-8000-000000000002")
    today = datetime.now(UTC).date()
    try:
        with session_scope(org_id=other_org) as db:
            db.add(
                CostMetric(
                    org_id=other_org,
                    metric_date=today,
                    token_usage_input=999,
                    token_usage_output=999,
                    token_usage_total=1998,
                    doc_count=1,
                    counted_doc_ids=[str(uuid.uuid4())],
                    single_doc_cost=1998.0,
                )
            )
            db.commit()

        response = client.get(
            DASHBOARD_PATH,
            headers=dev_headers,
            params={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )

        assert response.status_code == 200, response.text
        assert response.json()["token_usage_total"] == 0
    finally:
        _cleanup(other_org)
