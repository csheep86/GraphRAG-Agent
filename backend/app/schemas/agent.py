"""M3 图谱问答相关契约模型（对齐 `specs/m3-graphqa-citation.md` §4.1 / §4.2）。"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.document import GraphEdge, GraphNode

QueryScope = Literal["single_doc", "cross_doc"]
QueryRoute = Literal["m3_graphqa", "m4_affiliation"]
QueryConfidence = Literal["high", "medium", "low"]
RefusalReason = Literal["no_grounded_evidence", "out_of_scope", "low_confidence"]


class AgentQueryRequest(BaseModel):
    """`POST /api/v1/agent/query` 请求体（M3 §4.1）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "A 公司的子公司的供应商是否同时是 B 公司的股东？",
                "scope": "cross_doc",
                "kg_version": "20260320T1430Z-01H9X9ABCDEF",
            }
        }
    )

    question: str = Field(min_length=1, description="用户问题（单轮，不做多轮上下文）")
    scope: QueryScope = Field(
        default="cross_doc", description="检索范围；`single_doc` 时 `doc_id` 必填"
    )
    doc_id: UUID | None = Field(
        default=None, description="限定文档 id，仅 `scope = single_doc` 时使用"
    )
    kg_version: str | None = Field(
        default=None,
        description=(
            "指定图谱版本，缺省取最新 active 版本。"
            "若指定版本的 status ≠ active（writing / failed / superseded），"
            "一律返回 409 KG_VERSION_NOT_ACTIVE，严禁静默降级（ADR-0002 §3.2）"
        ),
    )

    @model_validator(mode="after")
    def _require_doc_id_for_single_doc(self) -> AgentQueryRequest:
        if self.scope == "single_doc" and self.doc_id is None:
            raise ValueError("scope=single_doc 时 doc_id 必填")
        return self


class Citation(BaseModel):
    """引用条目：答案的每一个事实句都必须能回溯到此结构（M3 §4.2）。

    引用覆盖率必须为 100%，否则必须拒答（反证条件 F3）。

    **Sprint 6 批次 B（Q1 拍板）**：``page`` 改为 nullable——页码来自 MinerU
    ``content_list`` 文本对齐反推（批次 A 的 ``PageIndex``），
    **对齐失配时必须给 ``null``，严禁兜底伪造 1**。
    """

    doc_id: UUID
    page: int | None = Field(
        default=None,
        description="页码（1-based）；页码无法判定时为 `null`（严禁伪造）",
    )
    chunk_id: str
    char_offset: int = Field(
        description=(
            "引用在 chunk 内的字符偏移。"
            "批次 B 为 chunk 起点（0）；实体级偏移待 `:Entity` 落 `char_start` 后细化"
        )
    )
    snippet: str = Field(description="用于 UI 高亮的原文片段（≤ 200 字的 chunk 摘录）")


class TokenUsage(BaseModel):
    """LLM token 用量（对齐 DeepSeek / OpenAI 兼容 API 的 `usage` 格式）。

    按「实测结果反哺规则」：骨架链路 / LLM 未返回 usage 时，
    上层字段 ``AgentQueryResponse.token_usage`` 置 ``null``，**严禁造数据**。
    """

    prompt_tokens: int = Field(default=0, ge=0, description="输入 token 数")
    completion_tokens: int = Field(default=0, ge=0, description="输出 token 数")
    total_tokens: int = Field(default=0, ge=0, description="总 token 数")


class AgentQueryResponse(BaseModel):
    """`POST /api/v1/agent/query` 响应（M3 §4.2）。

    Sprint 4 阶段 10.0 批次 A 扩展（Sprint 3 缺口 1 偿还）：
    新增 ``kg_nodes`` / ``kg_relations`` / ``token_usage`` 三字段，
    供前端 p03「引用证据」面板展示图谱证据与 token 用量。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "是。示例子公司 A 的供应商 C 同时持有 B 公司 12% 股权 [source: doc-9/page-3/chunk-12]",
                "citations": [
                    {
                        "doc_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
                        "page": 3,
                        "chunk_id": "chunk-12",
                        "char_offset": 480,
                        "snippet": "……供应商 C 持有本公司 12% 股权……",
                    }
                ],
                "route": "m3_graphqa",
                "confidence": "high",
                "refused": False,
                "refusal_reason": None,
                "kg_version": "20260320T1430Z-01H9X9ABCDEF",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
                "kg_nodes": [
                    {
                        "id": "e-001",
                        "label": "Entity",
                        "entity_type": "公司",
                        "canonical_name": "示例科技有限公司",
                        "confidence": 0.93,
                        "kg_version": "20260320T1430Z-01H9X9ABCDEF",
                    }
                ],
                "kg_relations": [
                    {
                        "id": "r-001",
                        "type": "AFFILIATED_WITH",
                        "source": "e-001",
                        "target": "e-002",
                        "properties": {"share_pct": 51.0},
                    }
                ],
                "token_usage": {
                    "prompt_tokens": 2048,
                    "completion_tokens": 256,
                    "total_tokens": 2304,
                },
            }
        }
    )

    answer: str = Field(
        description='答案文本，含 `[source: ...]` 标记；拒答时恒为 `"无法回答"`'
    )
    citations: list[Citation] = Field(
        description="引用列表；`refused = false` 时必须覆盖全部事实句（覆盖率 100%）"
    )
    route: QueryRoute = Field(
        description="意图路由结果；`m4_affiliation` 表示已转交 M4 场景识别"
    )
    confidence: QueryConfidence = Field(
        description="`low` 时前端必须标记「建议人工复核」（M3 §3 验收 6）"
    )
    refused: bool = Field(description="是否拒答（严禁 LLM 编造引用，M3 §3 验收 3）")
    refusal_reason: RefusalReason | None = Field(
        default=None, description="仅 `refused = true` 时非空"
    )
    kg_version: str = Field(description="本次检索实际使用的图谱版本（必为 active）")
    trace_id: str
    kg_nodes: list[GraphNode] = Field(
        default_factory=list,
        description=(
            "支撑本次答案的图谱节点（复用 `DocumentGraphResponse.nodes` 同构模型）；"
            "拒答 / 图谱为空时为空列表"
        ),
    )
    kg_relations: list[GraphEdge] = Field(
        default_factory=list,
        description=(
            "支撑本次答案的图谱关系（复用 `DocumentGraphResponse.edges` 同构模型）；"
            "拒答 / 图谱为空时为空列表"
        ),
    )
    token_usage: TokenUsage | None = Field(
        default=None,
        description=(
            "LLM token 用量；拒答分支未调用 LLM、或 LLM 未返回 usage 时为 `null`"
        ),
    )
