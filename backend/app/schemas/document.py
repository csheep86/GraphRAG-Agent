"""M1 文档接入相关契约模型。

字段来源：
- `specs/m1-async-ingest.md` §3 验收 1 / 5、§4.1 `documents` 表、§5.4 端点草案；
- `specs/m2-extract-kg.md` §4.1 / §4.2（图谱节点与关系）；
- `docs/adr/ADR-0002-neo4j-postgres-consistency.md` §3.2（查询层只认 active 版本）。
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ErrorCode

DocumentStatus = Literal["pending", "processing", "completed", "failed"]
"""M1 硬约束 H1 的状态机取值，**不得新增**。"""

NodeLabel = Literal["Document", "Chunk", "Entity", "Evidence"]
"""对齐 Neo4j 标签 `:Document` / `:Chunk` / `:Entity` / `:Evidence`（M2 §4.1）。"""

RelationType = Literal[
    "HAS_CHUNK",
    "MENTIONS",
    "SUPPORTED_BY",
    "AFFILIATED_WITH",
    "SUPPLIES_TO",
    "PARTY_TO",
]
"""对齐 Neo4j 关系类型（M2 §4.2）。"""


class UploadResponse(BaseModel):
    """`POST /api/v1/documents/upload` 响应（M1 验收 1）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
                "status": "pending",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    task_id: UUID = Field(
        description="任务 id（UUIDv4），与 `documents.id` 一致；M2 抽取任务复用同一 id 空间"
    )
    status: Literal["pending"] = Field(
        description="上传受理后恒为 `pending`（异步执行）"
    )
    trace_id: str


class DocumentError(BaseModel):
    """`documents.status = failed` 时的失败信息。

    与顶层 `ErrorResponse` 的区别：这里**不含** `trace_id`，
    因为响应体已在外层携带同一个 `trace_id`。
    """

    code: ErrorCode = Field(
        description="失败错误码。进程重启回收的场景为 `TASK_INTERRUPTED`（ADR-0001 §3.2）"
    )
    message: str
    detail: dict[str, Any] | None = Field(
        default=None,
        description="失败明细摘要。**禁止**回显 `documents.error_detail` 原文（敏感）",
    )


class DocumentStatusResponse(BaseModel):
    """`GET /api/v1/documents/{id}/status` 响应（M1 验收 5）。

    前端轮询建议：首次 2s，3 次后降为 10s。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
                "status": "processing",
                "progress": None,
                "error": None,
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    task_id: UUID
    status: DocumentStatus = Field(
        description="仅取 `pending / processing / completed / failed`（H1）"
    )
    progress: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="0–1 的粗粒度进度。解析进度不可精确估计时为 `null`（Sprint 1 恒为 null）",
    )
    error: DocumentError | None = Field(
        default=None, description="仅当 `status = failed` 时非空"
    )
    trace_id: str


class GraphNode(BaseModel):
    """图谱节点。

    **刻意不含** `pii_flags`：M2 §5.3 明确禁止该字段外泄。
    """

    id: str
    label: NodeLabel
    entity_type: str | None = Field(
        default=None,
        description="`:Entity.type`（公司 / 自然人 / 法人 / 地址 / 证件号等）",
    )
    canonical_name: str | None = Field(
        default=None, description="`:Entity.canonical_name`（消解后的标准名）"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="抽取置信度"
    )
    kg_version: str = Field(description="节点所属图谱版本，必须等于响应的 `kg_version`")


class GraphEdge(BaseModel):
    id: str
    type: RelationType
    source: str = Field(description="起点节点 id")
    target: str = Field(description="终点节点 id")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="关系属性（如 `share_pct` / `since` / `amount` / `role`），不含证据原文",
    )


class DocumentGraphResponse(BaseModel):
    """`GET /api/v1/documents/{id}/graph` 响应：该文档在 Neo4j 中的子图。

    **一致性约束（ADR-0002 §3.2）**：只返回 `status = active` 的 `kg_version`；
    该文档无 active 版本时返回 `409 KG_VERSION_NOT_ACTIVE`，**绝不静默降级**到其他版本。

    规模上限对齐 M3 §3 验收 1：单次返回节点数 ≤ 500，超限时 `truncated = true`。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "doc_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
                "kg_version": "20260320T1430Z-01H9X9ABCDEF",
                "version_status": "active",
                "nodes": [
                    {
                        "id": "e-001",
                        "label": "Entity",
                        "entity_type": "公司",
                        "canonical_name": "示例科技有限公司",
                        "confidence": 0.93,
                        "kg_version": "20260320T1430Z-01H9X9ABCDEF",
                    }
                ],
                "edges": [
                    {
                        "id": "r-001",
                        "type": "AFFILIATED_WITH",
                        "source": "e-001",
                        "target": "e-002",
                        "properties": {"share_pct": 51.0, "since": "2021-03-01"},
                    }
                ],
                "node_count": 1,
                "relation_count": 1,
                "truncated": False,
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    doc_id: UUID
    kg_version: str = Field(
        description="本次返回的图谱版本，来自 `GET /internal/kg/active` 的 active 版本"
    )
    version_status: Literal["active"] = Field(
        description="恒为 `active`，是 ADR-0002 一致性强制的可见契约"
    )
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count: int = Field(ge=0, description="`nodes` 实际条数（截断后）")
    relation_count: int = Field(ge=0, description="`edges` 实际条数（截断后）")
    truncated: bool = Field(default=False, description="是否因超过 500 节点上限被截断")
    trace_id: str
