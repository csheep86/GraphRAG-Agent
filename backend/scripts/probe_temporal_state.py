"""时态治理**体检**脚本（¥0、只读）：把「表/列存在但没人写」这类洞变成红灯。

为什么需要它
------------
Sprint 9 的时态能力由三样东西构成：``documents.document_date``（事实维兜底源）、
``relation_expiry_policies``（哪些类型只允许一个当前值）、关系上的
``valid_from`` / ``valid_to``。三者**缺任何一样，能力都是半成品**——而半成品不会
报错，只会安静地降级：抽取拿不到日期就渲染 ``unknown``，仲裁查不到策略就按
``append_only``（不封任何旧边）。

本项目已经吃过一次这个亏：dev 库靠 ``create_all`` 演进、迁移从未应用，
``documents`` 表**根本没有 ``document_date`` 列**，而模型里声明了它——
读它的代码在开发态直接 ``no such column``。测试全绿是因为测试用的是
``create_all`` 建的**新**库。**跑一次本脚本就能看见**。

判据（任一 FAIL ⇒ 退出码 1）
---------------------------
1. **迁移未漂移**：库里的 alembic 版本 == head。漂移 ⇒ 模型与库各说各话；
2. **``document_date`` 列已落地**（漂移检查过了还不够，stamp 过的库可能仍缺列）；
3. **已抽取的文档里有带日期的**：全库 0 条有日期 ⇒ 时态能力在真实数据上没生效；
4. **策略表非空**：0 行 ⇒ 所有类型按 ``append_only``，L1 仲裁**永不封边**；
5. **图上有时态边**（Neo4j 不可达时 SKIP，不算 FAIL——CI 没有 Neo4j）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/probe_temporal_state.py

不写库、不调 LLM、不连 Neo4j 也能跑（Neo4j 段自动 SKIP）。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

#: 与初始化脚本共用同一份「哪些类型只允许一个当前值」的定义——两处各写一份
#: 迟早漂移，而漂移的表现又是**安静的**（体检数行看不出类型名拼错）。
from seed_expiry_policies import DEFAULT_SINGLE_CURRENT  # noqa: E402
from sqlalchemy import inspect, select, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402

#: 退出码：0 = 无 FAIL；1 = 有 FAIL
EXIT_FAIL = 1


def force_utf8_console() -> None:
    """Windows GBK 控制台会吃掉中文（与 import_to_neo4j.py 保持同款处理）。"""
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None)
        if stream and enc and enc.lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


class Report:
    """收集检查结论；FAIL 会决定退出码。"""

    def __init__(self) -> None:
        self.results: list[tuple[str, str, str]] = []  # (状态, 项, 说明)

    def add(self, status: str, item: str, detail: str) -> None:
        self.results.append((status, item, detail))
        print(f"  [{status:<4}] {item}：{detail}")

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for s, _, _ in self.results)

    def banner(self, title: str) -> None:
        print("\n" + "=" * 74)
        print(title)
        print("=" * 74)


def check_migrations(report: Report) -> None:
    """库里的 alembic 版本必须 == head（否则模型与库漂移）。"""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    head = script.get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_heads()

    if not current:
        report.add(
            "FAIL",
            "迁移未漂移",
            f"库未 stamp（head={head[:12]}）⇒ 库是 create_all 建的，"
            "模型与库已漂移；跑 alembic stamp/upgrade 对齐",
        )
        return
    if current != (head,):
        report.add(
            "FAIL", "迁移未漂移", f"库={[c[:12] for c in current]} head={head[:12]}"
        )
        return
    report.add("OK", "迁移未漂移", f"库版本 == head = {head[:12]}")


def check_document_date(report: Report, engine_: Engine) -> None:
    """``document_date`` 列要落地，且**真实数据里得有值**（否则能力等于没接）。"""
    cols = [c["name"] for c in inspect(engine_).get_columns("documents")]
    if "document_date" not in cols:
        report.add("FAIL", "document_date 列", "列不存在（模型里有、库里没有）")
        return
    report.add("OK", "document_date 列", "已落地")

    db = SessionLocal()
    try:
        total = db.execute(text("select count(*) from documents")).scalar() or 0
        dated = (
            db.execute(
                text("select count(*) from documents where document_date is not null")
            ).scalar()
            or 0
        )
    finally:
        db.close()

    if total == 0:
        report.add("SKIP", "文档日期覆盖", "库里没有文档（空库，不算洞）")
    elif dated == 0:
        report.add(
            "FAIL",
            "文档日期覆盖",
            f"{total} 份文档、**0** 份有 document_date ⇒ 抽取侧恒渲染 unknown、"
            "问答侧 as_of 恒 unknown（列存在但没人写）",
        )
    else:
        report.add("OK", "文档日期覆盖", f"{dated}/{total} 份文档有日期")


def check_policies(report: Report, *, org_id: object) -> None:
    """策略表 0 行 ⇒ 所有类型按 append_only，L1 仲裁永不封边。

    用 ORM 而不是 raw SQL 查 ``org_id``：``Uuid`` 列在 SQLite 里存的是**无连字符**
    hex，直接拿带连字符的字符串去比会「明明有行却查不到」——本脚本自己差点
    犯这个错（种子写完仍判 FAIL）。
    """
    from app.db.models import RelationExpiryPolicy

    db = SessionLocal()
    try:
        rows = db.execute(
            select(RelationExpiryPolicy.relation_type, RelationExpiryPolicy.policy)
        ).all()
        mine = db.execute(
            select(
                RelationExpiryPolicy.relation_type, RelationExpiryPolicy.policy
            ).where(RelationExpiryPolicy.org_id == org_id)  # type: ignore[arg-type]
        ).all()
    finally:
        db.close()

    if not rows:
        report.add(
            "FAIL",
            "有效期策略",
            "relation_expiry_policies **0 行** ⇒ 全部类型按 append_only，"
            "L1 仲裁不封任何旧边；跑 scripts/seed_expiry_policies.py 初始化",
        )
        return
    if not mine:
        report.add(
            "FAIL",
            "有效期策略",
            f"库里共 {len(rows)} 行，但**默认租户 {org_id[:8]} 一行都没有** ⇒ "
            "该租户的仲裁同样不生效",
        )
        return
    single = [r[0] for r in mine if r[1] == "single_current"]

    # 行数够 ≠ 判定对：真正的判据是**仲裁函数**对这些类型说什么。直接问它，
    # 而不是数行——数行会放过「行写错了 / 类型名拼错」这类同样安静的失败。
    from app.services.kg.policies import load_expiry_policies

    judge = load_expiry_policies(db, org_id=org_id)  # type: ignore[arg-type]
    wanted = {t: judge(t) for t in DEFAULT_SINGLE_CURRENT}
    missing = [t for t, ok in wanted.items() if not ok]
    if missing:
        report.add(
            "FAIL",
            "有效期策略",
            f"默认租户 {len(mine)} 行，但仲裁判定 {missing} 不是 single_current ⇒ "
            "这些类型的旧边不会被封",
        )
        return
    report.add(
        "OK",
        "有效期策略",
        f"默认租户 {len(mine)} 行，仲裁判定 {sorted(single)} = 唯一当前；"
        f"未知类型按并存 = {not judge('SOME_UNKNOWN_TYPE')}",
    )


def check_graph_temporal(report: Report) -> None:
    """图上得有时态边；Neo4j 不可达时 SKIP（CI 没有 Neo4j）。"""
    from app.services.graphs import GraphService

    graph = GraphService.instance()
    try:
        with graph._session() as session:  # noqa: SLF001 - 只读探针
            rows = list(
                session.run(
                    """
