"""Sprint 9.5 批次 D2：职责边界的**守卫测试**（不是文档）。

口径：**规则引擎出数值 → LLM 只出措辞**；**无溯源即拒答**（守 F3）。

**为什么必须是测试而不是 md**：md 不会被 CI 拦截，边界失守时没人会红。
本文件把边界钉成断言，覆盖现有归因（C2）、规则引擎（C1）与新增推理路径（D1）：

1. 规则引擎每条风险里的**数值**必须能在「计算过程」或「规则值出处」里找到来源；
2. 归因每条命中原因必须带证据节点 id；**零证据 ⇒ 置信度 0 + 结论「不成立」**
   （**不**给 60% 这种凑合分）；
3. 推理路径只承载节点 / 边，**不**承载数值结论；
4. 出数值的模块**不得**接 LLM（源码级机械守卫，防后人把 LLM 接进规则引擎）；
5. 问答无证据 ⇒ 拒答，**不**给凑合答案。

**发现的现有违规一律用 ``xfail(strict=True)`` 登记**：CI 绿但显式可见，
由主代理决定是否修——**绝不**为过测试而放宽断言（放宽即等于把违规合法化）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.schemas.agent import ReasoningPathHop
from app.services.rules import engine as engine_module
from app.services.rules.attribution import attribute_absence
from app.services.rules.policy_values import RuleValueBook, resolve_rule_values

BACKEND_DIR = Path(__file__).resolve().parents[1]

#: 出数值 / 出证据链的模块——**不得**出现 LLM 客户端
_NUMERIC_MODULES = (
    "app/services/rules/engine.py",
    "app/services/rules/attribution.py",
    "app/services/rules/policy_values.py",
    "app/services/reasoning.py",
)

_LLM_TOKENS = ("langchain", "ChatOpenAI", "build_chat_model", "llm_api_key")


# --------------------------------------------------------------------------- #
# 规则值（从制度文本真解析，出处可核）
# --------------------------------------------------------------------------- #
def _policy_book() -> RuleValueBook:
    """把 4 个规则值从**制度原文**解析出来（出处 = `document:doc:attendance:L<n>`）。"""
    from app.services.rules.policy_values import _TextSegment

    lines = (
        "第七条 综合计算工时制以月为周期核算，月标准工时为 174 小时。",
        "第八条 每月加班时间不得超过 36 小时。",
        "第九条 调休应在加班所在季度内使用，季度剩余不足 30 天视为临期。",
        "第十条 连续出勤达到 12 天应当安排休息。",
    )
    return resolve_rule_values(
        documents=tuple(
            _TextSegment(
                text=line,
                source="document",
                reference=f"doc:attendance:L{index}",
                order=("attendance", index),
            )
            for index, line in enumerate(lines, start=1)
        )
    )


class _FactsSession:
    """按 Cypher 关键字回放考勤事实的假会话（不连真机）。"""

    def __init__(self) -> None:
        days = [date(2026, 10, day) for day in range(1, 23)]
        self._employees = [
            {
                "node_id": "EMPLOYEE:E002",
                "name": "李静",
                "department": "生产部",
                "position": "产线操作工",
                "wts": "综合计算工时制",
            }
        ]
        self._shifts = [
            {
                "employee": "EMPLOYEE:E002",
                "node_id": f"SHIFT:S{i:05d}",
                "date": day.isoformat(),
                "hours": 12.0 if i < 10 else 8.0,
                "rest": 0,
            }
            for i, day in enumerate(days)
        ]
        self._attendance = [
            {
                "employee": "EMPLOYEE:E002",
                "node_id": f"ATTENDANCE_RECORD:A{i:05d}",
                "date": day.isoformat(),
                "hours": 8.0,
                "core": 6.0,
                "status": "normal",
                "rest": 0,
            }
            for i, day in enumerate(days)
        ]
        self._overtime = [
            {
                "employee": "EMPLOYEE:E002",
                "node_id": "OVERTIME:OT0001",
                "date": "2026-10-11",
                "hours": 22.0,
                "approved": 1,
                "comp_off": 22.0,
                "comp_off_used": 0.0,
            }
        ]

    def run(self, cypher: str, **params: object) -> list[dict]:
        if "e.id AS node_id" in cypher:
            return list(self._employees)
        if "HAS_SHIFT" in cypher:
            return list(self._shifts)
        if "HAS_ATTENDANCE" in cypher:
            return list(self._attendance)
        if "ACCUMULATED_OVERTIME" in cypher:
            return list(self._overtime)
        return []


def _scan(monkeypatch: pytest.MonkeyPatch):
    book = _policy_book()
    monkeypatch.setattr(engine_module, "resolve_rule_values", lambda **kw: book)
    return engine_module.scan_compliance(
        session=_FactsSession(),
        kg_version="v-test",
        org_id="org",
        as_of=date(2026, 10, 31),
    ), book


# --------------------------------------------------------------------------- #
# 守卫 1：规则引擎的数值可溯源
# --------------------------------------------------------------------------- #
def test_finding_numbers_appear_in_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    """`observed` / `threshold` 必须能在计算过程里逐字找到（数值可念、可核）。"""
    report, _ = _scan(monkeypatch)
    assert report.findings, "扫描必须有命中，否则本守卫等于没跑"

    for finding in report.findings:
        assert f"{finding.observed:g}" in finding.calculation
        assert f"{finding.threshold:g}" in finding.calculation


def test_finding_policy_refs_match_rule_value_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """每条风险的 `policy_refs` 必须是**已解析规则值**的出处（不得凭空写出处）。"""
    report, book = _scan(monkeypatch)
    legal = {f"{item.source}:{item.reference}" for item in book.values}

    for finding in report.findings:
        assert finding.policy_refs, f"{finding.rule} 无规则值出处"
        assert set(finding.policy_refs) <= legal


def test_finding_evidence_is_graph_node_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """每条风险必须带证据节点 id（可回查图谱）——没证据的判定等于猜。"""
    report, _ = _scan(monkeypatch)
    for finding in report.findings:
        assert finding.evidence, f"{finding.rule} 无证据节点"
        assert all(":" in node_id for node_id in finding.evidence)


def test_every_threshold_comes_from_policy_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**严格守卫**：`threshold` 必须来自规则值出处，**不得**是裸代码常量。

    **唯一例外**（2026-09-28 处置）：`SENTINEL_UNUSED_BOUNDARY`（0.0）是**规则
    语义边界**而非制度阈值——它判定的是「有没有开始消化」这种**有无**问题，
    制度里没有对应的数值可解析（制度的临期判据是「季度剩余 < 30 天」，
    已由 `RuleValueBook` 提供并进了 `policy_refs`）。

    做法是把它提为**具名常量**并要求常量的语义写进 `calculation`
    ——不是给守卫开后门：任何新出现的裸数值照样会被这里打红。
    """
    report, book = _scan(monkeypatch)
    legal = {item.value for item in book.values}

    for finding in report.findings:
        if finding.threshold == engine_module.SENTINEL_UNUSED_BOUNDARY:
            # 语义边界必须在计算过程里说清自己是什么，否则还是"来历不明的 0"
            assert "判定边界" in finding.calculation, (
                f"{finding.rule} 用了语义边界却没在计算过程里说明"
            )
            continue
        assert finding.threshold in legal, (
            f"{finding.rule} 阈值 {finding.threshold} 无出处"
        )


