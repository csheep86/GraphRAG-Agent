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

CHUNK_NOT_FOUND: dict[int, dict[str, Any]] = {
    404: {
        "model": ErrorResponse,
        "description": (
            "原文片段不存在（`NOT_FOUND`）：该文档尚未产出 `chunks.json`，"
            "或其中没有该 `chunk_id`。"
            "**跨租户访问返回 403 而非 404**（ADR-0003 / M5 §3 验收 1）"
        ),
    }
}

KG_VERSION_NOT_FOUND: dict[int, dict[str, Any]] = {
    404: {
        "model": ErrorResponse,
        "description": (
            "指定的 `kg_version` 不存在（`NOT_FOUND`）：PG `kg_versions` 真源表中"
            "查不到该 (org_id, version)，或 Neo4j 侧没有该版本的图数据。复用"
            "`ErrorCode.NOT_FOUND`，**不**新增错误码。"
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

AFFILIATION_TASK_NOT_FOUND: dict[int, dict[str, Any]] = {
    404: {
        "model": ErrorResponse,
        "description": (
            "检测任务不存在（`NOT_FOUND`）。"
            "**跨租户访问返回 403 而非 404**（ADR-0003 / M5 §3 验收 1）"
        ),
    }
}

AFFILIATION_SUSPICION_NOT_FOUND: dict[int, dict[str, Any]] = {
    404: {
        "model": ErrorResponse,
        "description": (
            "疑点不存在（`NOT_FOUND`）。"
            "**跨租户访问返回 403 而非 404**（ADR-0003 / M5 §3 验收 1）"
        ),
    }
}

COMPLIANCE_NO_FACTS: dict[int, dict[str, Any]] = {
    409: {
        "model": ErrorResponse,
        "description": (
            "active kg_version 内没有考勤事实（`COMPLIANCE_NO_FACTS`）："
            "查不到 CSV 派生的 `EMPLOYEE` 节点，规则**无从下手**。"
            "与 501 区分——库是通的、版本是对的，只是这份图里没有考勤数据，"
            "请先执行 `scripts/ingest_attendance_csv.py`"
        ),
    }
}

SCHEMA_VERSION_NOT_ACTIVE: dict[int, dict[str, Any]] = {
    409: {
        "model": ErrorResponse,
        "description": (
            "本体 schema 版本冲突（`SCHEMA_VERSION_NOT_ACTIVE`，M6 §5.5）："
            "① `POST /ontology/confirm` 对同一 version **重复确认**；"
            "② `GET /ontology/active` 时本租户**尚无 active schema**。"
            "与 409 `KG_VERSION_NOT_ACTIVE` 同一纪律——**严禁**静默降级到旧版本 / 默认"
            "schema（那会让用户以为自己配过）"
        ),
    }
}

#: **占位**端点的 501 声明（M6 契约先行批次）。
#: ⚠️ 语义冲突登记：项目 `ErrorCode.NOT_IMPLEMENTED` 的既有口径是「**基础设施不可用**」，
#: 明确写了「**不**表示接口未实现」。本批 7 个占位端点复用 501（HTTP 语义即 Not Implemented），
#: 靠 `detail.blocked_by` 区分「功能未实现」与「基础设施故障」。
#: ⇒ 该冲突登记为定稿增补项（F3 裁决）；M6 实现批次替换占位时须一并复核。
PLACEHOLDER_NOT_IMPLEMENTED: dict[int, dict[str, Any]] = {
    501: {
        "model": ErrorResponse,
        "description": (
            "**占位骨架，功能未实现**（M6 契约先行批次）。返回 501，"
            "`detail.blocked_by` 标明「实现归 P5-M6 批次」。"
            "与既有 501（基础设施不可用）靠 `detail` 区分"
        ),
    }
}

ANOMALY_NOT_FOUND: dict[int, dict[str, Any]] = {
    404: {
        "model": ErrorResponse,
        "description": (
            "要归因的对象不存在（`NOT_FOUND`）：员工不在当前 active 版本内，"
            "或该员工在指定日期没有异常记录。"
            "**不**返回零证据的归因结果——那会被读成「系统判断他不成立」，"
            "而实际是根本没查到这个人 / 这一天（Sprint 9.5 批次 C4）"
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
