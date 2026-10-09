"""M6 §4.3 的成本日聚合：写入与读出的唯一入口。

P6-V（2026-10-09）落地，取代 ``routes/cost.py`` 的 501 占位。本模块只做两件事，
且**两件都对着同一张表**（``cost_metrics``）：

1. :func:`record_answer_usage` —— M3 问答每次真实 LLM 调用后累加到当日那一行；
2. :func:`build_dashboard` —— 按日期区间把若干天聚成仪表盘的一屏。

**为什么粒度是「天」而不是「每次调用」**：spec §4.3 的表就是以 ``date`` 为键
（``UNIQUE (org_id, metric_date)``），C3-a 要的是 ``token_usage_total / doc_count``，
一个**区间级**的均值——逐条明细表本批不建（要加就是新表 + 迁移 + ADR-0004 登记，
不是顺手写一列）。

**``doc_count`` 为什么需要 ``counted_doc_ids``（偏离 X-3）**：它的口径是**去重后**
的文档数，而累加发生在多次请求之间——没有这份清单，同一份文档被问三次就会被数三次，
``single_doc_cost`` 随提问次数单调下降 ⇒ 指标失真。清单是 JSON 列、不进契约，
只在 :func:`record_answer_usage` 里读写。

工艺纪律（本项目红线，别图省事踩）：

- ``token_usage`` 缺失（拒答 / 无证据）时 **既不写 0 也不造数**——前者让表看起来
  「有数据」，后者把成本隐匿；做法是**跳过 + 打日志**（见下);
- ``db`` 为 ``None``（脚本 / CLI 直连）时同样**跳过 + 打 warning**，不静默丢。
  LLM 已经花了钱，比「记不下来」更错的是「记不下来也不说一声」。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import CostMetric


def utc_day(moment: datetime | None = None) -> date:
    """取 UTC 自然日（与 P6-U 的"以 UTC 为准"同口径，不用本地时区）。"""
    current = moment or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).date()


def record_answer_usage(
    *,
    org_id: uuid.UUID,
    token_usage: Any,
    doc_ids: Sequence[uuid.UUID | None] = (),
    occurred_at: datetime | None = None,
    db: Session | None = None,
    trace_id: str = "",
) -> CostMetric | None:
    """把一次**带 LLM 的问答**累加到当日的成本行上。

    :param token_usage: ``app.services.llm.router.TokenUsage``（有
        ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``）。``None`` =
        本次没有真实调用（拒答 / 无有效证据）⇒ 跳过。
    :param doc_ids: 本次触及的文档 id（``None`` 项丢弃）。同一 ``(org, day)`` 内
        重复出现不会重复计数（X-3：靠 ``counted_doc_ids`` 去重）。
    :param db: PG 会话；``None`` ⇒ 跳过并告警。
    :returns: 落好的那一行；跳过时返回 ``None``。

    **并发怎么不错账**：先 ``ON CONFLICT DO NOTHING`` 确保当日行存在，再
    ``SELECT ... FOR UPDATE`` 拿行锁，最后在 Python 侧合并。之所以不追求「一条
    UPDATE 解决」：``doc_count`` 的增量取决于**去重结果**（依赖于既有清单），
    写成纯 SQL 既难读又容易错；而这里的写入频率是「一次问答一次」，行锁的代价
    远小于算错指标。
    """
    if token_usage is None:
        logger.bind(module="cost_metrics").info(
            "cost_metrics_record_skipped_no_usage",
            org_id=str(org_id),
            trace_id=trace_id,
            reason="本次没有真实 LLM 调用（拒答 / 无有效证据）",
        )
        return None
    if db is None:
        logger.bind(module="cost_metrics").warning(
            "cost_metrics_record_skipped_no_db",
            org_id=str(org_id),
            trace_id=trace_id,
            reason="调用方没有 PG 会话 ⇒ 本次 token 用量不计入 cost_metrics",
        )
        return None

    day = utc_day(occurred_at)
    prompt = int(getattr(token_usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(token_usage, "completion_tokens", 0) or 0)
    total = int(getattr(token_usage, "total_tokens", 0) or 0) or (prompt + completion)
    new_docs = {str(doc_id) for doc_id in doc_ids if doc_id is not None}

    seed = {
        "org_id": org_id,
        "metric_date": day,
        "token_usage_input": prompt,
        "token_usage_output": completion,
        "token_usage_total": total,
        "doc_count": len(new_docs),
        "counted_doc_ids": sorted(new_docs),
        "single_doc_cost": (total / len(new_docs)) if new_docs else 0.0,
    }
    row = _upsert_day_row(
        db=db,
        org_id=org_id,
        day=day,
        prompt=prompt,
        completion=completion,
        total=total,
        new_docs=new_docs,
        seed=seed,
    )
    db.commit()
    return row


def _upsert_day_row(
    *,
    db: Session,
    org_id: uuid.UUID,
    day: date,
    prompt: int,
    completion: int,
    total: int,
    new_docs: set[str],
    seed: dict[str, Any],
) -> CostMetric:
    """取当日行（不存在就建），把本次用量**合并**进去。

    **为什么循环两次**：先 SELECT 后 INSERT 之间存在窗口——另一个并发请求可能
    抢先建了当日行，此时 INSERT 会撞 ``UNIQUE (org_id, metric_date)``。
    用 savepoint（``begin_nested``）包住 INSERT，撞了就回滚这个保存点**再试一次**，
    第二次必定 SELECT 到对手建的行。整轮下来只有两种结局：**要么我建、要么我合**。

    ⚠️ 这里**没有用** ``ON CONFLICT DO NOTHING`` + ``rowcount`` 判新旧的写法：
    本批实测它对"有没有真的插进去"的返回不可靠（第二次记帐被整段跳过 ⇒
    同一天的 token 只留下第一笔），而指标被悄悄少计比报错更难发现。
    """
    for _attempt in (1, 2):
        existing = db.execute(
            select(CostMetric)
            .where(
                CostMetric.org_id == org_id,
                CostMetric.metric_date == day,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if existing is not None:
            fresh = new_docs - set(existing.counted_doc_ids or [])
            existing.token_usage_input += prompt
            existing.token_usage_output += completion
            existing.token_usage_total += total
            existing.doc_count += len(fresh)
            existing.counted_doc_ids = sorted(
                set(existing.counted_doc_ids or []) | new_docs
            )
            existing.single_doc_cost = (
                existing.token_usage_total / existing.doc_count
                if existing.doc_count
                else 0.0
            )
            existing.updated_at = datetime.now(UTC)
            return existing

        try:
            with db.begin_nested():
                created = CostMetric(**seed)
                db.add(created)
        except IntegrityError:  # pragma: no cover —— 由下一次循环接管
            continue
        return created
    raise CostMetricsUnavailableError(  # pragma: no cover —— 两次都抢不到，属异常
        f"cost_metrics 当日行两轮竞抢都没建成（org_id={org_id}, date={day}）"
    )


class CostMetricsUnavailableError(Exception):
    """成本落点不可用（**不影响主链路**：调用方由 N 层兜住）。"""


def build_dashboard(
    *,
    db: Session,
    org_id: uuid.UUID,
    date_from: date,
    date_to: date,
    trace_id: str = "",
) -> dict[str, Any]:
    """把 ``[date_from, date_to]`` 内的日行聚成仪表盘的一屏。

    **区间级怎么算**（别对按天值再取一次平均——那样每天权重相同，会掩盖重活的那天）：

    - ``token_usage_total`` / ``doc_count``：直接**求和**；
    - ``single_doc_cost``：``总和(total) / 总和(doc_count)``；
    - ``cost_ratio``：``总和(incremental) / 总和(full_rebuild)``，无分母时取 ``0.0``。

    **为什么空区间返回全 0 而不是报错**：契约没有给「无数据」准备语义（本批不改
    契约），而这不是「假做」——占位期的 501 是因为**整个落点都不存在**，
    现在口径已经能出数；区间内空 ⇒ 真实含义就是"这段没有记到 LLM 调用"。
    ⇒ 登记为已知限制 X-4，并配套一条可观测：空区间打 warning，
    让人能把「这段真的没业务」与「落点坏了」分开。

    **应用层仍然显式带 org_id 过滤**（ADR-0003：RLS 不是唯一防线，应用层不因
    RLS 生效而撤掉）。
    """
    rows = sorted(
        db.scalars(
            select(CostMetric).where(
                CostMetric.org_id == org_id,
                CostMetric.metric_date >= date_from,
                CostMetric.metric_date <= date_to,
            )
        ).all(),
        key=lambda row: row.metric_date,
    )

    total_tokens = sum(int(row.token_usage_total or 0) for row in rows)
    doc_count = sum(int(row.doc_count or 0) for row in rows)
    incremental = sum(float(row.incremental_cost or 0.0) for row in rows)
    full_rebuild = sum(float(row.full_rebuild_cost or 0.0) for row in rows)
    single_doc_cost = (total_tokens / doc_count) if doc_count else 0.0
    cost_ratio = (incremental / full_rebuild) if full_rebuild > 0 else 0.0

    if not rows:
        logger.bind(module="cost_metrics").warning(
            "cost_metrics_range_empty",
            org_id=str(org_id),
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            trace_id=trace_id,
            hint="区间内没有 cost_metrics 行：要么是这段没有 LLM 调用，要么是落点坏了",
        )
    if cost_ratio > get_settings().cost_ratio_alert_threshold:
        # spec §6：超阈值**只告警不阻断**（本句就是那个配置的唯一消费者）
        logger.bind(module="cost_metrics").warning(
            "cost_ratio_above_threshold",
            org_id=str(org_id),
            cost_ratio=cost_ratio,
            threshold=get_settings().cost_ratio_alert_threshold,
            trace_id=trace_id,
        )

    return {
        "token_usage_total": total_tokens,
        "single_doc_cost": single_doc_cost,
        "cost_ratio": cost_ratio,
        "by_date": [
            {
                "date": row.metric_date,
                "token_usage_total": int(row.token_usage_total or 0),
                "single_doc_cost": float(row.single_doc_cost or 0.0),
            }
            for row in rows
        ],
    }
