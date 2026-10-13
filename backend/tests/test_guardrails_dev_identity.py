"""**G-27（P7-C 新增，2026-10-13）：dev 身份兜底在「非开发形态」机械不可达**（B1）。

**为什么必须新增这条护栏**：发版就绪度审计 §4 B1 指出「dev 身份兜底未删除」。
复核后事实是**分叉**的，不能一刀切：

- `X-Org-Id` 兜底：已由 `ALLOW_DEV_ORG_HEADER` + 非生产双重把关 ⇒ 交付形态 `None`；
- `Bearer dev.<org_id>.<actor_id>`：**只看 `is_production`**，而交付 compose
  （`deploy/docker-compose.delivery.yml`）**从不注入 `APP_ENV`** ⇒ 客户现场取默认
  `development` ⇒ 无签名 token 全程可用 ⇒ **任何人都能伪造任意租户身份**。

⇒ 收口动作 = 两条兜底共用 `Settings.dev_identity_enabled`（显式开关 **且** 非生产），
本文件把它钉住。**判据刻意不依赖 `APP_ENV`**：交付形态就是 `development`，
靠"生产模式"来关兜底根本不成立——这才是 B1 的根因。

**四条判据**：

1. 未开 dev 开关（**交付形态**：无 `.env`、`ALLOW_DEV_ORG_HEADER` 未设）⇒
   dev token **401**、`X-Org-Id` 返回 `None`；
2. 生产环境（即使开关开着）⇒ 两条都不可达；
3. 开发形态（开关开 + 非生产）⇒ 两条**仍可用**——这是反向守卫：收口不许把
   上千条既有用例的身份来源一起拆掉；
4. 部署侧：交付 compose 与 `deploy/.env.example` **不得**注入 `ALLOW_DEV_ORG_HEADER`
   （否则前面三条在客户现场全被绕过）。

**不覆盖的部分**（不得因本条绿灯外推）：
① 兜底**没有删除**，只是加了开关；删除属另一批（会牵动上千条用例）；
② 交付形态仍以 `APP_ENV=development` 运行 ⇒ 其它"仅生产生效"的守卫
   （G-21 禁 SQLite / 默认 JWT 密钥）在客户现场**同样不生效**——已登记为
   P7-C 遗留，不在本批处置。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from app.core.auth import identity_from_dev_headers, parse_bearer_token
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode

REPO_ROOT = Path(__file__).resolve().parents[2]
DELIVERY_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.delivery.yml"
DELIVERY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"
AUTH_MODULE = REPO_ROOT / "backend" / "app" / "core" / "auth.py"

#: 非默认的 JWT 密钥——构造「生产形态」Settings 时必须给，否则
#: `Settings._guard_production_jwt_secret` 会在**构造期**就抛错（那条守卫是对的，别绕）。
_NON_DEFAULT_SECRET = "p7-c-probe-secret"


def _settings(*, app_env: str, allow_dev_org_header: bool) -> Settings:
    """构造一个**与进程环境无关**的 Settings（`_env_file=None` 跳过 `backend/.env`）。

    为什么要这么绕：conftest 会把 `APP_ENV=test` / `ALLOW_DEV_ORG_HEADER=true`
    写进 `os.environ`，直接 `get_settings()` 拿不到「客户现场」那一档配置。
    """
    return Settings(
        _env_file=None,
        app_env=app_env,
        allow_dev_org_header=allow_dev_org_header,
        auth_jwt_secret=_NON_DEFAULT_SECRET,
    )


def _dev_token(settings: Settings) -> str:
    return f"dev.{settings.default_org_id}.{settings.default_actor_id}"


# --------------------------------------------------------------------------- #
# 判据 1：未开 dev 开关（= 交付形态）⇒ 两条兜底都不可达
# --------------------------------------------------------------------------- #


def test_g27_dev_fallbacks_unreachable_without_dev_switch() -> None:
    """**B1 本体**：交付形态（无 `.env`、`ALLOW_DEV_ORG_HEADER` 未设、`APP_ENV` 未设
    ⇒ `development`）下，`Bearer dev.*` 必须 **401**、`X-Org-Id` 必须 `None`。

    ⚠️ 本条刻意**不**设 `app_env=production`——交付 compose 从不注入 `APP_ENV`，
    靠"生产模式"关兜底是个**假的安全感**（改前实测：dev token 原样返回 Identity）。
    """
    settings = _settings(app_env="development", allow_dev_org_header=False)
    assert settings.is_production is False, (
        "本判据的前提是「非生产」——若这里为 True，说明交付形态已改为显式生产，"
        "判据需要重写（届时请把本条改成断言生产分支）"
    )

    with pytest.raises(AppError) as exc_info:
        parse_bearer_token(_dev_token(settings), settings)
    assert exc_info.value.code == ErrorCode.UNAUTHORIZED.value
    assert "ALLOW_DEV_ORG_HEADER" in exc_info.value.message

    assert (
        identity_from_dev_headers(
            settings=settings,
            org_id_header=str(uuid4()),
            actor_id_header=str(uuid4()),
        )
        is None
    )


# --------------------------------------------------------------------------- #
# 判据 2：生产环境（即使开关开着）⇒ 两条兜底都不可达
# --------------------------------------------------------------------------- #


def test_g27_dev_fallbacks_unreachable_in_production() -> None:
    """生产口径下 `ALLOW_DEV_ORG_HEADER=true` **也不得**放行（开关不是破例口）。"""
    settings = _settings(app_env="production", allow_dev_org_header=True)
    assert settings.dev_identity_enabled is False

    with pytest.raises(AppError) as exc_info:
        parse_bearer_token(_dev_token(settings), settings)
    assert exc_info.value.code == ErrorCode.UNAUTHORIZED.value
    assert "not accepted in production" in exc_info.value.message

    assert (
        identity_from_dev_headers(
            settings=settings,
            org_id_header=str(uuid4()),
            actor_id_header=str(uuid4()),
        )
        is None
    )


# --------------------------------------------------------------------------- #
# 判据 3（反向）：开发形态仍可用 —— 收口不许把开发通道一起拆掉
# --------------------------------------------------------------------------- #


def test_g27_dev_fallbacks_still_usable_when_switch_on() -> None:
    """**反向守卫**：显式开 `ALLOW_DEV_ORG_HEADER=true` 且非生产 ⇒ 两条兜底照旧可用。

    为什么必须留这一条：上千条既有用例的身份来源就是 dev token / dev header。
    只判"关得掉"会奖励一个把开发通道一起删掉的实现（那样判据 1/2 当然全绿，
    但测试全线失去身份来源）。
    """
    settings = _settings(app_env="development", allow_dev_org_header=True)
    assert settings.dev_identity_enabled is True

    identity = parse_bearer_token(_dev_token(settings), settings)
    assert identity.org_id == settings.default_org_id
    assert identity.actor_id == settings.default_actor_id

    header_org, header_actor = uuid4(), uuid4()
    from_header = identity_from_dev_headers(
        settings=settings,
        org_id_header=str(header_org),
        actor_id_header=str(header_actor),
    )
    assert from_header is not None
    assert (from_header.org_id, from_header.actor_id) == (header_org, header_actor)


# --------------------------------------------------------------------------- #
# 判据 4：部署侧不得把 dev 开关带进客户现场
# --------------------------------------------------------------------------- #


def test_g27_delivery_stack_never_enables_dev_switch() -> None:
    """交付 compose 的 `backend` 环境 + `deploy/.env.example` **都不得**出现
    `ALLOW_DEV_ORG_HEADER`。

    为什么盯部署文件：判据 1~3 验的是**代码**，而客户现场拿的是**这套编排**。
    只要有人在 compose 里补一行 `ALLOW_DEV_ORG_HEADER: "true"`，
    前面三条在客户现场就被整体绕过，而 CI 依然全绿。
    """
    compose = yaml.safe_load(DELIVERY_COMPOSE.read_text(encoding="utf-8"))
    backend_env = compose["services"]["backend"]["environment"]
    leaked = [
        key
        for key in backend_env
        if isinstance(key, str) and key.upper() == "ALLOW_DEV_ORG_HEADER"
    ]
    assert not leaked, (
        f"{DELIVERY_COMPOSE.name} 的 backend 环境注入了 {leaked} ⇒ "
        "客户现场可用无签名 token 伪造任意租户身份（B1）。"
        "开发态需要它时请改用开发 compose（deploy/docker-compose.yml）。"
    )

    env_example = DELIVERY_ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "ALLOW_DEV_ORG_HEADER" not in env_example, (
        f"{DELIVERY_ENV_EXAMPLE.name} 出现 ALLOW_DEV_ORG_HEADER ⇒ "
        "客户照模板复制 .env 就会把 dev 兜底带进生产。"
    )


# --------------------------------------------------------------------------- #
# 反向守卫：拦截代码本身不许被删（删了上面四条就一起哑掉）
# --------------------------------------------------------------------------- #


def test_g27_dev_token_guard_still_present() -> None:
    """`auth.py` 的 dev 分支里必须存在对 `dev_identity_enabled` 的拦截。

    与 G-21 同款口径：本文件前四条验的是**行为**，这一条验的是**拦截还在**
    ——把那两行 `raise` 删掉，行为用例会因为「恰好没人带 dev token」而照样绿。
    """
    source = AUTH_MODULE.read_text(encoding="utf-8")
    assert "dev_identity_enabled" in source, (
        f"{AUTH_MODULE.name} 不再引用 settings.dev_identity_enabled ⇒ "
        "dev token 的收口拦截被摘掉了（B1 复发）。"
    )
