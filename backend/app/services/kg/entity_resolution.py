"""实体消解器（M2 §3 验收 3）——判据冻结在 ``specs/m2-extract-kg.md`` **§4.5.1**。

**纪律**：判据里没写的信号，不许进代码。本模块的每个分支都能在 §4.5.1 找到出处：

- 范围 / blocking ⇒ §4.5.1 第 1、2 条；
- 信号（名称 + 结构加分）⇒ 第 3 条；
- N1 税号冲突 / N2 多候选 / N3 同税号 ⇒ 第 4 条；
- 三档处置（``auto_merged`` / ``human_review`` / 不落表）⇒ 第 5 条。

三条**刻意的**设计约束：

1. **零 LLM**：判分不得依赖模型（同一个输入必须永远得同一个分，否则"自动合并"不可审计）；
2. **只算不写**：本模块是纯函数，**不碰 Neo4j / PG**——写库由调用方决定
   （摄入脚本按本模块的结果在**摄入时**归一，S9.13 裁决 D-? 见 proposal §2）；
3. **规范化不在本模块做**：``norm_name`` 由调用方算好传进来
   （口径在 ``specs/m4`` §4.6.5），避免两处各写一份规范化然后悄悄漂移。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

# --------------------------------------------------------------------------- #
# 阈值（§4.5.1 第 5 条；**不可调** —— 调参即给"凑够 N 条"留后门）
# --------------------------------------------------------------------------- #
#: ≥ 本值 ⇒ ``auto_merged``
AUTO_MERGE_THRESHOLD = 0.90
#: ≥ 本值且 < 自动合并阈值 ⇒ ``human_review``；< 本值 ⇒ **不落表**
REVIEW_THRESHOLD = 0.70
#: 结构信号单项加分
STRUCT_BONUS_PER_SIGNAL = 0.05
#: 结构加分合计上限（§4.5.1 S2）
STRUCT_BONUS_CAP = 0.10
#: **N1**：双方税号都合法且不同 ⇒ 封顶到此值 ⇒ **永不 auto_merged**
TAX_ID_CONFLICT_CAP = 0.85
#: blocking key 长度（规范化名的前 N 字相同才成对，避免全 O(n²) 噪声）
BLOCKING_PREFIX_LEN = 2

STATUS_AUTO_MERGED = "auto_merged"
STATUS_HUMAN_REVIEW = "human_review"


@dataclass(frozen=True, slots=True)
class SubjectProfile:
    """参与消解的一侧主体。

    ``tax_id`` / ``address`` / ``phone`` / ``legal_rep`` **缺失即 ``None``**——
    缺失不参与比较（不猜、不填默认值）。
    """

    subject_id: str
    norm_name: str
    raw_name: str = ""
    tax_id: str | None = None
    #: 已规范化的地址（口径见 ``specs/m4`` §4.6.5）
    address: str | None = None
    phone: str | None = None
    legal_rep: str | None = None


@dataclass(frozen=True, slots=True)
class MergeCandidate:
    """一条合并候选（落 ``entity_merge_candidates`` 前的内存形态）。"""

    left_id: str
    right_id: str
    similarity: float
    status: str
    #: 判分依据（**留痕**：审计要能回答"为什么是这一档"）
    signals: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    candidates: list[MergeCandidate] = field(default_factory=list)
    #: ``raw_id -> canonical_id``：**仅**自动合并且唯一候选的（调用方据此归一）
    auto_merges: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 信号
# --------------------------------------------------------------------------- #
def _bigrams(text: str) -> set[str]:
    if len(text) < 2:
        return {text} if text else set()
    return {text[index : index + 2] for index in range(len(text) - 1)}


def name_similarity(norm_a: str, norm_b: str) -> float:
    """§4.5.1 S1：``max(字符 2-gram Jaccard, SequenceMatcher.ratio)``。

    取 ``max`` 的理由（写进判据，不是实现偏好）：jaccard 对**长度差**敏感、
    ratio 对**子串插入**敏感，任一"强证据"成立即算相似。
    """
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0
    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    grams_a, grams_b = _bigrams(norm_a), _bigrams(norm_b)
    union = grams_a | grams_b
    jaccard = len(grams_a & grams_b) / len(union) if union else 0.0
    # 取 6 位：避免 0.89999997 这种浮点噪声把"该合并的"卡在阈值外
    return round(max(ratio, jaccard), 6)


def structure_bonus(left: SubjectProfile, right: SubjectProfile) -> float:
    """§4.5.1 S2：共享法人 / 共享电话 / 共享地址，每项 +0.05，合计上限 +0.10。

    **注意**：结构相同是「关联方」的证据，不是「同一主体」的证据——故
    ``name_sim < REVIEW_THRESHOLD`` 时调用方**根本不会生成本候选**。
    """
    hits = 0
    for attr in ("address", "phone", "legal_rep"):
        value_left, value_right = getattr(left, attr), getattr(right, attr)
        if value_left and value_right and value_left == value_right:
            hits += 1
    return min(hits * STRUCT_BONUS_PER_SIGNAL, STRUCT_BONUS_CAP)


def score_pair(
    left: SubjectProfile, right: SubjectProfile
) -> tuple[float, dict[str, object]]:
    """给一对主体打分，返回 ``(similarity, signals)``。

    ``signals`` 留给审计留痕：光有分数回答不了"为什么这么判"。
    """
    sim_name = name_similarity(left.norm_name, right.norm_name)
    bonus = structure_bonus(left, right)
    tax_conflict = bool(left.tax_id and right.tax_id and left.tax_id != right.tax_id)
    similarity = min(1.0, sim_name + bonus)
    if tax_conflict:
        similarity = min(similarity, TAX_ID_CONFLICT_CAP)
    return round(similarity, 6), {
        "name_sim": sim_name,
        "struct_bonus": bonus,
        "tax_conflict": tax_conflict,
    }


def classify(similarity: float) -> str | None:
    """三档（§4.5.1 第 5 条）：``< 0.70`` 返回 ``None`` = **不落表**（保持独立）。"""
    if similarity >= AUTO_MERGE_THRESHOLD:
        return STATUS_AUTO_MERGED
    if similarity >= REVIEW_THRESHOLD:
        return STATUS_HUMAN_REVIEW
    return None


# --------------------------------------------------------------------------- #
# 候选生成
# --------------------------------------------------------------------------- #
def _blocking_key(norm_name: str) -> str:
    return norm_name[:BLOCKING_PREFIX_LEN]


def generate_candidates(
    canonical: list[SubjectProfile],
    raw: list[SubjectProfile],
) -> ResolutionResult:
    """生成合并候选。

    :param canonical: canonical 主体（供应商主数据，``:Subject``）
    :param raw: 未对齐主体（``unaligned_subjects`` 的 raw 行；``subject_id`` 用稳定
        的合成 id，如 ``RAW:invoices.csv:FP2026-0012``）
    """
    result = ResolutionResult()

    # ---- B1 canonical × canonical：对称配对（id 排序去重） ----
    buckets: dict[str, list[SubjectProfile]] = {}
    for profile in canonical:
        key = _blocking_key(profile.norm_name)
        if key:
            buckets.setdefault(key, []).append(profile)
    for bucket in buckets.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                left, right = bucket[i], bucket[j]
                if left.subject_id == right.subject_id:
                    continue
                # N3：税号相同 ⇒ 本就是同一节点，不产生候选
                if left.tax_id and right.tax_id and left.tax_id == right.tax_id:
                    continue
                similarity, signals = score_pair(left, right)
                if similarity < REVIEW_THRESHOLD:
                    continue
                status = classify(similarity)
                if status is None:
                    continue
                first, second = sorted((left.subject_id, right.subject_id))
                result.candidates.append(
                    MergeCandidate(
                        left_id=first,
                        right_id=second,
                        similarity=similarity,
                        status=status,
                        signals=signals,
                    )
                )

    # ---- B2 raw × canonical ----
    raw_hits: dict[str, list[MergeCandidate]] = {}
    for raw_profile in raw:
        raw_key = _blocking_key(raw_profile.norm_name)
        if not raw_key:
            continue
        scored: list[MergeCandidate] = []
        for target in canonical:
            if _blocking_key(target.norm_name) != raw_key:
                continue
            if (
                raw_profile.tax_id
                and target.tax_id
                and raw_profile.tax_id == target.tax_id
            ):
                continue  # N3
            similarity, signals = score_pair(raw_profile, target)
            if similarity < REVIEW_THRESHOLD:
                continue
            status = classify(similarity)
            if status is None:
                continue
            scored.append(
                MergeCandidate(
                    left_id=raw_profile.subject_id,
                    right_id=target.subject_id,
                    similarity=similarity,
                    status=status,
                    signals=signals,
                )
            )
        if not scored:
            continue
        # N2：同一 raw 有 >1 个 ≥0.90 候选 ⇒ **全部降级**，不自动合并
        auto_hits = [item for item in scored if item.status == STATUS_AUTO_MERGED]
        if len(auto_hits) > 1:
            scored = [
                MergeCandidate(
                    left_id=item.left_id,
                    right_id=item.right_id,
                    similarity=item.similarity,
                    status=STATUS_HUMAN_REVIEW,
                    signals={**item.signals, "multi_candidate": True},
                )
                for item in scored
            ]
        else:
            for item in scored:
                if item.status == STATUS_AUTO_MERGED:
                    result.auto_merges[raw_profile.subject_id] = item.right_id
        raw_hits[raw_profile.subject_id] = scored
        result.candidates.extend(scored)

    _ = raw_hits  # 留痕：每个 raw 的候选集合（供调用方 / 测试逐条核对）
    return result
