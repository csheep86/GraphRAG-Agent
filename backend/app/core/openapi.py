"""OpenAPI 文档构建：`contracts/openapi.yaml` 的唯一生成入口。

设计要点（保证阶段 3.3 的 CI `git diff --exit-code` 可用）：
1. 契约由 FastAPI 从 Pydantic 模型**生成**，后端模型是唯一真源；
2. 移除 FastAPI 自动生成的 `422 / HTTPValidationError`——本项目所有校验失败
   统一返回 400 + `VALIDATION_ERROR`（见 `core/exception_handlers.py`），
   契约中不得出现第二种错误体结构；
3. `info.version` 取常量 `APP_VERSION`，不含时间戳等易变字段；
4. 顶层路径按字典序排列，导出时再 `sort_keys=True`，确保字节级可复现。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.config import get_settings
from app.core.errors import ERROR_CODE_DESCRIPTIONS, ERROR_CODE_SOURCES, ErrorCode

API_DESCRIPTION = """
GraphRAG-Agent 后端 API（契约 v1.0，Sprint 1）。

## 租户隔离（ADR-0003，**所有接口强制**）
- `org_id` **只能**来自认证态：`Authorization: Bearer <token>` 解析结果；
  **严禁**从请求 body / query 读取。
- 开发态兜底（`ALLOW_DEV_ORG_HEADER=true` 且非生产）可用 `X-Org-Id` / `X-Actor-Id` 请求头，
  该兜底 **Sprint 3 必须移除**。
- 跨租户访问一律 `403 FORBIDDEN`；`org_id` 过滤**必须**经 ORM / 统一注入，禁止裸写 SQL。
- **例外**：`GET /api/v1/health` 不要求认证、不返回任何业务数据。

## trace_id（M1 验收 7 / M5 §5.3）
- 请求头 `X-Trace-Id` 可选透传（必须是合法 UUID），缺失则服务端生成 UUIDv4；
- 响应头 `X-Trace-Id` 恒回显；错误体 `trace_id` 与之一致。

## 统一错误响应
所有 4xx / 5xx 均为 `{code, message, detail, trace_id}`，`code` 取自 `ErrorCode` 枚举。

## 图谱版本一致性（ADR-0002）
查询层只认 `kg_version.status = active`。请求显式指定非 active 版本时，
一律返回 `409 KG_VERSION_NOT_ACTIVE`，**严禁静默降级**到最新版本。

## 实现状态（Sprint 4）
五个接口均已实装真实链路；`501 NOT_IMPLEMENTED` 不再表示「接口未实现」，而是
**基础设施故障**（Neo4j 不可用 / LLM 未配置或装配失败）的统一出口。
""".strip()

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "health",
        "description": "健康检查。**唯一豁免租户上下文的接口**，不返回业务数据。",
    },
    {
        "name": "documents",
        "description": "M1 文档接入与异步解析（上传 / 状态 / 图谱子图）。**全部要求租户上下文**。",
    },
    {
        "name": "agent",
        "description": "M3 图谱问答与可溯源引用。**全部要求租户上下文**。",
    },
    {
        "name": "audit",
        "description": (
            "M5 审计留痕（只读查询）。写入由审计中间件统一完成，本 tag 下只有两个查询端点；"
            "**全部要求租户上下文**，返回项已按 `org_id` 过滤。"
        ),
    },
]


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """构造用于导出的 OpenAPI 3.1 结构。"""
    settings = get_settings()
    schema = get_openapi(
        title=settings.app_name,
        version=settings.app_version,
        description=API_DESCRIPTION,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )

    # 路径已内嵌 /api/v1 前缀，servers 只声明同源根，避免出现双重前缀
    schema["servers"] = [
        {"url": "/", "description": "同源部署（开发默认；生产由网关注入实际域名）"}
    ]

    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})

    # 1) 统一错误体：删除 FastAPI 自动注入的 422 与其专属模型
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if isinstance(responses, dict):
                responses.pop("422", None)

    # 2) 错误码枚举补充语义与决策来源（前端 / 人工阅读用）
    error_code_schema = schemas.get("ErrorCode")
    if isinstance(error_code_schema, dict):
        error_code_schema["description"] = (
            "统一业务错误码。HTTP 状态码与业务错误码分离（CODEBUDDY.md 错误响应规范）。"
        )
        error_code_schema["x-enum-descriptions"] = {
            code.value: ERROR_CODE_DESCRIPTIONS[code] for code in ErrorCode
        }
        error_code_schema["x-enum-sources"] = {
            code.value: ERROR_CODE_SOURCES[code] for code in ErrorCode
        }

    # 3) 路径排序，保证导出可复现
    paths = schema.get("paths", {})
    schema["paths"] = {key: paths[key] for key in sorted(paths)}

    return schema
