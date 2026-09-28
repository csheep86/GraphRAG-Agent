"""考勤域**异常归因**（Sprint 9.5 批次 C2，复用 M4 的「疑点 = 证据链」形态）。

**做什么**：给一个异常（演示用例 E001：张伟 10-16 **工作日缺卡**）算出
**原因排序 + 置信度 + 结论**，结构即 M4 扩展的 ``causes``：

    causes: [{reason, confidence, evidence[]}]

**三条硬纪律**：

1. **置信度 = 证据匹配度确定性加权**（``Σ命中权重 / Σ全部权重``），
   **禁止 LLM 生成置信度**（纪律 3 / proposal §5.4）——模型给的百分数不可复核；
2. **零证据即不成立**：``causes`` 里只有 ``matched=True`` 的项才计入分子，
   没有一条命中 ⇒ 置信度 0 ⇒ 结论「不成立」，**不是**"给个 60% 凑合"；
3. **结论里的制度措辞必须可溯源**：「自动补卡」这类话术**不许硬编码**，
   走 :func:`search_policy_sentences` 从制度文本里取原句与出处（守 F3）。
   2025 版要求手工补卡、2026 版改为系统自动补卡 ⇒ 命中多条是**正常的**，
   正是 ADR-0005 时效演示要看的版本更替。

**证据链口径（制度四《外勤与出差考勤补充规定》）**：
门禁**不作为唯一判据** ⇒ 用「出差审批 + 工单闭环 + 定位一致」三件套互相印证，
外加「当日无门禁、前一日有门禁」的**对比项**（不构成出勤证据，只作旁证）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from loguru import logger

from app.services.rules.policy_values import (
    PolicySentence,
    load_policy_clauses,
    load_policy_documents,
    search_policy_sentences,
)

__all__ = [
    "ANOMALY_STATUSES",
    "ANOMALY_MISSING_CHECK_IN",
    "ATTENDANCE_SUSPICION_TYPES",
    "FINANCE_SUSPICION_TYPES",
    "AttributionResult",
    "Cause",
    "attribute_absence",
    "find_anomaly_days",
    "suspicion_types_for_domain",
]

#: 金融域（M4 原有两个类型，**保留不删**）
FINANCE_SUSPICION_TYPES: tuple[str, ...] = ("shared_legal_rep", "shared_address")

#: 考勤域疑点类型（域化的新增部分）
ANOMALY_MISSING_CHECK_IN = "missing_check_in"
ATTENDANCE_SUSPICION_TYPES: tuple[str, ...] = (ANOMALY_MISSING_CHECK_IN,)

#: 考勤记录里算「异常」的状态（缺卡 / 缺勤）
ANOMALY_STATUSES: tuple[str, ...] = ("absent", "missing_check_in")

#: 证据权重（**确定性加权**，合计 1.0）
#: 三项主证据 0.35 + 0.30 + 0.22 = 0.87（对齐 proposal §5.4 的示例 87%），
#: 门禁对比 0.13 作为旁证 ⇒ 四项齐备时为 1.00。
EVIDENCE_WEIGHTS: Mapping[str, float] = {
    "trip_approved": 0.35,
    "order_closed": 0.30,
    "location_match": 0.22,
    "access_contrast": 0.13,
}

#: 结论阈值
CONFIDENCE_ACCEPT = 0.80
CONFIDENCE_REVIEW = 0.50

#: 结论文案的制度关键词（**不硬编码结论**，只声明要找什么）
ACTION_KEYWORD = "自动补卡"

#: 动作文案：前者是**制度动作**（前提：取到制度原句），后者是**兜底动作**
#: 二者的分界由 ``sentences``（制度原句）决定，不由置信度单独决定——
#: 见 `attribute_absence` 里的说明。
ACTION_AUTO_FIX = "系统自动补卡"
ACTION_MANUAL = "按异常处理流程跟进"


def suspicion_types_for_domain(domain: str | None) -> tuple[str, ...]:
    """按业务域给出合法的 ``suspicion_type`` 集合（M4 枚举域化）。

    **保留金融枚举不删**（proposal §5.4：只加不改）；未知域 ⇒ **抛错**，
    不静默回落到金融域——回错了域会让「考勤疑点」被当成「关联交易疑点」解释。
    """
    if domain is None or domain == "finance":
        return FINANCE_SUSPICION_TYPES
    if domain == "attendance":
        return ATTENDANCE_SUSPICION_TYPES
    raise ValueError(f"未知业务域：{domain!r}（合法：finance / attendance）")


# --------------------------------------------------------------------------- #
# 输出模型
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Cause:
    """一条原因（M4 ``causes[]`` 的元素）。"""

    code: str
    reason: str
    weight: float
    matched: bool
    evidence: tuple[str, ...]  # 图谱节点 id（可回查）


@dataclass(frozen=True, slots=True)
class AttributionResult:
    """一次归因的完整结论。"""

    employee_id: str
    employee_name: str
    date: str
    anomaly_type: str
    causes: tuple[Cause, ...]
    confidence: float
    conclusion: str
    action: str
    policy_refs: tuple[str, ...]  # 结论文案的制度出处


# --------------------------------------------------------------------------- #
# Cypher
# --------------------------------------------------------------------------- #
_CYPHER_TRIP = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg, org_id: $org})
      -[:RELATION {relation_type: 'ON_BUSINESS_TRIP', kg_version: $kg}]->
      (t:Entity {entity_type: 'BUSINESS_TRIP', kg_version: $kg})
WHERE e.id = $emp AND t.start_date <= $day AND t.end_date >= $day
RETURN t.id AS node_id, t.destination AS destination, t.site AS site,
       t.status AS status, t.start_date AS start_date, t.end_date AS end_date
ORDER BY t.id
"""

