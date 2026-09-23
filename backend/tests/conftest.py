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

# 存储抽象层隔离：测试统一写入临时目录，不污染 backend/storage/
os.environ["STORAGE_ROOT"] = str(_TMP_DIR / "storage")

# 无 MINERU_TOKEN 时 PDF 解析任务会以 MineruApiError 重试 3 次；
# 等待降至最小值（字段校验 gt=0）避免用例真实 sleep 1s + 2s。
os.environ["TASK_RETRY_INITIAL_SECONDS"] = "0.001"

# 图谱相关端点（/graph、/agent/query）在测试中必须**确定性**降级：
# 指向本机不可达端口，保证 GraphService 一定抛 GraphUnavailableError。
# 环境变量优先级高于 `.env`，因此能稳定覆盖开发者本地 .env 里的真实 Neo4j 配置——
# 否则一旦本机 Neo4j 在跑，测试结果就会随外部依赖漂移（CI 上必挂）。
# 需要「图谱可用」的用例请用 monkeypatch 显式打桩，不要依赖真实 Neo4j。
os.environ["NEO4J_URI"] = "bolt://127.0.0.1:1"
os.environ["NEO4J_PASSWORD"] = ""

# 同理中和**外部凭据**：环境变量优先级高于 `.env`，而开发者 / CI 一旦注入真实
# token，用例就会真的去调外部服务——实测（Sprint 6 T0）：注入 MINERU_TOKEN 后
# 单个上传用例 0.11s → 37s，全量 pytest 3.67s → 226s，且结果随外部服务漂移。
# 需要「真实调用」的用例请用 monkeypatch 显式开启，不要依赖本机 / CI 的密钥。
os.environ["MINERU_TOKEN"] = ""
os.environ["LLM_API_KEY"] = ""
# 同理中和**抽取引擎**：Sprint 7.0 起 extraction_engine 默认 'llm'（生产 / 演示要真数据），
# 测试必须**显式**落到 'mock' 档——否则用例会带着空 key 去真连 DeepSeek，
# 结果与外部服务漂移（与上方 MINERU_TOKEN / LLM_API_KEY 同一条纪律）。
# 需要验证「真实 LLM 抽取」的用例请 monkeypatch 注入假 invoker，不要依赖外部服务。
os.environ["EXTRACTION_ENGINE"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.kg.versioning import KgVersioningService  # noqa: E402

OTHER_ORG_ID = "00000000-0000-4000-8000-000000000002"

#: ``KgVersioningService.get_active`` 的**原始**实现——:func:`pg_active_kg_version`
#: 会把它桩掉，:func:`real_pg_get_active` 用它恢复（顺序：autouse 先、显式后）。
_REAL_GET_ACTIVE = KgVersioningService.get_active


@pytest.fixture(autouse=True)
def pg_active_kg_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认让 **PG 真源存在一条 ready 版本**（Sprint 6.3：读侧 PG 优先）。

    测试库是空 SQLite：不桩的话 ``fetch_active_kg_version`` 的 PG 分支会先抛
    ``NoActiveKgVersionError``（409），把「Neo4j 不可达」这类**基础设施故障**
    伪装成「无 active 版本」——与既有 501 用例的语义直接冲突（plan §4.4 纪律）。
    桩了 ``fetch_active_kg_version`` 的用例不受影响（整方法被替换）。

    需要验证「PG 无 ready → 409」的用例请显式覆盖本桩（见
    ``test_graph_overview_and_entity.py::test_overview_409_when_pg_has_no_ready_version``）。
    """
    from uuid import uuid4

    from app.services.kg.versioning import KgVersioningService, KgVersionRecord

    def _get_active(self: KgVersioningService, *, org_id: object) -> KgVersionRecord:
        return KgVersionRecord(
            id=uuid4(),
            org_id=org_id,  # type: ignore[arg-type]
            version="v-test",
            status="ready",
            source_doc_ids=[],
            entity_count=0,
            relation_count=0,
            error_code=None,
            error_detail=None,
            ready_at=None,
            trace_id=uuid4(),
        )

    monkeypatch.setattr(KgVersioningService, "get_active", _get_active)


@pytest.fixture
def real_pg_get_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """撤销 :func:`pg_active_kg_version` 的桩，恢复 ``get_active`` 真实实现。

    供 :mod:`tests.test_kg_versioning` 里「断言真源状态机本身」的用例使用——
    它们要验的正是「PG 无 ready → None」，不能被上面的默认桩遮蔽。
    """
    monkeypatch.setattr(KgVersioningService, "get_active", _REAL_GET_ACTIVE)


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
