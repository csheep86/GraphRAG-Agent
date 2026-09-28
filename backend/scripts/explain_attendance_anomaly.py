"""考勤异常归因 CLI（Sprint 9.5 批次 C2 的自检入口）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/explain_attendance_anomaly.py              # 默认 E001
    uv run python scripts/explain_attendance_anomaly.py --employee E002
    uv run python scripts/explain_attendance_anomaly.py --employee E001 --date 2026-10-16

打印三件事：

1. 该员工的**异常日**（缺卡 / 缺勤）——先说清楚"要给谁归因"；
2. 每条证据的**命中与否 + 权重 + 证据节点 id**（置信度怎么来的，可逐条核对）；
3. 结论与**制度出处**（「自动补卡」这话必须能指回制度原句，不许硬编码）。

末尾断言演示用例 E001（10-16 缺卡 ⇒ 外勤出勤成立），不成立即 exit 1。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from neo4j import GraphDatabase  # type: ignore[import-not-found]  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.rules import attribute_absence, find_anomaly_days  # noqa: E402
from app.services.rules.attribution import (  # noqa: E402
    CONFIDENCE_ACCEPT,
    load_policy_clauses,
    load_policy_documents,
    search_policy_sentences,
)

DEFAULT_KG_VERSION = "attendance-demo-v1"
#: 演示用例 E001：张伟 2026-10-16（周五，工作日）缺卡 ⇒ 外勤出勤成立
DEMO_EMPLOYEE = "E001"
DEMO_DATE = "2026-10-16"


def _print_result(result: object, sentences: tuple) -> None:
    print(
        f"\n===== 归因：{result.employee_id} {result.employee_name} "  # type: ignore[attr-defined]
        f"{result.date}（{result.anomaly_type}） ====="  # type: ignore[attr-defined]
    )
    for cause in result.causes:  # type: ignore[attr-defined]
        flag = "命中" if cause.matched else "未命中"
        print(f"  [{flag}] {cause.code:<16} 权重 {cause.weight:.2f}  {cause.reason}")
        if cause.evidence:
            print(f"        证据：{', '.join(cause.evidence)}")
    print(f"  置信度：{result.confidence:.2%}（Σ命中权重 / Σ全部权重，确定性加权）")  # type: ignore[attr-defined]
    print(f"  结论：{result.conclusion} ⇒ 动作：{result.action}")  # type: ignore[attr-defined]
    if result.policy_refs:  # type: ignore[attr-defined]
        print(f"  制度出处：{', '.join(result.policy_refs)}")  # type: ignore[attr-defined]
        for item in sentences:
            print(f"    - [{item.source}:{item.reference}] {item.text}")
    else:
        print("  [warn] 未取到制度出处（结论中的制度话术不可声称）")


def main() -> int:
    parser = argparse.ArgumentParser(description="考勤异常归因（确定性证据加权）")
    parser.add_argument("--kg-version", default=DEFAULT_KG_VERSION)
    parser.add_argument("--employee", default=DEMO_EMPLOYEE)
    parser.add_argument(
        "--date", default=None, help="异常日（ISO）；默认取该员工第一个异常日"
    )
    args = parser.parse_args()

    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )
    try:
        with driver.session(database=settings.neo4j_database) as session:
            org_id = str(settings.default_org_id)
            days = find_anomaly_days(
                session=session,
                kg_version=args.kg_version,
                org_id=org_id,
                employee_id=args.employee,
            )
            print(f"===== {args.employee} 的异常日（缺卡 / 缺勤） =====")
            print(f"  {', '.join(days) if days else '（无）'}")
            if not days and not args.date:
                print("  没有异常日可归因（换个 --employee 或显式给 --date）")
                return 1

            target = args.date or days[0]
            name = session.run(
                "MATCH (e:Entity {entity_type:'EMPLOYEE', kg_version:$kg, "
                "org_id:$org}) WHERE e.id = $emp "
                "RETURN e.canonical_name AS name",
                kg=args.kg_version,
                org=org_id,
                emp=f"EMPLOYEE:{args.employee}",
            ).single()
            documents = load_policy_documents(org_id=org_id)
            clauses = load_policy_clauses(
                session=session, kg_version=args.kg_version, org_id=org_id
            )
            result = attribute_absence(
                session=session,
                kg_version=args.kg_version,
                org_id=org_id,
                employee_id=args.employee,
                employee_name=str(name["name"]) if name else "",
                day=target,
                policy_documents=documents,
                policy_clauses=clauses,
            )
            sentences = search_policy_sentences(
                keyword="自动补卡", clauses=clauses, documents=documents
            )
    finally:
        driver.close()

    _print_result(result, sentences)

    print("\n===== 演示用例断言 =====")
    ok = (
        args.employee == DEMO_EMPLOYEE
        and target == DEMO_DATE
        and result.confidence >= CONFIDENCE_ACCEPT
    )
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E001 10-16 缺卡 ⇒ 外勤出勤成立"
        f"（实测置信度 {result.confidence:.2%}，阈值 {CONFIDENCE_ACCEPT:.0%}）"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