MATCH ()-[r]->()
RETURN type(r) AS t, count(*) AS n,
       sum(CASE WHEN properties(r)['valid_from'] IS NULL THEN 0 ELSE 1 END) AS has_from,
       sum(CASE WHEN properties(r)['valid_to'] IS NULL THEN 0 ELSE 1 END) AS has_to
ORDER BY n DESC
"""
                )
            )
    except Exception as exc:  # noqa: BLE001 - 不可达按 SKIP 处理
        report.add("SKIP", "图时态覆盖", f"Neo4j 不可达：{type(exc).__name__}")
        return

    total = sum(r["n"] for r in rows)
    with_from = sum(r["has_from"] for r in rows)
    print(f"         边共 {total} 条，按类型：")
    for r in rows:
        print(
            f"           {r['t']:<28} n={r['n']:<5} valid_from={r['has_from']:<5} "
            f"valid_to（已封）={r['has_to']}"
        )
    if with_from == 0:
        report.add(
            "FAIL",
            "图时态覆盖",
            f"{total} 条边**没有一条**带 valid_from ⇒ 写侧从未产生时态事实",
        )
    else:
        report.add("OK", "图时态覆盖", f"{with_from}/{total} 条边带 valid_from")


def main() -> int:
    force_utf8_console()
    settings = get_settings()
    print("NEO4J_URI =", settings.neo4j_uri)
    print("default_org =", settings.default_org_id)

    report = Report()

    report.banner("1. schema 与迁移")
    check_migrations(report)
    check_document_date(report, engine)

    report.banner("2. 策略与图上时态")
    check_policies(report, org_id=settings.default_org_id)
    check_graph_temporal(report)

    report.banner("结论")
    for status, item, _detail in report.results:
        print(f"  [{status:<4}] {item}")
    if report.failed:
        print(
            "\n  ❌ 时态能力存在半成品环节（详见上方 FAIL）。"
            "这些洞不会报错，只会安静降级。"
        )
        return EXIT_FAIL
    print("\n  ✅ 时态链路各环节均已落地（SKIP 项不算失败）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
