"""Sprint 5 批次 A2：集成接缝收口单元测试。

覆盖四个接缝的最小闭环（changes/Sprint5.2/tasks.md §1~§4）：

1. **接缝 3 Provider 工厂**（``app.services.providers``）：
   - ``llm_provider = openai_compatible`` → 返回 ChatOpenAI 且参数收敛自 ``llm_*``；
   - 未知档位 → :class:`LlmProviderError` 显式报错（不静默回退默认档）。
2. **接缝 1 AuthProvider**（``app.services.auth``）：
   - 工厂返回 ``LocalAuthProvider``（登记集合恰好 1 个实现）；
   - Bearer token / dev header 两档语义与 ``app.core.auth`` 完全一致（回归）；
   - 无任何凭据输入 → None（由依赖层决定 401）。
3. **接缝 4 pipeline_stages**（``app.tasks.pipeline``）：
   - 默认四阶段中仅已登记执行体的阶段生效（当前只有 document.parse）；
   - 顺序 = 配置顺序；删除 = 停用；全停 → first 返回 None。
4. **接缝 2 documents 预留字段**（ADR-0004 §2.2）：
   - 8 个字段在 ORM 全部存在且 nullable（check_seams 的双向判据落到 pytest 层）。

隔离策略：全部为纯函数 / 模型层测试，不经过 TestClient / HTTP / 真实 LLM。
``get_settings()`` 是 ``lru_cache`` 单例，改字段一律用 ``monkeypatch.setattr``
（teardown 自动回滚，见 test_auth.py 同款约定）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.db.models import Document
from app.services.auth import AuthProvider, LocalAuthProvider, get_auth_provider
from app.services.providers import LlmProviderError, build_chat_model
from app.tasks.pipeline import (
    DEFAULT_STAGES,
    first_pipeline_stage,
    resolve_pipeline_stages,
)

# --------------------------------------------------------------------------- #
# 1. 接缝 3：LLM Provider 工厂
# --------------------------------------------------------------------------- #


def test_build_chat_model_openai_compatible_returns_chat_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认档位构造 ChatOpenAI，参数逐项收敛自 llm_* 配置（「只多一层」）。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "openai_compatible")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.example.com")
    monkeypatch.setattr(settings, "llm_request_timeout_seconds", 7.5)

    chat = build_chat_model()

    assert type(chat).__name__ == "ChatOpenAI"
    assert chat.model_name == "test-model"
    assert chat.openai_api_base == "https://llm.example.com"


@pytest.mark.parametrize("provider", ["", "deepseek", "ollama", "vllm"])
def test_build_chat_model_unknown_provider_raises(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    """未知档位显式报错——静默回退会掩盖配置错误（plan §4.4 纪律）。"""
    monkeypatch.setattr(get_settings(), "llm_provider", provider)

    with pytest.raises(LlmProviderError, match="llm_provider"):
        build_chat_model()


# --------------------------------------------------------------------------- #
# 2. 接缝 1：AuthProvider 收口（回归）
# --------------------------------------------------------------------------- #


def test_get_auth_provider_returns_local_provider() -> None:
    """工厂返回唯一登记实现 LocalAuthProvider（check_seams 判据 1 的运行时印证）。"""
    provider = get_auth_provider()

    assert isinstance(provider, LocalAuthProvider)
    assert isinstance(provider, AuthProvider)


def test_local_provider_bearer_token_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bearer token 语义与 core.auth 一致：dev token → Identity（source=bearer_token）。"""
    settings = get_settings()
    org_id, actor_id = uuid4(), uuid4()

    identity = get_auth_provider().authenticate(
        settings=settings,
        bearer_token=f"dev.{org_id}.{actor_id}",
        org_id_header=str(uuid4()),
        actor_id_header=str(uuid4()),
    )

    assert identity is not None
    assert identity.org_id == org_id
    assert identity.actor_id == actor_id
    assert identity.source == "bearer_token"


