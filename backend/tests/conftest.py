"""测试夹具。

**必须在导入 `app.*` 之前**改写环境变量：`app.main` 在模块导入时就调用
`create_app()`，而 `get_settings()` 有 `lru_cache`。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import UUID

_TMP_DIR = Path(tempfile.mkdtemp(prefix="graphrag-backend-tests-"))

# 存储抽象层隔离：测试统一写入临时目录，不污染 backend/storage/
os.environ["STORAGE_ROOT"] = str(_TMP_DIR / "storage")

#: **DR-B2 / G-8**：测试库是 PostgreSQL 16.x 上的固定库 ``graphrag_test``。
#: 不再用 SQLite 临时文件——在 SQLite 上跑通的租户隔离（T1 / T2）什么都不证明：
#: SQLite 既没有 RLS，也没有 ``SET LOCAL``（ADR-0003 §4.1）。
#:
#: **P3-A（2026-10-04）：业务测试一律走受限角色 ``app_rls``**（裁决 4）。
#: 本机 / CI 的默认库用户往往就是**超级用户**（``docker run -e POSTGRES_USER=graphrag``
#: ⇒ rolsuper=true），而超级用户**绕过一切 RLS** ⇒ 用它跑测试 = RLS 从未被验证。
#: ⇒ 建表 / 迁移走 owner（``DATABASE_URL_OWNER``），业务查询走本串（受限角色）。
#: 角色与策略由 ``scripts/init_rls_roles.py`` 建立（CI 里是 Pytest 前的独立步骤）。
_TEST_DATABASE_URL = "postgresql+psycopg://app_rls:app_rls@localhost:5432/graphrag_test"

#: 建表 / 迁移用的 **owner** 连接串（与 :mod:`pg_scratch` 同一真源）
_TEST_OWNER_URL = (
    "postgresql+psycopg://app_owner:app_owner@localhost:5432/graphrag_test"
)

os.environ.setdefault("DATABASE_URL_OWNER", _TEST_OWNER_URL)
os.environ["APP_ENV"] = "test"
os.environ["ALLOW_DEV_ORG_HEADER"] = "true"
# 用 **setdefault** 而不是直接赋值，也不能完全不设：
#   直接赋值 ⇒ 盖掉 CI 的显式注入；
#   完全不设   ⇒ 被开发者 .env 里的**开发库**带偏，测试写脏真实数据。
os.environ.setdefault("DATABASE_URL", _TEST_DATABASE_URL)

# 无 MINERU_TOKEN 时 PDF 解析任务会以 MineruApiError 重试 3 次；
# 等待降至最小值（字段校验 gt=0）避免用例真实 sleep 1s + 2s。
os.environ["TASK_RETRY_INITIAL_SECONDS"] = "0.001"

# 限流（M5 §3 验收 5）：共享 client 的限流实际关闭（上限调到不可触达），
# 否则全量跑测时同一接口的累计请求数可能撞 60/min 限——限流行为本身由
# test_rate_limit.py 用独立 app（RATE_LIMIT_PER_MINUTE=1）专测。
os.environ["RATE_LIMIT_PER_MINUTE"] = "100000"

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

# ⚠️ **License 的 env 必须在这里就落地**（P4）：
# `get_settings()` 是 `lru_cache`，而 `app.core.config` 在**模块级**就实例化了 Settings
# ⇒ 一旦下面第 84 行导入 `app.services.license.fingerprint`（它会连带导入 app.core.config），
# Settings 就**带着默认值被缓存**了，之后再设 env 一律无效
# （表现为：测试环境永远 LICENSE_MISSING，而 pdb/命令行里却正常）。
os.environ["LICENSE_FILE_PATH"] = str(_TMP_DIR / "license" / "pytest.lic")
os.environ["LICENSE_PUBLIC_KEY"] = ""  # 下面签出密钥后立刻覆盖为真实公钥

# License（接缝 9 / DR-C1）：测试**带着一份真 license 跑**，而不是把 enforce 关掉。
#
# 为什么不是 ``LICENSE_ENFORCE=false``：那样所有请求都被放行，
# ① 掩盖「中间件到底拦没拦」这个本批唯一要证明的事；
# ② 每条请求都会写一条 ``license.bypass`` 审计，把 /audit 的用例全污染掉。
# ⇒ 在这里现签一份 ``.lic``：真的 Ed25519 签名 + 真的本机指纹 + 未来有效期，
#   私钥**只在进程内**（测试脚手架），不入仓库、不作为交付资产。
import base64  # noqa: E402
import json  # noqa: E402

from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: E402

from app.services.license.fingerprint import compute_fingerprint  # noqa: E402

_TEST_LICENSE_PRIVATE_KEY = ed25519.Ed25519PrivateKey.generate()
_TEST_LICENSE_PUBLIC_KEY_B64 = base64.b64encode(
    _TEST_LICENSE_PRIVATE_KEY.public_key().public_bytes_raw()
).decode()

# ⚠️ **顺序不能换**：`get_settings()` 是 `lru_cache`，而下面算指纹时会调用它 ——
# 若先算指纹（即先缓存一份"还没设 env"的 Settings），再设 env 就**全部无效**
# （部署 ≤ 早于 P4 岔口踩过：表现为资源测试环境一律 LICENSE_MISSING）。
# ⇒ env 必须在**第一次**触发 get_settings() 之前落地。
os.environ["LICENSE_FILE_PATH"] = str(_TMP_DIR / "license" / "pytest.lic")
os.environ["LICENSE_PUBLIC_KEY"] = _TEST_LICENSE_PUBLIC_KEY_B64

_TEST_LICENSE_BODY = {
    "license_id": "00000000-0000-4000-8000-00000000beef",
    "schema_version": 1,
    "product": "graphrag-agent",
    "customer": "pytest-scaffold",
    "fingerprint": compute_fingerprint(),
    "issued_at": "2026-01-01T00:00:00Z",
    "not_before": "2026-01-01T00:00:00Z",
    # 有效期给到很远的未来：**测试不得依赖真实时钟** ——
    # 需要验证过期 / 宽限期的用例请另签一份特定日期的 license，而不是改系统时间。
    "not_after": "2099-12-31T00:00:00Z",
    "grace_days": 30,
    "limits": {"max_orgs": 100, "max_seats": 100},
    "modules": [
        "m1_ingest",
        "m2_extract",
        "m3_graphqa",
        "m4_affiliation",
        "m5_permission",
        "m6_ontology",
        "connectors",
    ],
}
_TEST_CANONICAL = json.dumps(
    _TEST_LICENSE_BODY, ensure_ascii=False, sort_keys=True, separators=(",", ":")
)
_TEST_LICENSE_FILE = _TMP_DIR / "license" / "pytest.lic"
_TEST_LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
_TEST_LICENSE_FILE.write_text(
    json.dumps(
        {
            **_TEST_LICENSE_BODY,
            "signature": base64.b64encode(
                _TEST_LICENSE_PRIVATE_KEY.sign(_TEST_CANONICAL.encode("utf-8"))
            ).decode(),
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pg_scratch import ensure_database  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.graphs import GraphService  # noqa: E402
from app.services.kg.versioning import KgVersioningService  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def license_environment():
    """把 License 配置写进**已经缓存的那个** Settings 实例。

    **为什么不走 env**：``get_settings()`` 是 ``lru_cache``，而 Settings 在 pytest 进程里
    早于 conftest 的 env 改写就被实例化和缓存了（表现为：``os.environ`` 已改、读到的仍是默认值；
    在命令行里 python -c 却一切正常 —— 时序依赖，极难定位）。
    ⇒ 这里直接改字段，**不依赖任何导入时序**。

    用 ``object.__setattr__`` 是因为 pydantic 默认禁止直接赋值。
    """
    settings = get_settings()
    object.__setattr__(settings, "license_file_path", str(_TEST_LICENSE_FILE))
    object.__setattr__(settings, "license_public_key", _TEST_LICENSE_PUBLIC_KEY_B64)
    object.__setattr__(settings, "license_enforce", True)
    return settings


# 测试库是**持久**的（不再像 SQLite 时代那样每次换一个临时文件），因此必须显式
# 保证它存在。`create_app()` 只建 engine 不连库，所以放在导入之后仍然来得及。
ensure_database("graphrag_test")


@pytest.fixture(autouse=True)
def default_org_for_bare_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    """给「直接建 Session」的用例绑定**默认租户**（A10 / 坑 8 的脚手架处置）。

    **为什么必须有这条**：RLS + FORCE 之后，``SessionLocal()`` 开出来的会话若没绑
    org，业务表**一行都看不到、一行都写不进**（fail-closed）。而既有用例里有一大批
    是「直接建 Session 造数据 + 直接查库断言」的**单元测试形态**——它们压根不经过
    HTTP 请求，也就没有认证态可以给 org。逐个给它们塞身份，等于把这批单元测试改写成
    集成测试（改动量与回归风险都不可接受）。

    于是这里在 ``sessionmaker`` 上预置一个 **info 默认值**：用例自己显式绑 org 的
    （``session_scope(org_id=...)`` / ``open_session(org_id=...)``）**不受影响**，
    没绑的落到默认租户。

    ⚠️ **它不验什么**（与 ``rbac_default_actor_is_admin`` 同一类脚手架边界）：
    它让「忘了绑 org」在测试里**不至于全红**，因此**不能**用来证明「某条应用路径
    的租户绑定是对的」。租户绑定本身由两处机械证明：

    1. **G-26 判据 3**：用**裸连接**（不经过 Session）验证「不设 org ⇒ 0 行、
       设了 org ⇒ 只看到本 org」——绕开本脚手架，无法被它糊弄；
    2. **A5 行为用例**：后台任务用**非默认** org 跑通，证明执行体的 org 来自
       ``TaskSpec.org_id`` 而不是本默认值。

    ⚠️ 反向风险已堵：若某用例要写**别的租户**的数据，本默认值会让 ``WITH CHECK``
    直接拒绝（**响亮失败**，不是静默串号）⇒ 该用例必须显式绑 org。
    """
    from app.db.session import ORG_ID_INFO_KEY, SessionLocal

    settings = get_settings()
    # ``setitem`` 而不是直接改字典：用例结束由 monkeypatch 自动还原，
    # 避免把「默认租户」泄漏给下一个不需要它的用例。
    monkeypatch.setitem(
        SessionLocal.kw, "info", {ORG_ID_INFO_KEY: settings.default_org_id}
    )


OTHER_ORG_ID = "00000000-0000-4000-8000-000000000002"

#: **P2-C / R30**：第二个租户的**专属主体**。
#:
#: 为什么不能沿用 ``DEFAULT_ACTOR_ID``：``users.id`` 是**主键**，同一个 UUID 不可能
#: 在两个租户里各占一行（而 ``user_roles.user_id`` 若仍指向 org A 的那个 UUID，
#: 形态就是「org B 的授权挂在 org A 的人身上」—— 那正是 R30 第 ① 条抓到的跨租户引用）。
#: ⇒ 每个租户**各有一个主体**，``actor_id`` 的唯一来源随之变成"这个租户里的这个账号"。
OTHER_ORG_ACTOR_ID = UUID("00000000-0000-4000-8000-0000000000bb")

#: 测试库里两个 dev 主体的**登录口令**（`POST /auth/login` 真校验用）。
#: ``users.username`` 全库唯一 ⇒ 两个主体必须用两个名字；口令刻意取同一个，
#: 让"换租户 = 换账号"这件事只体现在 username 上，不给判据增加第二个变量。
DEV_LOGIN_PASSWORD = "dev-login-password"
DEFAULT_ORG_LOGIN_USERNAME = "dev-admin-a"
OTHER_ORG_LOGIN_USERNAME = "dev-admin-b"

#: ``KgVersioningService.get_active`` 的**原始**实现——:func:`pg_active_kg_version`
#: 会把它桩掉，:func:`real_pg_get_active` 用它恢复（顺序：autouse 先、显式后）。
_REAL_GET_ACTIVE = KgVersioningService.get_active

#: 同上的 ``get_by_version`` 原始实现（2026-09-26：`GET /graph/overview` 的统计值
#: 改走 ``get_by_version`` 读 PG 真源后，桩必须成对覆盖，否则「Neo4j 不可达」用例
#: 会因统计真源缺失被误判成 409 —— 与 501 语义冲突）。
_REAL_GET_BY_VERSION = KgVersioningService.get_by_version


@pytest.fixture(autouse=True)
def pg_active_kg_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认让 **PG 真源存在一条 ready 版本**（Sprint 6.3：读侧 PG 优先）。

    测试库是持久的 PostgreSQL（`graphrag_test`，P1-C 起）：不桩的话
    ``fetch_active_kg_version`` 的 PG 分支会先抛
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

    def _get_by_version(
        self: KgVersioningService, *, org_id: object, version: str
    ) -> KgVersionRecord | None:
        return _get_active(self, org_id=org_id) if version == "v-test" else None

    monkeypatch.setattr(KgVersioningService, "get_active", _get_active)
    monkeypatch.setattr(KgVersioningService, "get_by_version", _get_by_version)


@pytest.fixture(autouse=True)
def graph_reasoning_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """给特性开关留的默认桩：推理路径一律「零命中」，除非用例自己覆盖。

    **为什么要有这个默认桩**：批次 D1 在问答主链路第 2.7 步新增了
    ``GraphService.fetch_reasoning_path``（与既有第 2.6 步同 semantics：Neo4j
    故障 ⇒ 501，**不**降级为空）。既有问答用例（`test_agent_citations.py` /
    `test_graph_and_agent_routes.py` / `test_audit.py`）验的是引用 / 拒答 / 审计，
    没有给它打桩 ⇒ 全部走到不可达的 Neo4j ⇒ 被判 501 打红——那不是回归，
    是**新依赖没接线**。逐个补桩会让这些用例各背一段与己无关的样板。

    与 :func:`pg_active_kg_version` 同一口径：**不打桩会让基础设施故障伪装成
    别的语义**。要验路径本身的用例请 monkeypatch 覆盖本桩（顺序：autouse 先、
    显式后，覆盖生效），集中在 ``test_agent_reasoning_path.py``。
    """
    # 桩在**类**上（不是 instance）：写到实例属性会遮蔽类属性，
    # 用例自己再 setattr(GraphService, ...) 就覆盖不掉了。
    monkeypatch.setattr(
        GraphService, "fetch_reasoning_path", lambda _self, **_kwargs: []
    )
    # 同上：证据注入的锚点查询（R14 修）也是新依赖，不打桩会让这批改过的
    # 用例去连不可达的 Neo4j ⇒ 501。默认「无锚点」，验锚点的用例自行覆盖。
    monkeypatch.setattr(
        GraphService, "fetch_anchor_entity_ids", lambda _self, **_kwargs: ()
    )


#: ...上面那个 autouse 桩**之前**抓下来的真身。
#:
#: **为什么要在模块级抓**：桩是 autouse 的，每个用例都会把它装上 ⇒ 等到用例体
#: 里再去 ``GraphService.__dict__`` 找，找到的已经是那个 ``lambda`` 了。要在 conftest
#: 的**导入期**（此时还只有真身）就把它们留下，给「要验路径本身」的用例一条退路。
_REAL_FETCH_REASONING_PATH = GraphService.fetch_reasoning_path
_REAL_FETCH_ANCHOR_ENTITY_IDS = GraphService.fetch_anchor_entity_ids


@pytest.fixture
def real_graph_read_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """撤掉 :func:`graph_reasoning_path_default` 的恒空桩 ⇒ 走**真实**读路径。

    **什么时候该挂它**：用例要验的是推理路径本身（而不是把它当作无关依赖给
    屏蔽掉）的场合，例如 P5-H 的「版本继承读」要证的就是「校正之后推理链仍能
    读回来」—— 挂着恒空桩时这条判据**永远绿也永远没意义**。

    **它不是放宽护栏**：桩的目的写得很清楚（防把基础设施故障插为别的语义），
    这里是把"自己要验的那一段"交还给它本来的实现，其他用例的屏蔽不变。
    """
    monkeypatch.setattr(
        GraphService, "fetch_reasoning_path", _REAL_FETCH_REASONING_PATH
    )
    monkeypatch.setattr(
        GraphService, "fetch_anchor_entity_ids", _REAL_FETCH_ANCHOR_ENTITY_IDS
    )


@pytest.fixture(scope="session", autouse=True)
def rbac_default_actor_is_admin() -> None:
    """给**默认 dev 主体**在两个租户里各授一份 `admin`（P2-B 的测试脚手架）。

    **为什么必须有这条**：P2-B 起受保护端点会走 RBAC 强制校验，而 dev token /
    dev header 解析出来的主体在 `user_roles` 里**天然没有任何授权**
    （真实账号链路归 P2-C）⇒ 不播种的话全站受保护端点一律 403，
    **818 条既有用例会为了与己无关的原因集体变红**。

    **它不是"绕过护栏"**：校验照常执行、矩阵照常生效，只是把「这个主体是谁」
    补上——与 :func:`pg_active_kg_version` 桩掉一个 ready 版本是同一类动作
    （不打桩会让基础设施故障伪装成别的语义）。

    **为什么两个 org 都授**：跨租户用例要在 org B 里**能写能读**
    （`test_documents_list.py` 就往 org B 上传文档）——不授 org B，跨租户用例就会被
    RBAC 抢在应用层 `org_id` 过滤**之前**拦掉，于是「跨租户返回空 / 403」的既有判据
    （G-9 / G-10 / `test_documents.py`）虽然仍然绿，验的却不再是它们要验的那层。

    ⚠️ **它同时意味着**：默认主体是 admin ⇒ 默认路径**验不到**拒绝分支。
    拒绝分支由 `tests/test_rbac.py` 用**另外的 actor id** 专测（见该文件）。

    **2026-10-07 P2-C（R30）：每个租户各播一个**主体锚点**（`users` 的一行）。**
    原先只有 `user_roles`、没有 `users` ⇒ 授权挂在库里不存在的人身上（R29 的孤儿），
    而 org B 那条更是**跨租户引用**（`user_roles.org_id=B` 却指向 org A 的主体）。
    `users.id` 是主键 ⇒ 两个租户不可能共用同一个 UUID ⇒ org B 改用
    :data:`OTHER_ORG_ACTOR_ID`，`cross_tenant_headers` 的 actor 随之改用它。
    机械断言见 `tests/test_identity_anchor.py`（严格视图孤儿 = 0）。
    """
    from sqlalchemy import create_engine

    from app.core.config import get_settings
    from app.db.models import USER_STATUS_ACTIVE, Role, User, UserRole
    from app.db.rls import apply_tenant_rls, ensure_exempt_tables_unprotected
    from app.db.session import init_db, session_scope
    from app.services.auth.password import hash_password
    from app.services.rbac import ensure_preset_roles

    settings = get_settings()
    # autouse 夹具跑在 `client`（建 app → lifespan → create_all）**之前**，
    # 此时测试库可能还是空的 ⇒ 先自己建表（create_all 幂等，不会覆盖已有数据）。
    #
    # **P3-A**：建表与落 RLS 策略**必须走 owner**——受限角色无权 ALTER TABLE，
    # 而策略若由业务角色建，等于让被测对象给自己发豁免（裁决 4）。
    owner_engine = create_engine(os.environ["DATABASE_URL_OWNER"])
    try:
        init_db(bind=owner_engine)
        with owner_engine.begin() as connection:
            apply_tenant_rls(connection)
            ensure_exempt_tables_unprotected(connection)
        with session_scope() as session:
            ensure_preset_roles(session)
            roles = {row.name: row.id for row in session.query(Role).all()}
            admin_id = roles["admin"]
    finally:
        owner_engine.dispose()

    # `user_roles` / `users` 都是**租户数据**（含 org_id）⇒ 每个 org 必须在自己的
    # 租户视野里播种（RLS 下跨租户写会被 WITH CHECK 直接拒掉，不是静默失败）。
    #
    # **P2-C**：每个租户 = (一个 org, 一个专属 actor, 一行 users, 一条 admin 授权)。
    # activated_at **刻意留 NULL** —— 它由「首次成功登录」回填，
    # 这里播种就等同于造假席位（P4-D5 明令禁止）。
    # **R30 第 ① 条的"清创"**：删掉 org B 里那条指向 **org A** 主体的历史授权
    # （`user_roles.org_id=B` 而 `user_id=DEFAULT_ACTOR_ID`）。
    # 不删它，严格视图孤儿就永远是 1（`tests/test_identity_anchor.py` 会红）；
    # **只删这一条、绝不泛化清理** —— 泛化会把 `test_rbac.py` 授给其它 actor 的
    # 记录一并删掉，那些是别人的判据。（CI 的库是空的，这条清理对它无副作用。）
    with session_scope(org_id=UUID(OTHER_ORG_ID)) as session:
        session.query(UserRole).filter(
            UserRole.org_id == UUID(OTHER_ORG_ID),
            UserRole.user_id == settings.default_actor_id,
        ).delete(synchronize_session=False)
        # `session_scope` **不**代提交（它只 close），不显式 commit 就是静默回滚
        session.commit()

    tenants = (
        (
            settings.default_org_id,
            settings.default_actor_id,
            DEFAULT_ORG_LOGIN_USERNAME,
        ),
        (UUID(OTHER_ORG_ID), OTHER_ORG_ACTOR_ID, OTHER_ORG_LOGIN_USERNAME),
    )
    for org_id, actor_id, username in tenants:
        with session_scope(org_id=org_id) as session:
            if (
                session.query(User)
                .filter(User.org_id == org_id)
                .filter(User.id == actor_id)
                .first()
                is None
            ):
                session.add(
                    User(
                        id=actor_id,
                        username=username,
                        password_hash=hash_password(DEV_LOGIN_PASSWORD),
                        org_id=org_id,
                        status=USER_STATUS_ACTIVE,
                    )
                )
            exists = (
                session.query(UserRole)
                .filter(UserRole.org_id == org_id)
                .filter(UserRole.user_id == actor_id)
                .filter(UserRole.role_id == admin_id)
                .first()
            )
            if exists is None:
                session.add(
                    UserRole(
                        org_id=org_id,
                        user_id=actor_id,
                        role_id=admin_id,
                        doc_scope=None,
                        scene_scope=None,
                        granted_by=actor_id,
                    )
                )
            session.commit()


@pytest.fixture
def real_pg_get_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """撤销 :func:`pg_active_kg_version` 的桩，恢复 ``get_active`` 真实实现。

    供 :mod:`tests.test_kg_versioning` 里「断言真源状态机本身」的用例使用——
    它们要验的正是「PG 无 ready → None」，不能被上面的默认桩遮蔽。

    ``get_by_version`` 一并恢复（与上面的桩成对，见 :data:`_REAL_GET_BY_VERSION`）。
    """
    monkeypatch.setattr(KgVersioningService, "get_active", _REAL_GET_ACTIVE)
    monkeypatch.setattr(KgVersioningService, "get_by_version", _REAL_GET_BY_VERSION)


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
def dev_login() -> dict[str, str]:
    """默认租户那个**真实账号**的登录凭据（P2-C：`POST /auth/login` 真校验用）。

    与 :func:`dev_headers` 的区别：后者是 dev 脚手架头（不查库、不做口令校验），
    本夹具走的是**真登录**——拿它登录会真的去比对 `users.password_hash`，
    并真的回填 `activated_at`（席位计数的唯一来源）。
    """
    return {
        "username": DEFAULT_ORG_LOGIN_USERNAME,
        "password": DEV_LOGIN_PASSWORD,
    }


@pytest.fixture(scope="session")
def cross_tenant_headers() -> dict[str, str]:
    # **P2-C**：actor 用 org B **自己的**主体（:data:`OTHER_ORG_ACTOR_ID`）——
    # 沿用默认主体会构成跨租户引用（R30 第 ① 条）。跨租户用例验的是
    # 「org A 的资源在 org B 视野下不可见」，与 actor 是否相同无关。
    return {"X-Org-Id": OTHER_ORG_ID, "X-Actor-Id": str(OTHER_ORG_ACTOR_ID)}
