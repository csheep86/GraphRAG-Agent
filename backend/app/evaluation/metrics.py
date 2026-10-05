"""C1–C3 判据的**指标口径**（可执行定义）。

**本模块只有纯函数**：不读配置、不发 HTTP、不连 Neo4j / PG、不调 LLM。
⇒ 断网单机可跑，边界能被 CI 真测到（`--offline` 模式的地基）。

四条纪律（对应 `changes/P0-m6-eval/proposal.md` §6 的登记项）：

1. **零除与空集一律返回 ``None``**（A7）。**严禁**返回 ``0`` 冒充"没测出来"——
   ``0`` 会被读成"召回为 0"，直接误触发反证 **F2**；也**严禁**返回 ``inf``。
   由 :mod:`app.evaluation.criteria` 负责把 ``None`` 转成 ``BLOCKED`` / ``UNKNOWN``。
2. **口径分歧点显式参数化**（A2 匹配 / A4 单位 / A5 去重 / A6 拒答是否入分母），
   并原样回传，使两次运行的结论**可归因**（qset v1→v2→v3 三次换版的教训）。
3. **确定性 tie-break**：任何去重 / 排序都必须稳定（现脚本踩过「并列退化为
   ``chunk_id`` 字典序 ≈ 随机抽样」的坑，`graphs.py` 有记录）。
4. **单位写死在返回值里**（A4）：C3-a 的单位是 **token/文档**，**不是**元——
   spec §4.3 的字段名 `single_doc_cost` 把 token 与钱混用了，这里不再继承那个歧义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: C3-a 的单位（**A4**：spec §4.3 字段名 `single_doc_cost` 把 token 与钱混用，
#: 这里显式钉死为 token/文档，报告必带此单位）。
UNIT_TOKEN_PER_DOC = "token/doc"

#: C3-b（增量 / 全量成本比）的判定阈值（**D3：不落 `config.py`**）。
#: 为什么不落：① 与 spec §6 的 ``COST_RATIO_ALERT_THRESHOLD`` 撞名；
#: ② **无真实消费者**（无增量重算）⇒ 落了即**幽灵配置**（上批刚犯过）。
#: 来源：矩阵 §5.1「显著 < 1.00」——**人工裁决定值**，不是实测推算、
#: 也不是 provisional 推算，与 C3-a 的 32 000 **不同族**，不要互相套用。
COST_RATIO_SIGNIFICANT = 1.00

#: C2-a / C2-b 的匹配口径（**A2**：spec 未定义"识别正确"的判定方式）。
#: - ``triple``        : ``(head_id, relation_type, tail_id)`` —— **默认**，方向敏感；
#: - ``entity_pair``   : ``(head_id, tail_id)`` —— 忽略关系类型，方向仍敏感；
#: - ``canonical_name``: ``(head_name, relation_type, tail_name)`` —— 无 ID 时的退路。
MatchRule = Literal["triple", "entity_pair", "canonical_name"]

#: C3-a 的 ``doc_count`` 去重口径（**A5**：同一文档多次重算算几次？spec 未定）。
#: - ``last_success`` : 只计该文档**最后一次**成功记录（重算覆盖，失败重试不计）——**默认**；
#: - ``first_success``: 只计首次成功（用于"首次入库成本"口径）；
#: - ``sum_all``      : 该文档全部成功记录求和（用于"累计投入"口径）。
DedupRule = Literal["last_success", "first_success", "sum_all"]

#: C2-c 的分母口径（**A6**：矩阵写"总答案数"，而现脚本实测**排除拒答** ⇒ 字面与实现不一致）。
#: ``include_refused=False`` 与现脚本一致；``True`` 时拒答计入分母（此时拒答必然拉低覆盖率）。
DEFAULT_CHUNK_PREFIX = "chunk-"


@dataclass(frozen=True)
class Relation:
    """一条（被 gold 标注或被系统识别的）关系，供 C2-a / C2-b 计算。"""

    head_id: str
    tail_id: str
    relation_type: str
    head_name: str = ""
    tail_name: str = ""

    def match_key(self, rule: MatchRule) -> tuple[str, ...]:
        """按 `rule` 生成匹配键（**方向敏感**：``(A,B)`` 与 ``(B,A)`` 不等价）。"""
        if rule == "entity_pair":
            return (self.head_id, self.tail_id)
        if rule == "canonical_name":
            return (self.head_name, self.relation_type, self.tail_name)
        return (self.head_id, self.relation_type, self.tail_id)


@dataclass(frozen=True)
class CitationRef:
    """一条引用（`M3` 响应体 `citations[]` 的投影）。"""

    chunk_id: str
    #: 是否带**可回溯 span**（矩阵 C2-c 原文要求"含可回溯 span"）。
    #: 现脚本只用 ``chunk-`` 前缀作代理（`require_span=False`），差异登记为 A6。
    has_span: bool = False


@dataclass(frozen=True)
class AnswerRecord:
    """一次问答结果（供 C2-c / 答对率计算）。"""

    refused: bool
    citations: tuple[CitationRef, ...] = ()
    #: 人工判分结果（`None` = 未判分）。**A3**：脚本不做关键词判分（会假达标），
    #: 由人按 `MANIFEST.json` 的 rubric 判，判分人记入 `judged_by`。
    correct: bool | None = None
    judged_by: str | None = None
    #: **答案原文**（P6-F）。**只作判分留证，不参与任何指标计算**——
    #: 此前没有它，人只能对着结构化记录（refused / citations 计数）判分，等于盲判，
    #: 事后也无法复核某题当初到底答了什么。默认为空 ⇒ 既有构造点**全部**不受影响。
    answer_text: str = ""


@dataclass(frozen=True)
class DocumentCostRecord:
    """一次文档级处理的 token 打点（C3-a 的输入）。"""

    doc_id: str
    token_usage_total: int
    #: ``completed`` / ``failed`` / ``superseded``。失败与作废**默认不计**（A5）。
    outcome: Literal["completed", "failed", "superseded"] = "completed"
    #: 同一 ``doc_id`` 内的先后次序（重算 / 重试递增），用于 ``last_/first_success``。
    sequence: int = 0


@dataclass(frozen=True)
class MetricValue:
    """指标结果：**值 + 口径**。

    口径随值一起返回，是为了让**两次运行的结论可比**——
    只比对数字而口径不同，等于拿 v1 题集的分数和 v3 的比（本仓已栽过三次）。
    """

    metric: str
    value: float | None
    unit: str | None = None
    #: ``None`` 且 ``value is None`` ⇒ 说明为什么没算出（零除 / 空集），**不许**静默成 0。
    reason: str | None = None
    options: dict[str, str] = field(default_factory=dict)


def _dedupe(relations: tuple[Relation, ...], rule: MatchRule) -> tuple[Relation, ...]:
    """保序去重（**确定性**：同键保留**首次**出现者，顺序不变）。"""
    seen: set[tuple[str, ...]] = set()
    kept: list[Relation] = []
    for rel in relations:
        key = rel.match_key(rule)
        if key in seen:
            continue
        seen.add(key)
        kept.append(rel)
    return tuple(kept)


def _split(
    gold: tuple[Relation, ...],
    detected: tuple[Relation, ...],
    rule: MatchRule,
) -> tuple[tuple[Relation, ...], tuple[Relation, ...], tuple[Relation, ...]]:
    """返回 ``(matched, missed, spurious)``，三者均按匹配键**字典序**排序（确定性）。"""
    gold_u = _dedupe(gold, rule)
    det_u = _dedupe(detected, rule)
    gold_keys = {rel.match_key(rule) for rel in gold_u}

    matched = tuple(
        sorted(
            (rel for rel in det_u if rel.match_key(rule) in gold_keys),
            key=lambda r: r.match_key(rule),
        )
    )
    missed = tuple(
        sorted(
            (
                rel
                for rel in gold_u
                if rel.match_key(rule) not in {r.match_key(rule) for r in det_u}
            ),
            key=lambda r: r.match_key(rule),
        )
    )
    spurious = tuple(
        sorted(
            (rel for rel in det_u if rel.match_key(rule) not in gold_keys),
            key=lambda r: r.match_key(rule),
        )
    )
    return matched, missed, spurious


def recall(
    gold: tuple[Relation, ...],
    detected: tuple[Relation, ...],
    *,
    match_rule: MatchRule = "triple",
) -> MetricValue:
    """**C2-a 隐性关联召回** = 正确识别数 / 实际植入数（gold）。

    空 gold ⇒ ``None`` + ``reason``（A7：**不**返回 0，0 会被读成"召回为 0"）。
    """
    if not gold:
        return MetricValue(
            metric="recall",
            value=None,
            reason="gold 为空，召回率无定义（A7：不返回 0）",
            options={"match_rule": match_rule},
        )
    matched, _missed, _spurious = _split(gold, detected, match_rule)
    return MetricValue(
        metric="recall",
        value=len(matched) / len(_dedupe(gold, match_rule)),
        options={"match_rule": match_rule},
    )


def false_positive_rate(
    detected: tuple[Relation, ...],
    gold: tuple[Relation, ...],
    *,
    match_rule: MatchRule = "triple",
) -> MetricValue:
    """**C2-b 误报率** = 错误识别数 / 识别出总数。

    ``detected`` 为空 ⇒ ``None`` + ``reason``：**0/0 不是 0**（A7）。
    """
    if not detected:
        return MetricValue(
            metric="false_positive_rate",
            value=None,
            reason="识别出总数为 0，误报率无定义（A7：不返回 0）",
            options={"match_rule": match_rule},
        )
    _matched, _missed, spurious = _split(gold, detected, match_rule)
    return MetricValue(
        metric="false_positive_rate",
        value=len(spurious) / len(_dedupe(detected, match_rule)),
        options={"match_rule": match_rule},
    )


def graph_gain(graph_score: float | None, baseline_score: float | None) -> MetricValue:
    """**C1 图谱相对 RAG 增益** = ``(图谱 − 基线) / 基线``。

    基线缺失或 ≤ 0 ⇒ ``None`` + ``reason``（A7 / A1：基线尚未实现，分母不存在）。
    """
    if graph_score is None or baseline_score is None:
        return MetricValue(
            metric="graph_gain",
            value=None,
            reason="图谱侧或基线侧分数缺失（A1：RAG 基线尚未实现）",
        )
    if baseline_score <= 0:
        return MetricValue(
            metric="graph_gain",
            value=None,
            reason="基线分数 ≤ 0，增益无定义（A7：不返回 inf）",
        )
    return MetricValue(
        metric="graph_gain", value=(graph_score - baseline_score) / baseline_score
    )


def citation_coverage(
    answers: tuple[AnswerRecord, ...],
    *,
    include_refused: bool = False,
    require_span: bool = False,
    chunk_prefix: str = DEFAULT_CHUNK_PREFIX,
) -> MetricValue:
    """**C2-c 引用覆盖率**（硬约束 = 1.00）= 含可回溯引用的答案数 / 分母。

    - 分子：答案**未**被拒答（或 ``include_refused``）、``citations`` 非空、
      每条 ``chunk_id`` 均以 ``chunk_prefix`` 开头、且（``require_span`` 时）均带 span；
    - 分母：**A6** 显式两档 —— ``include_refused=False``（**默认，与现脚本一致**）
      只数非拒答；``True`` 时拒答计入（拒答无引用 ⇒ 必然拉低覆盖率）。

    分母为 0 ⇒ ``None`` + ``reason``（不返回 0）。
    """
    options = {
        "include_refused": str(include_refused),
        "require_span": str(require_span),
        "chunk_prefix": chunk_prefix,
    }
    denominator = [item for item in answers if include_refused or not item.refused]
    if not denominator:
        return MetricValue(
            metric="citation_coverage",
            value=None,
            reason="分母为 0（无答案或非拒答答案为 0），覆盖率无定义（A7）",
            options=options,
        )

    def _is_cited(item: AnswerRecord) -> bool:
        if not item.citations:
            return False
        if not all(str(c.chunk_id).startswith(chunk_prefix) for c in item.citations):
            return False
        return not require_span or all(c.has_span for c in item.citations)

    hit = sum(1 for item in denominator if _is_cited(item))
    return MetricValue(
        metric="citation_coverage",
        value=hit / len(denominator),
        options=options,
    )


def dedupe_document_costs(
    records: tuple[DocumentCostRecord, ...],
    *,
    rule: DedupRule = "last_success",
) -> dict[str, int]:
    """按 **A5** 口径把打点聚合成「每文档 token」；返回 ``{doc_id: token}``（键有序）。

    - ``last_success`` / ``first_success``：只取一条成功记录（失败 / 作废**不计**）；
    - ``sum_all``：该文档全部成功记录求和。
    """
    successes = [r for r in records if r.outcome == "completed"]
    ordered = sorted(successes, key=lambda r: (r.doc_id, r.sequence))
    per_doc: dict[str, list[DocumentCostRecord]] = {}
    for record in ordered:
        per_doc.setdefault(record.doc_id, []).append(record)

    result: dict[str, int] = {}
    for doc_id in sorted(per_doc):
        items = per_doc[doc_id]
        if rule == "sum_all":
            result[doc_id] = sum(i.token_usage_total for i in items)
        elif rule == "first_success":
            result[doc_id] = items[0].token_usage_total
        else:  # last_success（默认）
            result[doc_id] = items[-1].token_usage_total
    return result


def single_doc_cost(
    records: tuple[DocumentCostRecord, ...],
    *,
    rule: DedupRule = "last_success",
) -> MetricValue:
    """**C3-a 单文档处理成本** = 每文档 token 的均值（**A4 单位：token/文档**）。

    无成功记录 ⇒ ``None`` + ``reason``（不返回 0）。
    """
    per_doc = dedupe_document_costs(records, rule=rule)
    if not per_doc:
        return MetricValue(
            metric="single_doc_cost",
            value=None,
            unit=UNIT_TOKEN_PER_DOC,
            reason="无成功记录，单文档成本无定义（A7：不返回 0）",
            options={"dedup_rule": rule},
        )
    return MetricValue(
        metric="single_doc_cost",
        value=sum(per_doc.values()) / len(per_doc),
        unit=UNIT_TOKEN_PER_DOC,
        options={"dedup_rule": rule},
    )


#: M4 疑点（**组**级单元）的匹配口径（**A2** 在"组"语义下的表达）。
#: - ``type_and_members`` : ``(type, *成员（去重、排序）)`` —— **默认**，最严格；
#: - ``members_only``     : 只看成员集合，忽略疑点类型；
#: - ``type_and_size``    : 只看类型 + 成员个数（最松，用于"数量对不对"的粗查）。
FindingMatchRule = Literal["type_and_members", "members_only", "type_and_size"]


@dataclass(frozen=True)
class Finding:
    """一条**疑点**（M4 输出单元）：一个类型 + 一组主体。

    **为什么不是二元组**：M4 的疑点是「一组主体共同具备某种隐性关联」（同一法人 / 同一地址 /
    持股环 / 三方金额不一致），持股环可以是 **2 / 3 / 4 个主体**——拆成 :class:`Relation`
    二元组会把「1 条 4 环」变成「4 条边」，与检测器输出的 1 条疑点**对不上**，
    召回就会被算成 1/4。故另立组级单元。
    """

    type: str
    entity_ids: tuple[str, ...]

    def members(self) -> tuple[str, ...]:
        """成员：**去重 + 排序**（顺序不敏感，与其他口径一样吃确定性纪律）。"""
        return tuple(sorted(set(self.entity_ids)))

    def match_key(self, rule: FindingMatchRule) -> tuple[str, ...]:
        members = self.members()
        if rule == "members_only":
            return members
        if rule == "type_and_size":
            return (self.type, str(len(members)))
        return (self.type, *members)


def _finding_split(
    gold: tuple[Finding, ...],
    detected: tuple[Finding, ...],
    rule: FindingMatchRule,
) -> tuple[int, int]:
    """返回 ``(命中数, 误报数)``；两侧各自按匹配键去重（同一疑点重复报只算一次）。"""
    gold_keys = {f.match_key(rule) for f in gold}
    det_keys = {f.match_key(rule) for f in detected}
    return len(gold_keys & det_keys), len(det_keys - gold_keys)


def findings_recall(
    gold: tuple[Finding, ...],
    detected: tuple[Finding, ...],
    *,
    match_rule: FindingMatchRule = "type_and_members",
) -> MetricValue:
    """**C2-a 隐性关联召回**（组级）= 正确识别的疑点数 / 实际植入数（gold）。

    空 gold ⇒ ``None`` + ``reason``（A7：不返回 0）。
    """
    if not gold:
        return MetricValue(
            metric="findings_recall",
            value=None,
            reason="gold 为空，召回率无定义（A7：不返回 0）",
            options={"match_rule": match_rule},
        )
    hit, _spurious = _finding_split(gold, detected, match_rule)
    #: A8：把 ``hit`` / 分母 **一并给出**——统计口径要算置信界，
    #: 光有比例算不出界（n=9 与 n=200 的 1.00 完全不是一回事）。
    return MetricValue(
        metric="findings_recall",
        value=hit / len({f.match_key(match_rule) for f in gold}),
        options={
            "match_rule": match_rule,
            "hit": hit,
            "n": len({f.match_key(match_rule) for f in gold}),
        },
    )


def findings_false_positive_rate(
    detected: tuple[Finding, ...],
    gold: tuple[Finding, ...],
    *,
    match_rule: FindingMatchRule = "type_and_members",
) -> MetricValue:
    """**C2-b 误报率**（组级）= 错误识别的疑点数 / 识别出总数。

    ``detected`` 为空 ⇒ ``None`` + ``reason``（A7：0/0 不是 0）。
    """
    if not detected:
        return MetricValue(
            metric="findings_false_positive_rate",
            value=None,
            reason="识别出总数为 0，误报率无定义（A7：不返回 0）",
            options={"match_rule": match_rule},
        )
    _hit, spurious = _finding_split(gold, detected, match_rule)
    return MetricValue(
        metric="findings_false_positive_rate",
        value=spurious / len({f.match_key(match_rule) for f in detected}),
        options={
            "match_rule": match_rule,
            "spurious": spurious,
            "n": len({f.match_key(match_rule) for f in detected}),
        },
    )


def accuracy(answers: tuple[AnswerRecord, ...]) -> MetricValue:
    """**答对率**（多跳答对率 / C1 分子共用）= 已判分中判对的比例。

    **A3**：只认**人工判分**（``correct is not None``）；未判分的答案**不计入**分母，
    脚本**不做**关键词判分（关键词命中会把答非所问读成达标）。
    全部未判分 ⇒ ``None`` + ``reason``。
    """
    judged = [item for item in answers if item.correct is not None]
    if not judged:
        return MetricValue(
            metric="accuracy",
            value=None,
            reason="无已判分答案（A3：脚本不自动判分），答对率无定义",
        )
    hit = sum(1 for item in judged if item.correct)
    return MetricValue(metric="accuracy", value=hit / len(judged))
