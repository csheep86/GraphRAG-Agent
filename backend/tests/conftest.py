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
