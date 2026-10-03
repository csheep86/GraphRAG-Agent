"""受控问题集评估器（Sprint 6 §5.3 验收第 1 条：引用覆盖率 100%、无拒答误伤）。

**只评估、不调 Prompt**（plan §4.2 纪律）：本脚本只跑真实链路并统计，
发现质量问题应登记到 `changes/Sprint6.*/integration-log.md`，**不**就地改 Prompt。

**问题集换版（2026-09-26，v2）**：v1 的 14 题基于 Sprint 6 语料「2025 年度集团经营
指标分析报告」，与当前 active 图谱（种子集 3 份招商局系文件）**不同源** ⇒ 实测拒答
口径不符 11/14。按 `docs/release-notes/v1.4.0.md` §7.2 与决策 A15，**换版安排在演示语料
固化之后**——`docs/demo-seed-dataset.md` 已固化 ⇒ 本次按**同一批语料**重出 14 题
（12 库内 + 2 库外），每题在注释里登记**出处文档与期望答案要点**，便于后续复核。
冻结口径：`kg_version = v-s71a-fe1c4dc3`（换版基准，语料再变即作废需重出）。

**问题集换版（2026-09-30，v3）**：v2 冻结的 `v-s71a-fe1c4dc3` **在 Neo4j 上已无 chunk**
（`probe_e0_active.py` 实测：图上只剩 `attendance-demo-v1` 230 chunks 与
`affiliation-demo-v1` 128 chunks；该版本仅剩 SQLite 一行 `ready` 记录）。
⇒ v2 题集**全部不同源，直接跑必然全拒答**，会得出「召回坏了」的**假结论**
（与 v1→v2 同族）。故按当前 active 语料重出 14 题：4 份考勤制度 docx + 9 张考勤 CSV，
出处均经 `:Chunk` 正文核对（2026-09-30 实测）。
冻结口径：`kg_version = attendance-demo-v1`。

用法::

    uv run python scripts/eval_controlled_qset.py            # 默认 http://127.0.0.1:8002
    EVAL_BASE_URL=http://127.0.0.1:8000 uv run python scripts/eval_controlled_qset.py
    uv run python scripts/eval_controlled_qset.py --diagnose # ¥0：只复算候选集，不调 LLM

统计口径：

- **引用覆盖率** = 非拒答回答中「`citations` 非空 **且** 每条 `chunk_id` 均为
  ``chunk-`` 前缀」的比例（目标 100%）；
- **拒答误伤** = 标注了 ``should_refuse=True`` 却未拒答，或反之（目标 0）。

退出码：覆盖率 < 100% 或存在误伤 → ``1``（可作为机械判据接入验收，不进 CI 门禁）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Windows 控制台默认 GBK，中文结果会 UnicodeEncodeError —— 强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

BASE_URL = os.environ.get("EVAL_BASE_URL", "http://127.0.0.1:8002")
ORG_ID = "00000000-0000-4000-8000-000000000001"
ACTOR_ID = "00000000-0000-4000-8000-0000000000aa"

#: 问题集版本与冻结口径（换版依据见模块 docstring）。
QSET_VERSION = "v3-2026-09-30"
QSET_KG_VERSION = "attendance-demo-v1"

#: (问题, 是否预期拒答)。
#:
#: 库内 12 题：覆盖种子集 3 份原件（招商公路 / 招商蛇口募集说明书 + 招商轮船 2025 年报），
#: 每题注释登记「出处 → 期望答案要点」，均经 Neo4j `:Chunk` 正文命中核对（2026-09-26 实测）。
#: 库外 2 题：验证拒答出口不被误伤（F3 的反面：不该答的别答）——**刻意选语料里完全不存在的
#: 主体**（库外问若仍带「招商轮船 + 营业收入」这类库内高词频词，会被误召回 ⇒ 拒答判据失真）。
QUESTIONS: list[tuple[str, bool]] = [
    # ---- 制度 1：《员工考勤管理制度（2026 版）》HR-ATD-2026-001 ----
    # 出处：第三章 第八条 → 期望「每名员工每月补卡不超过 3 次，超出按事假处理」
    ("每名员工每月的补卡次数上限是多少？", False),
    # 出处：第二章 第六条 → 期望「晚于排班上班时间 30 分钟以内记迟到；超过 30 分钟按事假半天」
    ("迟到是怎么认定的？超过 30 分钟怎么算？", False),
    # ---- 制度 2：《外勤与出差考勤补充规定》HR-FWA-2026-004 ----
    # 出处：第一章 第一条 → 期望「因公外出（外勤）或出差期间无法按常规方式打卡的员工」
    ("外勤与出差考勤补充规定适用于哪些员工？", False),
    # 出处：第二章 第三条 → 期望「不能；门禁仅覆盖公司自有场所，不得以无门禁记录否定出勤」
    ("能不能因为没有门禁刷卡记录就认定外勤员工未出勤？", False),
    # ---- 制度 3：《加班与调休管理办法》HR-OTC-2026-003 ----
    # 出处：第二章 第四条 → 期望「每月不得超过 36 小时（依据劳动法第四十一条）」
    ("每月加班时间不得超过多少小时？", False),
    # 出处：第一章 第二条 → 期望「不认定为加班（须经审批）」
    ("员工自愿延长在岗时间、未经审批的，算加班吗？", False),
    # ---- 制度 4：《工时制实施细则》HR-WTS-2026-002 ----
    # 出处：第三章 岗位适用表 → 期望「不定时工作制（已履行审批）」
    ("销售经理适用哪种工时制？", False),
    # 出处：第四章 第十二条 → 期望「核心在岗时段 10:00 至 16:00」
    ("标准工时制岗位的核心在岗时段是什么时候？", False),
    # ---- CSV：employees.csv（首行 E001,张伟,售后部,售后工程师,综合计算工时制）----
    # 出处：employees.csv → 期望「售后部 / 售后工程师」
    ("张伟在哪个部门、担任什么岗位？", False),
    # 出处：employees.csv → 期望「综合计算工时制」
    ("张伟适用哪种工时制？", False),
    # ---- CSV：leave_requests.csv（首行 LV0001,E004,病假,2026-10-25,2026-10-27,3）----
    # 出处：leave_requests.csv → 期望「病假，3 天」
    ("E004 在 2026 年 10 月 25 日请的是什么假，共几天？", False),
    # ---- CSV：work_orders.csv（首行 SO-2026-0912,E001,武汉光谷希尔顿酒店,武汉光谷）----
    # 出处：work_orders.csv → 期望「武汉光谷希尔顿酒店（武汉光谷）」
    ("工单 SO-2026-0912 的处理地点在哪里？", False),
    # ---- 库外问题：预期拒答（refused=true）----
    # 库外问刻意选语料里**完全不存在**的主体（比亚迪 / 红楼梦）
    ("比亚迪 2025 年新能源汽车销量是多少？", True),
    ("《红楼梦》中贾宝玉的妻子是谁？", True),
]


def ask(question: str) -> dict[str, Any]:
    payload = json.dumps({"question": question, "scope": "cross_doc"}).encode()
    request = urllib.request.Request(  # noqa: S310 - 固定本地地址
        f"{BASE_URL}/api/v1/agent/query",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Org-Id": ORG_ID,
            "X-Actor-Id": ACTOR_ID,
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def diagnose() -> int:
    """**¥0 候选集诊断**：复算问答链路「能看到哪些 chunk」，不调 LLM。

    为什么需要它：问答的候选集是**结构性**的——active 版本全量实体按
    ``select_subgraph_nodes`` 选前 ``_GRAPH_NODE_LIMIT`` 个（**按 ``entity_type`` 保底 +
    组内度数降序**，Sprint 10 批次 C 之前是"无 ORDER BY 的扫描序"）→ 按 ``MENTIONS``
    反查 chunk → 再 ``LIMIT _EVIDENCE_CHUNK_LIMIT``（**无排序、无打分**），
    ``question`` 文本**不参与**。于是「某文档 0 条注入」⇒ 关于它的问题**必然拒答**，
    与问题怎么写无关。换版后若出现非预期拒答，先跑这条命令归因，
    别急着改问题集（plan §4.2 纪律：只评估、不调 Prompt）。
    """
    from uuid import UUID  # noqa: PLC0415

    from neo4j import GraphDatabase  # noqa: PLC0415 - 仅诊断模式需要

    from app.core.config import get_settings  # noqa: PLC0415
    from app.services.agents import (  # noqa: PLC0415 - 直接复用线上常量，避免脚本写死后漂移
        _GRAPH_NODE_LIMIT,
    )
    from app.services.graphs import (  # noqa: PLC0415
        _EVIDENCE_CHUNK_LIMIT,
        GraphService,
    )

    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        with driver.session() as session:
            total_chunks = session.run(
                "MATCH (c:Chunk {kg_version:$v}) RETURN count(c) AS n",
                v=QSET_KG_VERSION,
            ).single()["n"]
            total_docs = session.run(
                "MATCH (d:Document {kg_version:$v}) RETURN count(d) AS n",
                v=QSET_KG_VERSION,
            ).single()["n"]

            # Sprint 10 批次 C：候选集改由**服务层**算（不再在脚本里复刻线上 Cypher——
            # 复刻就意味着两处逻辑必然漂移，诊断结论也就不可信了）。
            candidate_nodes, _edges, _truncated = (
                GraphService.instance().fetch_all_subgraph(
                    kg_version=QSET_KG_VERSION,
                    org_id=UUID(ORG_ID),
                    node_limit=_GRAPH_NODE_LIMIT,
                )
            )
            entity_ids = [node.id for node in candidate_nodes]

            # Sprint 10 批次 C 残留缺口：注入的 20 条同样改由**服务层**算
            # （原先这里复刻线上 Cypher 的 ``LIMIT 20`` 无序语义；线上改成
            # 「每文档保底 + 余量 span 优先」后，复刻版给出的诊断就是错的）。
            # 可达数只做 **count**（不复刻投影逻辑，避免第二处漂移）。
            reachable_n = session.run(
                "MATCH (c:Chunk {kg_version:$v})-[:MENTIONS]->"
                "(e:Entity {kg_version:$v}) WHERE e.id IN $ids "
                "RETURN count(DISTINCT c) AS n",
                v=QSET_KG_VERSION,
                ids=entity_ids,
            ).single()["n"]
            reachable_docs = session.run(
                "MATCH (c:Chunk {kg_version:$v})-[:MENTIONS]->"
                "(e:Entity {kg_version:$v}) WHERE e.id IN $ids "
                "OPTIONAL MATCH (d:Document {kg_version:$v})-[:HAS_CHUNK]->(c) "
                "RETURN count(DISTINCT d) AS n",
                v=QSET_KG_VERSION,
                ids=entity_ids,
            ).single()["n"]
            injected = GraphService.instance().fetch_evidence_chunks(
                kg_version=QSET_KG_VERSION,
                org_id=UUID(ORG_ID),
                entity_ids=entity_ids,
                limit=_EVIDENCE_CHUNK_LIMIT,
            )
    finally:
        driver.close()

    def tally(chunks: list[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for chunk in chunks:
            key = str(chunk.doc_id)[:8] if chunk.doc_id else "(未挂文档)"
            counts[key] = counts.get(key, 0) + 1
        return counts

    injected_counts = tally(injected)

    print(f"kg_version        : {QSET_KG_VERSION}")
    print(
        f"候选实体 / 窗口    : {len(candidate_nodes)} / {_GRAPH_NODE_LIMIT}"
        "（按 entity_type 保底 + 组内度数降序）"
    )
    print(f"文档总数          : {total_docs}")
    print(f"chunk 总数        : {total_chunks}")
    print(
        f"窗口内可达 chunk  : {reachable_n}  "
        f"(覆盖 {reachable_n / total_chunks * 100:.1f}% of chunks；"
        f"仅 {reachable_docs}/{total_docs} 篇文档可达)"
    )
    print(
        f"实际注入 Prompt   : {len(injected)}  (LIMIT {_EVIDENCE_CHUNK_LIMIT}，"
        "每文档保底 + 余量 span 优先——Sprint 10 批次 C 残留缺口)\n"
    )
    print("按文档（doc_id 前 8 位，注入条数）：")
    for doc in sorted(injected_counts, key=lambda k: -injected_counts[k]):
        print(f"  {doc}  注入={injected_counts[doc]}")
    uncovered = total_docs - reachable_docs
    print(
        "\n结论："
        + (
            f"{uncovered}/{total_docs} 篇文档**完全不可达** ⇒ 关于它们的问题必然拒答"
            "（结构性窗口截断，与问题质量无关）"
            if uncovered
            else "所有文档均有 chunk 可达"
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="只做 ¥0 候选集诊断（复算问答能看到哪些 chunk），不调 LLM",
    )
    parser.add_argument(
        "--out",
        help="把每题完整响应（answer / citations / kg_version）落盘为 JSON，"
        "供**人工判分**——答对率只能人读，脚本不做关键词判分（会假达标）",
    )
    args = parser.parse_args()
    if args.diagnose:
        return diagnose()

    answered = 0
    cited = 0
    mismatches: list[str] = []
    failures: list[str] = []
    results: list[dict[str, Any]] = []

    print(
        f"base_url={BASE_URL}  questions={len(QUESTIONS)}  "
        f"qset={QSET_VERSION}  kg_version={QSET_KG_VERSION}\n"
    )

    for index, (question, should_refuse) in enumerate(QUESTIONS, start=1):
        try:
            response = ask(question)
        except urllib.error.HTTPError as exc:
            failures.append(f"Q{index} HTTP {exc.code}")
            print(f"[Q{index:02d}] HTTP {exc.code}  {question}")
            continue
        except Exception as exc:  # noqa: BLE001 - 评估器需跑完全集
            failures.append(f"Q{index} {exc!r}")
            print(f"[Q{index:02d}] ERROR {exc!r}  {question}")
            continue

        refused = bool(response.get("refused"))
        citations = response.get("citations") or []
        chunk_hits = [
            item
            for item in citations
            if str(item.get("chunk_id") or "").startswith("chunk-")
        ]
        kg_version = response.get("kg_version")

        if refused != should_refuse:
            mismatches.append(
                f"Q{index} 期望拒答={should_refuse} 实际={refused} :: {question}"
            )

        if not refused:
            answered += 1
            if citations and len(chunk_hits) == len(citations):
                cited += 1

        print(
            f"[Q{index:02d}] refused={refused!s:<5} conf={response.get('confidence')} "
            f"citations={len(citations)}(chunk={len(chunk_hits)}) "
            f"kg_version={kg_version} :: {question}"
        )
        print(f"       answer: {str(response.get('answer'))[:120]}")

        results.append(
            {
                "index": index,
                "question": question,
                "should_refuse": should_refuse,
                "refused": refused,
                "confidence": response.get("confidence"),
                "kg_version": kg_version,
                "citations": citations,
                "answer": response.get("answer"),
            }
        )

    coverage = (cited / answered * 100) if answered else 0.0
    print("\n================ 汇总 ================")
    print(f"总题数          : {len(QUESTIONS)}")
    print(f"非拒答          : {answered}")
    print(f"引用命中(chunk-): {cited}")
    print(f"引用覆盖率      : {coverage:.1f}%  (目标 100%)")
    print(f"拒答口径不符    : {len(mismatches)}")
    for line in mismatches:
        print(f"  - {line}")
    print(f"请求失败        : {len(failures)}")
    for line in failures:
        print(f"  - {line}")

    if args.out:
        Path(args.out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n完整响应已落盘: {args.out}（供人工判分答对率）")

    ok = coverage >= 100.0 and not mismatches and not failures
    print("\n结论:", "PASS" if ok else "NOT PASS（仅登记，不在本脚本改 Prompt）")
    print(
        "注：脚本只判「引用覆盖率 + 拒答口径」；**答对率需人读 --out 的 answer**，"
        "不做关键词判分（关键词命中会把答非所问读成达标）"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
