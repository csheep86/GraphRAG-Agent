"""P6-V4：**C3-a / C3-b 出数化**的行为测试（proposal J1~J5）。

钉死五件事：

1. **J1**：``blocked_by`` 只写**当前真实缺口**，不得出现已失效的旧文案
   （「缺 M2 抽取侧」/「无写入方」）——那两条落点分别在 P6-V2 / P6-V3 就落地了；
2. **J2**：``BLOCKED`` 的 ``value`` **恒为 ``None`` 而不是 0**（0 会被读成"成本真的小"）；
3. **J3**：有 ``stage='extraction'`` 样本行 ⇒ C3-a **真的出数**（``unit=token/doc``）；
4. **J4**：C3-b 有分母 ⇒ 出比值；**无分母 ⇒ 仍是 ``BLOCKED``**（不按 0.0 计）；
5. **J5**：取样器导出的 JSON **真能被 ``--calibrate`` 吃下**且**不改配置**。

**为什么单开一个文件**：``test_eval_acceptance_cli.py`` 走的是**子进程 CLI** 契约
（跑得慢、且只能看到 offline 形态），而本批要考的是 evaluator 在有数据 / 无数据
两种情况下的**分支**——靠子进程只能覆盖无数据那一半。
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

from app.db.models import COST_STAGE_EXTRACTION, CostMetric
from app.db.session import session_scope
from app.evaluation.criteria import (
    THRESHOLD_PROVISIONAL,
    CriterionResult,
    CriterionStatus,
    Verdict,
)
from app.evaluation.runner import (
    C_COST,
    C_COST_RATIO,
    RunnerContext,
    run,
)
from app.services.cost_metrics import aggregate_stage, to_cost_records

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND_DIR / "scripts" / "eval_acceptance.py"

#: **J1 的两条失效文案**（P6-V4 立项的直接原因）：它们曾经是真的，
#: 但落点补齐后没人通知 ⇒ runner 继续对全世界宣布"还差一整张表/写入方"。
STALE_COST_PHRASES = (
    "缺 M2 抽取侧",  # 落点 P6-V2 已落地
    "无写入方",  # 两侧写入方 P6-V3 已落地
    "P5-M6",  # 批次名当永久占位（P6-V 已订正过一次，别再回来）
)


def _ctx(mode: str = "live") -> RunnerContext:
    return RunnerContext(mode=mode, git_hash="unit-test")  # type: ignore[arg-type]


def _aggregate(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "stage": COST_STAGE_EXTRACTION,
        "rows": 1,
        "token_usage_total": 60_000,
        "doc_count": 3,
        "single_doc_cost": 20_000.0,
        "incremental_cost": 25.0,
        "full_rebuild_cost": 100.0,
        "date_from": date(2026, 10, 1),
        "date_to": date(2026, 10, 1),
    }
    base.update(overrides)
    return base


def _patch_reading(monkeypatch: pytest.MonkeyPatch, aggregate: dict | None) -> None:
    """顶掉读库（本文件考的是 evaluator 分支，不是 SQL）。"""
    import app.evaluation.runner as runner

    monkeypatch.setattr(
        runner, "_cost_reading", lambda ctx, *, stage: (aggregate, None)
    )


def _one(criterion: str, ctx: RunnerContext) -> CriterionResult:
    return run(ctx, criteria=(criterion,))[0]


# --------------------------------------------------------------------------- #
# J1 / J2：无数据 ⇒ BLOCKED，但理由必须是**当前**真实缺口，value 恒 None
# --------------------------------------------------------------------------- #


def test_offline_is_blocked_with_none_not_zero() -> None:
    """**J2**：offline 不读库 ⇒ ``BLOCKED`` + ``value is None``（**不是** 0）。"""
    c3a = _one(C_COST, _ctx("offline"))
    c3b = _one(C_COST_RATIO, _ctx("offline"))
    for item in (c3a, c3b):
        assert item.status is CriterionStatus.BLOCKED
        assert item.value is None, "BLOCKED 带数字会被读成真实测量值"
        assert item.blocked_by


def test_blocked_reason_is_current_not_stale() -> None:
    """**J1**：``blocked_by`` 不得再出现「缺 M2 抽取侧」/「无写入方」这类失效理由。

    这两条曾经都是真的，但落点补齐后**没有任何东西通知过 runner** ——
    P6-V4 立项正是因为这种"过期而非错误"的机器结论。
    """
    reasons = [
        _one(C_COST, _ctx("offline")).blocked_by,
        _one(C_COST_RATIO, _ctx("offline")).blocked_by,
    ]
    for phrase in STALE_COST_PHRASES:
        for reason in reasons:
            assert phrase not in reason, f"失效文案仍在 blocked_by：{phrase} @ {reason}"


def test_live_without_sample_rows_is_blocked_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """live 有落点但**没跑过** ⇒ 仍 ``BLOCKED``（且 value=None，不回落到 0）。

    「落点已建」与「跑过一次」是两件事：本批最容易混淆的正是这一对。
    """
    _patch_reading(monkeypatch, _aggregate(rows=0, token_usage_total=0, doc_count=0))
    c3a = _one(C_COST, _ctx("live"))
    assert c3a.status is CriterionStatus.BLOCKED
    assert c3a.value is None
    assert "还没跑过" in c3a.blocked_by, c3a.blocked_by

    _patch_reading(monkeypatch, _aggregate(incremental_cost=0.0, full_rebuild_cost=0.0))
    c3b = _one(C_COST_RATIO, _ctx("live"))
    assert c3b.status is CriterionStatus.BLOCKED
    assert c3b.value is None


# --------------------------------------------------------------------------- #
# J3 / J4：有数据 ⇒ 真出数
# --------------------------------------------------------------------------- #


def test_c3a_measures_extraction_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    """**J3**：有 ``stage='extraction'`` 样本 ⇒ 出数，``unit=token/doc``。"""
    _patch_reading(monkeypatch, _aggregate())
    c3a = _one(C_COST, _ctx("live"))

    assert c3a.status is CriterionStatus.MEASURED_PROVISIONAL
    assert c3a.value == pytest.approx(60_000 / 3)
    assert c3a.unit == "token/doc"
    assert c3a.detail["doc_count"] == 3
    assert c3a.detail["token_usage_total"] == 60_000
    #: 阈值仍是 provisional ⇒ 即便达标也只给 PASS(provisional)（§5.2 第 3 条）
    assert c3a.threshold_source == THRESHOLD_PROVISIONAL
    assert c3a.verdict is Verdict.PASS_PROVISIONAL


def test_c3a_fails_when_above_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """出数之后**必须还能判红**——否则"能出数"只是把 BLOCKED 换成了恒绿。"""
    _patch_reading(monkeypatch, _aggregate(token_usage_total=300_000, doc_count=3))
    c3a = _one(C_COST, _ctx("live"))
    assert c3a.value == pytest.approx(100_000)
    assert c3a.verdict is Verdict.FAIL


def test_c3b_measures_ratio_with_denominator(monkeypatch: pytest.MonkeyPatch) -> None:
    """**J4**：有分母 ⇒ 出比值（分子分母同为「图元素个数」⇒ 无量纲）。"""
    _patch_reading(
        monkeypatch, _aggregate(incremental_cost=25.0, full_rebuild_cost=100.0)
    )
    c3b = _one(C_COST_RATIO, _ctx("live"))

    assert c3b.status is CriterionStatus.MEASURED_PROVISIONAL
    assert c3b.value == pytest.approx(0.25)
    assert c3b.unit == "ratio"
    assert c3b.threshold == 1.00
    assert c3b.verdict is Verdict.PASS


def test_c3b_fails_when_ratio_not_significant(monkeypatch: pytest.MonkeyPatch) -> None:
    """增量不比全量省 ⇒ 判红（「显著 < 1.00」的**反向**守卫）。"""
    _patch_reading(
        monkeypatch, _aggregate(incremental_cost=120.0, full_rebuild_cost=100.0)
    )
    c3b = _one(C_COST_RATIO, _ctx("live"))
    assert c3b.value == pytest.approx(1.20)
    assert c3b.verdict is Verdict.FAIL


def test_zero_over_zero_column_semantics_unchanged() -> None:
    """**裁决护栏**：表内 ``cost_ratio`` 列的 ``0/0 → 0.0`` 语义本批**未改**。

    P6-V4 改的是「判据读到 0 分母时**不采纳**那个 0.0」，而不是改列语义本身
    —— 两件事不要互相裹挟（改后者会让仪表盘与历史报告口径漂移）。
    """
    from app.services.cost_metrics import _refresh_cost_ratio  # noqa: PLC0415

    row = SimpleNamespace(
        incremental_cost=None, full_rebuild_cost=None, cost_ratio=None
    )
    _refresh_cost_ratio(row)  # type: ignore[arg-type]
    assert row.cost_ratio == 0.0
    assert not isinstance(row.cost_ratio, bool)


# --------------------------------------------------------------------------- #
# 读侧：aggregate_stage 只认指定 stage（真 PG）
# --------------------------------------------------------------------------- #


def test_aggregate_stage_ignores_other_stages() -> None:
    """抽取决不能把问答那一行算进来 ⇒ 分子与分母必须来自**同一个过程**。"""
    org_id = uuid.uuid4()
    today = datetime.now(UTC).date()
    docs = [str(uuid.uuid4()) for _ in range(3)]
    try:
        with session_scope(org_id=org_id) as db:
            db.add_all(
                [
                    CostMetric(
                        org_id=org_id,
                        metric_date=today,
                        stage=COST_STAGE_EXTRACTION,
                        token_usage_input=40_000,
                        token_usage_output=20_000,
                        token_usage_total=60_000,
                        doc_count=3,
                        counted_doc_ids=docs,
                        single_doc_cost=20_000.0,
                        incremental_cost=25.0,
                        full_rebuild_cost=100.0,
                    ),
                    CostMetric(
                        org_id=org_id,
                        metric_date=today,
                        stage="answer",
                        token_usage_input=9_000,
                        token_usage_output=1_000,
                        token_usage_total=10_000,
                        doc_count=5,
                        counted_doc_ids=[str(uuid.uuid4()) for _ in range(5)],
                        single_doc_cost=2_000.0,
                    ),
                ]
            )
            db.commit()

            payload = aggregate_stage(db=db, org_id=org_id, stage=COST_STAGE_EXTRACTION)

        assert payload["rows"] == 1, "把 answer 行也算进来了"
        assert payload["token_usage_total"] == 60_000
        assert payload["doc_count"] == 3, "分母混进了问答侧文档"
        assert payload["single_doc_cost"] == pytest.approx(20_000.0)
        assert payload["incremental_cost"] == pytest.approx(25.0)
        assert payload["full_rebuild_cost"] == pytest.approx(100.0)
    finally:
        with session_scope(org_id=org_id) as db:
            db.execute(delete(CostMetric).where(CostMetric.org_id == org_id))
            db.commit()


# --------------------------------------------------------------------------- #
# V4-b / J5：取样器导出的 JSON 真能被 --calibrate 吃下
# --------------------------------------------------------------------------- #


def test_to_cost_records_flattens_day_rows() -> None:
    """日聚合 ⇒ 逐文档记录；**没有文档清单的行整行跳过**（无分母 ⇒ 不造数）。"""
    org_id = uuid.uuid4()
    docs = [str(uuid.uuid4()) for _ in range(2)]
    rows = [
        CostMetric(
            org_id=org_id,
            metric_date=date(2026, 10, 1),
            stage=COST_STAGE_EXTRACTION,
            token_usage_total=60_000,
            counted_doc_ids=docs,
        ),
        CostMetric(
            org_id=org_id,
            metric_date=date(2026, 10, 2),
            stage=COST_STAGE_EXTRACTION,
            token_usage_total=9_999,
            counted_doc_ids=[],  # 无文档 ⇒ 摊不出每文档数 ⇒ 跳过
        ),
    ]
    records = to_cost_records(rows)

    assert len(records) == 2
    assert {item["doc_id"] for item in records} == set(docs)
    assert all(item["token_usage_total"] == 30_000 for item in records)
    assert all(item["outcome"] == "completed" for item in records)


def test_calibrate_accepts_exported_records(tmp_path: Path) -> None:
    """**J5**：取样器导出的 JSON ⇒ ``--calibrate`` 真的能算出建议值，且**不写配置**。

    ⚠️ 这里顺便钉住一个**已知限制**：日聚合摊平后同一天所有文档同值 ⇒
    ``P50 == P90``。断言里把它写出来，是为了让"分位数退化"成为**被测试记录的事实**，
    而不是一个只在 docstring 里提一句的免责声明。
    """
    org_id = uuid.uuid4()
    docs = [str(uuid.uuid4()) for _ in range(4)]
    rows = [
        CostMetric(
            org_id=org_id,
            metric_date=date(2026, 10, 1),
            stage=COST_STAGE_EXTRACTION,
            token_usage_total=80_000,
            counted_doc_ids=docs,
        )
    ]
    records = tmp_path / "cost-records.json"
    records.write_text(
        json.dumps(to_cost_records(rows), ensure_ascii=False), encoding="utf-8"
    )

    config = BACKEND_DIR / "app" / "core" / "config.py"
    before = config.read_text(encoding="utf-8")

    proc = subprocess.run(  # noqa: S603 - 固定参数，无 shell
        [sys.executable, str(SCRIPT), "--calibrate", "--cost-records", str(records)],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "P50 / P90" in proc.stdout
    assert "文档数（去重后）      : 4" in proc.stdout
    #: 日聚合摊平 ⇒ 分位数退化（不掩饰，钉成事实）：80_000 / 4 = 20_000
    assert "P50 / P90（token/文档）: 20000 / 20000" in proc.stdout
    assert config.read_text(encoding="utf-8") == before, "--calibrate 写了 config"