def test_local_provider_dev_header_fallback() -> None:
    """无 Bearer 时走 dev header 兜底（test 环境 ALLOW_DEV_ORG_HEADER=true）。"""
    settings = get_settings()
    org_id, actor_id = uuid4(), uuid4()

    identity = get_auth_provider().authenticate(
        settings=settings,
        bearer_token=None,
        org_id_header=str(org_id),
        actor_id_header=str(actor_id),
    )

    assert identity is not None
    assert identity.org_id == org_id
    assert identity.source == "dev_org_header"


def test_local_provider_no_credentials_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无任何凭据 → None（401 由依赖层决定，provider 不越权决定错误形态）。"""
    monkeypatch.setattr(get_settings(), "allow_dev_org_header", False)

    identity = get_auth_provider().authenticate(
        settings=get_settings(),
        bearer_token=None,
        org_id_header=None,
        actor_id_header=None,
    )

    assert identity is None


# --------------------------------------------------------------------------- #
# 3. 接缝 4：pipeline_stages 启停与顺序
# --------------------------------------------------------------------------- #


def test_resolve_pipeline_stages_skips_unregistered() -> None:
    """默认四阶段均已登记（Sprint 7.1 批次 A 起 ``risk.detect`` 落地）。"""
    stages = resolve_pipeline_stages()

    # ``risk.detect`` 在 Sprint 7.1 批次 A 登记后自动进入管线（未登记的阶段会被跳过）
    assert stages == [
        "document.parse",
        "document.extract",
        "kg.build",
        "risk.detect",
    ]


def test_resolve_pipeline_stages_respects_order_and_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """顺序 = 配置顺序；删除 = 停用；未登记阶段跳过。"""
    monkeypatch.setattr(
        get_settings(),
        "pipeline_stages",
        ["kg.build", "document.parse", "risk.detect", "document.extract"],
    )

    # 顺序 = 配置顺序（risk.detect 已登记，故保留在配置给的位置）
    assert resolve_pipeline_stages() == [
        "kg.build",
        "document.parse",
        "risk.detect",
        "document.extract",
    ]

    # 只留一个**未登记**的阶段 → 空（证明「未登记即跳过」仍成立）
    monkeypatch.setattr(
        get_settings(), "pipeline_stages", ["risk.detect", "not.registered"]
    )
    assert resolve_pipeline_stages() == ["risk.detect"]


def test_first_pipeline_stage_none_when_all_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全停用 / 全未登记 → first 返回 None（上传链路告警「管线全停」）。"""
    monkeypatch.setattr(get_settings(), "pipeline_stages", [])

    assert first_pipeline_stage() is None


def test_default_stages_constant_matches_registry() -> None:
    """DEFAULT_STAGES 常量与 Settings.pipeline_stages 默认值一致（文档锚点）。"""
    assert DEFAULT_STAGES == tuple(get_settings().pipeline_stages)


# --------------------------------------------------------------------------- #
# 4. 接缝 2：documents 预留字段（ADR-0004 §2.2）
# --------------------------------------------------------------------------- #

#: ADR-0004 §2.2 登记的 8 个预留字段（与 scripts/check_seams.py 的 RESERVED_FIELDS 同源）
RESERVED_FIELDS = (
    "source_type",
    "source_ref",
    "document_key",
    "content_hash",
    "source_version",
    "acl_scope",
    "acl_owner_ref",
    "deleted_at",
)


def test_documents_reserved_fields_all_nullable() -> None:
    """8 个预留字段在 ORM 全部存在且 nullable（只落库、不进契约）。"""
    columns = Document.__table__.columns
    for name in RESERVED_FIELDS:
        assert name in columns, f"documents 缺少预留字段 {name}"
        assert columns[name].nullable, (
            f"documents.{name} 必须可空（ADR-0004 §3 第 1 条）"
        )


def test_documents_reserved_fields_default_null() -> None:
    """新建 Document（仅填必填列）时预留字段默认为 NULL——存量库无需回填。"""
    document = Document(
        filename_hash="0" * 64,
        mime_type="application/pdf",
        size_bytes=1,
        status="pending",
        uploaded_by=uuid4(),
        org_id=uuid4(),
        retry_count=0,
        trace_id=uuid4(),
    )

    for name in RESERVED_FIELDS:
        assert getattr(document, name) is None
