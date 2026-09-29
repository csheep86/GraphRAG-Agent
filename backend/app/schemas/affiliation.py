"""M4 关联交易疑点的对外契约模型（Sprint 7.2 批次 B）。

契约事实上的真源是**本文件的 Pydantic 模型**（`backend/CODEBUDDY.md` §3 铁律）：
先改这里 → `uv run python scripts/export_openapi.py` 重导出 → `npm run gen:api`。

端点与语义逐字遵循 `specs/m4-affiliation-detection.md` §5.5；**路径口径**以 spec 的
`/affiliation/suspicions` 为准（批次 B 决策 **B1**——`plan.md:275` 原写 `suspects`
已同步为 `suspicions`）。

**类型枚举只列真能产出的类型**：Sprint 7.2 只有规则型两类；Sprint 9.5 加考勤域
`missing_check_in`；**Sprint 9.12 批次 C2 补算法型三类** `shared_phone` / `cycle` /
`amount_mismatch`——它们的输入（`:Phone` / `:Contract` / `:Invoice` / `:Voucher`
与持股边）到 S9.12 才由摄入器落成节点。此前**刻意不进契约**：把产不出的类型写进
OpenAPI 枚举等于向调用方**承诺一个不存在的能力**（根 `CODEBUDDY.md` 功能预留原则）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: 疑点类型——**只加不改**（金融两类照旧 + 考勤域 `missing_check_in`）
#: + **Sprint 9.12 批次 C2 算法型三类** `shared_phone` / `cycle` / `amount_mismatch`。
#:
#: 域化口径（proposal §5.4）：金融两类**保留不删**，考勤域新增一类；
#: 前端按域选择展示哪些类型，不做跨域混用。
#:
#: 算法三类**现在**才进契约（此前一直刻意不进）：它们依赖 `:Phone` / `:Contract` /
#: `:Invoice` / `:Voucher` 与持股边，语料与摄入器就位（S9.11 / S9.12）后才真能产出；
#: 提前写进枚举 = 向调用方承诺不存在的能力。
SuspicionType = Literal[
    "shared_address",
    "shared_legal_rep",
    "missing_check_in",
    "shared_phone",
    "cycle",
    "amount_mismatch",
]
#: 疑点严重度（spec §4.3）
SuspicionSeverity = Literal["high", "medium", "low"]
#: 疑点复核状态（spec §4.3）；`open` 为初始态
SuspicionReviewStatus = Literal["open", "dismissed", "confirmed"]
#: 疑点状态流转的输入：只允许从 `open` 落到终态（`confirmed` / `dismissed`）
SuspicionPatchStatus = Literal["dismissed", "confirmed"]
#: 任务状态（spec §4.4，ADR-0001：唯一真值源 = PostgreSQL）
AffiliationTaskStatusValue = Literal["pending", "processing", "completed", "failed"]


class AffiliationDetectRequest(BaseModel):
    """`POST /affiliation/detect` 请求体。

    `doc_ids` 是本次检测要覆盖的文档集合；**空则为 400**（校验在 Pydantic 层完成）。
    文档是否属于当前租户由**服务层**按 `documents.org_id` 校验——跨租户文档 → **403**
    （ADR-0003），不静默剔除。

    **注意**：`org_id` **严禁**出现在请求体里（ADR-0003 §3.3，只认 `X-Org-Id` 请求头）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "doc_ids": [
                    "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
                    "b7d0c4a1-8e2f-4c6b-9a35-1f7e2d9c4b08",
                ]
            }
        }
    )

    doc_ids: list[UUID] = Field(
        min_length=1,
        max_length=200,
        description="纳入本次检测的文档 id 列表（须均属当前租户，至少一个）",
    )


