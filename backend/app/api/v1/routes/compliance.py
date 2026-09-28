"""考勤域合规预警路由（Sprint 9.5 批次 C3）：`GET /attendance/compliance/scan`。

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
    COMPLIANCE_NO_FACTS,
    KG_VERSION_NOT_ACTIVE,
    NOT_IMPLEMENTED,
    TENANT_ERROR_RESPONSES,
)
from app.core.errors import AppError, ErrorCode
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
from app.services.rules import ComplianceScanError, rule_label

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
