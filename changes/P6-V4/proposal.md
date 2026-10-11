# P6-V4：让 **C3-a / C3-b 真正出数**（解除 MVP 准入最后一条 `BLOCKED`）

> 计划真源：[`docs/delivery-plan.md` §9.2 序 5d（P6-V3）](../../docs/delivery-plan.md) 之后的新切片。
> 立批裁决：2026-10-11 用户 —— **当前目标不是交付，而是让软件本身可上线**
> ⇒ 排序按「距离 P8「零缺口」还差什么」，而不是按交付节奏。

---

## 0. 一句话

把 `runner.py` 里两个**写死 `BLOCKED`** 的评价函数换成**真读 `cost_metrics`** 的实现，
消除「P6-V3 声称能让两侧出数、机器却恒 `BLOCKED`」的脱节；跑出一轮实测值，
把 **TBD-7** 从"拍脑袋"变成"看数据选择题"。

---

## 1. 为什么做（**全是机器读数，不是转述文档**）

| # | 证据 | 说明 |
|---|---|---|
| 1 | `backend/app/evaluation/runner.py:849-873` `eval_single_doc_cost` | **硬 `return BLOCKED`**，从不读表；`blocked_by` 写「缺 M2 抽取侧 token 落点」 |
| 2 | `backend/app/services/cost_metrics.py:113` `record_extraction_usage` + `backend/app/tasks/registry.py:566` | **上述落点已由 P6-V2 落地**（还有 `stage='extraction'` 行与迁移 `a1f7c2b93d04`） |
| 3 | `runner.py:876-894` `eval_incremental_cost_ratio` | 同样硬 `BLOCKED`，`blocked_by` 写「`incremental_cost` / `full_rebuild_cost` 无写入方」 |
| 4 | `cost_metrics.py:170` `record_full_rebuild_cost` / `:202` `record_incremental_rebuild_cost` + `registry.py:837` / `incremental.py:299` | **上述写入方已由 P6-V3 落地** |
| 5 | `changes/P6-V3/integration-log.md:126` | 写着「本批只让两侧**能出数**」⇒ **与本批实测矛盾：runner 恒 `BLOCKED`，出不了数** |
| 6 | `backend/scripts/eval_acceptance.py:167-173` | 无 `--cost-records` 时提示「要等 `cost_metrics` 表（token 只进日志未落库）」⇒ **提示也已过期** |

**最讽刺的一点**（`runner.py:846-847` 注释原文）：

> `blocked_by` 换成真实缺口（**照抄旧理由"表未建"会让后来人以为还差一整张表**）

作者特意防的正是这件事 —— 结果 V2 / V3 补完后，**他自己写下的理由过期了，且没有任何东西通知任何人**。
这与 P7-A §5.2「跳过 7 条无人察觉」是同一类病：**机器的结论在说谎，形式是过期而非错误。**

**不做的后果**：带着 `BLOCKED` 进 P8 逐行对账 ⇒ 「零缺口」不可达成；
更糟的是，**为了让 P8 通过而把判据改松**的压力会随之而来 —— 那正好是本项目反复防的那条路。

---

## 2. Non-goals（边界，**不许越过**）

1. **不自动改阈值** —— 纪律 **RK-E7**：`--calibrate` 只输出建议，**绝不写 `config.py` / `.env`**（`eval_acceptance.py:25-26`）。阈值必须由人裁决。
2. **不动 C3-b 的量纲裁决** —— 2026-10-10 已拍板 **A 组「图规模同量纲」**：分子分母**同为「图元素个数」（实体数 + 关系数）**；分母 = 首次全量构建的元素数，且**复用 `kg_version` 的重跑不计**（`fresh_build` 判定）。改成金额口径须另行裁决。
3. **不做 `stage` 切片契约变更 / 仪表盘改造** —— P6-V3 §6.3 明列未做，属契约变更，另批。
4. **不做交付动作** —— P6-X 双人演练、release notes、打 tag 一律不碰（用户裁决：目标是可上线，不是交付）。
5. **不许伪造 `value`** —— `BLOCKED` / `UNKNOWN` 的 `value` **恒为 `null` 而非 0**（`eval_acceptance.py:23-24`）；0 会被读成"召回为 0"。
6. **不许以降低判据换绿**（R-10）—— 出不了真数就如实登记 `BLOCKED`。

---

## 3. 做法切片

| 切片 | 内容 |
|---|---|
| **V4-a** | `runner.py` 两个函数**出数化**：真读 `cost_metrics` 聚合出 `value`；**无数据才 `BLOCKED`**，且 `blocked_by` 只写**当前真实缺口** |
| **V4-b** | 新增 **cost-records 取样器**：从 `cost_metrics` 导出 `--calibrate` 能吃的 JSON，消除「无 `--cost-records` ⇒ 无法校准」的死循环 |
| **V4-c** | **实测一轮**：得到 C3-a 真值 + C3-b 比值，产出给用户的**裁决包**（实测值 + TBD-7 建议值 + 各选项后果） |

⚠️ **V4-c 需要真 LLM 调用**（抽取 / 增量重算），会产生费用 ⇒ 属 §6 的停机条件，**须先获批准**。

---

## 4. 出口判据（**机器可验**）

| # | 判据 | 判法 |
|---|---|---|
| **J1** | 无数据时仍 `BLOCKED`，但理由真实 | 断言 `blocked_by` **不含**已失效文案：「缺 M2 抽取侧」「无写入方」 |
| **J2** | **`value` 恒 `null`，不是 0** | 无数据时 `CriterionResult.value is None` |
| **J3** | 有数据 ⇒ C3-a 真出数 | 注入 `stage='extraction'` 行 ⇒ `value` 非 `null`，`unit` = token/文档 |
| **J4** | C3-b 出比值 | 注入 full / incremental ⇒ 比值出数；`0/0` 仍按裁决报 **`0.0`**（不得改此语义） |
| **J5** | `--calibrate` 闭环 | 喂 V4-b 导出的 JSON ⇒ 输出建议值，且**校验 config 未被写** |
| **J6** | 不倒退 | `pytest` 不降、`ruff check` + `ruff format --check` 绿、`check_seams` 无 ERROR |

---

## 5. 遗留（登记，不自行处置）

1. **TBD-7 的最终裁决权在你** —— 本批只提供数据，不替你决定。
2. **`0/0` 报 `0.0`** 的语义缺陷（无法区分"缺失"与"真为 0"）已在 P6-V3 §6.5 登记，本批不改。
3. 仪表盘**无 `stage` 切片**（P6-V3 §6.3）⇒ 区间视图仍是混合口径。
4. 增量**失败**时已写出的图操作记不到（`_fail` 拿不到计数）⇒ 分子偏保守。

---

## 6. 停机条件（碰到就找用户）

1. **要不要花真 LLM 跑 V4-c**（会产生费用）；
2. 若发现 C3-b 的量纲裁决需要推翻（= 要动 2026-10-10 已拍板的 A 组）；
3. 若发现要让 C3 出数必须改契约（属 Non-goal 第 3 条）；
4. 实测值出来后，**采纳哪一个阈值**由你决定。
