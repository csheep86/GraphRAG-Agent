"""阶段十一 11.2：认证态解析单元测试。

覆盖 :mod:`app.core.auth` 的两个核心函数 + :mod:`app.api.deps.get_current_identity` 的优先级：

1. ``parse_bearer_token`` 开发态格式（合法）；
2. ``parse_bearer_token`` 非法格式 → ``UNAUTHORIZED``（参数化 3 种：非 dev 前缀 / 段数错 / UUID 错）；
3. ``parse_bearer_token`` 在生产环境拒绝 dev token（即使格式正确）；
4. ``identity_from_dev_headers`` 在生产环境禁用；
5. ``identity_from_dev_headers`` 在开发环境启用；
6. ``get_current_identity`` 优先级：Bearer 覆盖 dev_headers。

**隔离策略**：

- 全部为纯函数 / 纯依赖测试，**不**经过 TestClient / HTTP / 数据库 / 真实认证服务；
- ``parse_bearer_token`` / ``identity_from_dev_headers`` 是纯函数，直接传参调用；
- ``get_current_identity`` 直调（``asyncio.run``），构造 ``HTTPAuthorizationCredentials`` 入参，
  跳过 FastAPI 依赖注入框架；
- 环境切换用 ``monkeypatch.setattr`` 改 ``settings.app_env``，pytest 的 monkeypatch 自动
  记录原值、teardown 时自动回滚，无需 ``try/finally``；
- 与 ``test_error_contract.py::test_missing_authentication_returns_401`` 不冲突：
  那个测错误体形状（集成级），本批测函数行为（单元级）。

**设计意图文档化（B5）**：

``parse_bearer_token`` 优先检查 ``is_production``，再检查格式——防止生产环境泄露 token
格式细节（攻击者拿到 401 message 可推断格式期望，进而构造探测请求）。
该优先级由 ``test_parse_bearer_token_dev_format_in_production_rejected`` 锁定。

**已知约束（不修）**：

- ``Identity.roles`` 字段在 Sprint 1 始终为 ``()``（M5 登录后才填充）；
- ``parse_bearer_token`` 仅识别 ``dev.*`` 前缀；JWT 解析留待 Sprint 3 M5 接入；
- ``identity_from_dev_headers`` 的 only-org / only-actor fallback（走 default_actor_id /
  default_org_id）已在 10.1.1 联调实测，本批不重复覆盖。
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import get_current_identity
from app.core.auth import Identity, identity_from_dev_headers, parse_bearer_token
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode

# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


@pytest.fixture
def production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """临时把 ``settings.app_env`` 设为 ``"production"``；``monkeypatch`` 自动恢复原值。

    **不使用** ``try/finally``：pytest 的 ``monkeypatch`` 在用例 teardown 时会自动
    回滚所有 ``setattr`` / ``setenv`` / ``delattr`` 操作，无需手动管理。

    让 ``Settings.is_production`` 在用例期间返回 True，从而触发 ``parse_bearer_token``
    与 ``identity_from_dev_headers`` 的「生产环境禁用」分支。

    安全性：
    - ``is_production`` 是 ``@property``，每次访问重算 ``self.app_env == "production"``，
      属性注入后立即生效；
    - Pydantic ``BaseSettings.validate_assignment`` 默认 False，attribute 赋值不做类型校验；
    - ``_guard_production_sqlite`` 是 ``@model_validator(mode="after")``，仅在构造时跑，
      属性注入不再触发；
    - ``BaseSettings.model_config.extra="ignore"``，无 unknown field 干扰。
    """
    monkeypatch.setattr(get_settings(), "app_env", "production")


# --------------------------------------------------------------------------- #
# 1. parse_bearer_token dev format（合法）
# --------------------------------------------------------------------------- #


def test_parse_bearer_token_dev_format_returns_identity() -> None:
    """``dev.<org_id>.<actor_id>`` → ``Identity``，``source="bearer_token"``，roles 空。"""
    settings = get_settings()
    token = f"dev.{settings.default_org_id}.{settings.default_actor_id}"

    identity = parse_bearer_token(token, settings)

    assert isinstance(identity, Identity)
    assert identity.org_id == settings.default_org_id
    assert identity.actor_id == settings.default_actor_id
    assert identity.source == "bearer_token"
    assert identity.roles == ()


# --------------------------------------------------------------------------- #
# 2. parse_bearer_token 非法格式 → UNAUTHORIZED（参数化 3 子类）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("token", "expected_message"),
    [
        # 非 dev 前缀：落到最末 fallback
        ("jwt.something.invalid", "Unsupported bearer token"),
        # dev 前缀但段数错（只 2 段）
        ("dev.abcdef", "Malformed development token"),
        # dev 前缀但 UUID 非法
        ("dev.not-a-uuid.not-a-uuid", "Development token carries malformed UUIDs"),
    ],
)
def test_parse_bearer_token_invalid_format_raises_unauthorized(
    token: str, expected_message: str
) -> None:
    """非合法格式一律 ``UNAUTHORIZED``，且 3 种异常路径必须命中不同 message。"""
    settings = get_settings()

    with pytest.raises(AppError) as exc_info:
        parse_bearer_token(token, settings)

    assert exc_info.value.code == ErrorCode.UNAUTHORIZED.value
    assert exc_info.value.message == expected_message


# --------------------------------------------------------------------------- #
# 3. parse_bearer_token 在生产环境拒绝 dev token（B5 锁定）
# --------------------------------------------------------------------------- #


def test_parse_bearer_token_dev_format_in_production_rejected(
    production_env: None,
) -> None:
    """B5：生产环境一律拒绝 dev token（即使格式正确）。

    锁定 ``parse_bearer_token`` 中「``is_production`` 检查在前、format 检查在后」的语义——
    防止生产环境泄露 token 格式细节（攻击者拿到 401 message 可推断格式期望）。
    """
    settings = get_settings()
    token = f"dev.{settings.default_org_id}.{settings.default_actor_id}"

    with pytest.raises(AppError) as exc_info:
        parse_bearer_token(token, settings)

    assert exc_info.value.code == ErrorCode.UNAUTHORIZED.value
    assert "not accepted in production" in exc_info.value.message


# --------------------------------------------------------------------------- #
# 4. identity_from_dev_headers 在生产环境禁用
# --------------------------------------------------------------------------- #


def test_identity_from_dev_headers_returns_none_in_production(
    production_env: None,
) -> None:
    """生产环境 ``dev_org_header_enabled=False`` → 即使有 header 也返回 None（不抛）。"""
    settings = get_settings()
    org_id = str(uuid4())
    actor_id = str(uuid4())

    result = identity_from_dev_headers(
        settings=settings, org_id_header=org_id, actor_id_header=actor_id
    )

    assert result is None


# --------------------------------------------------------------------------- #
# 5. identity_from_dev_headers 在开发环境启用
# --------------------------------------------------------------------------- #


def test_identity_from_dev_headers_returns_identity_when_enabled() -> None:
    """默认 test 环境 ``dev_org_header_enabled=True`` + header 提供 → ``Identity``。"""
    settings = get_settings()
    org_id = str(uuid4())
    actor_id = str(uuid4())

    result = identity_from_dev_headers(
        settings=settings, org_id_header=org_id, actor_id_header=actor_id
    )

    assert result is not None
    assert isinstance(result, Identity)
    assert result.org_id == UUID(org_id)
    assert result.actor_id == UUID(actor_id)
    assert result.source == "dev_org_header"


# --------------------------------------------------------------------------- #
# 6. get_current_identity 优先级：Bearer 覆盖 dev_headers
# --------------------------------------------------------------------------- #


def test_get_current_identity_prefers_bearer_over_dev_headers() -> None:
    """Authorization 与 X-Org-Id/X-Actor-Id 同时存在时，Bearer 优先（与 ADR-0003 一致）。

    直调 ``get_current_identity``（不走 TestClient）：构造 ``HTTPAuthorizationCredentials``
    入参，跳过 FastAPI 依赖注入框架；``Annotated`` 在直调路径下只是元数据，不影响 kwargs 传递。
    """
    bearer_org = uuid4()
    bearer_actor = uuid4()
    dev_org = uuid4()
    dev_actor = uuid4()
    token = f"dev.{bearer_org}.{bearer_actor}"

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    identity = asyncio.run(
        get_current_identity(
            credentials=credentials,
            x_org_id=str(dev_org),
            x_actor_id=str(dev_actor),
        )
    )

    assert isinstance(identity, Identity)
    assert identity.source == "bearer_token"
    assert identity.org_id == bearer_org
    assert identity.actor_id == bearer_actor
