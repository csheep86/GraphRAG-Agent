"""考勤域合规扫描 CLI（Sprint 9.5 批次 C1 的自检入口）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/scan_attendance_compliance.py
    uv run python scripts/scan_attendance_compliance.py --as-of 2026-12-15
    uv run python scripts/scan_attendance_compliance.py --only E002

**为什么单独一个脚本**：规则引擎是**确定性**的，最容易出的错不是异常，
而是「跑通了但数不对 / 演示用例静默不出现」。脚本因此做三件事：

1. 打印**每个规则值的出处**（哪条条款 / 哪份文档第几行）——不是数值本身可信，
   是出处可核查才可信（守 F3）；
2. 打印风险清单与**计算过程**（演示时要能逐条念出来）；
3. **断言 5 条已埋设的演示用例**（E002 月加班 + 连续出勤、E003 弹性越界、
   E004 调休未消化、E005 周工时超限）确实出现——不出现即 **exit 1**，
   绝不"扫了个寂寞还报成功"。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from neo4j import GraphDatabase  # type: ignore[import-not-found]  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.rules import (  # noqa: E402
    LEVEL_HIGH,
    RULE_COMP_OFF,
    RULE_CONSECUTIVE,
    RULE_CORE_WINDOW,
    RULE_MONTHLY_OVERTIME,
    RULE_WEEKLY_HOURS,
    scan_compliance,
)

DEFAULT_KG_VERSION = "attendance-demo-v1"

#: 已埋设的演示用例（``demo/attendance/README.md`` §4）：员工 → 必须出现的规则
DEMO_EXPECTATIONS: tuple[tuple[str, str, str], ...] = (
    ("E002", RULE_MONTHLY_OVERTIME, "月加班超限 42h > 36h"),
    ("E002", RULE_CONSECUTIVE, "连续出勤 22 天 ≥ 12 天"),
    ("E003", RULE_CORE_WINDOW, "核心时段未在岗 7 次 > 5 次"),
    ("E004", RULE_COMP_OFF, "已产生调休额度 22h、已调休 0h"),
    ("E005", RULE_WEEKLY_HOURS, "第 42 周实际工时 48h > 40h"),
)


def _print_rule_values(report: object) -> None:
    print("\n===== 规则值（解析自制度文本，**非硬编码**） =====")
    for item in report.rule_values.values:  # type: ignore[attr-defined]
        print(
            f"  {item.label:<16} {item.value:>6g} {item.unit}"
            f"  [{item.source}:{item.reference}]"
        )
        print(f"      出处原文：{item.evidence}")
    if report.rule_values.unresolved:  # type: ignore[attr-defined]
        print(
            "  [warn] 未解析（对应规则已跳过，**未用默认值兜底**）："
            + ", ".join(report.rule_values.unresolved)  # type: ignore[attr-defined]
        )
    if report.skipped_rules:  # type: ignore[attr-defined]
        print("  [warn] 因缺规则值而跳过的规则：" + ", ".join(report.skipped_rules))  # type: ignore[attr-defined]


def _print_findings(report: object, only: str | None = None) -> None:
    findings = [
        item  # type: ignore[attr-defined]
        for item in report.findings
        if only is None or item.employee_id == only
    ]
    print(
        f"\n===== 合规扫描（kg_version={report.kg_version} "  # type: ignore[attr-defined]
        f"观察日={report.as_of} 员工={report.employee_count}） ====="  # type: ignore[attr-defined]
    )
    if not findings:
        print(f"  （无风险项{f'：{only}' if only else ''}）")
        return
    high = sum(1 for item in findings if item.level == LEVEL_HIGH)
    print(f"  风险 {len(findings)} 条（high {high} / medium {len(findings) - high}）")
    for item in findings:
        print(
            f"  [{item.level}] {item.employee_id} {item.employee_name}"
            f"（{item.department} / {item.work_time_system}）{item.title}"
        )
        print(f"         计算：{item.calculation}")
        print(f"         依据：{', '.join(item.policy_refs)}")
        print(f"         证据：{', '.join(item.evidence) or '（无）'}")


def _assert_demo_cases(report: object) -> int:
    print("\n===== 演示用例断言（语料已埋设，不出现即失败） =====")
    present = {(item.employee_id, item.rule) for item in report.findings}  # type: ignore[attr-defined]
    failed = 0
    for employee_id, rule, hint in DEMO_EXPECTATIONS:
        ok = (employee_id, rule) in present
        failed += 0 if ok else 1
        print(f"  [{'OK ' if ok else 'FAIL'}] {employee_id} {rule} — {hint}")
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description="考勤域合规扫描（确定性规则引擎）")
    parser.add_argument("--kg-version", default=DEFAULT_KG_VERSION)
    parser.add_argument(
        "--as-of",
        default=None,
        help="观察日（ISO 日期）；默认取数据窗口末日，保证可复现",
    )
    parser.add_argument("--only", default=None, help="只看某个员工，如 E002")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )

    try:
        with driver.session(database=settings.neo4j_database) as session:
            report = scan_compliance(
                session=session,
                kg_version=args.kg_version,
                org_id=str(settings.default_org_id),
                as_of=as_of,
            )
    finally:
        driver.close()

    _print_rule_values(report)
    _print_findings(report, only=args.only)
    failed = 0 if args.only else _assert_demo_cases(report)
    print(f"\n扫描完成：{'存在未满足的演示用例' if failed else '全部演示用例成立'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
