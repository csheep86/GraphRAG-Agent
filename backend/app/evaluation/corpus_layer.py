"""**P6-D**：``corpus_layer`` 的**机器判定**（L1 算法层 / L2 端到端）。

为什么要有这个模块：写死一个 ``corpus_layer = "L1"`` 的常量，
等于把「这次跑的是不是端到端」交给**人记得改**。两种错都会发生，且都无从证伪：

- 跑了 L2 的实测，报告却标 L1 ⇒ 白干；
- 跑了 L1，把常量改成 L2 ⇒ **假绿**（这才是要命的方向）。

判据沿用仓库既有口径（A8 裁决 4 / ``gold-affiliation-v2.json::source.corpus_layer_note``）：

> **L1** = 语料**不经 M2 抽取**直接入图；**L2** = 真机文档 → M1 解析 → M2 抽取 → 入图 → …

机器怎么判：M2 抽取器产出的实体 id 带 ``ent_`` 前缀（``ingest_attendance_csv.py`` 头注释）。
实测（2026-10-05）：``attendance-demo-v1`` = 180 个 ⇒ L2；``affiliation-demo-v2`` = 0 个 ⇒ L1。
⇒ **该标记对两侧有区分度**，不是拍脑袋选的。

**图不可用 ⇒ 返回 ``None``（不猜）**：归因不明时报告宁可空着，也不许填一个漂亮的层号。
"""

from __future__ import annotations

from uuid import UUID

from app.services.graphs import GraphService, GraphUnavailableError

LAYER_ALGORITHM = "L1"
LAYER_END_TO_END = "L2"

#: M2 抽取产物的 id 前缀（与 ``scripts/ingest_attendance_csv.py`` 的口径一致）
M2_ENTITY_ID_PREFIX = "ent_"


def detect_corpus_layer(*, kg_version: str, org_id: UUID | None = None) -> str | None:
    """按**图内实测**判定语料层；判不出来返回 ``None``。

    :returns: ``"L2"``（有 M2 抽取产物）/ ``"L1"``（有数据但无 M2 产物）/ ``None``
    """
    if not kg_version:
        return None
    service = GraphService.instance()
    try:
        m2_count = service.count_m2_entities(kg_version=kg_version, org_id=org_id)
        #: 只取 1 条就够判断"这个版本有没有数据"
        has_data = bool(
            service.fetch_chunk_pool(kg_version=kg_version, org_id=org_id, limit=1)
        )
    except GraphUnavailableError:
        return None
    if m2_count > 0:
        return LAYER_END_TO_END
    if has_data:
        return LAYER_ALGORITHM
    #: 图里根本没这个版本 ⇒ 什么都别写（不是 L1 也不是 L2）
    return None


__all__ = [
    "LAYER_ALGORITHM",
    "LAYER_END_TO_END",
    "M2_ENTITY_ID_PREFIX",
    "detect_corpus_layer",
]
