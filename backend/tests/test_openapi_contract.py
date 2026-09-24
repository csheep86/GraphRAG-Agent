"""契约测试（F 节验收 4）。

断言对象是 `contracts/openapi.yaml` 的真源——由 Pydantic 模型生成的结构。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.main import app

CORE_PATHS = {
    "/api/v1/health",
    "/api/v1/documents",
    "/api/v1/documents/upload",
    "/api/v1/documents/{document_id}/status",
    "/api/v1/documents/{document_id}/graph",
    # Sprint 6 批次 B：chunk 回查端点（引用溯源，Q2）
    "/api/v1/documents/{document_id}/chunks/{chunk_id}",
    "/api/v1/graph/overview",
    "/api/v1/entities/{entity_id}",
    "/api/v1/agent/query",
    # Sprint 6.3：在线激活端点（真机发现：建图后无人把版本置为可消费）
    "/api/v1/graph/versions/{version}/activate",
    # Sprint 7.2 批次 B：M4 疑点四端点（spec §5.5；路径口径以 spec 为准）
    "/api/v1/affiliation/detect",
    "/api/v1/affiliation/tasks/{task_id}",
    "/api/v1/affiliation/suspicions",
    "/api/v1/affiliation/suspicions/{suspicion_id}",
    # Sprint 8.1 批次 A：M5 审计两个只读端点（plan §7.2 步骤 6 / M5 §3 验收 7）
    "/api/v1/audit",
    "/api/v1/audit/trace/{trace_id}",
}

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}

#: ADR 强制要求的错误码（ADR-0001 / 0002 / 0003）
ADR_REQUIRED_CODES = {"TASK_INTERRUPTED", "KG_VERSION_NOT_ACTIVE", "FORBIDDEN"}

TENANT_PROTECTED_PATHS = CORE_PATHS - {"/api/v1/health"}


@pytest.fixture(scope="module")
def schema() -> dict:
    return app.openapi()


def _operations(schema: dict) -> list[tuple[str, str, dict]]:
    return [
        (path, method, operation)
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]


def test_core_paths_match_contract(schema: dict) -> None:
    """Sprint 5 批次 C 由 5 路径扩为 8 路径；Sprint 6 批次 B 再增
    `GET /documents/{document_id}/chunks/{chunk_id}`（引用溯源，Q2）→ 9 路径；
    Sprint 6.3 再增 `POST /graph/versions/{version}/activate`（在线激活）→ 10 路径；
    Sprint 7.2 批次 B 再增 M4 疑点四端点（`/affiliation/detect` / `/affiliation/tasks/{id}` /
    `/affiliation/suspicions` / `PATCH /affiliation/suspicions/{id}`，spec §5.5）→ **14 路径**；
    Sprint 8.1 批次 A 再增审计两端点（`GET /audit` / `GET /audit/trace/{trace_id}`）→ **16 路径**。
    """
    assert set(schema["paths"]) == CORE_PATHS


def test_chunk_endpoint_declares_tenant_isolation(schema: dict) -> None:
    """新增的 chunk 回查端点必须自带租户隔离与 401/403/404（ADR-0003 / M5 §3 验收 1）。"""
    operation = schema["paths"]["/api/v1/documents/{document_id}/chunks/{chunk_id}"][
        "get"
    ]
    assert operation["operationId"] == "getDocumentChunk"
    parameter_names = {parameter.get("name") for parameter in operation["parameters"]}
    assert {"document_id", "chunk_id"} <= parameter_names
    assert set(operation["responses"]) == {"200", "401", "403", "404"}


def test_operation_ids_are_unique(schema: dict) -> None:
    operation_ids = [
        operation["operationId"] for _, _, operation in _operations(schema)
    ]
    # 10 → 14（Sprint 7.2 批次 B 四个 affiliation 端点）→ 16
    # （Sprint 8.1 批次 A 两个 audit 端点；operation_id 不得重复）
    assert len(operation_ids) == len(set(operation_ids)) == 16


def test_info_version_is_constant(schema: dict) -> None:
    """版本必须是常量，否则导出不可复现、CI diff 永远失败。

    断言对齐 `settings.app_version`（唯一真源）：v1.1.0 前此处硬编码 `"1.0.0"`，
    版本 bump 后未同步，且本地 `.env` 的过期 `APP_VERSION` 覆盖了默认值，
    造成「本地绿、CI 红」（CI #9）。对齐真源后，版本 bump 无需再改此处。
    """
    assert schema["info"]["version"] == get_settings().app_version


def test_error_code_enum_contains_adr_codes(schema: dict) -> None:
    enum = set(schema["components"]["schemas"]["ErrorCode"]["enum"])
    assert ADR_REQUIRED_CODES <= enum
    assert enum == {code.value for code in ErrorCode}


def test_error_response_has_exactly_four_fields(schema: dict) -> None:
    properties = schema["components"]["schemas"]["ErrorResponse"]["properties"]
    assert set(properties) == {"code", "message", "detail", "trace_id"}
    assert set(schema["components"]["schemas"]["ErrorResponse"]["required"]) == {
        "code",
        "message",
        "trace_id",
    }


def test_no_second_error_shape(schema: dict) -> None:
    """所有非 2xx 响应必须复用 ErrorResponse，且不得残留 FastAPI 的 422。"""
    schemas = schema["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas

    for path, method, operation in _operations(schema):
        for status, response in operation["responses"].items():
            if status.startswith("2"):
                continue
            content = response.get("content", {}).get("application/json")
            assert content is not None, (
                f"{method.upper()} {path} {status} 缺少 JSON 错误体"
            )
            assert content["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}


def test_tenant_isolation_declared_on_protected_paths(schema: dict) -> None:
    """ADR-0003 + 阶段 3.1 要求 5：非 health 接口必须显式声明认证与租户头。"""
    for path in TENANT_PROTECTED_PATHS:
        for method, operation in schema["paths"][path].items():
            if method not in HTTP_METHODS:
                continue
            assert operation["security"] == [{"bearerAuth": []}], path
            header_names = {
                parameter["name"]
                for parameter in operation.get("parameters", [])
                if parameter["in"] == "header"
            }
            assert {"X-Org-Id", "X-Actor-Id"} <= header_names, path


def test_health_is_exempt_from_tenant_context(schema: dict) -> None:
    operation = schema["paths"]["/api/v1/health"]["get"]
    assert operation.get("security", []) == []
    assert operation.get("parameters", []) == []


def test_protected_paths_declare_401_and_403(schema: dict) -> None:
    for path, method, operation in _operations(schema):
        if path not in TENANT_PROTECTED_PATHS:
            continue
        assert {"401", "403"} <= set(operation["responses"]), f"{method.upper()} {path}"


def test_graph_declares_version_conflict(schema: dict) -> None:
    """ADR-0002 §3.2：非 active 版本必须 409，而不是静默降级。"""
    responses = schema["paths"]["/api/v1/documents/{document_id}/graph"]["get"][
        "responses"
    ]
    assert "409" in responses


def test_openapi_json_endpoint_serves_same_schema(client: TestClient) -> None:
    """`/openapi.json` 与导出用结构一致（保证前后端读到同一份契约）。"""
    assert client.get("/openapi.json").status_code == 200
