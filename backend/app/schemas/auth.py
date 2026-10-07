"""登录契约模型（P2-C：`POST /api/v1/auth/login`）。

**契约纯净纪律（本文件最重要的一条）**：

- ``users.password_hash`` **绝不**出现在任何 Schema 里（M5 §3 验收 3 / §4.5）；
- ``users.activated_at`` / ``disabled_at`` **不进契约** —— ADR-0006:123 明写
  「MVP 内该字段只有 License 一处消费者」，前端拿到它没有任何合法用途；
- ``issuer`` / ``subject`` 是**预留字段**，同样不进契约（CODEBUDDY「功能预留原则」第 4 条）。

**为什么请求体没有 `org_id`**：ADR-0003 §3.3 禁止 org 来自 body / query。
登录时租户是**从账号推导**出来的（`users.org_id`），不是由调用方声明的——
否则任何人都能声明自己属于任意租户。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

#: 令牌类型。固定值（不是枚举）：Bearer 是 RFC 6750 的唯一形态，
#: 留成可协商的字段只会让人以为还有别的选择。
TOKEN_TYPE_BEARER = "Bearer"


class LoginRequest(BaseModel):
    """登录请求。

    **只有两个字段是刻意的**：不加 `org_id`（见模块 docstring）、不加 `captcha`
    / `client_id` / `grant_type`（OAuth 形态的登录不在 P2-C 边界内）。
    """

    username: str = Field(
        min_length=1,
        max_length=255,
        description="登录名（对应 `users.username`，全库唯一）",
    )
    password: str = Field(
        min_length=1,
        max_length=255,
        description="明文口令。仅存在于本请求体中，服务端只与哈希比对、不落日志",
    )


class LoginResponse(BaseModel):
    """登录成功响应。

    **不含角色**：角色的唯一真源是 `user_roles` 表，塞进响应/令牌都会产生
    「库里已撤权、手里还写着有」的窗口（见 `app/core/token.py` 模块 docstring）。

    ``org_id`` 只是**回显**当前账号归属的租户，供前端展示用；它不是授权声明——
    后续每个请求的租户仍由令牌解析得出（ADR-0003 §3.3）。
    """

    access_token: str = Field(
        description="JWT 访问令牌（`Authorization: Bearer <token>` 携带）"
    )
    token_type: str = Field(
        default=TOKEN_TYPE_BEARER, description="令牌类型，恒为 `Bearer`"
    )
    expires_at: datetime = Field(description="令牌过期时刻（UTC）")
    user_id: UUID = Field(description="登录主体的 `users.id`")
    org_id: UUID = Field(description="该主体所属租户（`users.org_id`，**只读回显**）")
    trace_id: str = Field(description="链路追踪 id")
