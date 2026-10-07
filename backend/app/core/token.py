"""访问令牌的签发与验签（P2-C：``POST /auth/login`` 的产物）。

**为什么放在 `app/core/` 而不是 `app/services/auth/`**：``app/core/auth.py`` 是令牌的
**校验方**，而 ``from app.services.auth.token import ...`` 会先执行
``app/services/auth/__init__.py`` ⇒ 它 import ``local.py`` ⇒ ``local.py`` 反过来
import 尚在半初始化状态的 ``app.core.auth`` ⇒ **循环导入**。令牌是核心原语（与
``auth.py`` 同一层、不依赖任何服务域），放在 ``core`` 下即可让依赖方向单一。

**为什么是 HS256 而不是引第三方库**：``hmac`` + ``hashlib`` 全在标准库里，JWT 的
HS256 就是「base64url(header).base64url(payload) 的 HMAC-SHA256」——为了它引入
``PyJWT`` / ``python-jose`` 属「无消费者的新依赖」（预留纪律第 6 条）。
换 RS256 / Ed25519 属**另一批**的事（那要动密钥分发，不是换个库）。

**刻意不做的三件事**（都不是"以后顺手加"，各自要单独评估）：

1. **不把角色塞进令牌** —— 角色的唯一真源是 ``user_roles`` 表；塞进令牌就会出现
   「库里已撤权、令牌还说有」的窗口，而令牌在有效期内无法撤回。
2. **不做刷新令牌 / 吊销列表** —— 会话管理不在 P2-C 边界内（Non-goal 9）。
3. **不实现登出端点** —— 令牌无状态，登出要么靠前端丢弃、要么靠吊销列表（即第 2 条）。

**不做算法协商**：只认 ``HS256``。``alg: none`` 与算法替换是 JWT 的经典降级攻击，
这里连"读 header 里的 alg 再选实现"这层都没有——直接比对字符串，不是它就不要。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import Settings

#: 令牌里唯一接受的算法（不接受协商，见模块 docstring 最后一段）
_ALGORITHM = "HS256"

#: 签发方标识。验签时**逐字比对**，不是"有就行"
_ISSUER = "graphrag-agent"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """验签通过的令牌内容。

    **不含**角色 —— 见模块 docstring「刻意不做的三件事」第 1 条。
    """

    org_id: UUID
    user_id: UUID
    expires_at: datetime


def _b64url_encode(raw: bytes) -> str:
    """base64url **不带**填充（JWT 的 JWS 紧凑序列化要求去掉 ``=``）。"""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """逆 :func:`_b64url_encode`；补回填充再解。"""
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _signature(signing_input: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return _b64url_encode(digest)


def issue_access_token(
    settings: Settings, *, user_id: UUID, org_id: UUID
) -> tuple[str, datetime]:
    """签发一枚访问令牌，返回 ``(令牌, 过期时刻)``。

    ``iat`` / ``exp`` 一律 UTC 秒级整数（JWT 的惯例；秒级避免各语言解析分歧）。
    """
    issued_at = datetime.now(tz=UTC)
    expires_at = issued_at + timedelta(minutes=settings.auth_jwt_ttl_minutes)

    header = {"alg": _ALGORITHM, "typ": "JWT"}
    payload = {
        "iss": _ISSUER,
        "sub": str(user_id),
        "org": str(org_id),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    signing_input = f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}.{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    return (
        f"{signing_input}.{_signature(signing_input, settings.auth_jwt_secret)}",
        expires_at,
    )


def verify_access_token(raw_token: str, settings: Settings) -> TokenClaims | None:
    """验签一枚令牌；**任何**一步不通过都返回 ``None``（不抛、不区分原因）。

    **为什么失败不细分**：``parse_bearer_token`` 对外的失败语义只有一种（401
    ``Unsupported bearer token``）。把「签名不对」「过期」「结构坏」分成三类，
    等于给攻击者一条探测令牌结构的旁路——与 :func:`app.services.auth.password.
    verify_password` 同一条纪律。
    """
    parts = raw_token.split(".")
    if len(parts) != 3 or not all(parts):
        return None

    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
    except (ValueError, TypeError):
        return None

    if not isinstance(header, dict) or not isinstance(payload, dict):
        return None
    # 算法协商一律拒绝：只认 HS256
    if header.get("alg") != _ALGORITHM:
        return None
    if payload.get("iss") != _ISSUER:
        return None

    expected = _signature(f"{parts[0]}.{parts[1]}", settings.auth_jwt_secret)
    if not hmac.compare_digest(expected, parts[2]):
        return None

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int):
        return None
    now = int(datetime.now(tz=UTC).timestamp())
    if expires_at <= now:
        return None

    try:
        return TokenClaims(
            org_id=UUID(str(payload["org"])),
            user_id=UUID(str(payload["sub"])),
            expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
        )
    except (KeyError, ValueError, TypeError):
        return None


__all__ = ["TokenClaims", "issue_access_token", "verify_access_token"]
