"""M6 §4.3 的成本日聚合：写入与读出的唯一入口。

P6-V（2026-10-09）落地，取代 ``routes/cost.py`` 的 501 占位。本模块只做两件事，
且**两件都对着同一张表**（``cost_metrics``）：

1. :func:`record_answer_usage` —— M3 问答每次真实 LLM 调用后累加到当日那一行；
2. :func:`record_extraction_usage` —— M2 抽取每次做完一篇文档后累加（**P6-V2**）；
3. :func:`build_dashboard` —— 按日期区间把若干天聚成仪表盘的一屏。

**「天」之外还有一维：``stage``（偏离 X-6，P6-V2）**：行粒度是
``UNIQUE (org_id, metric_date, stage)`` —— 即**一个租户一天的一个成本口径**。
抽取与问答落**两行**：抽取一篇文档是一笔 chunk 级开销，问答一次是一笔检索级
开销，两者混进同一行 ⇒ ``single_doc_cost`` 不再是任何一个口径。

**为什么粒度是「天」而不是「每次调用」**：spec §4.3 的表就是以 ``date`` 为键，
C3-a 要的是 ``token_usage_total / doc_count``，一个**区间级**的均值——逐条明细表
本批不建（要加就是新表 + 迁移 + ADR-0004 登记，不是顺手写一列）。

**``doc_count`` 为什么需要 ``counted_doc_ids``（偏离 X-3）**：它的口径是**去重后**
的文档数，而累加发生在多次请求之间——没有这份清单，同一份文档被问三次就会被数三次，
``single_doc_cost`` 随提问次数单调下降 ⇒ 指标失真。清单是 JSON 列、不进契约，
只在 :func:`record_answer_usage` 里读写。

工艺纪律（本项目红线，别图省事踩）：

- ``token_usage`` 缺失（拒答 / 无证据）时 **既不写 0 也不造数**——前者让表看起来
  「有数据」，后者把成本隐匿；做法是**跳过 + 打日志**（见下);
- ``db`` 为 ``None``（脚本 / CLI 直连）时同样**跳过 + 打 warning**，不静默丢。
  LLM 已经花了钱，比「记不下来」更错的是「记不下来也不说一声」。

**第四 / 五件事（P6-V3，偏离 X-7）**：``incremental_cost`` 与 ``full_rebuild_cost``
的两侧写入。它们与 token **不是同一个量纲**：记的是「**图元素个数**」（实体 + 关系），
取值来自 :meth:`~app.services.kg.versioning.KgVersioningService.mark_ready` 时的现成计数。

为什么不用 token：``app/services/kg/`` 全目录实读**零 LLM**（开机自检里
``build_chat_model`` / ``TokenUsage`` / ``invoke(`` 均 0 命中，见
``changes/P6-V3/proposal.md`` §1 的坐标表）⇒ token 口径下分子恒 0，
``cost_ratio`` 会**假性**「显著 < 1.00」而恰恰不构成达标证据；而两侧同为「个数」，
比值才有意义。换算口**只有** :func:`_graph_elements` 一个 ⇒ 两侧不可能各自漂移。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import COST_STAGE_ANSWER, COST_STAGE_EXTRACTION, CostMetric

#: X-7 分子 / 分母对应的两列（P6-V3）。写成常量而不是散写字面量：这两个字符串
#: 一旦拼错既不会异常也不会报错，只会让某一侧**永远停在 None**——而
#: ``cost_ratio`` 恰好会把「没数」读成 0.0，看上去跟"比值真的小"一模一样。
_FIELD_INCREMENTAL = "incremental_cost"
_FIELD_FULL_REBUILD = "full_rebuild_cost"


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
    """把一次**带 LLM 的问答**累加到当日**问答口径**的成本行上（``stage='answer'``）。

    :param token_usage: ``app.services.llm.router.TokenUsage``（有
        ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``）。``None`` =
        本次没有真实调用（拒答 / 无有效证据）⇒ 跳过。
    :param doc_ids: 本次触及的文档 id（``None`` 项丢弃）。同一 ``(org, day)`` 内
        重复出现不会重复计数（X-3：靠 ``counted_doc_ids`` 去重）。
    :param db: PG 会话；``None`` ⇒ 跳过并告警。
    :returns: 落好的那一行；跳过时返回 ``None``。
    """
    if token_usage is None:
        logger.bind(module="cost_metrics").info(
            "cost_metrics_record_skipped_no_usage",
            org_id=str(org_id),
            trace_id=trace_id,
            reason="本次没有真实 LLM 调用（拒答 / 无有效证据）",
        )
        return None
    triple = _usage_triple(token_usage)
    return _record_usage(
        stage=COST_STAGE_ANSWER,
        org_id=org_id,
        prompt=triple["prompt_tokens"],
        completion=triple["completion_tokens"],
        total=triple["total_tokens"],
        doc_ids=doc_ids,
        occurred_at=occurred_at,
        db=db,
        trace_id=trace_id,
    )


def record_extraction_usage(
    *,
    org_id: uuid.UUID,
    token_usage: Mapping[str, int | None] | None,
    doc_ids: Sequence[uuid.UUID | None] = (),
    occurred_at: datetime | None = None,
    db: Session | None = None,
    trace_id: str = "",
) -> CostMetric | None:
    """把**一篇文档的抽取**累加到当日**抽取口径**的成本行上（``stage='extraction'``）。

    P6-V2 新增。 ``token_usage`` 直接来自
    ``LangextractClient.extract_entities_relations(...).llm_usage`` ——那已经是
    **文档级**合计（逐 chunk 累加过了，见
    :class:`app.services.extraction.langextract._UsageTotals`），这里不必再聚合。

    :param token_usage: ``None`` **或空 dict** = 这次抽取没有真实 LLM 调用
        （``extraction_engine='mock'`` / 单测注入抽取器）⇒ **跳过**，不写 0
        （Y2：0 会让仪表盘看起来"有数据"）。缺的那一档按 0 计并打点。
    :returns: 落好的那一行；跳过时返回 ``None``。
    """
    if not token_usage:
        logger.bind(module="cost_metrics").info(
            "cost_metrics_record_skipped_no_usage",
            org_id=str(org_id),
            trace_id=trace_id,
            stage=COST_STAGE_EXTRACTION,
            reason="本次抽取没有真实 LLM 调用（mock 档 / 注入抽取器）",
        )
        return None

    missing = [key for key, value in token_usage.items() if value is None]
    if missing:
        logger.bind(module="cost_metrics").warning(
            "cost_metrics_usage_partially_missing",
            org_id=str(org_id),
            trace_id=trace_id,
            stage=COST_STAGE_EXTRACTION,
            missing_fields=sorted(missing),
            hint="响应里没有用量字段 ⇒ 这几项按 0 计（不猜数）",
        )
    prompt = int(token_usage.get("prompt_tokens") or 0)
    completion = int(token_usage.get("completion_tokens") or 0)
    total = int(token_usage.get("total_tokens") or 0) or (prompt + completion)
    return _record_usage(
        stage=COST_STAGE_EXTRACTION,
        org_id=org_id,
        prompt=prompt,
        completion=completion,
        total=total,
        doc_ids=doc_ids,
        occurred_at=occurred_at,
        db=db,
        trace_id=trace_id,
    )


def record_full_rebuild_cost(
    *,
    org_id: uuid.UUID,
    entity_count: int,
    relation_count: int,
    occurred_at: datetime | None = None,
    db: Session | None = None,
    trace_id: str = "",
) -> CostMetric | None:
    """**X-7 分母**：一次文档**首次全量构建**写入的图元素个数。

    写入方要求**仅此 1 处**（``registry.kg_build_executor`` 判定「全新构建」后才调），
    重跑同一 ``kg_version`` **不得**再调——重复计入会把分母成倍垫大，
    ``cost_ratio`` 被人为压低（这才是本列最容易失真的地方）。

    :param entity_count / relation_count: 本次全量构建实际写入 Neo4j 的实体 / 关系数
        （``ThreeStageKgBuilder.build`` 的 ``stats``，已由 ``mark_ready`` 落到
        ``KgVersion`` 同名列上）——这里读的是**同一份计数**，不另算、不估。
    :returns: 落好的那一行；跳过时返回 ``None``。
    """
    return _record_graph_cost(
        field=_FIELD_FULL_REBUILD,
        amount=_graph_elements(
            entity_count=entity_count, relation_count=relation_count
        ),
        org_id=org_id,
        occurred_at=occurred_at,
        db=db,
        trace_id=trace_id,
    )


def record_incremental_rebuild_cost(
    *,
    org_id: uuid.UUID,
    entity_count: int,
    relation_count: int,
    occurred_at: datetime | None = None,
    db: Session | None = None,
    trace_id: str = "",
) -> CostMetric | None:
    """**X-7 分子**：一次**增量重算**写入的图元素个数。

    写入方要求**仅此 1 处**（``kg.incremental.rebuild_incrementally`` 成功分支）。
    失败路径走 ``_fail(...)`` ⇒ **不调本函数**：那次重算的产出不是一个可用版本，
    记 0 会让仪表盘看起来"有数据"（沿用本模块"不写 0"的既有工艺纪律）。

    :param entity_count / relation_count: ``IncrementalRebuildResult`` 的两个计数
        （``incremental.py:139-140``，现成字段 ⇒ 本批零新埋点）。
    :returns: 落好的那一行；跳过时返回 ``None``。
    """
    return _record_graph_cost(
        field=_FIELD_INCREMENTAL,
        amount=_graph_elements(
            entity_count=entity_count, relation_count=relation_count
        ),
        org_id=org_id,
        occurred_at=occurred_at,
        db=db,
        trace_id=trace_id,
    )


def _usage_triple(token_usage: Any) -> dict[str, int]:
    """``TokenUsage``（属性式）→ int 三元组；缺项按 0 计、``total`` 缺则用两项之和。"""
    prompt = int(getattr(token_usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(token_usage, "completion_tokens", 0) or 0)
    total = int(getattr(token_usage, "total_tokens", 0) or 0) or (prompt + completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _graph_elements(*, entity_count: int, relation_count: int) -> int:
    """**两侧的唯一定价换算**：图规模 = 实体数 + 关系数（单位：图元素个数）。

    X-7 的分子分母**必须同量纲**，否则 ``cost_ratio`` 是一个无量纲都不成立的数字。
    把换算收在一个函数里，是为了让"两边单位一致"成为**结构上的事实**而不是
    两份注释之间的君子协定——谁要改单位，两侧一起改、测试里两条同量纲断言一起红。
    """
    return int(entity_count) + int(relation_count)


def _record_graph_cost(
    *,
    field: str,
    amount: int,
    org_id: uuid.UUID,
    occurred_at: datetime | None,
    db: Session | None,
    trace_id: str,
) -> CostMetric | None:
    """把一次图写入的**规模**累加到当日行的 ``field`` 列上。

    与 token 侧共用同一把行锁（:func:`_take_day_row`）⇒ 不会为本列车另开一个
    并发写入口（两个口的锁策略一旦漂移，丢账是静默的）。

    **为什么不写 0**：跟 token 侧同一个道理——写在表里的 0 与"压根没发生过"
    读起来一模一样，而它偏偏会让 ``cost_ratio`` 的分母看起来存在。⇒ 跳过并打日志。
    """
    if db is None:
        logger.bind(module="cost_metrics").warning(
            "cost_metrics_record_skipped_no_db",
            org_id=str(org_id),
            field=field,
            trace_id=trace_id,
            reason="调用方没有 PG 会话 ⇒ 本次图规模不计入 cost_metrics",
        )
        return None
    if amount <= 0:
        logger.bind(module="cost_metrics").info(
            "cost_metrics_graph_cost_skipped_empty",
            org_id=str(org_id),
            field=field,
            amount=amount,
            trace_id=trace_id,
            reason="本次没有写入任何图元素 ⇒ 跳过（不写 0）",
        )
        return None

    day = utc_day(occurred_at)
    seed = {
        "org_id": org_id,
        "metric_date": day,
        "stage": COST_STAGE_EXTRACTION,
        # 新建行时 token / doc 侧保持 0：本函数不知道文档清单，也不许碰去重口径
        "token_usage_input": 0,
        "token_usage_output": 0,
        "token_usage_total": 0,
        "doc_count": 0,
        "counted_doc_ids": [],
        "single_doc_cost": 0.0,
        field: float(amount),
    }
    row, is_new = _take_day_row(
        db=db, org_id=org_id, day=day, stage=COST_STAGE_EXTRACTION, seed=seed
    )
    if not is_new:
        setattr(row, field, float(getattr(row, field) or 0.0) + float(amount))
        row.updated_at = datetime.now(UTC)
    _refresh_cost_ratio(row)
    db.commit()

    logger.bind(
        module="cost_metrics",
        org_id=str(org_id),
        stage=COST_STAGE_EXTRACTION,
        field=field,
        amount=amount,
        **{field: float(getattr(row, field) or 0.0)},
        cost_ratio=row.cost_ratio,
        trace_id=trace_id,
    ).info("cost_metrics_graph_cost_recorded")
    return row


def _refresh_cost_ratio(row: CostMetric) -> None:
    """维护**行级** ``cost_ratio``（``incremental / full_rebuild``，无分母取 ``0.0``）。

    **为什么要维护行级这一列**：模型注释（``models.py:1179``）与
    :func:`build_dashboard` 的区间级口径都写着「无分母时为 ``0.0``」，只写一侧会让
    同一张表的两种读法打架。⚠️ 无分母时是 **``0.0`` 而不是 NaN** ——``0.0`` 的语义是
    「还没有比值」，``NaN`` 则会被 JSON 序列化成非法 float。
    """
    incremental = float(row.incremental_cost or 0.0)
    full_rebuild = float(row.full_rebuild_cost or 0.0)
    row.cost_ratio = (incremental / full_rebuild) if full_rebuild > 0 else 0.0


def _record_usage(
    *,
    stage: str,
    org_id: uuid.UUID,
    prompt: int,
    completion: int,
    total: int,
    doc_ids: Sequence[uuid.UUID | None],
    occurred_at: datetime | None,
    db: Session | None,
    trace_id: str,
) -> CostMetric | None:
    """两个口径**共用**的落点：锁行 → 合并 → 提交。

    **并发怎么不错账**：先 ``ON CONFLICT DO NOTHING`` 确保当日行存在，再
    ``SELECT ... FOR UPDATE`` 拿行锁，最后在 Python 侧合并。之所以不追求「一条
    UPDATE 解决」：``doc_count`` 的增量取决于**去重结果**（依赖于既有清单），
    写成纯 SQL 既难读又容易错；而这里的写入频率是「一次问答 / 抽取一次」，
    行锁的代价远小于算错指标。
    """
    if db is None:
        logger.bind(module="cost_metrics").warning(
            "cost_metrics_record_skipped_no_db",
            org_id=str(org_id),
            stage=stage,
            trace_id=trace_id,
            reason="调用方没有 PG 会话 ⇒ 本次 token 用量不计入 cost_metrics",
        )
        return None

    day = utc_day(occurred_at)
    new_docs = {str(doc_id) for doc_id in doc_ids if doc_id is not None}

    seed = {
        "org_id": org_id,
        "metric_date": day,
        "stage": stage,
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
        stage=stage,
        prompt=prompt,
        completion=completion,
        total=total,
        new_docs=new_docs,
        seed=seed,
    )
    db.commit()
    return row


def _take_day_row(
    *,
    db: Session,
    org_id: uuid.UUID,
    day: date,
    stage: str,
    seed: dict[str, Any],
) -> tuple[CostMetric, bool]:
    """取当日**该 stage** 的行（不存在就建），返回 ``(行, 是否本次新建)``。

    **⚠️ 查找条件必须带 ``stage``**（X-6 的承接）：P6-V2 之后同一 ``(org, day)``
    有两行（抽取 / 问答）。漏了这个谓词 ⇒ 抽取的 token 被合并进问答那一行，
    ``single_doc_cost`` 立刻变成混合口径，而且**不报错**——正是本批要防的那种静默。

    **为什么循环两次**：先 SELECT 后 INSERT 之间存在窗口——另一个并发请求可能
    抢先建了当日行，此时 INSERT 会撞 ``UNIQUE (org_id, metric_date, stage)``。
    用 savepoint（``begin_nested``）包住 INSERT，撞了就回滚这个保存点**再试一次**，
    第二次必定 SELECT 到对手建的行。整轮下来只有两种结局：**要么我建、要么我合**。

    ⚠️ 这里**没有用** ``ON CONFLICT DO NOTHING`` + ``rowcount`` 判新旧的写法：
    本批实测它对"有没有真的插进去"的返回不可靠（第二次记帐被整段跳过 ⇒
    同一天的 token 只留下第一笔），而指标被悄悄少计比报错更难发现。

    **为什么 P6-V3 要把它单独抽出来**：X-7 的图规模两列也落**同一张表的同一行**。
    这段锁-day-row 的并发处理若写成两份，迟早一边改一边忘——而由此丢掉的计数是
    **静默**的（``cost_ratio`` 只会"看起来变小了"）。⇒ **取行共用一处**，
    只有"拿到行以后怎么合并"是各自的事（**是否本次新建**由 ``is_new`` 回给调用方）。
    """
    for _attempt in (1, 2):
        existing = db.execute(
            select(CostMetric)
            .where(
                CostMetric.org_id == org_id,
                CostMetric.metric_date == day,
                CostMetric.stage == stage,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

        try:
            with db.begin_nested():
                created = CostMetric(**seed)
                db.add(created)
        except IntegrityError:  # pragma: no cover —— 由下一次循环接管
            continue
        return created, True
    raise CostMetricsUnavailableError(  # pragma: no cover —— 两次都抢不到，属异常
        f"cost_metrics 当日行两轮竞抢都没建成"
        f"（org_id={org_id}, date={day}, stage={stage}）"
    )


def _upsert_day_row(
    *,
    db: Session,
    org_id: uuid.UUID,
    day: date,
    stage: str,
    prompt: int,
    completion: int,
    total: int,
    new_docs: set[str],
    seed: dict[str, Any],
) -> CostMetric:
    """token / 文档侧的合并口径（取行与并发处理见 :func:`_take_day_row`）。

    ``seed`` 决定**新建**行长什么样；行已存在时走下面的增量合并——两条路径必须都
    把本次的 token 与文档计入，且文档按 ``counted_doc_ids`` 去重后再加。
    """
    existing, is_new = _take_day_row(
        db=db, org_id=org_id, day=day, stage=stage, seed=seed
    )
    if is_new:
        return existing

    fresh = new_docs - set(existing.counted_doc_ids or [])
    existing.token_usage_input += prompt
    existing.token_usage_output += completion
    existing.token_usage_total += total
    existing.doc_count += len(fresh)
    existing.counted_doc_ids = sorted(set(existing.counted_doc_ids or []) | new_docs)
    existing.single_doc_cost = (
        existing.token_usage_total / existing.doc_count if existing.doc_count else 0.0
    )
    existing.updated_at = datetime.now(UTC)
    return existing


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

    - ``token_usage_total``：直接**求和**（跨 stage 也求和：契约里只有一个数）；
    - ``doc_count``：按**文档 id 跨行去重**（见下）；
    - ``single_doc_cost``：``总和(total) / 去重后的文档数``；
    - ``cost_ratio``：``总和(incremental) / 总和(full_rebuild)``，无分母时取 ``0.0``。

    **为什么 ``doc_count`` 必须去重而不是求和（Y6）**：P6-V2 之后同一天会有
    ``extraction`` / ``answer`` 两行，**同一份文档两行都数它** ⇒ 直接求和会把
    分母翻倍、`single_doc_cost`` 腰斩，而且**不会报错**。spec §3.4 验收 8 说的是
    「按文档 ID 聚合」——去重合的正是这个口径。

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
    # Y6：同一文档可能同时出现在同日的抽取行与问答行 ⇒ 按 id 取并集，不直接求和
    counted_doc_ids: set[str] = set()
    for row in rows:
        counted_doc_ids |= set(row.counted_doc_ids or [])
    doc_count = len(counted_doc_ids)
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
