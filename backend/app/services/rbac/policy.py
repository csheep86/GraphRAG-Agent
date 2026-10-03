"""**角色 × 资源 × 操作**矩阵（DR-B9 / G-24 的"矩阵存在"判据本体）。

三条边界（P2-B 已钉死，改这里等于越界）：

1. **资源清单只能取自 `contracts/openapi.yaml` 里已存在的端点**——
   :data:`CONTRACT_PATH_RESOURCE` 是「契约端点 → 资源」的**逐条登记**，
   由 `tests/test_rbac.py::test_contract_paths_are_all_registered` 双向核对：
   契约里多一条路径没登记 ⇒ 红；登记了一条契约里没有的路径 ⇒ 红。
   ⇒ **凭空造资源类型在本仓不可能悄悄发生。** `/health` 是唯一豁免（探针，无业务对象）。
2. **角色集合封闭**：只有 :class:`app.services.rbac.roles.RoleName` 的四档。
3. **具体赋权属实现决策**（G-24 只断言矩阵存在、不断言取值）⇒ 本文件的取值与理由
   登记在 `changes/P2/integration-log.md`，改值须同步改那里。

**第二 / 第三粒度**（文档 `doc_scope`、场景 `scene_scope`）不在这张表里：
它们是**授权实例**上的收窄条件（同一角色，不同人可见的文档 / 场景不同），
判定逻辑见 :mod:`app.services.rbac.service`。
"""

from __future__ import annotations

from app.services.rbac.roles import RoleName

# --------------------------------------------------------------------------- #
# 资源：逐条登记自 contracts/openapi.yaml（键 = 契约里的完整路径）
# --------------------------------------------------------------------------- #

RESOURCE_AFFILIATION = "affiliation"
RESOURCE_AGENT = "agent"
RESOURCE_AUDIT = "audit"
RESOURCE_COMPLIANCE = "compliance"
RESOURCE_COST = "cost"
RESOURCE_DOCUMENT = "document"
RESOURCE_GRAPH = "graph"
RESOURCE_ONTOLOGY = "ontology"

#: 契约端点 → 资源。**键必须与 `contracts/openapi.yaml` 的 `paths` 逐字一致**
#: （`/api/v1/health` 除外——它是探针，不承载业务对象，故不登记）。
CONTRACT_PATH_RESOURCE: dict[str, str] = {
    "/api/v1/affiliation/detect": RESOURCE_AFFILIATION,
    "/api/v1/affiliation/suspicions": RESOURCE_AFFILIATION,
    "/api/v1/affiliation/suspicions/{suspicion_id}": RESOURCE_AFFILIATION,
    "/api/v1/affiliation/tasks/{task_id}": RESOURCE_AFFILIATION,
    "/api/v1/agent/query": RESOURCE_AGENT,
    "/api/v1/attendance/anomalies": RESOURCE_COMPLIANCE,
    "/api/v1/attendance/anomalies/explain": RESOURCE_COMPLIANCE,
    "/api/v1/attendance/compliance/scan": RESOURCE_COMPLIANCE,
    "/api/v1/audit": RESOURCE_AUDIT,
    "/api/v1/audit/trace/{trace_id}": RESOURCE_AUDIT,
    "/api/v1/cost/dashboard": RESOURCE_COST,
    "/api/v1/documents": RESOURCE_DOCUMENT,
    "/api/v1/documents/upload": RESOURCE_DOCUMENT,
    "/api/v1/documents/{document_id}/chunks/{chunk_id}": RESOURCE_DOCUMENT,
    "/api/v1/documents/{document_id}/graph": RESOURCE_DOCUMENT,
    "/api/v1/documents/{document_id}/status": RESOURCE_DOCUMENT,
    "/api/v1/entities/{entity_id}": RESOURCE_GRAPH,
    "/api/v1/graph/overview": RESOURCE_GRAPH,
    "/api/v1/graph/versions/{version}/activate": RESOURCE_GRAPH,
    "/api/v1/ontology/active": RESOURCE_ONTOLOGY,
    "/api/v1/ontology/cold-start": RESOURCE_ONTOLOGY,
    "/api/v1/ontology/confirm": RESOURCE_ONTOLOGY,
    "/api/v1/ontology/merge": RESOURCE_ONTOLOGY,
    "/api/v1/ontology/rename": RESOURCE_ONTOLOGY,
    "/api/v1/ontology/split": RESOURCE_ONTOLOGY,
}

