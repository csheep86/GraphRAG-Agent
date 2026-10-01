"""派生边的时间窗口继承（ADR-0005 §4 增补）。

口径见 ``changes/Sprint10.5/11-derived-window-inheritance.md``（待核准记录）：

    **派生边的有效窗口 := 它所指 POLICY_CLAUSE 节点自身的窗口；
      条款有多个候选窗口或没有窗口 ⇒ 派生边保持空，不猜。**

为什么单独成模块
----------------
``ingest_attendance_csv.py`` 与 ``ingest_attendance_policies.py`` **各有一处**
规则桥接边的生成点（前者工作→条款、后者文档内工时制→条款）。两处必须共用同一份
口径与同一句 Cypher，否则会出现「同一形状的边，一边有日期一边没有」——
那种不一致比全部没有更难诊断。

为什么这样取值不违反 R4
----------------------
继承的值全部来自抽取侧**已经**写在邻接关系上的 ``(valid_from, valid_to)``
（``kg_extraction_v3`` 字段约束 5：只有文本明确写了才填），本模块**不产生**任何新日期；
抽不出 ⇒ 写 ``None``，绝不补值。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

#: 「条款 → 文档窗口」的**共享登记册**（R4-b）。
#:
#: 为什么必须是跨脚本共享的一个文件：**只有制度入图器知道每个条款出自哪份文档**
#: （图里没有这条链接），而 CSV 入图器也要给它的桥接边补窗口 ⇒ 必须有一个地方
#: 让前者把结论留下来、后者读走。两份脚本各推定一份会导致同一形状的边一边有日期
#: 一边没有，那比全部没有更难诊断。
#:
#: 文件缺失（首次运行 / 只跑 CSV）⇒ 视为空登记册 ⇒ **兜底不生效**，不报错。
DEFAULT_SCOPE_STORE = Path(__file__).resolve().parent / "_clause_doc_scopes.json"

#: 条款节点自身窗口的候选集：该条款**所有邻接 RELATION** 上出现过的
#: ``(valid_from, valid_to)`` 组合去重后的集合。
#:
#: - ``collect(DISTINCT [...])`` 让同一个窗口重复出现多次也只算一个；
#: - ``size(wins)`` 决定能否继承：只有**恰好 1 个**才继承，>1 ⇒ 猜 ⇒ 放弃；
#: - ``ORDER BY p.id`` ⇒ 同库多次调用同解（确定性纪律）。
Q_CLAUSE_WINDOWS = """
MATCH (p:Entity {entity_type: $tail_type, kg_version: $kg})
      -[r:RELATION {kg_version: $kg}]-()
WITH p, collect(DISTINCT [toString(r.valid_from), toString(r.valid_to)]) AS raw
WITH p, [w IN raw WHERE w[0] IS NOT NULL OR w[1] IS NOT NULL] AS wins
RETURN p.id AS id, wins, size(wins) AS n
ORDER BY p.id
"""


def clause_windows(
    session: Any,
    *,
    kg_version: str,
    tail_type: str = "POLICY_CLAUSE",
) -> tuple[dict[str, tuple[str | None, str | None]], dict[str, int]]:
    """算出「哪些条款可以继承、继承哪个窗口」。

    :returns: ``(windows, stats)``。``windows`` 是 ``条款 id -> (valid_from, valid_to)``，
        **只收录恰好一个候选窗口**的条款；``stats`` 是 ``one / many / none`` 三项计数，
        供调用方打印可见的数量（不得静默）。
    """
    windows: dict[str, tuple[str | None, str | None]] = {}
    stats = {"one": 0, "many": 0, "none": 0}

    for row in session.run(Q_CLAUSE_WINDOWS, kg=kg_version, tail_type=tail_type):
        n = int(row["n"])
        if n > 1:
            # 多个候选窗口 ⇒ 继承哪个都是猜 ⇒ 按口径留空
            stats["many"] += 1
            continue
        if n == 0:
            # 条款本身没有日期 ⇒ 派生边保持无日期（不是每条都写到日期）
            stats["none"] += 1
            continue
        wins = list(row["wins"])
        stats["one"] += 1
        windows[str(row["id"])] = (wins[0][0], wins[0][1])

    return windows, stats


def document_window(
    *,
    text: str,
) -> tuple[tuple[str | None, str | None], str]:
    """文档**自身声明**的窗口 ``((valid_from, valid_to), source)``（R4-b）。

    用途只有一个：条款自身一个候选窗口都没有时（既有 ``clause_windows`` 判为
    ``none`` 的那些）的**兜底**，见
    ``changes/Sprint10.5/12-document-scope-inheritance.md``。

    两侧的值都从正文里**确定性**读出，一个字符都不新造：

    - 施行日 ← ``resolve_document_date``（既有解析器，已被
      ``probe_document_date.py`` 六份语料逐份验收）；
    - 失效日 ← ``resolve_document_expiry``（新增，同锚点纪律，只认自称条款行）。

    **任一读不出 ⇒ 那一侧为 ``None``**，不补值、不套当年年末。
    """
    from app.services.parsing.document_date import (
        resolve_document_date,
        resolve_document_expiry,
    )

    start, src_start = resolve_document_date(text=text)
    end, src_end = resolve_document_expiry(text=text)
    window = (
        start.isoformat() if start else None,
        end.isoformat() if end else None,
    )
    return window, f"{src_start}|{src_end}"


def load_document_scopes(store: Path) -> dict[str, list[str | None]]:
    """读回登记册；文件不存在 ⇒ ``{}``（首次运行，不是错误）。"""
    if not store.is_file():
        return {}
    raw = json.loads(store.read_text(encoding="utf-8"))
    return {str(key): list(value) for key, value in raw.items()}


def record_document_scope(
    *,
    store: Path,
    clause_ids: Iterable[str],
    window: tuple[str | None, str | None],
) -> tuple[int, int, int]:
    """把**本份文档**的窗口登记到它自己的条款上。

    **冲突 ⇒ 剔除**（R4-b §2.3）：同一个条款实体被窗口**不同**的两份文档认领，
    说明它跨代共存（如两个版本都提到的体例名词）⇒ 用哪个都是猜 ⇒ 从登记册里删掉，
    两条边都保持无日期。此判定与文档处理顺序无关，故结果确定。

    :returns: ``(一致, 冲突剔除, 累计条数)``——三项都必须可见，登记册不能悄悄变。
    """
    scopes = load_document_scopes(store)
    target = list(window)
    same = conflict = 0

    for clause_id in sorted({str(item).strip() for item in clause_ids}):
        if not clause_id:
            continue
        prior = scopes.get(clause_id)
        if prior is None:
            scopes[clause_id] = target
        elif prior == target:
            same += 1
        else:
            scopes.pop(clause_id)
            conflict += 1

    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(
        json.dumps(scopes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return same, conflict, len(scopes)


def apply_clause_window(
    row: dict[str, Any],
    *,
    windows: Mapping[str, tuple[str | None, str | None]],
    tail_id: str,
    fallback: tuple[str | None, str | None] | None = None,
) -> dict[str, Any]:
    """把继承来的窗口写进派生边行；窗口缺失就**原样返回**（不补值、不兜底）。

    取值优先级：**条款自身窗口** → **文档窗口（R4-b 兜底）** → 不写。
    顺序不能颠倒：条款自身那一屏是更细的证据，倒过来就等于拿粗粒度覆盖细粒度。
    """
    window = windows.get(tail_id)
    if window is None:
        window = fallback
    if window is None:
        return row
    row["valid_from"], row["valid_to"] = window
    return row
