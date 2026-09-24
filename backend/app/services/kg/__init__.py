"""KG 构建服务域（Sprint 5 批次 B：ADR-0002 三段式写入 Neo4j + kg_versions PG 真源）。

公开面：
- :class:`KgVersioningService`：封装 ``kg_versions`` 表的状态机（真源）；
- :class:`KgBuilder`：抽象协议（Protocol），三种实现之一：
- :class:`ThreeStageKgBuilder`：唯一实现——stage-1 schema MERGE / stage-2 batch LOAD /
  stage-3 cross-batch links（复用 ``scripts/import_to_neo4j.py`` 实战口径）。

设计纪律：
- **不**做内层事务——Neo4j 事务 + PG 事务分离（ADR-0002 §3.1 跨库一致性靠
  ``pending → ready`` 状态机 + 回填校验，不靠 ACID 跨库事务）；
- Neo4j driver **复用** :class:`GraphService` 懒加载的连接，**不**重建；
- ``kg_version_strategy`` 当前仅支持 ``per_org``；其它档显式报错
  （与 ``extraction_provider`` / ``llm_provider`` 同策略）。
"""

from app.services.kg.affiliation import (
    AffiliationService,
    Suspicion,
    SuspicionEvidence,
    detect_suspicions,
)
from app.services.kg.builder import KgBuilder, ThreeStageKgBuilder
from app.services.kg.versioning import KgVersioningService

__all__ = [
    "AffiliationService",
    "KgBuilder",
    "KgVersioningService",
    "Suspicion",
    "SuspicionEvidence",
    "ThreeStageKgBuilder",
    "detect_suspicions",
]
