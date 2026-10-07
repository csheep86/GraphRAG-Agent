"""P5-D：私域出向管控（M5 §3 验收 4 / §4.6）的**真行为测试**。

**为什么单开一个文件**：本守卫的失效方向与仓库里其它测试**相反**——
别人怕「被拦」，这里怕「没拦住」。混在其它文件里会互相掩护（一边删断言，另一边照样绿）。

**¥0 / 零出向的机械保证**（判据 5）：「被阻断」的用例全部断言**客户端构造从未发生**
（构造器被打桩成「调用即 AssertionError」）；另外两条断言 `socket.create_connection`
从未被调用——守卫必须在**构造期**就停住，而不是等到请求发出后再判。
"""

from __future__ import annotations

import socket
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import Settings, get_settings
from app.core.egress import (
    PRIVATE_DEPLOY_VIOLATION_ACTION,
    guard_egress,
    is_egress_allowed,
    is_internal_host,
    parse_egress_target,
)
from app.core.errors import AppError, ErrorCode
from app.db.models import AuditLog
from app.db.session import session_scope

_SETTINGS = get_settings()
_DEFAULT_ORG_ID = _SETTINGS.default_org_id

#: 本地 embedding 服务（`scripts/local_embedding_server.py`，端口 8009）——
#: 判据 3「内网双轨不被自己的守卫误杀」的**具体**验金石
_LOCAL_EMBEDDING_URL = "http://127.0.0.1:8009/v1"
_PUBLIC_URL = "https://api.deepseek.com"


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


@pytest.fixture
def switch_on(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """打开私域开关，**空白名单** ⇒ 只有内网 / 回环放行。"""
    monkeypatch.setattr(_SETTINGS, "private_deploy_enabled", True)
    monkeypatch.setattr(_SETTINGS, "allowed_egress_hosts", [])
    return _SETTINGS


def _allowlist(monkeypatch: pytest.MonkeyPatch, hosts: list[str]) -> None:
    """在开关打开的前提下设置白名单（``switch_on`` 已把 boolean 置 true）。"""
    monkeypatch.setattr(_SETTINGS, "allowed_egress_hosts", hosts)


@pytest.fixture(autouse=True)
def clean_violation_rows():
    """每个用例前后清掉本文件产生的 `private_deploy.violation` 行。

    为什么必须清：`GET /audit` 相关的用例会按 org 统计行数，而本文件一行接一行地
    往同一个默认租户里写违反记录 ⇒ 脏数据会以「别处突然多了几行」的形式污染别人。
    """
    _purge()
    yield
    _purge()


def _purge() -> None:
    with session_scope(org_id=_DEFAULT_ORG_ID) as session:
        session.execute(
            delete(AuditLog).where(AuditLog.action == PRIVATE_DEPLOY_VIOLATION_ACTION)
        )
        session.commit()


def _violation_rows(org_id: uuid.UUID | None = None) -> list[AuditLog]:
    with session_scope(org_id=org_id or _DEFAULT_ORG_ID) as session:
        return list(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.action == PRIVATE_DEPLOY_VIOLATION_ACTION
                )
            ).all()
        )


# --------------------------------------------------------------------------- #
# 1. URL 解析：只认解析结果，不认"看起来像"
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("url", "host", "port"),
    [
        ("https://api.deepseek.com", "api.deepseek.com", 443),
        ("http://127.0.0.1:8009/v1", "127.0.0.1", 8009),
        ("http://localhost:8009/v1", "localhost", 8009),
        ("localhost:11434/v1", "localhost", 11434),  # 不带 scheme，Ollama 常见写法
        ("https://10.20.30.40/v1", "10.20.30.40", 443),
    ],
)
def test_parse_egress_target(url: str, host: str, port: int) -> None:
    parsed = parse_egress_target(url)
    assert (parsed.host, parsed.port) == (host, port)


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "api.localhost",
        "127.0.0.1",
        "::1",
        "10.1.2.3",
        "172.16.9.9",
        "192.168.1.9",
        "169.254.1.1",
        "fd00::1",
        "fe80::1",
    ],
)
def test_internal_hosts_are_recognized(host: str) -> None:
    assert is_internal_host(host) is True


