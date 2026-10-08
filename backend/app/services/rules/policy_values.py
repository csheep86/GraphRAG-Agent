"""考勤域**规则值**解析（Sprint 9.5 批次 C1）。

**为什么单列一个模块**：规则引擎的判据数值（周 40h / 月标准 174h / 月加班上限 36h /
核心时段 6h / 越界 5 次 / 连续 12 天 / 季度剩余 30 天）必须**来自制度文本**，
而不是写死在代码里——制度改了，规则自动变（proposal §5.3「顺带演示制度可配置」）。

**两级来源（实测决定，见下）**：

1. **图谱 ``POLICY_CLAUSE``**（优先）：M2 抽出来的条款节点，带 ``mention`` /
   ``canonical_name``。
2. **M1 解析产物 ``full.md``**（兜底）：同一批制度文档的**完整正文**。

**为什么必须有第 2 级（2026-09-28 实测，重要）**：M2 是 **span 级**抽取，
``POLICY_CLAUSE`` 的名字常常只有「第十一条」「3」这种碎片——真机 84 条条款里
**只有 1 条**（``每月加班时间不得超过36小时``）能解析出数值，其余 6 个规则值
在图谱里根本不存在。**只认图谱 ⇒ 5 条规则有 4 条直接哑掉**，所以必须有一个
承载完整句子的来源；而 ``full.md`` 是**系统内产物**（M1 解析真实产出，不是
代码旁的静态文件），既同源又可核查。

**为什么不用源 Markdown / 不用硬编码常量兜底**：源 md 在 ``demo/`` 下、不在系统
产物里（拿它等于绕过入库链路）；而「解析不到就回落到 40 / 174 / 36」是本项目
最忌的**静默编数**——故解析不到即标记为 ``unresolved``，对应规则**跳过**并在
结果里显式列出（守 F3：无溯源即拒答）。

**确定性**：正则 + 固定遍历顺序（条款按 id 排序、文档按 stem 排序、行号升序），
同一份语料多次解析**同解**；全程无 LLM 参与（数值不出 LLM，纪律 3）。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

__all__ = [
    "POLICY_DOC_STEMS",
    "RuleValue",
    "RuleValueBook",
    "RuleValueUnresolvedError",
    "policy_document_id",
    "resolve_rule_values",
]

#: 4 份制度文档的 stem —— 与 ``scripts/ingest_attendance_policies.py`` 同一套
#: **uuid5 确定性命名**（``urn:graphrag-agent:demo:attendance:policy-doc:<stem>``），
#: 因此这里能直接算出文档 id 去取产物，无需依赖 PG 查询，也不需要「猜哪几份是制度」。
POLICY_DOC_STEMS: tuple[str, ...] = (
    "attendance-policy-2026",
    "fieldwork-attendance-rules",
    "overtime-and-comp-off",
    "worktime-system-rules",
)

_POLICY_DOC_URN = "urn:graphrag-agent:demo:attendance:policy-doc:{stem}"

#: 值出处来源标记
SOURCE_GRAPH = "graph"
SOURCE_DOCUMENT = "document"


class RuleValueUnresolvedError(KeyError):
    """规则值解析不到（未在制度文本中找到判据数值）。

    **不静默兜底**：调用方必须显式处理（跳过该规则并在结果里列出），
    严禁退回一个「看起来合理」的默认数——那是编数（守 F3）。
    """


def _as_float(match: re.Match[str]) -> float:
    """默认取值：捕获组 ``value`` 转 float。"""
    return float(match.group("value"))


def _core_window_hours(match: re.Match[str]) -> float:
    """核心在岗时段「10:00 至 16:00」→ 时长 6.0h。

    **为什么不直接写 6**：制度第十二条写的是「核心在岗时段为 10:00 至 16:00」，
    时长是**从制度算出来的**；若制度改成 10:00–15:00，阈值应自动变 5h。
    """
    start = int(match.group("from_h")) * 60 + int(match.group("from_m"))
    end = int(match.group("to_h")) * 60 + int(match.group("to_m"))
    return round((end - start) / 60.0, 2)


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """一条规则值的定义：叫什么、什么单位、怎么从文本里认出来。"""

    key: str
    label: str
    unit: str
    patterns: tuple[re.Pattern[str], ...]
    derive: Callable[[re.Match[str]], float] = _as_float


#: 规则值定义表。**正则全部对着真机 full.md 实测过**（2026-09-28），
#: 包括被 MinerU 渲染成 ``<table><tr><td>…</td>`` 的表格行——数值文本完整保留。
_RULE_SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        key="weekly_hours_cap",
        label="标准工时制周工时上限",
        unit="小时",
        patterns=(
            re.compile(r"每周工作\s*(?P<value>\d+(?:\.\d+)?)\s*小时"),
            re.compile(r"周工作超过\s*(?P<value>\d+(?:\.\d+)?)\s*小时"),
        ),
    ),
    RuleSpec(
        key="monthly_standard_hours",
        label="月标准工时",
        unit="小时",
        patterns=(re.compile(r"月标准工时为\s*(?P<value>\d+(?:\.\d+)?)\s*小时"),),
    ),
    RuleSpec(
        key="monthly_overtime_cap",
        label="月加班上限",
        unit="小时",
        patterns=(
            re.compile(r"每月加班时间不得超过\s*(?P<value>\d+(?:\.\d+)?)\s*小时"),
            re.compile(r"月累计加班超过\s*(?P<value>\d+(?:\.\d+)?)\s*小时"),
        ),
    ),
    RuleSpec(
        key="core_hours_required",
        label="核心在岗时段时长",
        unit="小时",
        patterns=(
            re.compile(
                r"核心在岗时段为\s*(?P<from_h>\d{1,2}):(?P<from_m>\d{2})"
                r"\s*至\s*(?P<to_h>\d{1,2}):(?P<to_m>\d{2})"
            ),
        ),
        derive=_core_window_hours,
    ),
    RuleSpec(
        key="core_absence_limit",
        label="核心时段未在岗次数上限",
        unit="次",
        patterns=(
            re.compile(r"未在核心时段在岗累计超过\s*(?P<value>\d+)\s*次"),
            re.compile(r"核心时段未在岗超过\s*(?P<value>\d+)\s*次"),
        ),
    ),
    RuleSpec(
        key="consecutive_days_limit",
        label="连续出勤天数阈值",
        unit="天",
        patterns=(re.compile(r"连续出勤达到\s*(?P<value>\d+)\s*天"),),
    ),
    RuleSpec(
        key="comp_off_quarter_remaining_days",
        label="季度剩余天数（调休临期判据）",
        unit="天",
        patterns=(re.compile(r"季度剩余不足\s*(?P<value>\d+)\s*天"),),
    ),
)

_SPEC_BY_KEY: Mapping[str, RuleSpec] = {spec.key: spec for spec in _RULE_SPECS}


@dataclass(frozen=True, slots=True)
class PolicySentence:
    """制度原文里命中关键词的一句话（含出处，供结论引用）。

    **为什么需要**：归因 / 问答的结论里不能出现「自动补卡」这类**未经溯源的制度措辞**
    ——那是编制度。凡是结论要引用制度，必须走这里把原句与出处一起带出来（守 F3）。
    """

    source: str
    reference: str
    text: str


def search_policy_sentences(
    *,
    keyword: str,
    clauses: Sequence[_TextSegment] = (),
    documents: Sequence[_TextSegment] = (),
    limit: int = 5,
) -> tuple[PolicySentence, ...]:
    """在制度文本里找含 ``keyword`` 的句子，返回 ``(出处, 原句)``。

    **只做包含匹配，不做语义判断**：命中即返回（按来源与顺序排序 ⇒ 同解）。
    命中多条是**正常的**——例如「自动补卡」在 2025 版（手工补卡）与 2026 版
    （系统自动补卡）各出现一次，正是 ADR-0005 时效演示要看的**版本更替**。
    """
    hits: list[PolicySentence] = []
    for segments in (
        sorted(clauses, key=lambda item: item.order),
        sorted(documents, key=lambda item: item.order),
    ):
        for segment in segments:
            if keyword in segment.text:
                hits.append(
                    PolicySentence(
                        source=segment.source,
                        reference=segment.reference,
                        text=segment.text.strip()[:200],
                    )
                )
                if len(hits) >= limit:
                    return tuple(hits)
    return tuple(hits)


@dataclass(frozen=True, slots=True)
class RuleValue:
    """一个已解析出的规则值（含出处，可逐条核查）。"""

    key: str
    label: str
    value: float
    unit: str
    source: str  # ``graph`` / ``document``
    reference: str  # ``clause:<id>`` 或 ``doc:<stem>:L<行号>``
    evidence: str  # 命中的原文片段


@dataclass(frozen=True, slots=True)
class RuleValueBook:
    """一次解析的结果：已解析值 + 未解析清单。

    **未解析必须显式暴露**：调用方据此跳过规则并写进报告，
    不能当作「用默认值算过了」——那会让演示结论不可复核。
    """

    values: tuple[RuleValue, ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def by_key(self) -> dict[str, RuleValue]:
        return {item.key: item for item in self.values}

    def value(self, key: str) -> float:
        """取数值；未解析抛 :class:`RuleValueUnresolvedError`。"""
        for item in self.values:
            if item.key == key:
                return item.value
        raise RuleValueUnresolvedError(key)

    def reference(self, key: str) -> str:
        """取出处（用于写进 ``policy_refs``）；未解析同样抛错。"""
        for item in self.values:
            if item.key == key:
                return f"{item.source}:{item.reference}"
        raise RuleValueUnresolvedError(key)


@dataclass(frozen=True, slots=True)
class _TextSegment:
    """一段待解析文本 + 它的出处坐标。"""

    text: str
    source: str
    reference: str
    #: 排序键：保证「同解」（条款 id / 行号升序）
    order: tuple[str, int]


def policy_document_id(stem: str) -> uuid.UUID:
    """制度文档 id（与 B2 入图脚本**同一套 uuid5 公式**）。"""
    return uuid.uuid5(uuid.NAMESPACE_URL, _POLICY_DOC_URN.format(stem=stem))


def load_policy_clauses(
    *,
    session: Any,
    kg_version: str,
    org_id: str,
    version_view: Any = None,
) -> tuple[_TextSegment, ...]:
    """读图谱里 ``POLICY_CLAUSE`` 的可判据文本（``mention`` + ``canonical_name``）。

    按 ``id`` 升序 ⇒ 多次调用**同解**。

    :param version_view: P5-H 版本继承读视野（类型标注用 ``Any``：本模块被
        ``policy_values`` 的上游多处复用，不为它牵一条新的 import 依赖）；
        ``None`` ⇒ 按 ``kg_version`` 单版本读。
    """
    from app.services.kg.version_scope import version_scope
    from app.services.kg.version_view import VersionReadView

    view = version_view or VersionReadView(versions=(kg_version,), selection={})
    rows = list(
        session.run(
            f"MATCH (n:Entity {{entity_type: 'POLICY_CLAUSE', org_id: $org}}) "
            f"WHERE {version_scope('n')} "
            "RETURN n.id AS id, n.canonical_name AS name, n.mention AS mention "
            "ORDER BY n.id",
            org=str(org_id),
            **view.cypher_params(),
        )
    )
    segments: list[_TextSegment] = []
    for row in rows:
        clause_id = str(row["id"] or "")
        text = " ".join(
            part for part in (str(row["mention"] or ""), str(row["name"] or "")) if part
        )
        if not clause_id or not text.strip():
            continue
        segments.append(
            _TextSegment(
                text=text,
                source=SOURCE_GRAPH,
                reference=f"clause:{clause_id}",
                order=(clause_id, 0),
            )
        )
    return tuple(segments)


def load_policy_documents(
    *, org_id: Any, storage: Any = None
) -> tuple[_TextSegment, ...]:
    """读 4 份制度文档的 M1 产物 ``full.md``，逐行切成待解析文本。

    **逐行切**而不是整篇：出处能精确到 ``doc:<stem>:L<行号>``，便于人工核对；
    且表格行在 ``full.md`` 里是一整行 HTML，按行解析不会漏。

    产物缺失时 **warn 后跳过**（不抛）：文档没解析完是数据问题，
    但它不该让「已经能解析的其它规则值」一起失效——缺失会在 ``unresolved`` 里显形。
    """
    if storage is None:
        from app.storage import get_storage  # 局部导入：避免模块导入即依赖配置

        storage = get_storage()

    from app.storage import build_parse_artifact_key  # 同上

    segments: list[_TextSegment] = []
    for stem in POLICY_DOC_STEMS:
        doc_id = policy_document_id(stem)
        key = build_parse_artifact_key(org_id=org_id, doc_id=doc_id, filename="full.md")
        try:
            text = storage.get(key, org_id=org_id).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - 缺产物 → warn 跳过，不阻断
            logger.bind(stem=stem, error=str(exc)).warning("policy_full_md_missing")
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            segments.append(
                _TextSegment(
                    text=line,
                    source=SOURCE_DOCUMENT,
                    reference=f"doc:{stem}:L{line_no}",
                    order=(stem, line_no),
                )
            )
    return tuple(segments)


def _snippet(text: str, match: re.Match[str], limit: int = 60) -> str:
    start = max(0, match.start() - limit // 3)
    end = min(len(text), match.end() + limit // 3)
    snippet = text[start:end].strip()
    return snippet if len(snippet) <= 160 else f"{snippet[:157]}…"


def resolve_rule_values(
    *,
    clauses: Sequence[_TextSegment] = (),
    documents: Sequence[_TextSegment] = (),
) -> RuleValueBook:
    """按「图谱条款 → 制度文档产物」的顺序解析全部规则值。

    每条第**一次命中即定**（先到先得），并把出处写进 :class:`RuleValue`；
    全部来源都没命中的 key 进 ``unresolved``。
    """
    sources = [
        sorted(clauses, key=lambda item: item.order),
        sorted(documents, key=lambda item: item.order),
    ]

    resolved: list[RuleValue] = []
    unresolved: list[str] = []
    for spec in _RULE_SPECS:
        hit: RuleValue | None = None
        for segments in sources:
            for segment in segments:
                for pattern in spec.patterns:
                    match = pattern.search(segment.text)
                    if match is None:
                        continue
                    hit = RuleValue(
                        key=spec.key,
                        label=spec.label,
                        value=spec.derive(match),
                        unit=spec.unit,
                        source=segment.source,
                        reference=segment.reference,
                        evidence=_snippet(segment.text, match),
                    )
                    break
                if hit is not None:
                    break
            if hit is not None:
                break
        if hit is None:
            unresolved.append(spec.key)
            logger.bind(rule=spec.key).warning("policy_rule_value_unresolved")
        else:
            resolved.append(hit)

    return RuleValueBook(values=tuple(resolved), unresolved=tuple(unresolved))


#: 供测试与文档引用：全部规则 key（顺序即定义顺序）
ALL_RULE_KEYS: tuple[str, ...] = tuple(spec.key for spec in _RULE_SPECS)