_CYPHER_ORDER = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg, org_id: $org})
      -[:RELATION {relation_type: 'HANDLED_ORDER', kg_version: $kg}]->
      (w:Entity {entity_type: 'WORK_ORDER', kg_version: $kg})
WHERE e.id = $emp AND w.dispatched_at STARTS WITH $day
RETURN w.id AS node_id, w.dispatched_at AS dispatched_at, w.closed_at AS closed_at,
       w.site AS site, w.status AS status
ORDER BY w.id
"""

_CYPHER_LOCATION = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg, org_id: $org})
      -[:RELATION {relation_type: 'LOCATED_AT', kg_version: $kg}]->
      (l:Entity {entity_type: 'LOCATION_RECORD', kg_version: $kg})
WHERE e.id = $emp AND l.date = $day
RETURN l.id AS node_id, l.time AS time, l.site AS site
ORDER BY l.id
"""

_CYPHER_DAY_STATUS = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg, org_id: $org})
      -[:RELATION {relation_type: 'HAS_ATTENDANCE', kg_version: $kg}]->
      (r:Entity {entity_type: 'ATTENDANCE_RECORD', kg_version: $kg})
WHERE e.id = $emp AND r.date = $day
RETURN r.status AS status
ORDER BY r.id
"""

_CYPHER_ACCESS = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg, org_id: $org})
      -[:RELATION {relation_type: 'SWIPED_AT', kg_version: $kg}]->
      (a:Entity {entity_type: 'ACCESS_RECORD', kg_version: $kg})
WHERE e.id = $emp AND a.date = $day
RETURN a.id AS node_id, a.in_time AS in_time, a.gate AS gate
ORDER BY a.id
"""

_CYPHER_ANOMALY_DAYS = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg, org_id: $org})
      -[:RELATION {relation_type: 'HAS_ATTENDANCE', kg_version: $kg}]->
      (r:Entity {entity_type: 'ATTENDANCE_RECORD', kg_version: $kg})
