"""图谱概览与实体详情契约（Sprint 5 批次 C）。

字段来源：
- ``specs/m2-extract-kg.md`` §4.1 / §4.2（图谱节点与关系）；
- ``docs/adr/ADR-0002-neo4j-postgres-consistency.md`` §3.2（kg_version 只读 active）；
- ``docs/v1.1.0-demo-mvp-plan.md`` §4.2 批次 C（图谱全局视图 + 实体详情）。

**与 ``document.GraphNode`` / ``document.GraphEdge`` 的区别**：
本批新增的 ``GraphOverviewNode`` / ``GraphOverviewEdge`` 是**前端力导向图布局**
所需的轻量投影（含 ``seed_x`` / ``seed_y`` / ``weight`` 等演示专属字段），
而 ``document.GraphNode`` / ``document.GraphEdge`` 是**真实 Neo4j 节点投影**
（含 ``label`` / ``entity_type`` / ``confidence`` / ``properties`` 等可溯源字段）。
两者用途不同，刻意不共用类型，避免演示字段污染契约可溯源链。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GraphCategory = Literal["topic", "norm", "org", "system"]
"""知识图谱节点分类（前端图例 4 类：topic / norm / org / system）。

**前端契约字段**——后端只透传 Neo4j ``:Entity.type`` 字符串映射结果，
不做语义猜测；演示数据由 ``langextract_mvp`` 写入 ``:Entity.type`` 时控制。
"""


class GraphOverviewNode(BaseModel):
    """`GET /graph/overview` 节点轻量投影。

    仅含前端力导向图渲染所需的最小字段集合，**不含** ``label`` /
    ``confidence`` / ``pii_flags`` 等（避免演示字段污染契约可溯源链）。
    """

    id: str = Field(description="Neo4j 节点 id（`:Entity.id`）")
    name: str = Field(description="`:Entity.canonical_name`")
    type: str = Field(description="`:Entity.type`（原始字符串）")
    category: GraphCategory = Field(description="前端图例分类（4 类）")
    #: 节点半径权重（前端 seed）
    weight: float = Field(ge=0, le=10, description="相对权重，决定节点半径")
    #: 初始布局坐标（0–1 归一化），前端用作力导向模拟的种子值
    seed_x: float = Field(ge=0, le=1)
    seed_y: float = Field(ge=0, le=1)


class GraphOverviewEdge(BaseModel):
    """`GET /graph/overview` 边轻量投影。"""

    id: str
    source: str = Field(description="起点节点 id")
    target: str = Field(description="终点节点 id")
    relation: str = Field(description="关系名（来自 Neo4j ``type(r)``）")


class GraphOverviewResponse(BaseModel):
    """`GET /graph/overview` 响应：全局图谱概览。

    节点 / 边上限 500（与 ``DocumentGraphResponse`` 对齐），超限时
    ``truncated = true`` —— 前端禁用「全部展开」以避免误以为是真实全量。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "doc_count": 27,
                "entity_count": 1428,
                "relation_count": 3604,
                "kg_version": "20260320T1430Z-01H9X9ABCDEF",
                "nodes": [
                    {
                        "id": "e-001",
                        "name": "数据安全合规",
                        "type": "核心主题",
                        "category": "topic",
                        "weight": 1.65,
                        "seed_x": 0.14,
                        "seed_y": 0.38,
                    }
                ],
                "edges": [
                    {
                        "id": "r-001",
                        "source": "e-001",
                        "target": "e-002",
                        "relation": "包含",
                    }
                ],
                "truncated": False,
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    doc_count: int = Field(ge=0, description="当前租户下有 active kg_version 的文档数")
    entity_count: int = Field(ge=0, description="active kg_version 内的实体数（总）")
    relation_count: int = Field(ge=0, description="active kg_version 内的关系数（总）")
    kg_version: str = Field(description="active kg_version 版本号")
    nodes: list[GraphOverviewNode]
    edges: list[GraphOverviewEdge]
    truncated: bool = Field(default=False, description="是否因超过 500 节点上限被截断")
    trace_id: str


class EntityAttribute(BaseModel):
    """实体详情属性项。"""

    label: str = Field(description="属性名（人类可读）")
    value: str = Field(description="属性值")


class EntityRelation(BaseModel):
    """实体详情关系项。"""

    relation: str = Field(description="关系名")
    target_id: str = Field(description="目标实体 id")
    target_name: str = Field(description="目标实体名（前端直接展示）")


class EntityDetail(BaseModel):
    """`GET /entities/{entity_id}` 响应：单个实体的属性 + 出边邻居。

    邻居数上限由 ``settings`` 或路由层硬上限（默认 50）控制；
    跨租户访问 → 403 ``FORBIDDEN``；不存在 → 404 ``ENTITY_NOT_FOUND``。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "e-001",
                "canonical_name": "数据安全合规",
                "entity_type": "核心主题",
                "category": "topic",
                "confidence": 0.98,
                "kg_version": "20260320T1430Z-01H9X9ABCDEF",
                "relation_count": 18,
                "attributes": [
                    {"label": "首次出现", "value": "企业知识库架构设计.pdf"},
                    {"label": "置信度", "value": "0.98"},
                ],
                "relations": [
                    {
                        "relation": "包含",
                        "target_id": "e-002",
                        "target_name": "数据分级分类",
                    }
                ],
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    id: str = Field(description="Neo4j `:Entity.id`")
    canonical_name: str = Field(description="`:Entity.canonical_name`（消解后标准名）")
    entity_type: str = Field(description="`:Entity.type`")
    category: GraphCategory = Field(description="前端图例分类")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    kg_version: str = Field(description="active kg_version")
    relation_count: int = Field(ge=0, description="实体的总出度 + 入度")
    attributes: list[EntityAttribute]
    relations: list[EntityRelation]
    trace_id: str


__all__ = [
    "EntityAttribute",
    "EntityDetail",
    "EntityRelation",
    "GraphCategory",
    "GraphOverviewEdge",
    "GraphOverviewNode",
    "GraphOverviewResponse",
]
