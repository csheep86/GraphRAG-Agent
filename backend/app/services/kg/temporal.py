"""知识时效：**确定性仲裁**（ADR-0005 §5 / D-3）。

**为什么全是纯函数**：仲裁是「当前值是否唯一」的唯一守门人。把逻辑埋进 Cypher，
「为什么张三那条边被封了」就无法单测——同一条理由让 :func:`builder._assign_entities_to_chunks`
把 chunk 归属判断留在了 Python 侧。这里每个函数零外部依赖（不连 Neo4j、不调 LLM），
裁判权归 ``tests/test_temporal_arbitration.py``。

四条规则（ADR-0005 §5）——判据**只有**结构与时间，不算相似度、不问模型：

- **R1 跨文档**：同 ``(head, relation_type)`` 出现新事实且 ``valid_from`` **严格晚于**
  旧事实 ⇒ 旧边 ``valid_to := 新边.valid_from``。**「严格」是命门**：写成 ``<=`` 会让
  同一变更句的旧值反过来把新值封掉（ADR §5 R3 引
  ``temporal_poc/README.md`` §4 坑 5：首版实测当前值全线阵亡）。
- **R2 同文档变更句**：「由张三变更为李四」在同一句里抽出两条边、``valid_from``
  **相同** ⇒ R1 管不到。保留 **tail 在原文最晚出现**的那条，其余 ``valid_to := valid_from``。
  判据用 **target 实体的字符偏移**（比 PoC 的「名字最后出现位置」更精确：不受同名干扰）。
- **R3 禁同批次互封**：失效动作**不得**作用于同一 ``source_document_id`` 内刚写入的边。
- **R4 不猜值**：本模块**只封旧**（写 ``valid_to``），**绝不**推断 ``valid_from``，
  也**绝不**替某条边"补"一个失效日期——拿不准就不封。
  保留多条 alive 边是可诊断的现状，封错边是**正在污染答案**的事故。

**作用域**：只有策略判定为 ``single_current``（唯一当前）的 ``relation_type`` 参与；
其余按 ``append_only`` 处理（多值并存，不封）。默认保守：未配置就封会让历史边静默消失。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TemporalRelation:
    """一条参与仲裁的关系（**事实维** + 血缘，摄入维由写入侧打）。

    :param head_id: 源节点 id。必须是**跨文档稳定**的 id——本项目 M4 主体层
        （``sub-<sha256(name)>`` / ``adr-…`` / ``lpr-…``）满足；M2 的 ``:Entity``
        id 是 ``ent_<uuid>``，**每次抽取都变**，跨文档必然连不上（见模块 §作用域）。
    :param valid_from: ``YYYY-MM-DD``；``None`` = 文本未给出 ⇒ **不参与时效比较**
        （R4：不猜、不补）。
    :param tail_position: target 实体在原文中的字符偏移，R2 的判据；``None`` = 定位失败。
    """

    head_id: str
    tail_id: str
    relation_type: str
    valid_from: str | None
    valid_to: str | None = None
    source_document_id: str | None = None
    tail_position: int | None = None

    @property
    def key(self) -> tuple[str, str]:
        """仲裁的作用单元：``(head_id, relation_type)``。"""
        return (self.head_id, self.relation_type)

    @property
    def is_alive(self) -> bool:
        """``valid_to`` 为空即仍有效（ADR-0005 §4 的空值语义）。"""
        return self.valid_to is None


@dataclass(frozen=True, slots=True)
class ExpiryPlan:
    """一条封边指令：把 ``relation`` 的事实维封到 ``valid_to``。

    摄入维 ``expired_at`` 由**写入侧**在真正执行时打（写库时刻），不在这里伪造。
    ``reason`` 落边的 ``invalidated_reason`` 属性 + 日志，用于回答
    「这条边为什么失效了」。
    """

    relation: TemporalRelation
    valid_to: str
    reason: str


#: 策略判定函数：``relation_type`` → 是否「唯一当前」（唯一 ⇒ 新事实封旧事实）。
#: 唯一来源是 :func:`app.services.kg.policies.load_expiry_policies` 读出的策略表。
PolicyLookup = Callable[[str], bool]


def always_append_only(_relation_type: str) -> bool:
    """默认策略：**一律并存**。

    保守默认是有意的：策略表没配的类型若按「唯一当前」处理，会把没人确认过的
    历史边静默封掉——那是比"答案里多几条旧事实"难查得多的事故。
    """
    return False


def plan_expiries(
    *,
    existing: Sequence[TemporalRelation],
    incoming: Sequence[TemporalRelation],
    is_single_current: PolicyLookup = always_append_only,
) -> list[ExpiryPlan]:
    """算「该封哪些旧边」；**纯函数**，不写库、不查库。

    :param existing: 图谱里已存在、**仍有效**的边（同一租户：过滤同 ``org_id``，跨 ``kg_version``）。
    :param incoming: 本次要写入的边。
    :param is_single_current: 该 ``relation_type`` 是否「唯一当前」。
    :return: 待执行的封边指令（已按边去重，同一边被多条新事实触发时取**最早**的失效日）。
    """
    plans: list[ExpiryPlan] = []
    plans.extend(_r1_cross_document(existing, incoming, is_single_current))
    plans.extend(_r2_same_anchor(incoming, is_single_current))
    return _dedupe(plans)


def _r1_cross_document(
    existing: Sequence[TemporalRelation],
    incoming: Sequence[TemporalRelation],
    is_single_current: PolicyLookup,
) -> list[ExpiryPlan]:
    """R1：新事实严格晚于旧事实 ⇒ 封旧。

    四道闸门缺一不可：同 key / 不同 tail / 旧边仍有效 / 不同来源文档（R3）/
    **严格**晚于。少任何一道都会把「并存的多值」或「同文档的变更句」误伤。
    """
    plans: list[ExpiryPlan] = []
    for new in incoming:
        if new.valid_from is None or not is_single_current(new.relation_type):
            continue  # 无可比时间 ⇒ 不封（R4）
        for old in existing:
            if old.key != new.key or old.tail_id == new.tail_id:
                continue
            if not old.is_alive:
                continue
            if (
                old.source_document_id
                and old.source_document_id == new.source_document_id
            ):
                continue  # R3：同一批次内不互封
            if old.valid_from is None or not old.valid_from < new.valid_from:
                continue  # R1 的「严格晚于」
            plans.append(ExpiryPlan(old, new.valid_from, "R1"))
    return plans


def _r2_same_anchor(
    incoming: Sequence[TemporalRelation],
    is_single_current: PolicyLookup,
) -> list[ExpiryPlan]:
    """R2：``valid_from`` 相同的多条边 ⇒ 保留原文里最后出现的 tail。

    拿不定就**不封**：``tail_position`` 缺失（定位失败）时整组跳过——这遵循 R4，
    也与项目的通用取舍一致（"不敢判就保留，留给诊断"优于"猜一个封掉"）。
    """
    groups: dict[tuple[str, str, str | None], list[TemporalRelation]] = {}
    for item in incoming:
        if not is_single_current(item.relation_type) or item.valid_from is None:
            continue
        groups.setdefault(
            (item.head_id, item.relation_type, item.valid_from), []
        ).append(item)

    plans: list[ExpiryPlan] = []
    for items in groups.values():
        if len(items) < 2:
            continue
        if any(item.tail_position is None for item in items):
            continue  # 定位不全 ⇒ 不敢判
        ordered = sorted(items, key=lambda item: item.tail_position or 0)
        kept = ordered[-1]
        for old in ordered[:-1]:
            if old.tail_id == kept.tail_id:
                continue  # 同一目标值的重复 evidence，不是"变更"
            plans.append(ExpiryPlan(old, str(old.valid_from), "R2"))
    return plans


def _dedupe(plans: Iterable[ExpiryPlan]) -> list[ExpiryPlan]:
    """同一条旧边被多条新事实触发 ⇒ 取**最早**的失效日。

    取最早（``min``）而非最晚：旧事实在最早的那个新事实生效时就已经不成立，
    晚封会让中间那段"已失效但还活着"被 as-of 查询当成真相。
    """
    best: dict[tuple[tuple[str, str], str, str | None], ExpiryPlan] = {}
    for plan in plans:
        identity = (plan.relation.key, plan.relation.tail_id, plan.relation.valid_from)
        current = best.get(identity)
        if current is None or plan.valid_to < current.valid_to:
            best[identity] = plan
    return list(best.values())