# --------------------------------------------------------------------------- #
# 守卫 2：归因 —— 零证据即不成立，不给凑合分
# --------------------------------------------------------------------------- #
class _EmptySession:
    """什么证据都没有（缺卡日既无出差、也无工单 / 定位 / 门禁）。"""

    def run(self, cypher: str, **params: object) -> list[dict]:
        return []


def test_zero_evidence_means_not_established() -> None:
    """零证据 ⇒ 置信度 0.0 + 结论「不成立」，**不**给「需人工复核」这种凑合态。"""
    result = attribute_absence(
        session=_EmptySession(),
        kg_version="v-test",
        org_id="org",
        employee_id="E001",
        day=date(2026, 10, 16),
        employee_name="张伟",
    )

    assert result.confidence == 0.0
    assert result.conclusion == "外勤出勤不成立"
    assert not any(cause.matched for cause in result.causes)
    # 命中项才进分子；没命中就**不许**带证据 id（否则前端会以为有据可依）
    assert all(not cause.evidence for cause in result.causes)


def test_matched_causes_must_carry_evidence_ids() -> None:
    """每条**命中**的原因都必须带证据节点 id（置信度的分子必须可回查）。"""

    class _Session:
        def run(self, cypher: str, **params: object) -> list[dict]:
            if "ON_BUSINESS_TRIP" in cypher:
                return [
                    {
                        "node_id": "BUSINESS_TRIP:BT1",
                        "destination": "武汉",
                        "site": "武汉",
                        "status": "approved",
                        "start_date": "2026-10-16",
                        "end_date": "2026-10-18",
                    }
                ]
            if "HANDLED_ORDER" in cypher:
                return [
                    {
                        "node_id": "WORK_ORDER:SO-2026-0912",
                        "dispatched_at": "2026-10-16 09:40",
                        "closed_at": "2026-10-16 10:22",
                        "site": "武汉",
                        "status": "closed",
                    }
                ]
            if "LOCATED_AT" in cypher:
                return [
                    {"node_id": "LOCATION_RECORD:L1", "time": "09:58", "site": "武汉"}
                ]
            return []

    result = attribute_absence(
        session=_Session(),
        kg_version="v-test",
        org_id="org",
        employee_id="E001",
        day=date(2026, 10, 16),
        employee_name="张伟",
    )

    matched = [cause for cause in result.causes if cause.matched]
    assert matched, "本例应有命中项（出差 + 工单 + 定位）"
    for cause in matched:
        assert cause.evidence, f"{cause.code} 命中却无证据节点"
    assert result.confidence > 0


