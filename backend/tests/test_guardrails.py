"""待建护栏测试：G-8 / G-9 / G-10 / G-17 / G-18。

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

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings


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
    """清空 ``audit_log`` / ``qa_logs``——审计由全站中间件写，不清空无法断言本次。"""
    from app.db.models import AuditLog, QaLog
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        session.query(AuditLog).delete()
        session.query(QaLog).delete()
        session.commit()


# --------------------------------------------------------------------------- #
# G-8：CI 起 PostgreSQL（本轮最关键的一条）
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="G-8 / DR-B1 / DR-B2：测试库仍是 SQLite，须切 PostgreSQL 16.x 并让 CI 跑在 PG 上",
)
def test_g8_test_database_is_postgres() -> None:
    """G-3（pytest）当前跑在 SQLite 上 ⇒ PG 相关的一切都没被真实验证过。"""
    assert get_settings().database_url.startswith("postgresql"), (
        "测试库不是 PostgreSQL。现 G-3 的结论不能代表 PG 上的行为。"
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
# G-18：users 表前置（P2 开工闸门）
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="G-18 / DR-B13：users 表未建，SSO(DR-D9) / RBAC(DR-B9) / License(DR-C1) 三条线全部阻塞",
)
def test_g18_users_table_exists() -> None:
    from app.db.models import Base

    assert "users" in Base.metadata.tables, (
        "users 表不存在。它是 DR-D9(SSO) / DR-B9(RBAC) / DR-C1(License 席位) "
        "三者的共同前置，须前置到 P2 第一步。"
    )


# --------------------------------------------------------------------------- #
# G-9：T1 跨 org 越权
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="G-9 / DR-B6 / DR-B11：T1 跨 org 越权，须在 PG 上跑且 RLS 尚未落地",
)
def test_g9_t1_cross_org_read_returns_empty(
    client: TestClient,
    dev_headers: dict[str, str],
    cross_tenant_headers: dict[str, str],
    clean_audit: None,
) -> None:
    """A org 产生审计，B org 查 ⇒ **空集**（不是错误，也不是别人的数据）。

    资源清单（ADR-0003 §4.1）：``documents`` / ``audit_log`` / ``qa_logs`` /
    ``storage_key``。本例覆盖 ``audit_log``；其余资源与**图谱侧**（DR-B11，
    须起 Neo4j 才能真实断言）在 P3 补齐后并入。
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


@pytest.mark.xfail(
    strict=True,
    reason="G-10 / DR-B7 / DR-B8：T2 并发串租户，须在 PG 上跑并覆盖连接池复用路径",
)
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
    """
    _require_postgres()

    assert client.get("/api/v1/documents", headers=dev_headers).status_code == 200

    def probe(headers: dict[str, str]) -> tuple[int, dict]:
        response = client.get("/api/v1/audit", headers=headers)
        return response.status_code, response.json()

    plan = [dev_headers if i % 2 == 0 else cross_tenant_headers for i in range(24)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(probe, plan))

    for headers, (status, body) in zip(plan, results, strict=True):
        assert status == 200
        if headers is cross_tenant_headers:
            assert body["items"] == [], (
                "并发下 B org 看到了 A org 的数据 ⇒ 连接池串租户"
                "（多为 SET LOCAL 误写成会话级 SET，见 DR-B8）"
            )
