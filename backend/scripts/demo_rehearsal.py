"""Sprint 8 批次 D 第 2 项：**演示彩排脚本** —— 机械走查「演示剧本 6 步」。

闭合 `docs/release-notes/v1.4.0.md` §7.2 第 8 项（关 Mock 硬门槛的**全站走查**此前
只有 audit 页的浏览器点验，**没有机械证据**）与 §7.3 第 2 项（彩排脚本未做）。

用法（工作目录 = `backend/`，**先**起服务）：

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
    uv run python scripts/demo_rehearsal.py                          # ¥0 默认（关联交易 6 步）
    uv run python scripts/demo_rehearsal.py --with-llm               # 含真实问答（**烧 token**）
    uv run python scripts/demo_rehearsal.py --frontend-base http://127.0.0.1:3000
    uv run python scripts/demo_rehearsal.py --json reports/rehearsal.json

    # 考勤域（Sprint 9.5）：异常清单 → 合规扫描 → 异常归因 → 问答 → 审计 → 前端 4 页
    uv run python scripts/demo_rehearsal.py --domain attendance
    uv run python scripts/demo_rehearsal.py --domain attendance --as-of 2026-12-15
    uv run python scripts/demo_rehearsal.py --domain attendance --frontend-base http://127.0.0.1:3000

退出码：**0** = 无 FAIL（SKIP 不算失败）／**1** = 有 FAIL／**2** = 配置或连通性错误。

纪律（与项目「不假做」一致）：

- **默认 ¥0**：第 3 步「提问」走真实 LLM，默认 **SKIP**，必须显式 `--with-llm` 才跑；
- **不改数据**：**不上传、不建图、不改库**。脚本核的是**既有**演示态（上传 / 重建属
  `docs/demo-seed-dataset.md` §4 的步骤，需 MinerU + LLM 费用且会写库，不由彩排脚本代做）；
- **同一 trace 手工贯穿**：前端 `client.ts::request()` **只读不发** `X-Trace-Id`
  （⇒ 浏览器自然操作每请求一个新 trace，审计页不会自然聚合），因此脚本**必须自己透传**
  同一个 UUID 才能让第 6 步「审计回放」成立（该缺口已登记 → S11）；
- **断言的是真实字段**：统计值 / `entity_type` / `evidence` / `action` 全部取自响应，
  任一回归（如属性名错配、统计值恒 0）都会在这里红。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

# 脚本位于 backend/scripts/ 下，需把 backend/（cwd）加进模块搜索路径，
# 才能 import app.core.config 复用**在线服务同一份配置**（不在脚本里硬编码 org_id）。
sys.path.insert(0, str(Path.cwd()))

#: 演示剧本 6 步各自**必须**留下的审计 action（缺一个 ⇒ 第 6 步无机械证据）。
REQUIRED_ACTIONS = (
    "document.list",  # 步骤 1 上传（核既有语料）
    "graph.overview",  # 步骤 2 看图
    "graph.entity",  # 步骤 3 点实体
    "document.status",  # 步骤 4 溯源
    "document.graph",  # 步骤 4 溯源（chunk / 证据链）
    "affiliation.list",  # 步骤 5 疑点
)

#: 抄自 `docs/demo-seed-dataset.md` §4 的复核问题（语料同源，避免问空）。
DEFAULT_QUESTION = "招商局集团有限公司与招商局轮船有限公司之间存在哪些关联？"

# ------------------------------------------------------------------ attendance
#: `--domain attendance`（Sprint 9.5 批次 F1）的必需 action。
#: `agent.query` **不**在默认集合里——问答默认 SKIP（¥0），把只在 `--with-llm`
#: 下才会出现的 action 写进来会让默认用例必 FAIL。
ATTENDANCE_REQUIRED_ACTIONS = (
    "compliance.scan",  # 步骤 A2 合规扫描
    "compliance.anomaly_list",  # 步骤 A1 异常清单
    "compliance.anomaly_explain",  # 步骤 A3 异常归因
)

#: 考勤域演示问题（语料同源：员工名 / 城市取自 `demo/attendance/`）
#:
#: **刻意取事实型问题**（2026-09-28 真机实测后改）：原默认问「李静的月加班超过上限了吗？」
#: 属**计算型**——数值不出 LLM，问答只能答「无法认定」；而同一份事实在合规预警页由
#: 规则引擎给出确定性结论「42h > 36h 超限（高）」⇒ 两页同屏**自相矛盾**，
#: 客户会读成「系统自己都说不清」（登记见 `docs/dev-doc-status.md` **R17**）。
#: 计算型问题**仍可用 `--question` 传**（刻意保留这条路径，用于演示能力边界），
#: 只是不再作为默认——默认必须是「两页口径一致、拿得出手」的那一种。
ATTENDANCE_QUESTION = "张伟 2026-10-16 被派了哪个工单？工单在哪天闭环？"

#: 考勤域前端页与各自的**必含关键词**（VA：页面是不是真的把真数据渲染出来了）
ATTENDANCE_PAGES = (
    ("/attendance", "考勤域", "考勤域首页"),
    ("/attendance/compliance", "合规预警", "合规预警页"),
    ("/attendance/attribution", "异常归因", "异常归因子页"),
    ("/attendance/qa", "政策问答", "政策问答子页"),
)


@dataclass
class Check:
    """一步走查的结果。"""

    step: str
    title: str
    status: str  # PASS / FAIL / SKIP
    detail: str


@dataclass
class Rehearsal:
    """一次彩排：收集全部 :class:`Check` 并给出退出码。"""

    checks: list[Check] = field(default_factory=list)

    def add(self, step: str, title: str, status: str, detail: str) -> None:
        self.checks.append(Check(step=step, title=title, status=status, detail=detail))
        print(f"[{status:4}] 步骤 {step} {title}: {detail}")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")


def _headers(trace_id: str) -> dict[str, str]:
    """从**在线服务的同一份配置**取 dev 头：不许在脚本里硬编码 org_id。"""
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "X-Org-Id": str(settings.default_org_id),
        "X-Actor-Id": str(settings.default_actor_id),
        "X-Trace-Id": trace_id,
    }


def _fail(report: Rehearsal, step: str, title: str, detail: str) -> None:
    report.add(step, title, "FAIL", detail)


def step_1_corpus(
    client: httpx.Client, report: Rehearsal, *, probe: int = 12
) -> list[str]:
    """步骤 1（上传 → 秒回 task_id → 状态流转）：核既有语料处于 completed。

    不代做上传——上传会烧 MinerU + LLM 且写库，属重建步骤（见模块 docstring）。

    :return: 至多 ``probe`` 篇 completed 文档 id（**按接口顺序**，其中可能含未建图的
        杂项文档 ⇒ 步骤 4 需逐篇试探取有子图的那篇，不能盲信第一条）。
    """
    data = client.get("/documents").json()
    items = data.get("items") or []
    completed = [i for i in items if i.get("status") == "completed"]
    if not items:
        _fail(
            report, "1", "语料就绪", "documents 为空——先按 demo-seed-dataset.md §4 重建"
        )
        return []
    if not completed:
        _fail(report, "1", "语料就绪", f"{len(items)} 篇文档无一 completed")
        return []
    ids = [str(i.get("id") or "") for i in completed[:probe]]
    report.add(
        "1",
        "语料就绪",
        "PASS",
        f"total={data.get('total')} completed={len(completed)}"
        f"（取前 {len(ids)} 篇待查子图；不代做上传，属重建步骤）",
    )
    return ids


def step_2_graph(client: httpx.Client, report: Rehearsal) -> tuple[int, int]:
    """步骤 2（看图）：统计值非 0 + 实体类型非空（防「恒 0 / 属性名错配」回归）。"""
    data = client.get("/graph/overview").json()
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    doc_count = int(data.get("doc_count") or 0)
    entity_count = int(data.get("entity_count") or 0)
    relation_count = int(data.get("relation_count") or 0)

    if not nodes or not edges:
        _fail(report, "2", "看图", f"nodes={len(nodes)} edges={len(edges)}（图谱为空）")
        return doc_count, entity_count
    if not (doc_count and entity_count and relation_count):
        _fail(
            report,
            "2",
            "看图",
            f"统计值有 0：doc={doc_count} entity={entity_count} rel={relation_count}"
            "（曾因硬编码 0 静默假数据，见 notes §7.5）",
        )
        return doc_count, entity_count

    # 实体类型非空：属性名错配（写 entity_type / 读 type）曾让该字段恒空 ⇒ 守住。
    typed = 0
    for node in nodes[:5]:
        node_id = node.get("id")
        if not node_id:
            continue
        entity = client.get(f"/entities/{node_id}").json()
        if entity.get("entity_type"):
            typed += 1
    if typed == 0:
        _fail(
            report,
            "2",
            "实体类型",
            "抽样 5 个节点 entity_type 全空（疑似属性名错配回归）",
        )
        return doc_count, entity_count

    report.add(
        "2",
        "看图",
        "PASS",
        f"nodes={len(nodes)} edges={len(edges)} doc={doc_count} "
        f"entity={entity_count} rel={relation_count} kg_version={data.get('kg_version')} "
        f"（抽样 {typed}/5 实体类型非空）",
    )
    return doc_count, entity_count


def step_3_ask(
    client: httpx.Client, report: Rehearsal, *, with_llm: bool, question: str
) -> None:
    """步骤 3（提问）：默认 SKIP（真实 LLM 烧钱），`--with-llm` 才真跑。"""
    if not with_llm:
        report.add(
            "3", "提问", "SKIP", "¥0 默认跳过（真实 LLM 烧 token）；加 --with-llm 才跑"
        )
        return
    print("      注意：以下步骤调用真实 LLM，**会产生费用**")
    data = client.post("/agent/query", json={"question": question}).json()
    answer = data.get("answer") or ""
    citations = data.get("citations") or []
    if not answer:
        _fail(report, "3", "提问", "answer 为空")
        return
    report.add(
        "3",
        "提问",
        "PASS",
        f"refused={data.get('refused')} route={data.get('route')} "
        f"citations={len(citations)} answer={answer[:40]}…",
    )


def step_4_trace_back(
    client: httpx.Client, report: Rehearsal, doc_ids: list[str]
) -> None:
    """步骤 4（溯源）：文档状态 completed + 文档子图有节点（chunk / 证据链）。

    候选里可能混着**未建图的杂项文档**（本机实况：9 篇 completed 中 3 篇 `node_count=0`，
    它们是未被纳入 active 版本的上传）⇒ 逐篇试探，取**第一个有子图的**，全空才算 FAIL。
    """
    if not doc_ids:
        report.add("4", "溯源", "SKIP", "无 completed 文档 id（见步骤 1）")
        return

    probed: list[str] = []
    for doc_id in doc_ids:
        status = client.get(f"/documents/{doc_id}/status").json().get("status")
        graph = client.get(f"/documents/{doc_id}/graph").json()
        node_count = int(graph.get("node_count") or 0)
        probed.append(f"{doc_id[:8]}:{node_count}")
        if status == "completed" and node_count > 0:
            report.add(
                "4",
                "溯源",
                "PASS",
                f"文档 {doc_id[:8]} status=completed，子图 node_count={node_count} "
                f"relation_count={graph.get('relation_count')}"
                f"（试过 {len(probed)} 篇：{' '.join(probed)}）",
            )
            return

    _fail(
        report,
        "4",
        "溯源",
        f"{len(probed)} 篇 completed 文档子图全为空（{' '.join(probed)}）"
        "—— active 版本未包含这些文档？",
    )


def step_5_suspicions(client: httpx.Client, report: Rehearsal) -> None:
    """步骤 5（疑点）：疑点非空且每条带证据链。"""
    data = client.get("/affiliation/suspicions").json()
    items = data.get("items") or []
    if not items:
        _fail(report, "5", "疑点", "total=0（疑点清单为空）")
        return
    with_evidence = [i for i in items if i.get("evidence")]
    if not with_evidence:
        _fail(report, "5", "疑点", f"{len(items)} 条疑点无一带 evidence")
        return
    report.add(
        "5",
        "疑点",
        "PASS",
        f"total={data.get('total')}，{len(with_evidence)}/{len(items)} 条带证据链 "
        f"（样例 {with_evidence[0].get('suspicion_type')} / {with_evidence[0].get('severity')}）",
    )


def step_6_audit(
    client: httpx.Client,
    report: Rehearsal,
    trace_id: str,
    *,
    min_rows: int,
    required: tuple[str, ...] = REQUIRED_ACTIONS,
    with_llm: bool = False,
) -> None:
    """步骤 6（审计）：同一 trace 回放 —— 条数达标 **且** 各步 action 齐全。"""
    data = client.get(f"/audit/trace/{trace_id}").json()
    items = data.get("items") or []
    actions = {i.get("action") for i in items}
    missing = [a for a in required if a not in actions]
    # 问答只在 `--with-llm` 下才发生：没跑就别要求它的 action 出现（反之必须出现）
    if with_llm and "agent.query" not in actions:
        missing.append("agent.query")
    if len(items) < min_rows:
        _fail(
            report, "6", "审计回放", f"同一 trace 仅 {len(items)} 条（需 ≥ {min_rows}）"
        )
        return
    if missing:
        _fail(
            report, "6", "审计回放", f"缺 action：{missing}（已录 {sorted(actions)}）"
        )
        return
    report.add(
        "6",
        "审计回放",
        "PASS",
        f"trace {trace_id[:8]} 共 {len(items)} 条，action 齐全：{sorted(actions)}",
    )


# ------------------------------------------------------------------ attendance
def step_a1_anomalies(client: httpx.Client, report: Rehearsal) -> list[dict]:
    """A1 异常清单：**有人才谈得上归因**。

    空清单 ⇒ FAIL：演示剧本第一件事就是「谁缺卡了」，没有用例说明语料没导入。
    """
    data = client.get("/attendance/anomalies").json()
    items = data.get("items") or []
    if not items:
        _fail(
            report,
            "A1",
            "异常清单",
            "items 为空——先执行 scripts/ingest_attendance_csv.py 导入演示语料",
        )
        return []
    report.add(
        "A1",
        "异常清单",
        "PASS",
        f"total={data.get('total')} kg_version={data.get('kg_version')} "
        f"首条={items[0].get('employee_name')} / {items[0].get('date')}",
    )
    return items


def step_a2_compliance(
    client: httpx.Client, report: Rehearsal, *, as_of: str | None
) -> None:
    """A2 合规扫描：有风险 + **每个规则值都带制度出处** + 没有规则被跳过。

    **为什么要单独验 `unresolved`**：规则值解析不出来时后端会「跳过该规则」，
    演示时表现为"扫完了没事"——但其实是**没算**。这是本项目最危险的静默失败，
    彩排必须在开讲前把它挑出来。
    """
    data = client.get(
        "/attendance/compliance/scan",
        params={"as_of": as_of} if as_of else None,
    ).json()
    findings = data.get("findings") or []
    values = data.get("rule_values") or []

    if not values:
        _fail(report, "A2", "规则值", "rule_values 为空（制度文本没解析出任何判据）")
        return
    sourceless = [
        item.get("key")
        for item in values
        if not (item.get("source") and item.get("reference") and item.get("evidence"))
    ]
    if sourceless:
        _fail(report, "A2", "规则值出处", f"以下规则值无出处：{sourceless}")
        return
    if data.get("unresolved"):
        _fail(
            report,
            "A2",
            "规则值解析",
            f"unresolved={data['unresolved']}（有判据没解析出来 ⇒ 对应规则被跳过）",
        )
        return
    if data.get("skipped_rules"):
        _fail(report, "A2", "规则跳过", f"skipped_rules={data['skipped_rules']}")
        return
    if not findings:
        _fail(
            report, "A2", "合规扫描", "findings 为空（五条规则零命中？语料被改坏了？）"
        )
        return

    high = sum(1 for item in findings if item.get("level") == "high")
    sample = findings[0]
    report.add(
        "A2",
        "合规扫描",
        "PASS",
        f"total={data.get('total')}（high {high} / medium {len(findings) - high}）"
        f" 规则值 {len(values)} 条全部带出处；样例 {sample.get('employee_name')}"
        f"「{sample.get('calculation')}」",
    )


def step_a3_attribution(
    client: httpx.Client, report: Rehearsal, cases: list[dict]
) -> None:
    """A3 异常归因：**自己重算一遍置信度**，对不上就是 Regression（含「补卡」措辞出处）。"""
    if not cases:
        report.add("A3", "异常归因", "SKIP", "无异常用例（见步骤 A1）")
        return

    case = cases[0]
    data = client.get(
        "/attendance/anomalies/explain",
        params={"employee_id": case["employee_id"], "date": case["date"]},
    ).json()
    causes = data.get("causes") or []
    if not causes:
        _fail(report, "A3", "原因排序", "causes 为空（归因没跑出任何原因）")
        return

    total = sum(float(item["weight"]) for item in causes)
    hit = sum(float(item["weight"]) for item in causes if item["matched"])
    expected = round(hit / total, 4) if total else 0.0
    if abs(float(data.get("confidence") or 0) - expected) > 1e-6:
        _fail(
            report,
            "A3",
            "置信度可核算",
            f"confidence={data.get('confidence')} ≠ Σ命中/Σ全部={expected}"
            "（确定性加权被改动）",
        )
        return

    evidenceless = [
        item["code"] for item in causes if item["matched"] and not item["evidence"]
    ]
    if evidenceless:
        _fail(report, "A3", "证据可回查", f"命中却无证据节点：{evidenceless}")
        return

    action = str(data.get("action") or "")
    if "补卡" in action and not data.get("policy_refs"):
        _fail(
            report,
            "A3",
            "制度措辞出处",
            f"结论里出现「补卡」（action={action}）但 policy_refs 为空（守 F3 不成立）",
        )
        return

    report.add(
        "A3",
        "异常归因",
        "PASS",
        f"{case['employee_name']} {case['date']} ⇒ {data.get('conclusion')}"
        f"（置信度 {data.get('confidence')} = {hit:g}/{total:g}，4 项原因、"
        f"政策出处 {len(data.get('policy_refs') or [])} 条）",
    )


def step_7_frontend(
    report: Rehearsal,
    base: str | None,
    *,
    timeout: float,
    pages: tuple[tuple[str, str, str], ...] = (
        ("/audit", "审计", "audit 页"),
        ("/settings", "演示环境", "settings 页 A16 标注"),
    ),
) -> None:
    """可选：`USE_MOCK=false` 下前端页走查（按域给定 `pages`）。"""
    if not base:
        report.add("7", "前端页", "SKIP", "未给 --frontend-base（需先起 next dev）")
        return
    with httpx.Client(base_url=base, timeout=timeout) as client:
        for path, must, title in pages:
            try:
                response = client.get(path)
            except httpx.HTTPError as exc:  # 前端没起 ≠ 演示失败 ⇒ SKIP 而非 FAIL
                report.add("7", title, "SKIP", f"请求失败：{exc}")
                continue
            if response.status_code != 200:
                _fail(report, "7", title, f"{path} → HTTP {response.status_code}")
                continue
            if must not in response.text:
                _fail(report, "7", title, f"{path} 200 但页面不含「{must}」")
                continue
            report.add("7", title, "PASS", f"{path} → 200 且含「{must}」")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="演示剧本 6 步彩排走查（默认 ¥0）")
    parser.add_argument(
        "--domain",
        choices=("default", "attendance"),
        default="default",
        help=(
            "演示剧本：`default`=既有关联交易 6 步；"
            "`attendance`=考勤域（Sprint 9.5：异常清单 A1 / 合规扫描 A2 / "
            "异常归因 A3 / 问答 A4 / 审计 A6 / 前端 A7）"
        ),
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--api-prefix", default="/api/v1", help="API 前缀")
    parser.add_argument("--frontend-base", default=None, help="前端地址（可选）")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="跑真实问答（步骤 3），**会产生 LLM 费用**；默认跳过",
    )
    parser.add_argument(
        "--question",
        default=None,
        help="--with-llm 时的提问（缺省按 --domain 取该域的语料同源问题）",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="考勤域合规扫描的观察日（ISO 日期；演示调休「临期升级」用 2026-12-15）",
    )
    parser.add_argument(
        "--min-trace-rows", type=int, default=7, help="步骤 6 最少审计条数"
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="单请求超时（秒）")
    parser.add_argument("--json", dest="json_path", default=None, help="报告输出路径")
    args = parser.parse_args(argv)

    # Windows 控制台默认 GBK，中文与「¥」会 UnicodeEncodeError ⇒ 强制 UTF-8 输出。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    trace_id = str(uuid4())
    report = Rehearsal()
    question = args.question or (
        ATTENDANCE_QUESTION if args.domain == "attendance" else DEFAULT_QUESTION
    )
    print(
        f"彩排开始：domain={args.domain} base={args.base_url} "
        f"trace_id={trace_id} with_llm={args.with_llm}"
    )

    client = httpx.Client(
        base_url=f"{args.base_url}{args.api_prefix}",
        headers=_headers(trace_id),
        timeout=args.timeout,
    )
    try:
        try:
            health = client.get("/health").json()
        except (httpx.HTTPError, ValueError) as exc:
            print(f"后端不可达：{exc}", file=sys.stderr)
            return 2
        if health.get("status") != "ok":
            print(f"后端不健康：{health}", file=sys.stderr)
            return 2
        report.add(
            "0",
            "服务健康",
            "PASS",
            f"version={health.get('version')} checks={health.get('checks')}",
        )

        if args.domain == "attendance":
            cases = step_a1_anomalies(client, report)
            step_a2_compliance(client, report, as_of=args.as_of)
            step_a3_attribution(client, report, cases)
            step_3_ask(client, report, with_llm=args.with_llm, question=question)
            step_6_audit(
                client,
                report,
                trace_id,
                min_rows=3,
                required=ATTENDANCE_REQUIRED_ACTIONS,
                with_llm=args.with_llm,
            )
            frontend_pages = ATTENDANCE_PAGES
        else:
            doc_ids = step_1_corpus(client, report)
            step_2_graph(client, report)
            step_3_ask(client, report, with_llm=args.with_llm, question=question)
            step_4_trace_back(client, report, doc_ids)
            step_5_suspicions(client, report)
            step_6_audit(
                client,
                report,
                trace_id,
                min_rows=args.min_trace_rows,
                with_llm=args.with_llm,
            )
            frontend_pages = (
                ("/audit", "审计", "audit 页"),
                ("/settings", "演示环境", "settings 页 A16 标注"),
            )
    finally:
        client.close()

    step_7_frontend(
        report, args.frontend_base, timeout=args.timeout, pages=frontend_pages
    )

    failed = report.failed
    passed = sum(1 for c in report.checks if c.status == "PASS")
    skipped = sum(1 for c in report.checks if c.status == "SKIP")
    print(f"\n彩排结束：PASS {passed} / FAIL {failed} / SKIP {skipped}")

    if args.json_path:
        payload: dict[str, Any] = {
            "trace_id": trace_id,
            "domain": args.domain,
            "base_url": args.base_url,
            "with_llm": args.with_llm,
            "summary": {"pass": passed, "fail": failed, "skip": skipped},
            "checks": [c.__dict__ for c in report.checks],
        }
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"报告已写入：{path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