class AffiliationDetectResponse(BaseModel):
    """`POST /affiliation/detect` 的 **202** 响应（spec §5.5）。

    检测异步执行，不阻塞请求。任务状态的**唯一真值源是 PG `affiliation_tasks` 表**
    （ADR-0001 要求 1：严禁保存于进程内存，进程重启靠 `recover()` 回收）——前端用
    `task_id` 轮询 `GET /affiliation/tasks/{id}`，**不**依赖任何进程内状态。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "9a4b2c6d-1e3f-4a8b-8c2d-5e7f0a1b3c5d",
                "status": "pending",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    task_id: UUID = Field(description="`affiliation_tasks.id`，后续轮询状态用")
    status: AffiliationTaskStatusValue = Field(
        description="任务初始状态，恒为 `pending`"
    )
    trace_id: str = Field(description="贯穿本次检测与所产疑点的 trace_id")


class AffiliationTaskResultSummary(BaseModel):
    """任务完成后的结果摘要（spec §4.4 `result_summary`）。

    未完成 / 失败的任务**不返回**该结构（字段为 `null`），失败信息走 `error_code`。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 10,
                "by_type": {"shared_legal_rep": 1, "shared_address": 9},
                "top_5_severity": ["medium", "medium", "medium", "medium", "medium"],
            }
        }
    )

    total: int = Field(ge=0, description="检出的疑点总条数")
    by_type: dict[str, int] = Field(
        description="按疑点类型统计（`{type: 条数}`），键取自本次实际产出的 `suspicion_type`"
    )
    top_5_severity: list[str] = Field(
        description="按严重度排序的前 5 条疑点的 `severity`（不足 5 条则按实际条数）"
    )


class AffiliationTaskResponse(BaseModel):
    """`GET /affiliation/tasks/{id}` 响应（spec §5.5）。

    任务不存在 → 404；**跨租户 → 403**（ADR-0003：不泄露资源存在性也不返回空 200）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "9a4b2c6d-1e3f-4a8b-8c2d-5e7f0a1b3c5d",
                "status": "completed",
                "doc_ids": ["3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11"],
                "result_summary": {
                    "total": 10,
                    "by_type": {"shared_legal_rep": 1, "shared_address": 9},
                    "top_5_severity": ["medium"],
                },
                "error_code": None,
                "created_at": "2026-09-24T10:15:30Z",
                "updated_at": "2026-09-24T10:16:12Z",
                "completed_at": "2026-09-24T10:16:12Z",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    task_id: UUID = Field(description="任务 id（与 `affiliation_tasks.id` 一致）")
    status: AffiliationTaskStatusValue = Field(
        description="任务状态（PG 为唯一真值源）"
    )
    doc_ids: list[UUID] = Field(description="本次检测覆盖的文档 id 列表")
    result_summary: AffiliationTaskResultSummary | None = Field(
        default=None,
        description="完成后的摘要；`pending` / `processing` / `failed` 时为 `null`",
    )
    error_code: str | None = Field(
        default=None,
        description="失败错误码（`TASK_INTERRUPTED` 表示进程重启回收，ADR-0001 §3.2）",
    )
    created_at: datetime = Field(description="任务创建时间")
    updated_at: datetime = Field(description="最近一次状态变更时间")
    completed_at: datetime | None = Field(
        default=None, description="进入 `completed` 的时间；未完成为 `null`"
    )
    trace_id: str = Field(description="任务级 trace_id（与它产出的每条疑点同值）")


class AffiliationEvidenceRef(BaseModel):
    """一条原文证据引用（复用 S6 的 `:Chunk` 反查链路）。

    来源：`:Subject` / `:LegalPerson` / `:Address` 的 `source_entity_ids` → `:Entity`
    → `(:Chunk)-[:MENTIONS]->`；**不**是 LLM 自报的实体偏移。`doc_id` 为 `null` 表示
    该 chunk 未挂 `:Document`（**不**伪造 UUID）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "node_id": "v-s71a:sub:8f2c1b7e9d4a4c1e",
                "chunk_id": "chunk-581e8912827d",
                "doc_id": "3f1a9c2e-7b45-4d8a-9e01-2c4f6a8b0d11",
                "page": 12,
                "char_start": 0,
                "char_end": 764,
                "text": "甲方的法定代表人为缪建民……",
            }
        }
    )

    node_id: str = Field(
        description="该证据支撑的主体层节点 id（`:Subject` / `:LegalPerson` / `:Address`）"
    )
    chunk_id: str = Field(description="原文片段 id（`chunk-<12 hex>`）")
    doc_id: UUID | None = Field(
        default=None, description="片段所属文档 id；未挂载为 `null`"
    )
    page: int | None = Field(default=None, description="片段所在页码；未知为 `null`")
    char_start: int = Field(ge=0, description="片段在页内起始字符偏移")
    char_end: int = Field(ge=0, description="片段在页内结束字符偏移")
    text: str = Field(description="片段原文（用于前端高亮回显）")


