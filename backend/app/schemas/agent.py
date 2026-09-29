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

ReasoningHopOrigin = Literal["cypher", "graph", "document"]
"""推理路径每一跳的**来源**（Sprint 9.5 批次 D1 / proposal §5.5）。

- ``cypher``：该跳由**多跳 Cypher**沿 ``:RELATION`` 遍历得出（本轮子图边集里没有）；
- ``graph``：该跳的两端点已在本轮**已检索子图的边集**里（直接来自图谱检索结果）；
- ``document``：该跳的终点能在**文档证据片段的原文**里找到（最强：有原文支撑）。

三者**互斥、按证据强度取最高**：``document`` > ``graph`` > ``cypher``。
**不得**为了让路径"看起来完整"而把弱来源标成强来源。
"""


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
            "引用在**片段内**的字符偏移（相对 `GET /documents/{id}/chunks/{chunk_id}` "
            "返回的 `text` 起点），由代码按 `实体 char_start − chunk char_start` "
            "**确定性换算**（偏移不由模型产出）。无实体级 span 命中时回退 0 = 整段引用"
        )
    )
    char_end: int = Field(
        description=(
            "引用在片段内的结束偏移（**不含**），与 `char_offset` 构成半开区间 "
            "`[char_offset, char_end)`，供前端精确定位高亮；回退档 = 片段长度 `len(text)`"
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


class ReasoningPathNode(BaseModel):
    """推理路径上的一个实体（proposal §5.5）：三个要素齐全才叫「可核查」——``id``（能回查图谱）、``name``（人能看懂）、``entity_type``（知道落在哪类实体上）。"""  # noqa: E501 - 契约描述串不折行（E501 已在 ruff 配置中关闭）

    id: str = Field(
        description="图谱节点 id（`Entity.id`），可回查 `GET /entities/{id}`"
    )
    name: str = Field(
        description=(
            "节点名称（`canonical_name`）；节点缺该属性时回落 ``id``，"
            "**严禁**编造一个看起来像名字的值"
        )
    )
    entity_type: str | None = Field(
        default=None,
        description="实体类型（`entity_type`）；节点缺该属性时为 `null`（**不**猜类型）",
    )


class ReasoningPathHop(BaseModel):
    """推理路径上的**一跳**：起点 --关系--> 终点 + 该跳来源。**刻意没有任何数值字段**（守「数值不出 LLM」）：路径只承载检索到的节点与边，数值结论由规则引擎（批次 C1）出，LLM 只出措辞（批次 D2）。"""  # noqa: E501 - 契约描述串不折行（E501 已在 ruff 配置中关闭）

    source: ReasoningPathNode = Field(description="起点实体")
    relation: str = Field(
        description=(
            "关系类型（图上真实的 ``relation_type``）。**不**做契约枚举投影——"
            "投影会把域关系一律兜底成 ``MENTIONS``（L7 同族失真）"
        )
    )
    target: ReasoningPathNode = Field(description="终点实体")
    origin: ReasoningHopOrigin = Field(description="该跳的来源（证据强度取最高）")
    evidence: str | None = Field(
        default=None,
        description=(
            "原文出处（仅 ``origin = document`` 时有值）：``chunk:<chunk_id>``；"
            "其余来源为 ``null``（**不**留空串冒充有出处）"
        ),
    )


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
                        "chunk_id": "chunk-581e8912827d",
                        "char_offset": 480,
                        "char_end": 560,
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
                "reasoning_path": [
                    {
                        "source": {
                            "id": "EMPLOYEE:E001",
                            "name": "张伟",
                            "entity_type": "EMPLOYEE",
                        },
                        "relation": "HAS_POSITION",
                        "target": {
                            "id": "POSITION:售后工程师",
                            "name": "售后工程师",
                            "entity_type": "POSITION",
                        },
                        "origin": "graph",
                        "evidence": None,
                    }
                ],
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
    reasoning_path: list[ReasoningPathHop] | None = Field(
        default=None,
        description=(
            "多跳推理路径（proposal §5.5）：「问句 → 定位实体 → 沿关系跳转 → 命中的条款/事实」"
            "的**逐跳链**，每一跳带起点 / 终点实体、关系类型与该跳来源。"
            "**可空语义（与 C2 `causes` 同一口径，二者语义相反，不许混用）**："
            "`null` = **未产出**（拒答分支不给路径——路径是证据链，拒答时返回它会让前端误以为"
            "答案有据可依，与 `citations = []` 同一条纪律）；"
            "`[]` = **检索了但零命中**（问句没在本轮子图里定位到锚点实体，"
            "或锚点沿关系走不到任何条款 / 事实节点），**禁止**填示例路径充数。"
        ),
    )
