"""M6 读侧的**版本继承读谓词**（P5-H 批次 C'）。

**为什么单独一个模块**：本模块**不导入任何 ``app.*``**（连模型都不牵）。

这不是洁癖，是被迫的：``app.services.kg.__init__`` 会把 ``builder``（→ ``graphs``）
一并拖进来，所以 ``graphs.py`` 在**模块级**导入 ``version_view``（它牵
``versioning`` → ``db.models``）会立刻形成一个环形导入
（``graphs → kg.__init__ → builder → graphs``），2026-10-08 实测就是 ``ImportError``。

而 Cypher 常量偏偏是**模块级**构建的（``_QUERY_GRAPH_OVERVIEW = ...``），推迟不到
函数里面去。于是把「生成谓词」这件事本身抽到一个零依赖模块，让三条读路径
（``graphs`` / ``reasoning`` / ``rules.engine``）与裁决层（``version_view``）
都从这一个地方取，**同一段判据只有一处定义**。
"""

from __future__ import annotations

__all__ = ["KGS_PARAM", "SEL_PARAM", "version_scope"]

#: Cypher 参数名：版本列表（**新 → 旧**有序）。
KGS_PARAM = "kgs"

#: Cypher 参数名：选中表（``{实体 id: 该 id 的可见版本}``）。
SEL_PARAM = "sel"


def version_scope(alias: str) -> str:
    """返回一个节点的**版本继承读**谓词（直接拼进 ``WHERE ... AND <本段>``）。

    **缺省零变化**：版本链只有 active 一条 ⇒ ``$sel`` 是**空 map** ⇒
    ``size(keys($sel)) = 0`` 为真 ⇒ 后半句恒真 ⇒ 只剩 ``IN $kgs``
    （列表里只有一个元素）⇒ 等价于原来的 ``{alias}.kg_version = $kg``。

    ⚠️ ``size(keys($sel)) = 0`` 这一句**不能省**，也**不能**改写成等价形态的
    ``$sel[x.id] IS NULL``：map 参数里**没有**某个 key 时 ``$sel[key]`` 同样取到
    ``null`` ⇒ 「选中表为空（缺省形态）」与「该 id 未被选中（已被 merge 删掉）」
    会被混为一谈 ⇒ **被删掉的节点会重新读出来**。本批实测踩过：症状是
    "merge 似乎没生效"，而 Cypher 一眼看去完全合理。

    注意：本段**不含** ``org_id`` —— 隔离键由各 Cypher 自己带（且选中表本身也按
    租户算），两者是**双保险**，不是互相替代。
    """
    return (
        f"{alias}.kg_version IN ${KGS_PARAM} "
        f"AND (size(keys(${SEL_PARAM})) = 0 "
        f"OR ${SEL_PARAM}[{alias}.id] = {alias}.kg_version)"
    )
