"""护栏测试：G-8 / G-9 / G-10 / G-17 / G-18。

**2026-10-01（P1-C）状态更新**：随测试库切到 PostgreSQL，**G-8 与 G-9（PG 侧 +
``audit_log`` 部分）已由 xfail 骨架转正常驻门禁**。

**2026-10-01（P2-A）再更新**：``users`` 表已建，**G-18 转正常驻门禁**（判据同时
从「表存在」加强为「列集合 = spec §4.1 + ``org_id`` 打头索引 + ``username`` 唯一」）。
⚠️ 它**只**解除三条线的**前置阻塞**：本表当前 **0 消费者**，
RBAC 归 P2-B、SSO 归 P2-C、License 归 P4，**不得**因本条转正宣称账号体系已完成。
本文件仍挂起的只剩 **G-10**（T2 并发，须先有 RLS，归 P3）。
真实状态一律以 ``check_startup_readiness.py`` 的输出为准，别只看本文注释。

对应 ``docs/delivery-requirements-and-guardrails.md`` §2.2。

## 关于 ``xfail(strict=True)`` 的用法（先读这段）

需求尚未完成 ⇒ 断言必然失败 ⇒ 记为 **XFAIL**（CI **保持绿**，且 ``-rs`` 会把
原因逐条打进日志）；需求完成后断言通过 ⇒ XPASS，而 ``strict=True`` **判为失败**，
强制来人摘掉 ``xfail`` 标记 ⇒ 护栏自动转为常驻门禁。

这样护栏可以**先于需求就位**，不会因"需求没做完"把 CI 染红；同时 ``-rs`` 的
日志让「哪些护栏还没真正生效」始终**可见**——不留在沉默里（与 CI 里"本地独占用例
单独跑一遍只为让 skip 原因写在日志里"是同一条纪律）。

**摘标记的时机就是该需求被宣称完成的时机**：谁摘，谁就在声明"这条已达成"。
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID as _UUID
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.core.config import Settings, get_settings

#: T1 / T2 用的第二个租户（与 conftest 的 ``OTHER_ORG_ID`` 同值）
OTHER_ORG_ID = "00000000-0000-4000-8000-000000000002"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
APP_ROOT = BACKEND_ROOT / "app"

#: **DR-B2 锁定 PostgreSQL 16.x**。光判「是 PG」不够——CI 哪天被换成 15 / 17
#: 也照样绿，方言债就是从这种"看起来一样"里重新渗进来的（RK-2 的成因）。
PG_MAJOR_VERSION = "16"


def _require_postgres() -> None:
    """T1 / T2 的硬前提：必须跑在 PostgreSQL 上（ADR-0003 §4.1）。

    在 SQLite 上跑通的"跨租户隔离"什么都不证明——SQLite 没有 RLS，
    而 T1 / T2 验的正是 RLS 与连接池 ``SET LOCAL`` 的行为。
    """
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.fail(
            f"T1/T2 必须在 PostgreSQL 上执行，当前库为 {url.split('://')[0]}"
            "（DR-B1 / DR-B2 未完成，见 delivery-requirements-and-guardrails.md §2.2 G-8）"
        )


@pytest.fixture
def clean_audit() -> None:
    """清空 ``audit_log`` / ``qa_logs``——审计由全站中间件写，不清空无法断言本次。

    **A10（P3-A）**：RLS 之后「清空」必须**逐租户**——一个会话只看见一个 org 的行。
    只清默认 org 会把 org B 的历史行留在库里，而本文件的 T1 断言的正是
    「org B 视角下不该看到 org A 的行」⇒ 残留会让它**假红**（看起来像泄漏）。
    """
    from uuid import UUID as _UUID

    from app.db.models import AuditLog, QaLog
    from app.db.session import session_scope

    for org_id in (
        get_settings().default_org_id,
        # 与 conftest 的 ``OTHER_ORG_ID`` 同值（T1 用的第二个租户）
        _UUID("00000000-0000-4000-8000-000000000002"),
    ):
        with session_scope(org_id=org_id) as session:
            session.query(AuditLog).delete()
            session.query(QaLog).delete()
            session.commit()


# --------------------------------------------------------------------------- #
# G-8：CI 起 PostgreSQL —— **已转正（2026-10-01，P1-C）**
# --------------------------------------------------------------------------- #


def test_g8_test_database_is_postgres() -> None:
    """✅ **已转正（2026-10-01，P1-C）**：CI 的 pytest 跑在 PostgreSQL **16.x** 上。

    转正常驻门禁后守两件事：

    1. **方言**：测试库必须是 PG。在 SQLite 上跑出来的结论（尤其租户隔离 T1 / T2）
       什么都不证明——SQLite 没有 RLS，也没有 ``SET LOCAL``（ADR-0003 §4.1）。
    2. **大版本**：必须是 **16.x**。DR-B2 锁的是具体大版本，不是「任意 PG」；
       ``ci.yml`` 的 ``services.postgres`` 与 ``deploy/docker-compose.yml`` 同 tag，
       任一侧漂移都得在这里被叫住。
    """
    url = get_settings().database_url
    assert url.startswith("postgresql"), (
        f"测试库不是 PostgreSQL（当前 {url.split('://')[0]}）——"
        "G-3 的结论不能代表 PG 上的行为（DR-B2）"
    )

    # 真连一次再判版本：URL 前缀只能证明"配的是 PG"，证明不了对面真跑着 16.x。
    # ``SHOW server_version`` 形如 `16.9 (Debian 16.9-1…)`，取首位即大版本。
    from app.db.session import engine

    with engine.connect() as connection:
        raw = connection.execute(text("SHOW server_version")).scalar_one()

    major = str(raw).split(".", 1)[0]
    assert major == PG_MAJOR_VERSION, (
        f"测试库须为 PostgreSQL {PG_MAJOR_VERSION}.x，实测 {raw}。"
        "请核对 ci.yml 的 services.postgres 与 compose 的 PG tag"
    )


# --------------------------------------------------------------------------- #
# G-17：fail-open 逃生阀围栏（**已完成实现，非骨架**）
# --------------------------------------------------------------------------- #


def test_g17_silently_disabling_isolation_is_rejected() -> None:
    """无声关闭跨租户隔离 ⇒ 配置校验失败（服务起不来）。

    ``agent_fail_closed=False`` 会让泄漏从「403 阻断」退化成「仅告警放行」，
    这是全系统唯一一个可配置关闭租户隔离的开关。
    """
    with pytest.raises(ValidationError, match="ALLOW_AGENT_FAIL_OPEN"):
        Settings(_env_file=None, agent_fail_closed=False, allow_agent_fail_open=False)


def test_g17_explicit_registration_allows_break_glass() -> None:
    """显式登记后允许破例——破例本身被允许，但**不许无声**。

    破例须同时完成「登记 + 告知客户 + 落审计」三项（与信创降级 DR-B10 同级）。
    """
    settings = Settings(
        _env_file=None, agent_fail_closed=False, allow_agent_fail_open=True
    )
    assert settings.agent_fail_closed is False


def test_g17_default_is_fail_closed() -> None:
    """默认值必须是 fail-closed（True）。"""
    assert Settings(_env_file=None).agent_fail_closed is True


# --------------------------------------------------------------------------- #
# G-18：users 表前置 —— ✅ 已转正（2026-10-01，P2-A）
# --------------------------------------------------------------------------- #

#: `specs/m5-permission-audit.md` §4.1 的 7 列（**不多不少**）
USER_COLUMNS = frozenset(
    {
        "id",
        "username",
        "password_hash",
        "org_id",
        "status",
        "created_at",
        "updated_at",
    }
)

#: **2026-10-06 P4 追加**：ADR-0006 §2.4 维度 2「席位 = 已激活且可登录」的谓词列。
#: 这两列 spec §4.1 里没有 —— 它们由 **ADR-0006**（DR-C1 席位口径）引入，
#: 缺了它们 License **算不出席位数**（补了 users 行也没用，见 §8 R29 的实测）。
#: ⇒ 判据从「恰好 7 列」放宽为「恰好 7 列 **+ 这 2 列**」：
#: **严格度不变**（任何**第四方**列仍会被下面的相等断言判红），只是把新的 ADR 来源显式登记进来。
SEAT_COLUMNS = frozenset({"activated_at", "disabled_at"})

#: **2026-10-07 P2-C**：外部身份的两列（子任务 ②）。与上面 `SEAT_COLUMNS` 同款处置——
#: **判据严格度不变**（任何**第五方**列仍会被下面的相等断言判红），只是把新的来源
#: 显式登记进来。两列**当前 0 消费者**：本地登录按 `username` 查，它们是给
#: 「接缝 1 第二实现（企业身份源）」留的查找键，启用条件登记在
#: `docs/adr/0004-integration-seams.md`（功能预留原则第 5 条）。
#: ⚠️ **不进契约**：`export_openapi.py --check` 必须仍是零 diff。
EXTERNAL_IDENTITY_COLUMNS = frozenset({"issuer", "subject"})


def test_g18_users_table_exists() -> None:
    """✅ **已转正（2026-10-01，P2-A）**：`users` 表已建，本例由 XPASS 转常驻门禁。

    转正的同时**把判据加强**（与 P1-C 给 G-8 补 16.x 断言同类动作：只摘 xfail 不算
    转正，判据太弱等于假防御）。原判据只看「有没有一张叫 users 的表」——删掉
    `org_id`、改名 `username`，它照样绿。现判四条：

    1. 表存在；
    2. **列集合逐字等于** `specs/m5-permission-audit.md` §4.1 的 7 列（不多不少）；
    3. 存在 **ADR-0003 §3.1 要求的 `org_id` 打头索引**（RLS 策略的性能前提）；
    4. `username` 有唯一约束（登录名不允许撞车）。

    ⚠️ **转正 ≠ 账号体系已完成**：本表当前 **0 消费者**（无登录 / 无 RBAC / 无 License），
    它只是这三条线的**共同前置**。接线分属 P2-B（RBAC）/ P2-C（SSO）/ P4（License）。
    """
    from sqlalchemy import UniqueConstraint

    from app.db.models import Base

    assert "users" in Base.metadata.tables, (
        "users 表不存在。它是 DR-D9(SSO) / DR-B9(RBAC) / DR-C1(License 席位) "
        "三者的共同前置，须前置到 P2 第一步。"
    )
    users = Base.metadata.tables["users"]

    columns = {column.name for column in users.columns}
    expected = set(USER_COLUMNS) | SEAT_COLUMNS | EXTERNAL_IDENTITY_COLUMNS
    assert columns == expected, (
        "users 的列必须逐字等于 specs/m5-permission-audit.md §4.1 的 7 列"
        "**加上 ADR-0006 §2.4 的两列席位列**"
        "**加上 ADR-0004 登记的两列外部身份预留列**："
        f"多 {sorted(columns - expected)}，缺 {sorted(expected - columns)}"
    )
    # 保留「spec 7 列一个都不能少」的原判据（上面放宽的那句容易被误读为整体放宽）
    assert set(USER_COLUMNS) <= columns, (
        f"spec §4.1 的 7 列被删减：{sorted(set(USER_COLUMNS) - columns)}"
    )

    leading_columns = {next(iter(index.columns.keys())) for index in users.indexes}
    assert "org_id" in leading_columns, (
        "users 缺少 org_id 打头的索引（ADR-0003 §3.1 第 1 条）："
        f"现有索引首列为 {sorted(leading_columns)}"
    )

    uniques = {
        frozenset(column.name for column in constraint.columns)
        for constraint in users.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert frozenset({"username"}) in uniques, (
        "users.username 缺少唯一约束（spec §4.1 标注 unique）："
        f"现有唯一约束为 {sorted(sorted(cols) for cols in uniques)}"
    )


#: `users` 表的**消费者登记**——RK-4「表已建 ≠ 账号体系落地」的机械处置。
#: **空集合 = 表已建、无人读它**。P2-B（RBAC）/ P2-C（SSO）/ P4（License）接线时，
#: 把引用 `User` 的模块**登记进来**——登记动作本身就是那批的开工闸门。
#: **2026-10-06 P4（DR-C1 License）登记**：`services/license/policy.py` 是 `users` 的
#: **第一个真实消费者**（`count_seats`= 席位口径的唯一实现）。一并交代要求的四件事：
#: ① **归属 DR-C1**（ADR-0006 §2.4 维度 2：席位数 = 已激活且未停用的用户）；
#: ② 所需两列 `activated_at` / `disabled_at` **随本批迁移** `f3a91c2d6b70` 补（**不**在 P2-A 预置）；
#: ③ 接缝 1（AuthProvider）**不受影响**，本批新增的是**接缝 9**（LicenseProvider），
#:    登记真源为 **ADR-0006 §4**（ADR-0004 §2.1 的八个接缝数量与编号不变）；
#: ④ #: ④ 提示早boost只是这里被登记了 —— G-23 转正仍必须看自身判据（行为侧 403 + 落审计）， —— G-23 转正仍必须看自身判据（行为侧 403 + 落审计），
#:    **不得**因为引用了 User 就宣称 License / 账号体系完工。
#: ⚠️ 即便登记了，`app/` 下**仍无端点直接读 users** ⇒ 仍不得宣称账号体系落地。
#: **2026-10-07 P2-C 登记**（第二批、第三批真实消费者）。一并交代四件事：
#: ① **归属 DR-D9**（真实登录）+ **DR-B9**（RBAC 判定）——本批把 `users.status`
#:    接进 RBAC（D4），并把「首次成功登录」接成 `activated_at` 的回填点；
#: ② 所需列：两处**都不**需要新列 —— `status` / `password_hash` / `activated_at`
#:    已随 P2-A / P4 的迁移就位；本批只加预留列 `issuer` / `subject`（**随本批迁移**补）；
#: ③ 接缝 1 若因此新增实现 ⇒ **没有**（D1 顺延）。登录**不**造第二个 `AuthProvider`：
#:    它只查库验口令，令牌签发/验签落在 `app/core/token.py`（核心原语，不是接缝实现）；
#: ④ 对应护栏：G-18 三条**仍绿**（users 表形状未变）+ G-26（新增受控函数已登记）
#:    + 契约零漂移 ⇒ **仍不得**宣称账号体系 / SSO 完成
#:      （见 `changes/archive/2026-10-07-P2-C/proposal.md` §5；该批已于 2026-10-07 归档）。
USERS_CONSUMER_MODULES: frozenset[str] = frozenset(
    {
        "services/license/policy.py",
        "services/auth/login.py",
        "services/rbac/service.py",
    }
)


def test_g18_users_consumers_are_registered() -> None:
    """把「G-18 转正 ≠ 账号体系落地」这条边界**钉成机械判据**。

    **为什么不能只写在文档里**：proposal / 基线文档都写了这条边界，但三个月后没人会翻，
    而 G-18 的绿灯**看起来**就像"用户体系做完了"。所以这里卡一道：
    `app/` 下任何引用 `User` 模型的地方，都必须**先**登记进
    :data:`USERS_CONSUMER_MODULES` 才允许存在——和 CODEBUDDY.md
    「预留必须有登记」是同一条纪律，只是这里拦的是**引用**而不是字段。

    登记时必须**同时**交代四件事，否则不许放行：

    1. 它服务哪条 DR（DR-B9 RBAC / DR-D9 SSO / DR-C1 License 席位）；
    2. 需要的列（外部身份 / 席位关联）**随该批自己的迁移**补，不在 P2-A 预置；
    3. 接缝 1 若因此新增实现，先扩写 ADR-0004 §2.1 登记行再改 `get_auth_provider()`；
    4. 对应护栏（G-24 / 接缝门禁）同步转正——**没转正就仍不得宣称完成**。

    ⚠️ 本条**不**拦"表还没人用"：那正是本批的预期状态（0 消费者）。它拦的是
    "有人开始用了，却没登记、没交代归属" —— 那才是悄悄把半成品说成完工的路径。
    """
    hits = sorted(
        path.relative_to(APP_ROOT).as_posix()
        for path in APP_ROOT.rglob("*.py")
        if path.name != "models.py"  # models.py 是定义处，不是消费者
        and re.search(r"\bUser\b", path.read_text(encoding="utf-8"))
    )
    unregistered = [module for module in hits if module not in USERS_CONSUMER_MODULES]
    assert not unregistered, (
        "以下模块引用了 User 模型但**未登记**："
        f"{unregistered} ⇒ 请登记进 USERS_CONSUMER_MODULES 并同时交代："
        "① 归属哪条 DR；② 所需列随本批迁移补；③ 接缝 1 是否需扩写 ADR-0004 §2.1；"
        "④ 对应护栏是否同步转正"
    )
    # 反向：登记了却查不到引用 ⇒ 登记成僵尸，同样不许
    stale = sorted(USERS_CONSUMER_MODULES - set(hits))
    assert not stale, (
        f"USERS_CONSUMER_MODULES 里登记了 {stale}，但代码里已无对应引用 ⇒ 登记必须随代码走"
    )


def test_g18_password_hash_is_not_in_public_contract() -> None:
    """`password_hash` 是敏感字段（M5 §3 验收 3 / §4.5）：**不得**出现在契约里。

    `users` 本批不对外暴露任何端点 ⇒ 契约里既不该有 users schema，也不该出现
    `password_hash` 字样。这条防的是「日后加 /users 端点时顺手把哈希吐出去」。
    """
    from app.db.models import Base

    contract = (REPO_ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8")
    assert "password_hash" not in contract, (
        "password_hash 出现在 contracts/openapi.yaml —— 敏感字段不得进契约"
    )
    assert "users" in Base.metadata.tables  # 本条随 G-18 一起生效，避免表被删后静默恒绿


# --------------------------------------------------------------------------- #
# G-9：T1 跨 org 越权 —— **已转正（2026-10-01，P1-C）：PG 侧 + audit_log 部分**
# --------------------------------------------------------------------------- #


def test_g9_t1_cross_org_read_returns_empty(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
    clean_audit: None,
) -> None:
    """A org 产生审计，B org 查 ⇒ **空集**（不是错误，也不是别人的数据）。

    ✅ **已转正（2026-10-01，P1-C）**：测试库切到 PG 后本例由 ``XPASS(strict)``
    转为常驻门禁——留在 xfail 里，CI 会一直红。

    ⚠️ **转正的边界，不许外推**：本条**只**证明「**应用层 ``org_id`` 过滤**在 PG 上
    拦住了跨 org 读」，这正是 ADR-0003 §3.7 定下的**常设防线**；它**不代表** RLS
    已落地（DR-B4 仍归 P3）。资源清单（ADR-0003 §4.1）里的 ``documents`` /
    ``qa_logs`` / ``storage_key`` 与**图谱侧**（DR-B11，须起 Neo4j 才能真实断言）
    均在 P3 补齐后并入。
    """
    _require_postgres()

    assert client.get("/api/v1/documents", headers=dev_headers).status_code == 200

    own = client.get("/api/v1/audit", headers=dev_headers)
    assert own.status_code == 200
    assert own.json()["total"] >= 1, "A org 自己应当能看到自己的审计"

    other = client.get("/api/v1/audit", headers=cross_tenant_headers)
    assert other.status_code == 200
    assert other.json()["items"] == [], "B org 看到了 A org 的审计 ⇒ 跨租户越权"


# --------------------------------------------------------------------------- #
# G-10：T2 并发串租户（须覆盖连接池复用路径）
# --------------------------------------------------------------------------- #


def test_g10_t2_concurrent_requests_do_not_cross_tenants(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
    clean_audit: None,
) -> None:
    """多 org 并发 ⇒ 每个请求只见自己的数据。

    **为什么要并发**：``SET LOCAL app.current_org`` 若误写成 ``SET``（会话级），
    单线程测试完全测不出来——连接一旦被归还并被下一个租户复用，org 就串了。
    因此本例必须并发，且要让连接池**真复用**连接。

    **2026-10-04（P3-A 转正）：断言口径改为「标记行」**
    原断言是「B org 的响应 ``items == []``」。RLS 生效后**该断言恒不成立**：
    这 24 个并发请求**本身就是 B 的请求**，中间件会在响应后为 B 各写一条审计，
    于是靠后的 B 请求理应看到靠前的 B 请求留下的行——那是 B **自己的**数据。
    「空」既不是隔离的目标，也不是隔离的结果；把它当判据会让本例在正确实现下
    依然红（也就是永远转不了正）。

    故改为：并发前给两个 org 各插一条**可区分的标记行**，
    判据是「每个响应**必须**看到本 org 的标记、**绝不能**看到对方的标记」——
    这既判「串没串」，也不依赖并发调度的偶然顺序。
    """
    _require_postgres()

    org_a = get_settings().default_org_id
    org_b = _UUID(OTHER_ORG_ID)
    marker_a = _seed_audit_marker(org_a, "tenant.marker.a")
    marker_b = _seed_audit_marker(org_b, "tenant.marker.b")
    try:

        def probe(headers: dict[str, str]) -> tuple[int, dict]:
            response = client.get("/api/v1/audit", headers=headers)
            return response.status_code, response.json()

        plan = [dev_headers if i % 2 == 0 else cross_tenant_headers for i in range(24)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(probe, plan))

        for headers, (status, body) in zip(plan, results, strict=True):
            assert status == 200
            actions = {item["action"] for item in body["items"]}
            own, foreign = (
                ("tenant.marker.a", "tenant.marker.b")
                if headers is dev_headers
                else ("tenant.marker.b", "tenant.marker.a")
            )
            assert own in actions, (
                f"并发下本 org 竟看不到自己的标记行（{own}）——"
                "审计写入丢了租户？那样 T2 就成了空跑"
            )
            assert foreign not in actions, (
                f"并发下看到了对方 org 的标记行（{foreign}）⇒ 连接池串租户"
                "（多为 SET LOCAL 误写成会话级 SET，见 DR-B8）"
            )
    finally:
        _delete_audit_markers([marker_a, marker_b])


def _seed_audit_marker(org_id: _UUID, action: str) -> _UUID:
    """给某个 org 插一条**只属于它**的审计行（T2 的判据锚点）。"""
    from app.db.models import AuditLog
    from app.db.session import session_scope

    with session_scope(org_id=org_id) as session:
        row = AuditLog(
            org_id=org_id,
            ts=datetime.now(UTC),
            action=action,
            actor_id=get_settings().default_actor_id,
            actor_ip="testclient",
            resource="POST /api/v1/__tenant_marker__",
            status="success",
            trace_id=uuid4(),
            detail={"marker": True},
        )
        session.add(row)
        session.commit()
        return row.id


def _delete_audit_markers(row_ids: list[_UUID]) -> None:
    from sqlalchemy import delete

    from app.db.models import AuditLog
    from app.db.session import session_scope

    for org_id in (get_settings().default_org_id, _UUID(OTHER_ORG_ID)):
        with session_scope(org_id=org_id) as session:
            session.execute(delete(AuditLog).where(AuditLog.id.in_(row_ids)))
            session.commit()