def test_conclusion_without_policy_source_is_refused() -> None:
    """**守 F3**：结论里出现制度措辞时，`policy_refs` 必须非空。

    推论 satisfied：四项证据全命中但**制度文本缺失**时（本用例假会话不回放
    制度原文），`action` 只能落到「按异常处理流程跟进」——**不许**在没有出处的
    情况下声称「系统自动补卡」（那等于替制度许了一个承诺）。
    """

    class _Session:
        def run(self, cypher: str, **params: object) -> list[dict]:
            if "ON_BUSINESS_TRIP" in cypher:
                return [
                    {
                        "node_id": "BUSINESS_TRIP:BT1",
                        "destination": "武汉",
                        "site": "武汉",
                        "status": "approved",
                        "start_date": "2026-10-16",
                        "end_date": "2026-10-18",
                    }
                ]
            if "HANDLED_ORDER" in cypher:
                return [
                    {
                        "node_id": "WORK_ORDER:SO-2026-0912",
                        "dispatched_at": "2026-10-16 09:40",
                        "closed_at": "2026-10-16 10:22",
                        "site": "武汉",
                        "status": "closed",
                    }
                ]
            if "LOCATED_AT" in cypher:
                return [
                    {"node_id": "LOCATION_RECORD:L1", "time": "09:58", "site": "武汉"}
                ]
            if "SWIPED_AT" in cypher:
                # 前一日（10-15）有门禁、当日无 ⇒ 门禁对比成立
                return (
                    [
                        {
                            "node_id": "ACCESS_RECORD:A1",
                            "in_time": "08:50",
                            "gate": "东门",
                        }
                    ]
                    if params.get("day") == "2026-10-15"
                    else []
                )
            return []

    result = attribute_absence(
        session=_Session(),
        kg_version="v-test",
        org_id="org",
        employee_id="E001",
        day=date(2026, 10, 16),
        employee_name="张伟",
    )

    assert result.confidence == 1.0  # 四项证据全命中
    if "补卡" in result.action:
        assert result.policy_refs, "结论含制度措辞却无制度出处（F3）"


# --------------------------------------------------------------------------- #
# 守卫 3 / 4：路径不承载数值 + 数值模块不接 LLM
# --------------------------------------------------------------------------- #
def test_reasoning_path_hop_has_no_numeric_field() -> None:
    """推理路径只承载节点 / 边，**不**承载数值结论（数值不出 LLM）。"""
    numeric = {
        name
        for name, field in ReasoningPathHop.model_fields.items()
        if field.annotation in (int, float)
    }
    assert not numeric, f"路径不该有数值字段：{numeric}"


def test_numeric_modules_never_touch_llm() -> None:
    """**机械守卫**：出数值 / 出证据链的模块不得引入任何 LLM 客户端。"""
    for relative in _NUMERIC_MODULES:
        source = (BACKEND_DIR / relative).read_text(encoding="utf-8")
        leaked = [token for token in _LLM_TOKENS if token in source]
        assert not leaked, f"{relative} 引入了 LLM 依赖：{leaked}"