WHERE e.id = $emp AND r.status IN $statuses
RETURN r.date AS date, r.status AS status
ORDER BY r.date
"""


def _rows(session: Any, cypher: str, **params: Any) -> list[Mapping[str, Any]]:
    return list(session.run(cypher, **params))


def find_anomaly_days(
    *, session: Any, kg_version: str, org_id: str, employee_id: str
) -> tuple[str, ...]:
    """列出该员工的全部异常日期（缺卡 / 缺勤），供「扫谁」用。"""
    rows = _rows(
        session,
        _CYPHER_ANOMALY_DAYS,
        kg=kg_version,
        org=str(org_id),
        emp=f"EMPLOYEE:{employee_id}",
        statuses=list(ANOMALY_STATUSES),
    )
    return tuple(str(row["date"]) for row in rows)


class AnomalyNotFoundError(LookupError):
    """要归因的**对象不存在**：员工不在图上，或该员工在指定日期没有异常记录。

    **显式失败**，不返回「零证据归因结果」——零证据会被算成置信度 0%，
    看起来像「系统判断他不成立」，实际是**根本没查到这个人/这一天**，
    二者语义相反（路由层映射为 404 ``NOT_FOUND``）。
    """


@dataclass(frozen=True, slots=True)
class AnomalyCase:
    """一条待归因的异常（列表端点用）：谁、哪天、什么状态。"""

    employee_id: str
    employee_name: str
    day: str
    status: str


@dataclass(frozen=True, slots=True)
class AnomalyCaseList:
    """异常清单 + 它所属的版本。

    **为什么连 ``kg_version`` 一起返回**：列表端点也要标出"这些异常是从哪个版本
    读出来的"，否则前端只看到一堆 E001 / 10-16，无法回答"你查的是哪张图"。
    """

    kg_version: str
    cases: tuple[AnomalyCase, ...]


_CYPHER_EMPLOYEE_NAME = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg, org_id: $org})
WHERE e.id = $emp
RETURN e.canonical_name AS name
"""


def employee_name(
    *, session: Any, kg_version: str, org_id: Any, employee_id: str
) -> str:
    """取员工姓名。

    **服务层必须显式查一次再传给** :func:`attribute_absence`——那边
    ``employee_name`` 默认为空串，不传就会在响应里出现「E001 」（空名字），
    演示时很不体面。查不到（员工不在图上 / 是抽取噪声节点）返回空串，
    由调用方决定是否报错。
    """
    rows = _rows(
        session,
        _CYPHER_EMPLOYEE_NAME,
        kg=kg_version,
        org=str(org_id),
        emp=f"EMPLOYEE:{employee_id}",
    )
    if not rows:
        return ""
    return str(rows[0]["name"] or "")


_CYPHER_ANOMALY_CASES = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg, org_id: $org})
      -[:RELATION {relation_type: 'HAS_ATTENDANCE', kg_version: $kg}]->
      (r:Entity {entity_type: 'ATTENDANCE_RECORD', kg_version: $kg})
WHERE r.status IN $statuses
  AND e.id STARTS WITH 'EMPLOYEE:'
  AND ($emp IS NULL OR e.id = $emp)
RETURN replace(e.id, 'EMPLOYEE:', '') AS employee_id,
       e.canonical_name AS employee_name,
       r.date AS date, r.status AS status
