"""`POST /api/v1/auth/login` —— 真实登录（P2-C）。

**它补的是 P4 留下的那个缺口**：席位按 `activated_at IS NOT NULL AND disabled_at IS NULL`
计数（ADR-0006 §2.4），而 `activated_at` 由**首次成功登录**回填 ⇒ 没有本端点，
席位数恒为 0，`max_seats` 判据永远触发不了。

**它不要求认证态，这是唯一的例外，理由写进契约排除集**：

`tests/test_openapi_contract.py::TENANT_PROTECTED_PATHS` 把本路径排除在
「必须声明 `bearerAuth` + 租户头」之外——登录是**认证态的签发入口**，请求时还没有
认证态，要求它自带 `bearerAuth` 是循环要求。**失效条件**：本端点的响应体一旦
开始返回租户业务数据（文档 / 图谱 / 审计等），必须立即把它移回受保护集。

**它不做 SSO**（D5）：本端点校验的是**本库 `users` 表里的口令**。接企业身份源
（AD / LDAP / OIDC）是接缝 1 第二个实现的事，属 D1 顺延范围。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import TraceId
from app.api.v1.responses import UNAUTHORIZED, VALIDATION_ERROR
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.token import issue_access_token
from app.schemas.auth import LoginRequest, LoginResponse
from app.services.auth.login import authenticate_password

router = APIRouter(tags=["auth"])


@router.post(
    "/auth/login",
    response_model=LoginResponse,
    operation_id="loginWithPassword",
    summary="口令登录并签发访问令牌",
    description=(
        "校验 `username` + `password`（对 `users` 表里的**口令哈希**，不是任何 mock），"
        "通过后签发一枚 JWT（`HS256`），前端以 `Authorization: Bearer <token>` 携带。\n\n"
        "**租户从账号推导，不由请求声明**：`org_id` 取自 `users.org_id`，"
        "请求体里**没有**也不接受 `org_id`（ADR-0003 §3.3：org_id 严禁来自 body / query）。\n\n"
        "**首次成功登录会回填 `users.activated_at`** —— 那是席位计数"
        "（`activated_at IS NOT NULL AND disabled_at IS NULL`，ADR-0006 §2.4 维度 2）"
        "的**唯一**来源。口令错、账号停用**都不**回填。\n\n"
        "**失败一律 401 且不区分原因**：`detail.reason` 会给出 `invalid_credentials` / "
        "`account_disabled`（供日志侧区分），但**消息与耗时不区分** —— 否则等于给出一条"
        "账号枚举旁路（能探出「这个用户名存在」）。\n\n"
        "**限流**：沿用全局 60/min（每 IP 每接口）。"
    ),
    responses={**UNAUTHORIZED, **VALIDATION_ERROR},
)
async def login_with_password(
    payload: LoginRequest, trace_id: TraceId
) -> LoginResponse:
    """登录。**不**记录请求体（含明文口令）到任何日志。"""
    outcome = authenticate_password(
        username=payload.username, password=payload.password
    )
    if not outcome.ok or outcome.user_id is None or outcome.org_id is None:
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "用户名或口令不正确",
            # reason 给日志 / 排障用；对外消息只有上面那一句（防账号枚举）
            detail={"reason": outcome.reason},
        )

    token, expires_at = issue_access_token(
        get_settings(), user_id=outcome.user_id, org_id=outcome.org_id
    )
    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user_id=outcome.user_id,
        org_id=outcome.org_id,
        trace_id=trace_id,
    )
