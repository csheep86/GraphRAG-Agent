"""受控问题集评估器（Sprint 6 §5.3 验收第 1 条：引用覆盖率 100%、无拒答误伤）。

**只评估、不调 Prompt**（plan §4.2 纪律）：本脚本只跑真实链路并统计，
发现质量问题应登记到 `changes/Sprint6.*/integration-log.md`，**不**就地改 Prompt。

**问题集换版（2026-09-26，v2）**：v1 的 14 题基于 Sprint 6 语料「2025 年度集团经营
指标分析报告」，与当前 active 图谱（种子集 3 份招商局系文件）**不同源** ⇒ 实测拒答
口径不符 11/14。按 `docs/release-notes/v1.4.0.md` §7.2 与决策 A15，**换版安排在演示语料
固化之后**——`docs/demo-seed-dataset.md` 已固化 ⇒ 本次按**同一批语料**重出 14 题
（12 库内 + 2 库外），每题在注释里登记**出处文档与期望答案要点**，便于后续复核。
冻结口径：`kg_version = v-s71a-fe1c4dc3`（换版基准，语料再变即作废需重出）。

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
QSET_VERSION = "v2-2026-09-26"
QSET_KG_VERSION = "v-s71a-fe1c4dc3"

#: (问题, 是否预期拒答)。
#:
#: 库内 12 题：覆盖种子集 3 份原件（招商公路 / 招商蛇口募集说明书 + 招商轮船 2025 年报），
#: 每题注释登记「出处 → 期望答案要点」，均经 Neo4j `:Chunk` 正文命中核对（2026-09-26 实测）。
#: 库外 2 题：验证拒答出口不被误伤（F3 的反面：不该答的别答）——**刻意选语料里完全不存在的
#: 主体**（库外问若仍带「招商轮船 + 营业收入」这类库内高词频词，会被误召回 ⇒ 拒答判据失真）。
QUESTIONS: list[tuple[str, bool]] = [
    # ---- 招商公路：2024 年第一期科技创新公司债募集说明书 ----
    # 出处：封面要素表 → 期望「不超过人民币 20 亿元（含 20 亿元）」
    ("招商公路本期债券的发行金额上限是多少？", False),
    # 出处：封面要素表 → 期望「不超过人民币 50 亿元（含 50 亿元）」
    ("招商公路本次债券的注册金额是多少？", False),
    # 出处：封面要素表「增信情况」→ 期望「无（无增信安排）」
    ("招商公路本期债券是否有增信安排？", False),
    # 出处：封面要素表「信用评级机构」→ 期望「中诚信国际信用评级有限责任公司」
    ("招商公路本期债券的信用评级机构是哪家？", False),
    # 出处：第三节「上市情况」→ 期望「深圳证券交易所」
    ("招商公路本期债券发行结束后拟申请在哪里上市交易？", False),
    # ---- 招商蛇口：2024 年第一期公司债募集说明书 ----
    # 出处：封面要素表「牵头主承销商」→ 期望「招商证券股份有限公司」
    ("招商蛇口本期债券的牵头主承销商是哪家机构？", False),
    # 出处：封面要素表「受托管理人」→ 期望「中信证券股份有限公司」
    ("招商蛇口本期债券的受托管理人是谁？", False),
    # 出处：封面要素表 → 期望「不超过人民币 50 亿元（含）」
    ("招商蛇口本期债券的发行金额上限是多少？", False),
    # 出处：封面要素表 → 期望「主体评级 AAA、债券评级 AAA，评级机构联合资信评估股份有限公司」
    ("招商蛇口本期债券的主体信用评级结果及评级机构是什么？", False),
    # 出处：封面要素表「增信措施情况」→ 期望「本期债券无担保」
    ("招商蛇口本期债券是否提供担保？", False),
    # ---- 招商轮船：2025 年年度报告 ----
    # 出处：年报首页「公司代码」→ 期望「601872」
    ("招商轮船的股票代码是多少？", False),
    # 出处：重要提示第三条 → 期望「毕马威华振会计师事务所（特殊普通合伙），标准无保留意见」
    ("招商轮船 2025 年年度报告由哪家会计师事务所审计，出具了什么意见？", False),
    # ---- 库外问题：预期拒答（refused=true）----
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

    为什么需要它：问答的候选集是**结构性**的——active 版本全量实体取前 ``_GRAPH_NODE_LIMIT``
    个（**无 ORDER BY**）→ 按 ``MENTIONS`` 反查 chunk → 再 ``LIMIT _EVIDENCE_CHUNK_LIMIT``
    （**无排序、无打分**），``question`` 文本**不参与**。于是「某文档 0 条注入」⇒ 关于它的
    问题**必然拒答**，与问题怎么写无关。换版后若出现非预期拒答，先跑这条命令归因，
    别急着改问题集（plan §4.2 纪律：只评估、不调 Prompt）。
    """
    from neo4j import GraphDatabase  # noqa: PLC0415 - 仅诊断模式需要

    from app.core.config import get_settings  # noqa: PLC0415
    from app.services.agents import (  # noqa: PLC0415 - 直接复用线上常量，避免脚本写死后漂移
        _GRAPH_NODE_LIMIT,
    )
    from app.services.graphs import (  # noqa: PLC0415
        _EVIDENCE_CHUNK_LIMIT,
        _QUERY_ALL_ENTITY_SUBGRAPH,
        _QUERY_EVIDENCE_CHUNKS_BY_ENTITIES,
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

            row = session.run(
                _QUERY_ALL_ENTITY_SUBGRAPH,
                kg_version=QSET_KG_VERSION,
                org_id=ORG_ID,
                node_limit=_GRAPH_NODE_LIMIT,
            ).single()
            entity_ids = [node["id"] for node in row["nodes"]]

            reachable = list(
                session.run(
                    _QUERY_EVIDENCE_CHUNKS_BY_ENTITIES,
                    kg_version=QSET_KG_VERSION,
                    entity_ids=entity_ids,
                    org_id=ORG_ID,
                    limit=10**6,  # 不截断：看窗口内**总共**能到多少 chunk
                )
            )
            injected = list(
                session.run(
                    _QUERY_EVIDENCE_CHUNKS_BY_ENTITIES,
                    kg_version=QSET_KG_VERSION,
                    entity_ids=entity_ids,
                    org_id=ORG_ID,
                    limit=_EVIDENCE_CHUNK_LIMIT,
                )
            )
    finally:
        driver.close()

    def tally(rows: list[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in rows:
            key = str(item["doc_id"])[:8] if item["doc_id"] else "(未挂文档)"
            counts[key] = counts.get(key, 0) + 1
        return counts

    reachable_counts = tally(reachable)
    injected_counts = tally(injected)

    print(f"kg_version        : {QSET_KG_VERSION}")
    print(
        f"实体总数 / 窗口    : {row['total_nodes']} / {_GRAPH_NODE_LIMIT}（无 ORDER BY，按扫描序）"
    )
    print(f"文档总数          : {total_docs}")
    print(f"chunk 总数        : {total_chunks}")
    print(
        f"窗口内可达 chunk  : {len(reachable)}  "
        f"(覆盖 {len(reachable) / total_chunks * 100:.1f}% of chunks；"
        f"仅 {len(reachable_counts)}/{total_docs} 篇文档可达)"
    )
    print(
        f"实际注入 Prompt   : {len(injected)}  (LIMIT {_EVIDENCE_CHUNK_LIMIT}，无排序/无打分)\n"
    )
    print("按文档（doc_id 前 8 位）：")
    for doc in sorted(reachable_counts, key=lambda k: -reachable_counts[k]):
        print(
            f"  {doc}  可达={reachable_counts[doc]:<5} 注入={injected_counts.get(doc, 0)}"
        )
    uncovered = total_docs - len(reachable_counts)
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
    args = parser.parse_args()
    if args.diagnose:
        return diagnose()

    answered = 0
    cited = 0
    mismatches: list[str] = []
    failures: list[str] = []

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

    ok = coverage >= 100.0 and not mismatches and not failures
    print("\n结论:", "PASS" if ok else "NOT PASS（仅登记，不在本脚本改 Prompt）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
