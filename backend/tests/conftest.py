"""测试夹具。

**必须在导入 `app.*` 之前**改写环境变量：`app.main` 在模块导入时就调用
`create_app()`，而 `get_settings()` 有 `lru_cache`。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="graphrag-backend-tests-"))

os.environ["APP_ENV"] = "test"
os.environ["ALLOW_DEV_ORG_HEADER"] = "true"
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"

# 图谱相关端点（/graph、/agent/query）在测试中必须**确定性**降级：
# 指向本机不可达端口，保证 GraphService 一定抛 GraphUnavailableError。
# 环境变量优先级高于 `.env`，因此能稳定覆盖开发者本地 .env 里的真实 Neo4j 配置——
# 否则一旦本机 Neo4j 在跑，测试结果就会随外部依赖漂移（CI 上必挂）。
# 需要「图谱可用」的用例请用 monkeypatch 显式打桩，不要依赖真实 Neo4j。
os.environ["NEO4J_URI"] = "bolt://127.0.0.1:1"
os.environ["NEO4J_PASSWORD"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402

OTHER_ORG_ID = "00000000-0000-4000-8000-000000000002"


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def dev_headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "X-Org-Id": str(settings.default_org_id),
        "X-Actor-Id": str(settings.default_actor_id),
    }


@pytest.fixture(scope="session")
def cross_tenant_headers() -> dict[str, str]:
    settings = get_settings()
    return {"X-Org-Id": OTHER_ORG_ID, "X-Actor-Id": str(settings.default_actor_id)}