#: 资源集合（由上面的登记派生，**不**手写——手写就会出现"登记了却没人用"的资源）
RESOURCES: tuple[str, ...] = tuple(sorted(set(CONTRACT_PATH_RESOURCE.values())))

# --------------------------------------------------------------------------- #
# 操作
# --------------------------------------------------------------------------- #

ACTION_READ = "read"
ACTION_WRITE = "write"
ACTIONS: tuple[str, ...] = (ACTION_READ, ACTION_WRITE)

# --------------------------------------------------------------------------- #
# 场景（第三粒度）：资源 → 场景。未登记的资源不做场景收窄。
# --------------------------------------------------------------------------- #

SCENE_AFFILIATION = "affiliation"
SCENE_QA = "qa"
SCENE_AUDIT = "audit"

#: 资源 → 场景（取值示例见 `specs/m5-permission-audit.md` §4.3 的
#: ``["affiliation", "qa"]``；`audit` 是本批按同一口径补的第三档）
SCENE_BY_RESOURCE: dict[str, str] = {
    RESOURCE_AFFILIATION: SCENE_AFFILIATION,
    RESOURCE_AGENT: SCENE_QA,
    RESOURCE_AUDIT: SCENE_AUDIT,
}

SCENES: tuple[str, ...] = tuple(sorted(set(SCENE_BY_RESOURCE.values())))

# --------------------------------------------------------------------------- #
# 矩阵本体：角色 → 资源 → 允许的操作
# --------------------------------------------------------------------------- #

_ALL_READ: frozenset[str] = frozenset({ACTION_READ})
_ALL_READ_WRITE: frozenset[str] = frozenset({ACTION_READ, ACTION_WRITE})
_NONE: frozenset[str] = frozenset()

#: **角色 × 资源 × 操作**（每个角色对每个资源都**显式**列出，不留空位——
#: 空位会让"忘了配"和"刻意不给"看起来一样）。取值理由登记在
#: `changes/P2/integration-log.md` 的「矩阵赋权」小节。
ROLE_PERMISSIONS: dict[str, dict[str, frozenset[str]]] = {
    RoleName.ADMIN: {resource: _ALL_READ_WRITE for resource in RESOURCES},
    RoleName.AUDITOR: {resource: _ALL_READ for resource in RESOURCES},
    RoleName.ANALYST: {
        RESOURCE_AFFILIATION: _ALL_READ_WRITE,
        RESOURCE_AGENT: _ALL_READ,
        RESOURCE_AUDIT: _ALL_READ,
        RESOURCE_COMPLIANCE: _ALL_READ,
        RESOURCE_COST: _ALL_READ,
        RESOURCE_DOCUMENT: _ALL_READ_WRITE,
        RESOURCE_GRAPH: _ALL_READ,
        RESOURCE_ONTOLOGY: _ALL_READ,
    },
    RoleName.VIEWER: {
        RESOURCE_AFFILIATION: _NONE,
        RESOURCE_AGENT: _ALL_READ,
        RESOURCE_AUDIT: _NONE,
        RESOURCE_COMPLIANCE: _ALL_READ,
        RESOURCE_COST: _NONE,
        RESOURCE_DOCUMENT: _ALL_READ,
        RESOURCE_GRAPH: _ALL_READ,
        RESOURCE_ONTOLOGY: _NONE,
    },
}


def allowed_actions(role: str, resource: str) -> frozenset[str]:
    """取某角色在某资源上的允许操作集合（未知角色 / 资源一律空集，**不**兜底放行）。"""
    return ROLE_PERMISSIONS.get(role, {}).get(resource, _NONE)


def scene_of(resource: str) -> str | None:
    """资源的场景归属；无归属返回 ``None``（该资源不做场景收窄）。"""
    return SCENE_BY_RESOURCE.get(resource)


__all__ = [
    "ACTIONS",
    "ACTION_READ",
    "ACTION_WRITE",
    "CONTRACT_PATH_RESOURCE",
    "RESOURCES",
    "RESOURCE_AFFILIATION",
    "RESOURCE_AGENT",
    "RESOURCE_AUDIT",
    "RESOURCE_COMPLIANCE",
    "RESOURCE_COST",
    "RESOURCE_DOCUMENT",
    "RESOURCE_GRAPH",
    "RESOURCE_ONTOLOGY",
    "ROLE_PERMISSIONS",
    "SCENES",
    "SCENE_AFFILIATION",
    "SCENE_AUDIT",
    "SCENE_BY_RESOURCE",
    "SCENE_QA",
    "allowed_actions",
    "scene_of",
]
