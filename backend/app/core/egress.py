"""私域出向管控（M5 §3 验收 4 / §4.6；spec 名 ``private_deploy``）。

**为什么必须构造期阻断**（不能"发出去再判"）：一旦请求已经发出，数据就出网了——
那时无论返回什么错误码，"私域"都已经不成立。故守卫挂在**客户端构造函数之前**：
被阻断时**出向调用数为 0**（由 ``tests/test_private_deploy_egress.py`` 用 monkeypatch
断言客户端构造从未发生——这是本批 ¥0 的机械保证，也是 §3 验收 4 唯一站得住的形态）。

**两条判定口径**（spec 只给了字段名，语义由本模块定义并登记）：

1. **内网 / 回环天然放行**（决策 **D9**）：spec §3 验收 4 的定语是「**外部网络**
   出向调用」，而 plan §18.4 的内网双轨要求「本地 vLLM / Ollama 只需改 base_url」
   ⇒ 内网端点**不能**被自己的守卫拦。判定只看 IPv4 / IPv6 **字面量**
   （回环 / RFC1918 / ULA / link-local / 保留）+ ``localhost``，**不做 DNS 解析**
   ——解析要联网，会把"零联网"这条判据自己破坏掉，且解析结果可被污染。
2. **白名单精确匹配**（决策 **D8**）：条目形如 ``host`` 或 ``host:port``；
   写了端口 ⇒ **端口必须也匹配**（**不**静默忽略端口那一部分——配了却只按 host 判，
   等于告诉用户"你可以限制端口"而实际没限）。
   **不支持通配 / 子域**（``*.a.com`` 不匹配 ``b.a.com``）：外推通配属新增需求。

**开关关闭 ⇒ 一切照旧**：``PRIVATE_DEPLOY_ENABLED=false`` 时本模块**直接返回**，
不改变任何既有行为（既有端点在关闭时的行为不受影响）。
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit
from uuid import UUID

from loguru import logger

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.middleware import get_trace_id_value, new_trace_id

if TYPE_CHECKING:  # 只出现在签名里，运行时无须 import SQLAlchemy
    from sqlalchemy.orm import Session

#: ⚠️ ``app.services.audit`` / ``app.db.session`` 只在**函数内**导入，不放在模块头：
#: ``app.db.session`` 在导入时就会 ``create_engine()``（模块级副作用），把 ``app.core``
#: 和它绑死 ⇒ 任何只想 import 一个 core 工具的地方都会连带建引擎（测试里表现为
#: 难以归因的数据库连接泄漏）。

#: 审计 action（M5 §3 验收 4 原文要求的事件名）
PRIVATE_DEPLOY_VIOLATION_ACTION = "private_deploy.violation"

#: 未显式给端口时按 scheme 推断——否则「白名单写了 443、URL 没写端口」会**匹配不上**，
#: 而用户的直觉是 https 就是 443（不推断 ⇒ 白名单条目形同虚设，属误导）。
_SCHEME_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}

_LOCALHOST = "localhost"


@dataclass(frozen=True)
class EgressTarget:
    """解析后的出向目标。**只看 URL 本身**，不发任何请求、不做 DNS 解析。"""

    host: str  #: 小写、去掉结尾点的主机名；解析不出即为空串（⇒ 不可判定 ⇒ 阻断）
    port: int | None
    scheme: str


def parse_egress_target(url: str) -> EgressTarget:
    """把出向地址解析成 :class:`EgressTarget`。

    允许不带 scheme（``localhost:8009/v1``）——``urlsplit`` 没见到 ``//`` 会把
    ``localhost`` 当成 scheme ⇒ 调用方补 ``//`` 再解析，避免把主机名读丢。
    """
    candidate = url if "//" in url else f"//{url}"
    parts = urlsplit(candidate)
    try:
        explicit_port = parts.port
    except ValueError:  # 端口越界等非法形态 ⇒ 视同未指定（下面按 scheme 兜）
        explicit_port = None
    port = explicit_port or _SCHEME_DEFAULT_PORTS.get(parts.scheme.lower())
    return EgressTarget(
        host=(parts.hostname or "").strip().lower().rstrip("."),
        port=port,
        scheme=parts.scheme.lower(),
    )


def is_internal_host(host: str) -> bool:
    """该 host 是否属于**内网 / 回环**（ ⇒ 天然放行，无需进白名单）。

    域名（非 IP 字面量）一律返回 ``False``：确认它指向内网**必须**做 DNS 解析，
    而那要联网——既破坏"零联网"判据，又引入"解析结果随环境漂移"的不确定性。
    """
    if not host:
        return False
    if host == _LOCALHOST or host.endswith(f".{_LOCALHOST}"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_unspecified
        or address.is_reserved
    )


def split_allowlist_entry(entry: str) -> tuple[str, int | None]:
    """白名单条目 → ``(host, port)``；``port`` 为 ``None`` = 不限制端口。"""
    text = entry.strip().lower()
    if not text:
        return "", None
    if text.startswith("["):  # [::1]:8000 —— IPv6 的方括号形态
        closing = text.find("]")
        if closing != -1:
            remainder = text[closing + 1 :]
            if remainder.startswith(":") and remainder[1:].isdigit():
                return text[1:closing], int(remainder[1:])
            return text[1:closing], None
    # 只有一个冒号才可能是端口；IPv6 字面量有多个冒号 ⇒ 整体是 host
    if text.count(":") == 1:
        candidate, _, raw_port = text.partition(":")
        if raw_port.isdigit():
            return candidate.rstrip("."), int(raw_port)
    return text.rstrip("."), None


def _matches_allowlist(target: EgressTarget, allowed_hosts: Iterable[str]) -> bool:
    for entry in allowed_hosts:
        allowed_host, allowed_port = split_allowlist_entry(entry)
        if not allowed_host or allowed_host != target.host:
            continue
        if allowed_port is not None and allowed_port != target.port:
            continue
        return True
    return False


def is_egress_allowed(url: str, *, allowed_hosts: Iterable[str]) -> bool:
    """出向是否被允许（**纯函数**：不读 settings、不写库、不联网，便于单测）。

    **host 解析不出 ⇒ 阻断**（fail-closed）：无法判定的目标不允许出网——
    「不知道去哪」不等于「可以去」。
    """
    target = parse_egress_target(url)
    if not target.host:
        return False
    if is_internal_host(target.host):
        return True
    return _matches_allowlist(target, allowed_hosts)


def guard_egress(
    url: str,
    *,
    target: str,
    org_id: UUID | None = None,
    session: Session | None = None,
) -> None:
    """构造期出向守卫：允许 ⇒ 静默返回；违规 ⇒ **先写审计**、再抛 ``AppError``。

    :param target: 出向面的**配置出处**（如 ``llm.base_url`` / ``mineru.api_base``
        / ``eval.embedding.base_url``），进日志与审计 ``detail``，便于定位是谁要出网。
    :param org_id: 审计行归属租户。**无法确定时留 None** ⇒ 回落
        ``settings.default_org_id``（偏离 **X-3**，理由见 changes/P5-D integration-log）。
    :param session: 外部会话。**给了就不自行 commit**（调用方正处在自己的事务里）；
        没给 ⇒ 自开短会话写入并显式提交——没有事务可依附时不提交等于写了个寂寞。
    """
    settings = get_settings()
    if not settings.private_deploy_enabled:
        return  # 开关关闭 ⇒ 一切照旧（Non-goal 9）

    if is_egress_allowed(url, allowed_hosts=settings.allowed_egress_hosts):
        return

    parsed = parse_egress_target(url)
    detail: dict[str, Any] = {
        "target": target,
        "host": parsed.host,
        "port": parsed.port,
        "scheme": parsed.scheme,
        "allowed_egress_hosts": list(settings.allowed_egress_hosts),
        # 结构化字段，不写 URL 原文（可能仍带路径 / query，属决策 A5 同口径）
        "reason": "not_internal_and_not_in_allowlist",
        "scope": "tenant" if org_id is not None else "system",
    }
    _record_violation(target=target, detail=detail, org_id=org_id, session=session)
    raise AppError(
        ErrorCode.PRIVATE_DEPLOY_BLOCKED,
        detail=detail,
    )


def _record_violation(
    *,
    target: str,
    detail: dict[str, Any],
    org_id: UUID | None,
    session: Session | None,
) -> None:
    """写一行 ``private_deploy.violation``。**写失败只记日志、不抛**（审计纪律）。

    为什么必须包在 try 里：本函数是抛 ``AppError`` **之前**的最后一步，
    审计缺陷（库不可达 / 列超长）绝不能把「阻断」这一主行为顶掉，
    更不能退化成一个看不懂的 500。
    """
    from app.services.audit import record_audit_entry

    trace_id = get_trace_id_value() or new_trace_id()
    logger.bind(
        trace_id=trace_id, target=target, host=detail["host"], port=detail["port"]
    ).warning("private_deploy_violation")

    settings = get_settings()
    write_org = org_id if org_id is not None else settings.default_org_id
    payload = {
        "org_id": write_org,
        "action": PRIVATE_DEPLOY_VIOLATION_ACTION,
        "resource": f"egress:{target}"[:255],
        "status": "failure",
        "trace_id": UUID(str(trace_id)),
        "detail": detail,
    }
    try:
        if session is not None:
            _ = record_audit_entry(session, **payload)
            return
        from app.db.session import session_scope

        with session_scope(org_id=write_org) as owned:
            record_audit_entry(owned, **payload)
            owned.commit()
    except Exception as exc:  # noqa: BLE001 - 审计写失败绝不上抛
        logger.bind(target=target, reason=str(exc)).warning(
            "private_deploy_violation_audit_failed"
        )


__all__ = [
    "PRIVATE_DEPLOY_VIOLATION_ACTION",
    "EgressTarget",
    "guard_egress",
    "is_egress_allowed",
    "is_internal_host",
    "parse_egress_target",
    "split_allowlist_entry",
]
