"""限流 429 全链路（M5 §3 验收 5，Sprint 8.1 批次 B，决策 A11 / A14）。

三个实测确认过的关键点（本地读 slowapi 0.1.10 源码，非文档转述）：

1. ``SlowAPIMiddleware.dispatch`` 走 ``sync_check_limits``，对 **async handler
   会静默回落**到 slowapi 默认 handler（``{"error": ...}``，不合 H3、无
   ``Retry-After``）——所以 :func:`app.core.exception_handlers.rate_limit_exceeded_handler`
   必须保持同步函数，本模块的 429 断言就是对这条的回归锁。
2. 中间件捕获异常后**自己调 handler 返回 Response**（不走全局异常处理器栈），
   响应仍流经外层 ``AuditMiddleware``（429 也落一条 failure）与
   ``TraceIdMiddleware``（回显头）。
3. ``Retry-After`` 由 handler 按 ``RateLimitItem.granularity`` 换算（minute→60）。

隔离策略：限流器是 ``lru_cache`` 单例、存储在进程内存——本模块用一个独立
app（``RATE_LIMIT_PER_MINUTE=1``）专测，结束后**恢复环境变量并清缓存**，
不影响其它用例（共享 client 的限流已在 conftest 调到不可触达）。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import ErrorCode, resolve_error_code
from app.core.limiter import get_limiter
from app.db.session import SessionLocal
from app.main import create_app


@pytest.fixture
def tight_client(
    dev_headers: dict[str, str],
) -> Iterator[tuple[TestClient, dict[str, str]]]:
    """`RATE_LIMIT_PER_MINUTE=1` 的独立 app；结束恢复环境与缓存。"""
    old_value = os.environ.get("RATE_LIMIT_PER_MINUTE")
    os.environ["RATE_LIMIT_PER_MINUTE"] = "1"
    get_settings.cache_clear()
    get_limiter.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client, dev_headers
    finally:
        if old_value is None:
            os.environ.pop("RATE_LIMIT_PER_MINUTE", None)
        else:
            os.environ["RATE_LIMIT_PER_MINUTE"] = old_value
        get_settings.cache_clear()
        get_limiter.cache_clear()


# --------------------------------------------------------------------------- #
# 429 响应契约
# --------------------------------------------------------------------------- #


def test_second_request_returns_429_with_contract_body(
    tight_client: tuple[TestClient, dict[str, str]],
) -> None:
    """第 2 次请求（N=1）→ 429 + `{code,message,detail,trace_id}` + Retry-After。"""
    client, headers = tight_client

    first = client.get("/api/v1/documents", headers=headers)
    assert first.status_code == 200, "限内请求应正常放行"

    second = client.get("/api/v1/documents", headers=headers)
    assert second.status_code == 429

    body = second.json()
    assert body["code"] == "RATE_LIMITED"
    assert body["message"] == "Too many requests"
    assert isinstance(body["detail"], dict) and body["detail"], "detail 须为结构化字段"
    assert body["trace_id"], "trace_id 不得为空"

    # Retry-After：minute 窗口 → 60 秒（M5 §3 验收 5 + 批次 B 必做项）
    assert second.headers.get("retry-after") == "60"
    # X-Trace-Id 回显与 body 一致（M5 §3 验收 6）
    assert second.headers.get("x-trace-id") == body["trace_id"]


def test_429_maps_to_rate_limited_not_http_error() -> None:
    """`resolve_error_code(429)` 必须落 `RATE_LIMITED`（矩阵 :133 判据，兜底映射）。"""
    assert resolve_error_code(429) is ErrorCode.RATE_LIMITED
    from app.core.errors import HTTP_STATUS_TO_ERROR_CODE

    assert HTTP_STATUS_TO_ERROR_CODE[429] is ErrorCode.RATE_LIMITED


# --------------------------------------------------------------------------- #
# 审计留痕（A14）
# --------------------------------------------------------------------------- #


def test_rate_limit_writes_audit_log(
    tight_client: tuple[TestClient, dict[str, str]],
) -> None:
    """触发限流同步写 `audit_log(action=rate_limit.triggered)`（A14）。"""
    from uuid import UUID

    client, headers = tight_client
    org_id = UUID(headers["X-Org-Id"])

    client.get("/api/v1/documents", headers=headers)
    triggered = client.get("/api/v1/documents", headers=headers)
    assert triggered.status_code == 429

    from app.db.models import AuditLog
    from app.services.audit import AUDIT_STATUS_VALUES

    triggered_trace = UUID(triggered.json()["trace_id"])
    with SessionLocal() as session:
        # 按本请求 trace_id 过滤：audit 表是共享库，前序用例可能留有同 action 旧行
        rows = (
            session.query(AuditLog)
            .filter(AuditLog.org_id == org_id)
            .filter(AuditLog.action == "rate_limit.triggered")
            .filter(AuditLog.trace_id == triggered_trace)
            .all()
        )
        assert len(rows) == 1, "一次限流只写一条 rate_limit.triggered"
        row = rows[0]
        assert row.status == "failure"
        assert row.trace_id == triggered_trace
        assert row.resource == "GET /api/v1/documents"
        assert row.detail["status_code"] == 429
        assert row.detail["limit"] == "1 per 1 minute"
        assert row.status in AUDIT_STATUS_VALUES


# --------------------------------------------------------------------------- #
# 豁免与放行
# --------------------------------------------------------------------------- #


def test_health_is_exempt_from_rate_limit(
    tight_client: tuple[TestClient, dict[str, str]],
) -> None:
    """health 探针豁免限流（与审计 A1 同一"探针噪声"口径）。"""
    client, headers = tight_client
    for _ in range(3):
        response = client.get("/api/v1/health", headers=headers)
        assert response.status_code == 200, "health 不得被 429"


def test_different_paths_do_not_share_quota(
    tight_client: tuple[TestClient, dict[str, str]],
) -> None:
    """默认限按「每接口」计（M5 §3 验收 5 原文）：A 接口打满不影响 B 接口。"""
    client, headers = tight_client

    assert client.get("/api/v1/documents", headers=headers).status_code == 200
    assert client.get("/api/v1/documents", headers=headers).status_code == 429

    other = client.get("/api/v1/audit", headers=headers)
    assert other.status_code != 429, "另一接口不应被同 IP 的 A 接口配额连坐"