ORDER BY employee_id, date
"""


def list_anomaly_cases(
    *,
    session: Any,
    kg_version: str,
    org_id: Any,
    employee_id: str | None = None,
) -> AnomalyCaseList:
    """列出待归因的异常（全部员工，或只看某人）。

    ``e.id STARTS WITH 'EMPLOYEE:'`` **不可省**：同一个 ``kg_version`` 里还住着
    M2 抽取的噪声节点（实测 EMPLOYEE 47 个里只有 40 个是 CSV 派生的，
    其余叫「全体在册员工」）——不过滤就会给一个**不存在的人**归因。
    """
    rows = _rows(
        session,
        _CYPHER_ANOMALY_CASES,
        kg=kg_version,
        org=str(org_id),
        statuses=list(ANOMALY_STATUSES),
        emp=f"EMPLOYEE:{employee_id}" if employee_id else None,
    )
    return AnomalyCaseList(
        kg_version=kg_version,
        cases=tuple(
            AnomalyCase(
                employee_id=str(row["employee_id"]),
                employee_name=str(row["employee_name"] or row["employee_id"]),
                day=str(row["date"]),
                status=str(row["status"]),
            )
            for row in rows
        ),
    )


def _cause(code: str, reason: str, matched: bool, evidence: Sequence[str]) -> Cause:
    return Cause(
        code=code,
        reason=reason,
        weight=EVIDENCE_WEIGHTS[code],
        matched=matched,
        evidence=tuple(evidence),
    )


def attribute_absence(
    *,
    session: Any,
    kg_version: str,
    org_id: Any,
    employee_id: str,
    day: date | str,
    employee_name: str = "",
    anomaly_type: str = "",
    policy_documents: Sequence[Any] = (),
    policy_clauses: Sequence[Any] = (),
    storage: Any = None,
) -> AttributionResult:
    """给「某员工某天缺卡」做归因。

    :param day: 异常日（``date`` 或 ISO 字符串）。
    :param anomaly_type: 异常类型；**为空时自动从图谱读**该员工当日的
        ``ATTENDANCE_RECORD.status``（``absent`` / ``missing_check_in``）。
    :param policy_documents / policy_clauses: 制度文本片段；**都为空时**自动从
        存储 / 图谱加载一次（调用方复用可省一次 IO）。
    """
    day_text = day.isoformat() if isinstance(day, date) else str(day)

    if not anomaly_type:
        # **不硬编码异常类型**（2026-09-28 修）：原先恒为 ``missing_check_in``，
        # 而当天真实状态是 ``absent``。CLI 只有一条用例时看不出来，一旦经 HTTP
        # 暴露就变成明显的失真——列表端点说 absent、归因端点说 missing_check_in。
        # 读不到（该日无考勤记录）才回落，且回落的是**同一套枚举**里的值。
        status_rows = _rows(
            session,
            _CYPHER_DAY_STATUS,
            kg=kg_version,
            org=str(org_id),
            emp=f"EMPLOYEE:{employee_id}",
            day=day_text,
        )
        anomaly_type = (
            str(status_rows[0]["status"]) if status_rows else ANOMALY_MISSING_CHECK_IN
        )

    params = {
        "kg": kg_version,
        "org": str(org_id),
        "emp": f"EMPLOYEE:{employee_id}",
        "day": day_text,
    }

    trips = _rows(session, _CYPHER_TRIP, **params)
    orders = _rows(session, _CYPHER_ORDER, **params)
    locations = _rows(session, _CYPHER_LOCATION, **params)
    same_day_access = _rows(session, _CYPHER_ACCESS, **params)

    previous_day = (date.fromisoformat(day_text) - timedelta(days=1)).isoformat()
    previous_access = _rows(session, _CYPHER_ACCESS, **{**params, "day": previous_day})

    approved_trips = [row for row in trips if str(row["status"]) == "approved"]
    trip_sites = {str(row["site"]) for row in approved_trips if row["site"]}

    closed_orders = [row for row in orders if str(row["closed_at"] or "").strip() != ""]
    matched_locations = [
        row for row in locations if not trip_sites or str(row["site"]) in trip_sites
    ]

    causes: list[Cause] = [
        _cause(
            "trip_approved",
            (
                f"出差审批覆盖当日（{approved_trips[0]['destination']}"
                f" {approved_trips[0]['start_date']}~{approved_trips[0]['end_date']}）"
                if approved_trips
                else "当日无已审批的出差单"
            ),
            bool(approved_trips),
            [str(row["node_id"]) for row in approved_trips],
        ),
        _cause(
            "order_closed",
            (
                f"当日工单已闭环 {len(closed_orders)} 条"
                f"（最早派单 {closed_orders[0]['dispatched_at']}）"
                if closed_orders
                else "当日无已闭环工单"
            ),
            bool(closed_orders),
            [str(row["node_id"]) for row in closed_orders],
        ),
        _cause(
            "location_match",
            (
                f"定位与出差目的地一致 {len(matched_locations)} 条"
                f"（{', '.join(sorted({str(r['site']) for r in matched_locations}))}）"
                if matched_locations
                else "当日定位与出差目的地不匹配（或无定位）"
            ),
            bool(matched_locations),
            [str(row["node_id"]) for row in matched_locations],
        ),
        _cause(
            "access_contrast",
            (
                "当日无门禁、前一日有门禁（外勤旁证）"
                if (not same_day_access and previous_access)
                else (
                    f"门禁对比不成立（当日 {len(same_day_access)} 条 / "
                    f"前一日 {len(previous_access)} 条）"
                )
            ),
            bool(not same_day_access and previous_access),
            [str(row["node_id"]) for row in previous_access],
        ),
    ]

    total_weight = sum(EVIDENCE_WEIGHTS.values())
    hit_weight = sum(item.weight for item in causes if item.matched)
    confidence = round(hit_weight / total_weight, 4) if total_weight else 0.0

    if confidence >= CONFIDENCE_ACCEPT:
        conclusion = "外勤出勤成立"
    elif confidence >= CONFIDENCE_REVIEW:
        conclusion = "证据不足，需人工复核"
    else:
        conclusion = "外勤出勤不成立"

    sentences = _policy_sentences(
        org_id=org_id,
        kg_version=kg_version,
        session=session,
        documents=policy_documents,
        clauses=policy_clauses,
        storage=storage,
    )
    # **制度措辞必须可溯源**（守 F3；2026-09-28 由 D2 守卫逼出来的修）：
    # 「自动补卡」是**制度动作**，不是我们的处置意见——制度原句取不到时
    # （`policy_refs` 为空）就**不许**声称补卡，只能落到人工跟进流程。
    # 否则屏幕上会出现一句「依据制度：自动补卡」而制度出处是空的。
    action = (
        ACTION_AUTO_FIX
        if (confidence >= CONFIDENCE_ACCEPT and sentences)
        else ACTION_MANUAL
    )

    if confidence < CONFIDENCE_ACCEPT:
        logger.bind(employee=employee_id, day=day_text, confidence=confidence).info(
            "attendance_attribution_below_threshold"
        )

    return AttributionResult(
        employee_id=employee_id,
        employee_name=employee_name,
        date=day_text,
        anomaly_type=anomaly_type,
        causes=tuple(causes),
        confidence=confidence,
        conclusion=conclusion,
        action=action,
        policy_refs=tuple(f"{item.source}:{item.reference}" for item in sentences),
    )


def _policy_sentences(
    *,
    org_id: Any,
    kg_version: str,
    session: Any,
    documents: Sequence[Any],
    clauses: Sequence[Any],
    storage: Any,
) -> tuple[PolicySentence, ...]:
    """取「自动补卡」的制度原句（缺制度文本 ⇒ 空元组，结论里就不声称出处）。"""
    if not documents and not clauses:
        try:
            documents = load_policy_documents(org_id=org_id, storage=storage)
            clauses = load_policy_clauses(
                session=session, kg_version=kg_version, org_id=str(org_id)
            )
        except Exception as exc:  # noqa: BLE001 - 制度文本缺失只影响出处，不阻断归因
            logger.bind(error=str(exc)).warning("policy_sentences_unavailable")
            return ()
    return search_policy_sentences(
        keyword=ACTION_KEYWORD,
        clauses=clauses,
        documents=documents,
    )
