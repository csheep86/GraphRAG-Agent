"""考勤域**合规预警 + 异常归因**路由（Sprint 9.5 批次 C3 / C4）。

三个端点（前缀 `/attendance`）：

- ``GET /compliance/scan`` —— 全量合规扫描（批次 C3）；
- ``GET /anomalies`` —— 待归因的缺卡 / 缺勤清单（批次 C4）；
- ``GET /anomalies/explain`` —— 一条异常的归因结论（批次 C4）。

**为什么是同步 GET 而不是异步任务**：扫描是**纯读**——不落库、不调 LLM、不写外部系统，
40 名员工实测秒级完成。异步任务形态（`POST … /scan` + `task_id` 轮询）是为「长耗时且
要留状态」准备的，这里引入只会多一轮往返，且没有状态可存（本批次**不建表**）。

**三条纪律在接口层的落点**：

1. **规则值可核查** ⇒ 响应原样带回 ``rule_values[]``（含制度出处），
   前端必须能把「40 小时」点开看到原句，而不是只看到一个数字；
2. **无判据即跳过** ⇒ ``unresolved[]`` / ``skipped_rules[]`` 显式返回，
   **不**用默认值算出一个"看起来合理"的结论（守 F3）；
3. **只读 active 版本** ⇒ 无 active 版本返回 **409** ``KG_VERSION_NOT_ACTIVE``，
   **严禁**静默降级到历史版本（ADR-0002 §3.2）。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentIdentity, DbSession, TraceId
from app.api.v1.responses import (
    ANOMALY_NOT_FOUND,
    COMPLIANCE_NO_FACTS,
    KG_VERSION_NOT_ACTIVE,
    NOT_IMPLEMENTED,
    TENANT_ERROR_RESPONSES,
)
from app.core.errors import AppError, ErrorCode
from app.schemas.affiliation import AffiliationCauseItem
from app.schemas.anomaly import (
    AnomalyCaseItem,
    AnomalyExplainResponse,
    AnomalyListResponse,
)
from app.schemas.compliance import (
    ComplianceFinding,
    ComplianceLevel,
    ComplianceRule,
    ComplianceScanResponse,
    RuleValueItem,
)
from app.services.graphs import (
    GraphService,
    GraphUnavailableError,
    NoActiveKgVersionError,
)
from app.services.rules import (
    AnomalyNotFoundError,
    ComplianceScanError,
    rule_label,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.get(
    "/compliance/scan",
    response_model=ComplianceScanResponse,
    operation_id="scanAttendanceCompliance",
    summary="考勤域合规预警扫描（Sprint 9.5 批次 C3）",
    description=(
        "对当前租户 **active kg_version** 内的全部员工跑一遍**确定性规则**（五条），"
        "返回风险清单 + 每条的计算过程 + 制度依据。\n\n"
        "**规则值来自制度文本，不硬编码**：响应里的 `rule_values[]` 每个值都带 "
        "`source` / `reference` / `evidence`，可逐条点开核查；制度改了，规则自动变。\n\n"
        "**无判据即跳过**：规则值解析不到时，对应规则**跳过**并在 `skipped_rules[]` "
        "里列出，**不**用默认值兜底算结论（守 F3）。\n\n"
        "**观察日 `as_of`**：影响「调休未消化」的临期判据（季度剩余 < 30 天判 high）。"
        "缺省取数据窗口末日（**不取系统当天**，保证可复现）——同一份数据换个 `as_of`，"
        "同一条风险会从 medium 升到 high。\n\n"
        "**过滤**：`employee_id` / `rule` / `level` 只影响 `findings`，"
        "`rule_values[]` 始终全量返回（判据不因过滤而消失）。\n\n"
        "**错误语义**：\n"
        "- 无 active 版本 → **409** `KG_VERSION_NOT_ACTIVE`（不静默降级）；\n"
        "- 版本内没有考勤事实 → **409** `COMPLIANCE_NO_FACTS`；\n"
        "- Neo4j 不可用 → **501** `NOT_IMPLEMENTED`；\n"
        "- 跨租户 → **403** `FORBIDDEN`。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **KG_VERSION_NOT_ACTIVE,
        **COMPLIANCE_NO_FACTS,
        **NOT_IMPLEMENTED,
    },
)
async def scan_attendance_compliance(
    identity: CurrentIdentity,
    db: DbSession,
    trace_id: TraceId,
    as_of: Annotated[
        date | None,
        Query(
            description=(
                "观察日（ISO 日期，如 `2026-12-15`）；缺省取数据窗口末日。"
                "推进观察日可演示调休「临期升级」"
            )
        ),
    ] = None,
    employee_id: Annotated[
        str | None,
        Query(min_length=1, max_length=32, description="只看该员工（如 `E002`）"),
    ] = None,
    rule: Annotated[ComplianceRule | None, Query(description="只看该规则")] = None,
    level: Annotated[ComplianceLevel | None, Query(description="只看该等级")] = None,
) -> ComplianceScanResponse:
    graph = GraphService.instance()
    try:
        report = graph.scan_attendance_compliance(
            org_id=identity.org_id, db=db, as_of=as_of
        )
    except NoActiveKgVersionError as exc:
        raise AppError(
            ErrorCode.KG_VERSION_NOT_ACTIVE,
            detail={"status": "none", "hint": "无 active 版本，拒绝静默降级"},
        ) from exc
    except ComplianceScanError as exc:
        raise AppError(
            ErrorCode.COMPLIANCE_NO_FACTS,
            detail={
                "reason": str(exc),
                "hint": "请先跑 scripts/ingest_attendance_csv.py",
            },
        ) from exc
    except GraphUnavailableError as exc:
        # 与 `routes/graph.py::_graph_not_available` 同一模板：
        # `detail.reason` 带上原始异常（**有意**，便于排障），但**不**带连接串 / 凭据。
        raise AppError(
            ErrorCode.NOT_IMPLEMENTED,
            "Graph store is unavailable",
            detail={
                "blocked_by": "Neo4j 不可用或 Cypher 执行失败",
                "hint": "scan_attendance_compliance 失败",
                "reason": str(exc),
            },
        ) from exc

    findings = list(report.findings)
    if employee_id is not None:
        findings = [item for item in findings if item.employee_id == employee_id]
    if rule is not None:
        findings = [item for item in findings if item.rule == rule]
    if level is not None:
        findings = [item for item in findings if item.level == level]

    return ComplianceScanResponse(
        kg_version=report.kg_version,
        as_of=report.as_of,
        employee_count=report.employee_count,
        rule_values=[
            RuleValueItem(
                key=item.key,
                label=item.label,
                value=item.value,
                unit=item.unit,
                source=item.source,
                reference=item.reference,
                evidence=item.evidence,
            )
            for item in report.rule_values.values
        ],
        unresolved=list(report.rule_values.unresolved),
        skipped_rules=list(report.skipped_rules),
        findings=[
            ComplianceFinding(
                rule=item.rule,
                rule_label=rule_label(item.rule),
                employee_id=item.employee_id,
                employee_name=item.employee_name,
                department=item.department,
                work_time_system=item.work_time_system,
                level=item.level,
                title=item.title,
                observed=item.observed,
                threshold=item.threshold,
                unit=item.unit,
                calculation=item.calculation,
                policy_refs=list(item.policy_refs),
                evidence=list(item.evidence),
            )
            for item in findings
        ],
        total=len(findings),
        trace_id=trace_id,
    )


@router.get(
    "/anomalies",
    response_model=AnomalyListResponse,
    operation_id="listAttendanceAnomalies",
    summary="考勤域待归因异常清单（Sprint 9.5 批次 C4）",
    description=(
        "列出当前 **active kg_version** 内的全部缺卡 / 缺勤记录（谁、哪天、什么状态），"
        "供异常归因子页挑选「要给谁归因」。\n\n"
        "**空列表是正常结果**：这份图里没人缺卡 —— 与合规扫描不同，那边「扫不到事实」"
        "要显式报 409，这边「没有异常」正是想听到的答案。\n\n"
        "**错误语义**：无 active 版本 → **409** `KG_VERSION_NOT_ACTIVE`；"
        "Neo4j 不可用 → **501** `NOT_IMPLEMENTED`；跨租户 → **403** `FORBIDDEN`。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **KG_VERSION_NOT_ACTIVE,
        **NOT_IMPLEMENTED,
    },
)
async def list_attendance_anomalies(
    identity: CurrentIdentity,
    db: DbSession,
    trace_id: TraceId,
    employee_id: Annotated[
        str | None,
        Query(min_length=1, max_length=32, description="只看该员工（如 `E001`）"),
    ] = None,
) -> AnomalyListResponse:
    graph = GraphService.instance()
    try:
        listing = graph.list_attendance_anomalies(
            org_id=identity.org_id, db=db, employee_id=employee_id
        )
    except NoActiveKgVersionError as exc:
        raise AppError(
            ErrorCode.KG_VERSION_NOT_ACTIVE,
            detail={"status": "none", "hint": "无 active 版本，拒绝静默降级"},
        ) from exc
    except GraphUnavailableError as exc:
        raise AppError(
            ErrorCode.NOT_IMPLEMENTED,
            "Graph store is unavailable",
            detail={
                "blocked_by": "Neo4j 不可用或 Cypher 执行失败",
                "hint": "list_attendance_anomalies 失败",
                "reason": str(exc),
            },
        ) from exc

    return AnomalyListResponse(
        kg_version=listing.kg_version,
        items=[
            AnomalyCaseItem(
                employee_id=case.employee_id,
                employee_name=case.employee_name,
                date=case.day,
                status=case.status,
            )
            for case in listing.cases
        ],
        total=len(listing.cases),
        trace_id=trace_id,
    )


@router.get(
    "/anomalies/explain",
    response_model=AnomalyExplainResponse,
    operation_id="explainAttendanceAnomaly",
    summary="考勤异常归因（Sprint 9.5 批次 C4）",
    description=(
        "给「某员工某天缺卡」做归因：跨 **HR / 门禁 / 工单 / 定位** 四个系统取证，"
        "按确定性权重给出置信度与结论。\n\n"
        "**置信度不出 LLM**：`confidence = Σ命中权重 / Σ全部权重`，"
        "每个 `weight` 都是常量（出差审批 0.35 / 工单闭环 0.30 / 定位一致 0.22 / "
        "门禁对比 0.13），命中与否由图谱证据说话 —— 不是模型的自我感觉。\n\n"
        "**未命中的原因照样返回**（`matched=false`）：演示时要能说清「哪一项没对上」，"
        "只给命中项会让用户误以为证据齐备。\n\n"
        "**`date` 缺省**取该员工的第一个异常日（与 CLI 同口径）。\n\n"
        "**错误语义**：员工不在图上 / 该日没有异常 → **404** `NOT_FOUND`"
        "（**不**返回零证据结果冒充「不成立」）；无 active 版本 → **409**；"
        "Neo4j 不可用 → **501**。"
    ),
    responses={
        **TENANT_ERROR_RESPONSES,
        **KG_VERSION_NOT_ACTIVE,
        **ANOMALY_NOT_FOUND,
        **NOT_IMPLEMENTED,
    },
)
async def explain_attendance_anomaly(
    identity: CurrentIdentity,
    db: DbSession,
    trace_id: TraceId,
    employee_id: Annotated[
        str, Query(min_length=1, max_length=32, description="员工工号（如 `E001`）")
    ],
    date_value: Annotated[
        date | None,
        Query(alias="date", description="异常日（ISO）；缺省取该员工第一个异常日"),
    ] = None,
) -> AnomalyExplainResponse:
    graph = GraphService.instance()
    try:
        version, result = graph.explain_attendance_anomaly(
            org_id=identity.org_id,
            db=db,
            employee_id=employee_id,
            day=date_value,
        )
    except NoActiveKgVersionError as exc:
        raise AppError(
            ErrorCode.KG_VERSION_NOT_ACTIVE,
            detail={"status": "none", "hint": "无 active 版本，拒绝静默降级"},
        ) from exc
    except AnomalyNotFoundError as exc:
        raise AppError(
            ErrorCode.NOT_FOUND,
            "Anomaly not found",
            detail={
                "employee_id": employee_id,
                "date": date_value.isoformat() if date_value else None,
                "reason": str(exc),
                "hint": "先用 GET /attendance/anomalies 确认该员工的异常日",
            },
        ) from exc
    except GraphUnavailableError as exc:
        raise AppError(
            ErrorCode.NOT_IMPLEMENTED,
            "Graph store is unavailable",
            detail={
                "blocked_by": "Neo4j 不可用或 Cypher 执行失败",
                "hint": "explain_attendance_anomaly 失败",
                "reason": str(exc),
            },
        ) from exc

    return AnomalyExplainResponse(
        kg_version=version,
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        date=result.date,
        anomaly_type=result.anomaly_type,
        causes=[
            AffiliationCauseItem(
                code=cause.code,
                reason=cause.reason,
                weight=cause.weight,
                matched=cause.matched,
                evidence=list(cause.evidence),
            )
            for cause in result.causes
        ],
        confidence=result.confidence,
        conclusion=result.conclusion,
        action=result.action,
        policy_refs=list(result.policy_refs),
        trace_id=trace_id,
    )
