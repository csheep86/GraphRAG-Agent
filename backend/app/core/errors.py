"""统一业务错误码与异常类型。

约束来源：
- `CODEBUDDY.md`「错误响应规范」：所有异常统一返回 `{code, message, detail, trace_id}`，
  HTTP 状态码与业务错误码分离。
- `ADR-0001`：`TASK_INTERRUPTED`（进程重启回收孤儿任务）。
- `ADR-0002`：`KG_VERSION_NOT_ACTIVE`（显式指定非 active 版本必须拒绝，禁止静默降级）。
- `ADR-0003`：`FORBIDDEN`（跨租户访问）。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """统一业务错误码。新增错误码必须先更新 `contracts/openapi.yaml` 与人类可读规格。"""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    KG_VERSION_NOT_ACTIVE = "KG_VERSION_NOT_ACTIVE"
    KG_TENANT_LEAK = "KG_TENANT_LEAK"
    #: M5 §3 验收 4：私域部署下检测到出向调用（目标既非内网、也不在
    #: `ALLOWED_EGRESS_HOSTS` 白名单内）⇒ **构造期**阻断，返回 503。
    #: 与 501 区分：501 = 基础设施不可用（连不上），本码 = **主动拒绝出网**（连通没问题）。
    PRIVATE_DEPLOY_BLOCKED = "PRIVATE_DEPLOY_BLOCKED"
    #: Sprint 9.5 批次 C3：active 版本里没有考勤事实（EMPLOYEE / SHIFT / 打卡），
    #: 扫描**无从下手**。与「服务不可用」区分开——库是通的、版本是对的，只是没有数据。
    COMPLIANCE_NO_FACTS = "COMPLIANCE_NO_FACTS"
    #: M6 §5.5（Sprint 12 契约先行批次）：本体 schema 版本冲突 ——
    #: 重复确认（`POST /ontology/confirm` 同一 version 二次确认）或
    #: 取 active schema 时本租户尚无 active 版本。与 `KG_VERSION_NOT_ACTIVE` 同源纪律：
    #: **不静默复用旧版本**。
    SCHEMA_VERSION_NOT_ACTIVE = "SCHEMA_VERSION_NOT_ACTIVE"
    TASK_INTERRUPTED = "TASK_INTERRUPTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    HTTP_ERROR = "HTTP_ERROR"

    # -- License（接缝 9 / DR-C1 / ADR-0006 §2.5）--
    #: 六个码是 ADR-0006 §2.5 的**逐字清单**，缺任一个前端都无法区分拒绝原因。
    #: 全部映射 403 —— ADR 明写「统一 403，不用 402：402 语义未标准化」。
    LICENSE_MISSING = "LICENSE_MISSING"
    LICENSE_INVALID = "LICENSE_INVALID"
    LICENSE_FINGERPRINT_MISMATCH = "LICENSE_FINGERPRINT_MISMATCH"
    LICENSE_EXPIRED = "LICENSE_EXPIRED"
    LICENSE_LIMIT_EXCEEDED = "LICENSE_LIMIT_EXCEEDED"
    LICENSE_MODULE_DISABLED = "LICENSE_MODULE_DISABLED"


#: 每个错误码的默认 HTTP 状态码（HTTP 状态码与业务错误码分离）
ERROR_HTTP_STATUS: Mapping[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.DOCUMENT_NOT_FOUND: 404,
    ErrorCode.ENTITY_NOT_FOUND: 404,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.KG_VERSION_NOT_ACTIVE: 409,
    ErrorCode.KG_TENANT_LEAK: 403,
    ErrorCode.COMPLIANCE_NO_FACTS: 409,
    ErrorCode.SCHEMA_VERSION_NOT_ACTIVE: 409,
    ErrorCode.TASK_INTERRUPTED: 409,
    ErrorCode.PRIVATE_DEPLOY_BLOCKED: 503,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.HTTP_ERROR: 500,
    # 全部 403（ADR-0006 §2.5「统一 403，不用 402——402 语义未标准化」）
    ErrorCode.LICENSE_MISSING: 403,
    ErrorCode.LICENSE_INVALID: 403,
    ErrorCode.LICENSE_FINGERPRINT_MISMATCH: 403,
    ErrorCode.LICENSE_EXPIRED: 403,
    ErrorCode.LICENSE_LIMIT_EXCEEDED: 403,
    ErrorCode.LICENSE_MODULE_DISABLED: 403,
}

#: 默认 human-readable 消息（英文短句，便于日志检索；面向用户的中文说明见人类可读规格）
DEFAULT_MESSAGES: Mapping[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "Request validation failed",
    ErrorCode.UNAUTHORIZED: "Authentication required",
    ErrorCode.FORBIDDEN: "Cross-tenant access denied",
    ErrorCode.NOT_FOUND: "Resource not found",
    ErrorCode.DOCUMENT_NOT_FOUND: "Document not found",
    ErrorCode.ENTITY_NOT_FOUND: "Entity not found",
    ErrorCode.FILE_TOO_LARGE: "Uploaded file exceeds the size limit",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "Unsupported media type",
    ErrorCode.KG_VERSION_NOT_ACTIVE: "Requested kg_version is not active",
    ErrorCode.KG_TENANT_LEAK: "Cross-tenant subgraph detected",
    ErrorCode.COMPLIANCE_NO_FACTS: "No attendance facts in the active kg_version",
    ErrorCode.SCHEMA_VERSION_NOT_ACTIVE: "Ontology schema version conflict",
    ErrorCode.TASK_INTERRUPTED: "Task interrupted by process restart",
    ErrorCode.PRIVATE_DEPLOY_BLOCKED: "Egress to a non-approved host blocked by private deploy policy",
    ErrorCode.NOT_IMPLEMENTED: "Infrastructure unavailable",
    ErrorCode.RATE_LIMITED: "Too many requests",
    ErrorCode.INTERNAL_ERROR: "Internal server error",
    ErrorCode.HTTP_ERROR: "Unmapped HTTP error",
    ErrorCode.LICENSE_MISSING: "No valid license file found",
    ErrorCode.LICENSE_INVALID: "License signature verification failed",
    ErrorCode.LICENSE_FINGERPRINT_MISMATCH: "License is bound to another machine",
    ErrorCode.LICENSE_EXPIRED: "License expired beyond the grace period",
    ErrorCode.LICENSE_LIMIT_EXCEEDED: "License quota exceeded",
    ErrorCode.LICENSE_MODULE_DISABLED: "Requested module is not licensed",
}

#: 错误码语义 + 决策依据（写入 OpenAPI 枚举描述，供前端与人工阅读）
ERROR_CODE_DESCRIPTIONS: Mapping[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "请求体 / 查询参数 / 路径参数未通过 Pydantic 校验。",
    ErrorCode.UNAUTHORIZED: "缺少或无法解析认证态（Bearertoken / 开发态请求头）。",
    ErrorCode.FORBIDDEN: "跨租户访问被拒（ADR-0003：org_id 不符），非本租户资源一律拒绝。",
    ErrorCode.NOT_FOUND: "通用资源不存在（含未注册路由）。",
    ErrorCode.DOCUMENT_NOT_FOUND: "文档不存在或未在本租户可见范围内。",
    ErrorCode.ENTITY_NOT_FOUND: "实体不存在或不属于当前 active kg_version；与跨租户 403 区分。",
    ErrorCode.FILE_TOO_LARGE: "上传文件超过 MAX_UPLOAD_SIZE_MB（默认 100MB，M1 验收 2）。",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "上传文件 MIME 不在白名单（M1 验收 3）。",
    ErrorCode.KG_VERSION_NOT_ACTIVE: (
        "请求显式指定了非 active 的 kg_version（writing / failed / superseded），"
        "按 ADR-0002 §3.2 一律拒绝，严禁静默降级到最新版。"
    ),
    ErrorCode.KG_TENANT_LEAK: (
        "跨租户子图泄漏检测到（ADR-0003 §4，Sprint 5 批次 B）。"
        "active kg_version 内任一 Entity 节点 org_id 与当前 org_id 不一致——"
        "属数据质量事故伪装为正常结论，由 /agent/query 路由层转 403。"
    ),
    ErrorCode.SCHEMA_VERSION_NOT_ACTIVE: (
        "本体 schema 版本冲突（M6 §5.5）：① `POST /ontology/confirm` 对同一 version "
        "重复确认；② `GET /ontology/active` 时本租户尚无 active schema。"
        "与 `KG_VERSION_NOT_ACTIVE` 同一纪律——**不**静默复用旧版本 / 默认 schema。"
    ),
    ErrorCode.TASK_INTERRUPTED: (
        "进程重启导致在途任务被 TaskManager.recover() 回收置 failed（ADR-0001 §3.2）。"
    ),
    ErrorCode.COMPLIANCE_NO_FACTS: (
        "active kg_version 内查不到 CSV 派生的 EMPLOYEE 节点，合规规则无从下手"
        "（Sprint 9.5 批次 C3）。与 501 区分：库是通的、版本是对的，只是没有考勤数据。"
    ),
    ErrorCode.PRIVATE_DEPLOY_BLOCKED: (
        "私域部署下的出向被阻断（M5 §3 验收 4）：`PRIVATE_DEPLOY_ENABLED=true` 时，"
        "出向目标必须落在**内网 / 回环**地址或 `ALLOWED_EGRESS_HOSTS` 白名单内，"
        "其余一律在**客户端构造期**拒绝（请求尚未发出），并写"
        "`audit_log(action=private_deploy.violation, status=failure)`。"
        "与 501 区分：本码表示**主动禁止出网**，不是外部依赖不可用。"
    ),
    ErrorCode.NOT_IMPLEMENTED: (
        "基础设施不可用（Neo4j 图谱存储不可用（连不上 / 查询失败）"
        "/ LLM 未配置或装配失败）时返回 501，**不**表示「接口未实现」。"
    ),
    ErrorCode.RATE_LIMITED: (
        "请求触发限流（M5 §3 验收 5，slowapi）：同一 IP 在时间窗口内对同一接口的"
        "调用超过 `rate_limit_per_minute`（默认 60）次。响应带 `Retry-After` 头"
        "（秒），限流同时写 `audit_log(action=rate_limit.triggered)`。"
    ),
    ErrorCode.INTERNAL_ERROR: "未预期的服务端异常，已记录日志（含 trace_id）。",
    ErrorCode.HTTP_ERROR: "未在错误码表中登记的 HTTP 状态兜底，保留原始 HTTP 状态语义。",
    ErrorCode.LICENSE_MISSING: (
        "未找到有效 license 文件（ADR-0006 §2.5）：文件缺失 ⇒ **全量拒绝**，"
        "仅 `/health` 与 `/license/status` 可访问（自检端点被锁死则现场无法诊断）。"
    ),
    ErrorCode.LICENSE_INVALID: (
        "license 存在但验签失败 / 正文非法（§2.3）：Ed25519 验签不通过即判无效，"
        "**不做宽松通过**，与「文件缺失」同等处理。"
    ),
    ErrorCode.LICENSE_FINGERPRINT_MISMATCH: (
        "license 绑定的机器指纹与本机不符（§2.1 / §2.5）：指纹组件交集 < 2/3 即判为另一台机器。"
    ),
    ErrorCode.LICENSE_EXPIRED: (
        "有效期已过且越过宽限期（§2.5 / §2.7）：宽限期（`grace_days`，默认 30）内**只读**，"
        "超期才全量拒绝——离线环境时钟不可信，硬拒有误伤风险。"
    ),
    ErrorCode.LICENSE_LIMIT_EXCEEDED: (
        "超出授权维度上限（§2.4 组合维度）：**卡增量、保存量** —— 租户数 / 席位数超限"
        "只拒绝**新增**动作（新建 org / 新建或启用用户），已有数据与只读查询不受影响"
        "（超限即锁死只读等于拿客户数据当人质，必然引发交付纠纷）。"
    ),
    ErrorCode.LICENSE_MODULE_DISABLED: (
        "请求所属功能模块**未被授权**（§2.4 维度 3，`modules[]` 未包含）：按模块收费的兑现点。"
    ),
}

#: 错误码 -> 决策来源（ADR / 规格），用于追溯
ERROR_CODE_SOURCES: Mapping[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "CODEBUDDY.md 错误响应规范",
    ErrorCode.UNAUTHORIZED: "M5 §3 验收 1",
    ErrorCode.FORBIDDEN: "ADR-0003 §3.3 / M5 §3 验收 1",
    ErrorCode.NOT_FOUND: "CODEBUDDY.md 错误响应规范",
    ErrorCode.DOCUMENT_NOT_FOUND: "M1 §5.4",
    ErrorCode.ENTITY_NOT_FOUND: "Sprint 5 批次 C / plans §4.2 批次 C",
    ErrorCode.FILE_TOO_LARGE: "M1 §3 验收 2",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "M1 §3 验收 3",
    ErrorCode.KG_VERSION_NOT_ACTIVE: "ADR-0002 §3.2 / M3 §4.1",
    ErrorCode.KG_TENANT_LEAK: "ADR-0003 §4 / Sprint 5 批次 B",
    ErrorCode.SCHEMA_VERSION_NOT_ACTIVE: "M6 §5.5 / changes/archive/2026-10-02-P0-m6-finalization F2",
    ErrorCode.TASK_INTERRUPTED: "ADR-0001 §3.2",
    ErrorCode.COMPLIANCE_NO_FACTS: "Sprint 9.5 批次 C3 / changes/archive/2026-09-28-Sprint9.5/proposal.md §5.3",
    ErrorCode.PRIVATE_DEPLOY_BLOCKED: "M5 §3 验收 4 / specs/m5-permission-audit.md §4.6",
    ErrorCode.NOT_IMPLEMENTED: "backend/CODEBUDDY.md §1.1 故障语义边界 / ADR-0002 §3.2",
    ErrorCode.RATE_LIMITED: "M5 §3 验收 5 / 决策 A14（Sprint 8.1 批次 B）",
    ErrorCode.INTERNAL_ERROR: "CODEBUDDY.md 错误响应规范",
    ErrorCode.HTTP_ERROR: "CODEBUDDY.md 错误响应规范",
    ErrorCode.LICENSE_MISSING: "ADR-0006 §2.5（文件缺失 ⇒ 全量拒绝）",
    ErrorCode.LICENSE_INVALID: "ADR-0006 §2.3 / §2.5",
    ErrorCode.LICENSE_FINGERPRINT_MISMATCH: "ADR-0006 §2.1 / §2.5",
    ErrorCode.LICENSE_EXPIRED: "ADR-0006 §2.5 / §2.7（宽限期 + max_seen_ts）",
    ErrorCode.LICENSE_LIMIT_EXCEEDED: "ADR-0006 §2.4 维度 1 / 2 + §2.5「卡增量保存量」",
    ErrorCode.LICENSE_MODULE_DISABLED: "ADR-0006 §2.4 维度 3（modules[]）/ §3.3",
}

#: HTTP 状态码 -> 错误码（用于拦截框架自身抛出的 HTTPException）
HTTP_STATUS_TO_ERROR_CODE: Mapping[int, ErrorCode] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.HTTP_ERROR,
    413: ErrorCode.FILE_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.RATE_LIMITED,
    501: ErrorCode.NOT_IMPLEMENTED,
}


def resolve_error_code(http_status: int) -> ErrorCode:
    """把任意 HTTP 状态码映射为已登记的错误码，未登记则兜底 `HTTP_ERROR`。"""
    return HTTP_STATUS_TO_ERROR_CODE.get(http_status, ErrorCode.HTTP_ERROR)


class AppError(Exception):
    """业务异常基类。所有业务错误必须抛本异常，禁止直接返回裸 JSON。"""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        detail: dict[str, Any] | None = None,
        http_status: int | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.code = ErrorCode(code)
        self.message = message or DEFAULT_MESSAGES[self.code]
        self.detail = detail
        self.http_status = http_status or ERROR_HTTP_STATUS[self.code]
        self.headers = dict(headers or {})
        super().__init__(f"{self.code.value}: {self.message}")

    def to_body(self, trace_id: str) -> dict[str, Any]:
        """构造统一错误响应体 `{code, message, detail, trace_id}`。"""
        return {
            "code": self.code.value,
            "message": self.message,
            "detail": self.detail,
            "trace_id": trace_id,
        }