class AffiliationCauseItem(BaseModel):
    """归因的一条原因（Sprint 9.5 批次 C2 扩展，结构即 M4 的 ``causes[]`` 元素）。

    **置信度不在这里**——它由 ``Σ命中权重 / Σ全部权重`` 在服务层算出（**禁止 LLM
    生成置信度**，纪律 3）：模型给的百分数不可复核，而这里每个 ``weight`` 都是
    确定性常量，命中与否由证据说话。

    ``matched=False`` 的项**照样返回**（不隐藏）：演示时要能说清「哪一项没对上」，
    只给命中项会让用户误以为证据齐备。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "trip_approved",
                "reason": "当日存在已审批的出差申请（武汉 10-16 ~ 10-18）",
                "weight": 0.35,
                "matched": True,
                "evidence": ["BUSINESS_TRIP:BT-2026-0017"],
            }
        }
    )

    code: str = Field(description="原因编码（如 `trip_approved` / `order_closed`）")
    reason: str = Field(description="原因说明（人可读）")
    weight: float = Field(ge=0, le=1, description="该证据的确定性权重（合计 1.0）")
    matched: bool = Field(description="该证据是否命中（未命中不计入置信度分子）")
    evidence: list[str] = Field(description="支撑该原因的证据节点 id；未命中时为空列表")


class AffiliationSuspicionItem(BaseModel):
    """一条疑点（结构对齐 M4 §3 验收 3：`{type, severity, entities[], evidence[]}`）。

    **引用覆盖率 = 100%** 是硬要求：产不出 `evidence` 的命中在算法层就被丢弃
    （`affiliation_suspicion_dropped_no_evidence`），因此这里的 `evidence` **非空**。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "2c6d1e3f-9a4b-4a8b-8c2d-5e7f0a1b3c5d",
                "task_id": "9a4b2c6d-1e3f-4a8b-8c2d-5e7f0a1b3c5d",
                "suspicion_type": "shared_legal_rep",
                "severity": "medium",
                "entities": [
                    "v-s71a:sub:8f2c1b7e9d4a4c1e",
                    "v-s71a:sub:1d4e7a9b3c6f2e80",
                ],
                "entity_names": ["招商局集团有限公司", "招商局轮船有限公司"],
                "evidence": [],
                "kg_version": "v-s71a-fe1c4dc3",
                "status": "open",
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": "2026-09-24T10:16:12Z",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    id: UUID = Field(description="疑点 id（`affiliation_suspicions.id`）")
    task_id: UUID = Field(
        description="产出该疑点的任务 id（批次 B 决策 B2 新增列；用于回答「返回哪一批疑点」）"
    )
    suspicion_type: SuspicionType = Field(description="疑点类型")
    severity: SuspicionSeverity = Field(description="严重度")
    entities: list[str] = Field(description="涉及节点 id：[主体A, 主体B, 共享节点]")
    entity_names: list[str] = Field(
        description="与 `entities` 对应的名称，仅用于展示；判重与落库以 id 为准"
    )
    evidence: list[AffiliationEvidenceRef] = Field(
        description="原文证据引用列表（非空：无证据的疑点不会落库）"
    )
    #: Sprint 9.12（spec §4.7.2 / §3 验收 5）：``amount_mismatch`` 的三方金额明细。
    #: 其余类型一律 ``null``——**不**用 ``{}`` 冒充「有明细」。
    #:
    #: 值类型**不收窄**为 ``float | str``：``cycle`` 的 ``cycle_length`` 是整数，
    #: 收窄会被 Pydantic 静默转成 ``2.0``（真机实测）——环长度不是金额，
    #: 无理由被浮点化。
    details: dict[str, Any] | None = Field(
        default=None,
        description=(
            "三方金额明细（仅 `amount_mismatch`）：`{trade_ref, contract_amount, "
            "invoice_amount, voucher_amount, max_diff}`；其余类型为 `null`"
        ),
    )
    causes: list[AffiliationCauseItem] | None = Field(
        default=None,
        description=(
            "归因原因链（Sprint 9.5 批次 C2 扩展）：`{code, reason, weight, matched, "
            "evidence[]}`，按权重降序。**考勤域疑点才有**；金融域疑点与 C2 之前落库的"
            "历史数据为 `null`（**不**用空列表冒充「已归因」）。"
        ),
    )
    kg_version: str = Field(description="疑点所属的图谱版本")
    status: SuspicionReviewStatus = Field(description="复核状态；初始恒为 `open`")
    reviewed_by: UUID | None = Field(
        default=None, description="复核人（`X-Actor-Id`；M5 落地后改为 token 主体）"
    )
    reviewed_at: datetime | None = Field(
        default=None, description="复核时间；未复核为 `null`"
    )
    created_at: datetime = Field(description="疑点落库时间")
    trace_id: str = Field(description="与产出它的任务 trace_id 同值")


