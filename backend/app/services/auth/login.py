"""口令登录（P2-C）—— `POST /api/v1/auth/login` 的服务层。

**本模块是全仓唯一允许回填 `users.activated_at` 的地方。**

席位口径 = ``activated_at IS NOT NULL AND disabled_at IS NULL``
（ADR-0006 §2.4 维度 2），而 ``activated_at`` 的语义就是「**首次成功登录**」。
⇒ 回填点多一个（目录同步 / 导入 / 手工补数），席位数就多一份不是真登录换来的
水分；P4-D5 对此的裁决是明令级别的：**不回填 `activated_at` 造假席位**。

**三条刻意的"不做"**：

1. **失败不回填** —— 口令错 / 账号停用都不算"登录成功"；
2. **停用账号在回填之前就拒** —— 否则一次成功的口令校验会把停用账号重新变成
   "已激活"，席位数凭空回涨（见 :func:`authenticate_password` 的判定顺序）；
3. **不写审计** —— 登录**失败**时拿不到 org（用户名都不存在），而审计行的
   ``org_id`` 是隔离键、不可填空（``middleware.py`` 对匿名请求的处理同此口径）。
   只给成功的一半写、失败的一半不写，比都不写更容易被读成"全都有痕"，
   故**整体不做**并登记为缺口（`changes/P2-C/integration-log.md`）。

**身份来源仍然是接缝 1**：本模块只回答「这个用户名 + 口令对不对」，不造第二个
``AuthProvider``（ADR-0004 §2.1 接缝 1 的实现集合恒为 1）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy import select, update

from app.db.models import USER_STATUS_ACTIVE, User
from app.db.rls import find_login_user
from app.db.session import session_scope, system_session
from app.services.auth.password import verify_password

#: 登录失败原因（**只**进日志与 `detail.reason`，不区分对外错误码——见模块 docstring）
REASON_BAD_CREDENTIALS = "invalid_credentials"
REASON_DISABLED = "account_disabled"

#: `users.status` 的"可用"取值（唯一定义处见 `app.db.models.USER_STATUS_ACTIVE`）
ACTIVE_STATUS = USER_STATUS_ACTIVE


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    """一次登录尝试的结果。

    ``ok=False`` 时 ``user_id`` / ``org_id`` 一律为 ``None``——**不**向调用方透露
    "用户名存在但口令错"与"用户根本不存在"的差别（账号枚举）。
    """

    ok: bool
    reason: str = ""
    user_id: UUID | None = None
    org_id: UUID | None = None
    #: 本次是否**首次**成功登录（即本次回填了 ``activated_at``）
    first_login: bool = False


def authenticate_password(*, username: str, password: str) -> LoginOutcome:
    """校验用户名 + 口令；成功则（必要时）回填 ``activated_at``。

    判定顺序是刻意的：**凭据 → 状态 → 回填**。先判凭据是为了让停用账号与不存在
    的账号在**耗时**上不可区分（否则成了一个账号枚举旁路）；先判状态再回填，
    是为了不让一次口令校验把停用账号重新变回"已激活"。

    **查用户走受控旁路**：登录时尚无认证态 ⇒ 无 org ⇒ RLS 下一行都查不到，
    故走 ``app.find_login_user``（``app/db/rls.py``，与 A7 同形态）。
    """
    with system_session() as lookup:
        record = find_login_user(lookup, username=username)

    if record is None or not verify_password(password, str(record["password_hash"])):
        return LoginOutcome(ok=False, reason=REASON_BAD_CREDENTIALS)

    user_id = UUID(str(record["id"]))
    org_id = UUID(str(record["org_id"]))

    if str(record["status"]) != ACTIVE_STATUS:
        return LoginOutcome(ok=False, reason=REASON_DISABLED)

    first_login = record["activated_at"] is None
    if first_login:
        backfill_activated_at(org_id=org_id, user_id=user_id)

    return LoginOutcome(
        ok=True,
        user_id=user_id,
        org_id=org_id,
        first_login=first_login,
    )


def backfill_activated_at(*, org_id: UUID, user_id: UUID) -> bool:
    """回填 `users.activated_at`（**席位计数的唯一来源**）。

    ``WHERE activated_at IS NULL`` 是**并发**下的幂等护栏：两个请求同时首次登录时，
    后到的那条 UPDATE 命中 0 行，不会把"首次登录时间"改写成第二次的时间。

    必须以 ``org_id`` 绑会话：``users`` 是租户表，RLS 的 ``WITH CHECK`` 要求写操作
    带上租户，不绑就会静默写 0 行。

    Returns:
        是否真的回填了（``False`` = 已被并发的那一方回填过）。
    """
    activated_at = datetime.now(tz=UTC)
    with session_scope(org_id=org_id) as session:
        result = session.execute(
            update(User)
            .where(User.id == user_id)
            .where(User.activated_at.is_(None))
            .values(activated_at=activated_at)
        )
        session.commit()
    backfilled = bool(result.rowcount)
    if backfilled:
        # 只记 ids 与时间，**绝不**记口令 / 哈希 / 令牌
        logger.bind(user_id=str(user_id), org_id=str(org_id)).info(
            "user_activated_by_first_login"
        )
    return backfilled


def load_activated_at(*, org_id: UUID, user_id: UUID) -> datetime | None:
    """读回该用户的 ``activated_at``（**仅**给判据 / 测试用，不是业务路径）。

    放在这里而不是让测试自己拼 SQL，是为了让"席位口径的读法"也只有一份。
    """
    with session_scope(org_id=org_id) as session:
        return session.scalar(select(User.activated_at).where(User.id == user_id))


__all__ = [
    "ACTIVE_STATUS",
    "REASON_BAD_CREDENTIALS",
    "REASON_DISABLED",
    "LoginOutcome",
    "authenticate_password",
    "backfill_activated_at",
    "load_activated_at",
]