@pytest.mark.parametrize(
    "host",
    ["api.deepseek.com", "mineru.net", "example.org", "8.8.8.8", "1.1.1.1"],
)
def test_public_hosts_are_not_internal(host: str) -> None:
    # 公网 IP 字面量（8.8.8.8 / 1.1.1.1）同样不是内网 —— 它们是**公网地址**，
    # 放在这里是为了防止有人把"IP 字面量"直接当成"内网"来判。
    assert is_internal_host(host) is False


def test_empty_host_is_not_internal() -> None:
    assert is_internal_host("") is False


# --------------------------------------------------------------------------- #
# 2. 判定：内网放行 / 公网阻断
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        _LOCAL_EMBEDDING_URL,
        "http://localhost:8009/v1",
        "https://10.0.0.7:8443/v1",
        "http://192.168.5.10:11434/v1",
        "http://[fd00::1]:8080/v1",
    ],
)
def test_internal_endpoints_are_allowed_with_empty_allowlist(
    url: str, switch_on: Settings
) -> None:
    """内网双轨的**核心**判据：只换 base_url ⇒ 不被自己的守卫拦（D9）。"""
    assert is_egress_allowed(url, allowed_hosts=switch_on.allowed_egress_hosts)


def test_local_embedding_endpoint_is_never_blocked(switch_on: Settings) -> None:
    """本地 embedding 服务（8009）必须始终可达——它正是判据 3 点名的那个地址。"""
    guard_egress(_LOCAL_EMBEDDING_URL, target="eval.embedding.base_url")


def test_public_endpoint_is_blocked(switch_on: Settings) -> None:
    assert (
        is_egress_allowed(_PUBLIC_URL, allowed_hosts=switch_on.allowed_egress_hosts)
        is False
    )


