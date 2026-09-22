"""接口级响应的可复用声明（保证契约中错误分支齐全且措辞统一）。"""

from __future__ import annotations

from typing import Any

from app.schemas.common import ErrorResponse

UNAUTHORIZED: dict[int, dict[str, Any]] = {
    401: {
        "model": ErrorResponse,
        "description": "缺少或无法解析认证态（`UNAUTHORIZED`）",
    }
}

FORBIDDEN: dict[int, dict[str, Any]] = {
    403: {
        "model": ErrorResponse,
        "description": "跨租户访问被拒（`FORBIDDEN`，ADR-0003 §3.3 / M5 §3 验收 1）",
    }
}

#: 所有要求租户上下文的接口都必须声明
TENANT_ERROR_RESPONSES: dict[int, dict[str, Any]] = {**UNAUTHORIZED, **FORBIDDEN}

FILE_TOO_LARGE: dict[int, dict[str, Any]] = {
    413: {
        "model": ErrorResponse,
        "description": "上传文件超过 `MAX_UPLOAD_SIZE_MB`（`FILE_TOO_LARGE`，M1 验收 2）",
    }
}

UNSUPPORTED_MEDIA_TYPE: dict[int, dict[str, Any]] = {
    415: {
        "model": ErrorResponse,
        "description": "MIME 不在白名单（`UNSUPPORTED_MEDIA_TYPE`，M1 验收 3）",
    }
}

DOCUMENT_NOT_FOUND: dict[int, dict[str, Any]] = {
    404: {
        "model": ErrorResponse,
        "description": (
            "文档不存在（`DOCUMENT_NOT_FOUND`）。"
            "**跨租户访问返回 403 而非 404**（ADR-0003 / M5 §3 验收 1）"
        ),
    }
}

ENTITY_NOT_FOUND: dict[int, dict[str, Any]] = {
    404: {
        "model": ErrorResponse,
        "description": (
            "实体不存在（`ENTITY_NOT_FOUND`）。"
            "**跨租户访问返回 403 而非 404**（ADR-0003 / M5 §3 验收 1；Sprint 5 批次 C）"
        ),
    }
}

KG_VERSION_NOT_ACTIVE: dict[int, dict[str, Any]] = {
    409: {
        "model": ErrorResponse,
        "description": (
            "指定的 `kg_version` 非 active（`KG_VERSION_NOT_ACTIVE`）。"
            "**严禁静默降级**到最新 active 版本（ADR-0002 §3.2）"
        ),
    }
}

KG_TENANT_LEAK: dict[int, dict[str, Any]] = {
    403: {
        "model": ErrorResponse,
        "description": (
            "403 跨租户拒绝，两种成因：① `FORBIDDEN`（ADR-0003 §3.3）——"
            "请求资源 org_id 不符；② `KG_TENANT_LEAK`（ADR-0003 §4，Sprint 5 批次 B）——"
            "fail-closed 校验发现 active kg_version 内存在不属于当前 org 的节点，"
            "属数据质量事故伪装为正常结论，**不**降级为拒答（200）"
        ),
    }
}

VALIDATION_ERROR: dict[int, dict[str, Any]] = {
    400: {
        "model": ErrorResponse,
        "description": "请求校验失败（`VALIDATION_ERROR`），`detail.errors` 给出字段级原因",
    }
}

NOT_IMPLEMENTED: dict[int, dict[str, Any]] = {
    501: {
        "model": ErrorResponse,
        "description": (
            "基础设施不可用（Neo4j 连接失败 / 查询超时，或 LLM 未配置、装配失败）时返回 501"
            "（`NOT_IMPLEMENTED`）"
        ),
    }
}