class AffiliationSuspicionListResponse(BaseModel):
    """`GET /affiliation/suspicions` 响应（spec §5.5）。

    **不支持分页**（spec 未规定，不引入无消费者的 `page` / `page_size`）；
    默认返回当前租户**最近一条 completed 任务**产出的疑点（批次 B 决策 B2），
    显式传 `task_id` 则按该任务过滤。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "total": 0,
                "task_id": "9a4b2c6d-1e3f-4a8b-8c2d-5e7f0a1b3c5d",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    items: list[AffiliationSuspicionItem] = Field(description="疑点列表")
    total: int = Field(ge=0, description="疑点条数（与 `len(items)` 一致）")
    task_id: UUID | None = Field(
        default=None,
        description="本次结果对应的任务 id；当前租户从未跑过检测时为 `null`",
    )
    trace_id: str = Field(description="本次请求的 trace_id")


class AffiliationSuspicionPatchRequest(BaseModel):
    """`PATCH /affiliation/suspicions/{id}` 请求体（spec §5.5）。

    只允许 `dismissed` / `confirmed`：`open` 不是合法输入（不允许把已复核的疑点"改回"未复核，
    避免复核留痕被抹掉）。
    """

    model_config = ConfigDict(json_schema_extra={"example": {"status": "confirmed"}})

    status: SuspicionPatchStatus = Field(description="目标复核状态")


class AffiliationSuspicionPatchResponse(BaseModel):
    """`PATCH /affiliation/suspicions/{id}` 响应（200）。

    只回写状态相关字段——复核动作不改变疑点本体（`entities` / `evidence` 一律不变）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "2c6d1e3f-9a4b-4a8b-8c2d-5e7f0a1b3c5d",
                "status": "confirmed",
                "reviewed_by": "00000000-0000-4000-8000-000000000001",
                "reviewed_at": "2026-09-24T11:02:45Z",
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    id: UUID = Field(description="疑点 id")
    status: SuspicionReviewStatus = Field(description="更新后的复核状态")
    reviewed_by: UUID | None = Field(default=None, description="复核人 id")
    reviewed_at: datetime | None = Field(default=None, description="复核时间")
    trace_id: str = Field(description="本次请求的 trace_id")


__all__ = [
    "AffiliationDetectRequest",
    "AffiliationDetectResponse",
    "AffiliationEvidenceRef",
    "AffiliationSuspicionItem",
    "AffiliationSuspicionListResponse",
    "AffiliationSuspicionPatchRequest",
    "AffiliationSuspicionPatchResponse",
    "AffiliationTaskResponse",
    "AffiliationTaskResultSummary",
    "AffiliationTaskStatusValue",
    "SuspicionPatchStatus",
    "SuspicionReviewStatus",
    "SuspicionSeverity",
    "SuspicionType",
]