def test_switch_off_lets_everything_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-goal 9：开关关闭 ⇒ **一切照旧**（含公网地址），既有行为一个字节都不变。"""
    monkeypatch.setattr(_SETTINGS, "private_deploy_enabled", False)
    monkeypatch.setattr(_SETTINGS, "allowed_egress_hosts", [])
    guard_egress(_PUBLIC_URL, target="llm.base_url")
    guard_egress("https://mineru.net", target="mineru.api_base")


@pytest.mark.parametrize("url", ["", "   ", "http://", "not a url at all"])
def test_unparseable_target_is_blocked_fail_closed(
    url: str, switch_on: Settings
) -> None:
    """解析不出 host ⇒ **阻断**：「不知道去哪」不是「可以去」。"""
    assert is_egress_allowed(url, allowed_hosts=[]) is False


# --------------------------------------------------------------------------- #
# 3. 白名单语义（决策 D8：精确 host；写了端口 ⇒ 端口必须匹配；不支持通配）
# --------------------------------------------------------------------------- #


def test_allowlist_exact_host_passes(
    monkeypatch: pytest.MonkeyPatch, switch_on: Settings
) -> None:
    _allowlist(monkeypatch, ["mineru.example.com"])
    assert is_egress_allowed(
        "https://mineru.example.com/api/v4",
        allowed_hosts=switch_on.allowed_egress_hosts,
    )


def test_allowlist_port_must_match(
    monkeypatch: pytest.MonkeyPatch, switch_on: Settings
) -> None:
    """写了端口 ⇒ 端口不符即阻断（**不**静默忽略端口那一部分）。"""
    _allowlist(monkeypatch, ["mineru.example.com:443"])
    assert is_egress_allowed(
        "https://mineru.example.com", allowed_hosts=switch_on.allowed_egress_hosts
    )
    assert (
        is_egress_allowed(
            "https://mineru.example.com:8443",
            allowed_hosts=switch_on.allowed_egress_hosts,
        )
        is False
    )


def test_allowlist_port_without_scheme_defaults_to_scheme_port(
    monkeypatch: pytest.MonkeyPatch, switch_on: Settings
) -> None:
    """`https://host`（未写端口）按 443 判 ⇒ 白名单 `host:443` 能匹配上。"""
    _allowlist(monkeypatch, ["vllm.example.com:8000"])
    assert is_egress_allowed(
        "http://vllm.example.com:8000/v1",
        allowed_hosts=switch_on.allowed_egress_hosts,
    )
    assert (
        is_egress_allowed(
            "https://vllm.example.com/v1",
            allowed_hosts=switch_on.allowed_egress_hosts,
        )
        is False
    )


def test_wildcard_is_not_supported(
    monkeypatch: pytest.MonkeyPatch, switch_on: Settings
) -> None:
    """本批**不支持**通配 / 子域（D8）——写 `*.example.com` 不会放行 `a.example.com`。"""
    _allowlist(monkeypatch, ["*.example.com"])
    assert (
        is_egress_allowed(
            "https://a.example.com/v1", allowed_hosts=switch_on.allowed_egress_hosts
        )
        is False
    )


def test_allowlist_entry_with_empty_entries_is_normalized() -> None:
    """清单型配置被解析成 `['']` 会让「空白名单」变成「放行一切」（本批陷阱之一）。"""
    assert Settings(allowed_egress_hosts="").allowed_egress_hosts == []
    assert Settings(allowed_egress_hosts=" , ,").allowed_egress_hosts == []
    assert Settings(
        allowed_egress_hosts=" A.COM , b.internal:8000 "
    ).allowed_egress_hosts == [
        "a.com",
        "b.internal:8000",
    ]


def test_settings_switch_values_are_readable() -> None:
    """`extra='ignore'` ⇒ 环境变量名拼错会被**静默忽略**；故断言**读到的值**而非"设了"。"""
    assert isinstance(
        Settings(private_deploy_enabled=False).private_deploy_enabled, bool
    )
    assert Settings(private_deploy_enabled=True).private_deploy_enabled is True
    assert Settings(allowed_egress_hosts='["x.example.com"]').allowed_egress_hosts == [
        "x.example.com"
    ]


# --------------------------------------------------------------------------- #
# 4. 构造期阻断：**零出向**（判据 5）
# --------------------------------------------------------------------------- #


@pytest.fixture
def forbid_real_outbound(monkeypatch: pytest.MonkeyPatch):
    """任何真实出向都判失败——守卫若退化成"发出去再判"，这条会先炸。"""
    original = socket.create_connection

    def _blocked(*args: object, **kwargs: object):
        raise AssertionError(
            "出现了真实出向连接：守卫必须在构造期阻断，而不是发出去之后再判"
        )

    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    return original


def test_build_chat_model_blocked_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    switch_on: Settings,
    forbid_real_outbound: object,
) -> None:
    """**零出向**的机械证明：被打桩的构造器一次都没被调用。

    ``llm.py`` 在函数内 ``from langchain_openai import ChatOpenAI`` ⇒ 每次调用都从
    模块取属性 ⇒ 这里的 setattr 会生效（这也是"构造期"落点能被单测的依据）。
    """
    import langchain_openai

    calls: list[object] = []

    def _forbidden(**kwargs: object) -> None:
        calls.append(kwargs)
        raise AssertionError("不得构造 LLM 客户端：被阻断的路径在构造之前就该停住")

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _forbidden)

    with pytest.raises(AppError) as captured:
        from app.services.providers.llm import build_chat_model

        build_chat_model()

    error = captured.value
    assert error.code == ErrorCode.PRIVATE_DEPLOY_BLOCKED
    assert error.http_status == 503
    assert error.detail is not None
    assert error.detail["target"] == "llm.base_url"
    assert error.detail["host"] == "api.deepseek.com"
    assert calls == []


def test_build_chat_model_uses_internal_base_url_without_blocking(
    monkeypatch: pytest.MonkeyPatch, switch_on: Settings
) -> None:
    """内网双轨：只把 `LLM_BASE_URL` 换成本地 vLLM ⇒ **必须**能构造成功。"""
    import langchain_openai

    seen: list[dict[str, object]] = []
    monkeypatch.setattr(
        langchain_openai, "ChatOpenAI", lambda **kwargs: seen.append(kwargs) or object()
    )
    monkeypatch.setattr(_SETTINGS, "llm_base_url", "http://127.0.0.1:8000/v1")

    from app.services.providers.llm import build_chat_model

    build_chat_model()
    assert len(seen) == 1
    assert seen[0]["base_url"] == "http://127.0.0.1:8000/v1"


def test_embedding_builder_passes_local_service(
    monkeypatch: pytest.MonkeyPatch, switch_on: Settings
) -> None:
    """本地 embedding 服务（8009）走 build_default_embedder ⇒ 守卫**放行**。"""
    monkeypatch.setattr(_SETTINGS, "eval_embedding_model", "bge-small-zh-v1.5")
    monkeypatch.setattr(_SETTINGS, "eval_embedding_api_key", "local")
    monkeypatch.setattr(_SETTINGS, "eval_embedding_base_url", _LOCAL_EMBEDDING_URL)

    from app.evaluation.baseline import build_default_embedder

    embedder = build_default_embedder()
    # 放行证据 = 构造成功且 base_url 原样透传（守卫没有改写也没有拦）
    assert embedder._base_url == _LOCAL_EMBEDDING_URL  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# 5. 审计留痕（M5 §3 验收 4 的另一半）
# --------------------------------------------------------------------------- #


def test_violation_writes_audit_row(switch_on: Settings) -> None:
    """被阻断时必须落一行 `private_deploy.violation`（status=failure、带 trace_id）。"""
    with pytest.raises(AppError):
        guard_egress(_PUBLIC_URL, target="llm.base_url")

    rows = _violation_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "failure"
    assert row.trace_id is not None
    assert row.detail is not None
    assert row.detail["target"] == "llm.base_url"
    assert row.detail["host"] == "api.deepseek.com"
    # 无租户上下文 ⇒ 回落默认租户并在 detail 里标 system（偏离 X-3）
    assert row.detail["scope"] == "system"
    assert row.org_id == _DEFAULT_ORG_ID


def test_violation_with_org_and_session_is_scoped_to_tenant(
    switch_on: Settings,
) -> None:
    """任务侧（如 MinerU）**有** org ⇒ 审计行归属明确，不落到 'system'。"""
    with session_scope(org_id=_DEFAULT_ORG_ID) as session:
        with pytest.raises(AppError):
            guard_egress(
                "https://mineru.net",
                target="mineru.api_base",
                org_id=_DEFAULT_ORG_ID,
                session=session,
            )
        session.commit()  # 给了 session ⇒ 由调用方决定是否提交（守卫不代劳）

    rows = _violation_rows()
    assert len(rows) == 1
    assert rows[0].detail is not None
    assert rows[0].detail["scope"] == "tenant"
    assert rows[0].detail["target"] == "mineru.api_base"


def test_audit_write_failure_does_not_mask_the_block(
    monkeypatch: pytest.MonkeyPatch, switch_on: Settings
) -> None:
    """库不可达时**仍然要阻断**——审计缺陷不得把主行为顶掉（更不能变成 500）。"""
    import app.services.audit as audit_module

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("db is down")

    monkeypatch.setattr(audit_module, "record_audit_entry", _boom)

    with pytest.raises(AppError) as captured:
        guard_egress(_PUBLIC_URL, target="llm.base_url")
    assert captured.value.code == ErrorCode.PRIVATE_DEPLOY_BLOCKED


def test_endpoint_returns_503_private_deploy_blocked(
    client: TestClient, dev_headers: dict[str, str], switch_on: Settings
) -> None:
    """端到端（判据 2）：真端点 ⇒ HTTP **503** + `PRIVATE_DEPLOY_BLOCKED`，body 四件套齐全。

    为什么挑 `POST /ontology/cold-start`：它是**唯一**无需任何前置数据就会走到
    `build_chat_model()` 的端点（P5-C 已实现）⇒ 守卫在构造点抛错时，端点内部
    **一个字节都没往 LLM 送**。
    """
    response = client.post(
        "/api/v1/ontology/cold-start",
        json={"domain_description": "考勤合规域"},
        headers=dev_headers,
    )
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == ErrorCode.PRIVATE_DEPLOY_BLOCKED.value
    assert body["detail"]["target"] == "llm.base_url"
    assert body["trace_id"]
