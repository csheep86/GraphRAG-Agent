"""Sprint 8.1 批次 A：真机状态盘点（**只读**，不写任何数据）。

用法（工作目录 = backend/）：

    uv run python ../changes/Sprint8.1/inspect_state.py

盘点项：
1. 故事实里有几张表（`audit_log` / `qa_logs` 是否已存在）；
2. 文档 / 图谱版本 / 疑点的现状，用于判断是否可"复用现有图谱、不重建"（决策 A13）；
3. audit_log 的行数与 action 分布——**演示路径的判据（≥ 7 条）就从这个数读出来**。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("dev.db")

QUERIES: dict[str, str] = {
    "tables": "select name from sqlite_master where type='table' order by name",
    "documents_by_status": "select status, count(*) from documents group by status",
    "kg_versions_by_status": "select status, count(*) from kg_versions group by status",
    "active_kg_version": (
        "select version, status, entity_count, relation_count, ready_at "
        "from kg_versions where status='ready' order by ready_at desc limit 3"
    ),
    "affiliation_tasks_by_status": (
        "select status, count(*) from affiliation_tasks group by status"
    ),
    "suspicions_by_status": (
        "select status, count(*) from affiliation_suspicions group by status"
    ),
    "completed_documents": (
        "select id, substr(filename_hash,1,12) from documents "
        "where status='completed' order by created_at desc limit 10"
    ),
}


def main() -> None:
    if not DB_PATH.is_file():
        print(f"[SKIP] 未找到 {DB_PATH}（工作目录应为 backend/）")
        return

    with sqlite3.connect(DB_PATH) as connection:
        names = [row[0] for row in connection.execute(QUERIES["tables"])]
        print(f"[tables] {len(names)} 张：{names}")
        print(f"[audit/qa] audit_log={'audit_log' in names} qa_logs={'qa_logs' in names}")

        for label in (
            "documents_by_status",
            "kg_versions_by_status",
            "active_kg_version",
            "affiliation_tasks_by_status",
            "suspicions_by_status",
            "completed_documents",
        ):
            rows = list(connection.execute(QUERIES[label]))
            print(f"[{label}] {rows if rows else '(空)'}")

        if "audit_log" in names:
            total = list(connection.execute("select count(*) from audit_log"))
            by_action = list(
                connection.execute(
                    "select action, status, count(*) from audit_log "
                    "group by action, status order by action"
                )
            )
            distinct_trace = list(
                connection.execute("select count(distinct trace_id) from audit_log")
            )
            print(f"[audit_log.total] {total[0][0]} 条 / distinct trace {distinct_trace[0][0]}")
            for row in by_action:
                print(f"    {row[0]:<28} {row[1]:<8} {row[2]}")

        if "qa_logs" in names:
            qa = list(
                connection.execute(
                    "select refused, count(*) from qa_logs group by refused"
                )
            )
            print(f"[qa_logs.by_refused] {qa if qa else '(空)'}")


if __name__ == "__main__":
    main()
