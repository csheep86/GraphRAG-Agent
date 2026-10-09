# P6-V1：as-of 排序口径对齐（`_cypher_paths()` DB 侧 ↔ Python 侧）

- **队列**：[`docs/delivery-plan.md` §9.2](../../docs/delivery-plan.md) 序 **5b**
- **前置**：P6-V 已收口并提交（见 [`changes/P6-V/integration-log.md`](../P6-V/integration-log.md)）
- **状态**：进行中（2026-10-09 开工）
- **来源**：[`changes/P6-U/13-as-of-evidence-rank.md`](../P6-U/13-as-of-evidence-rank.md) §遗留
  （2026-10-09 用户裁决采纳 ⇒ 旧称「是否对齐另开一轮」**已排期，勿再当作未排期项**）

---

## 1. 本批要做什么

把候选路径的**两侧排序口径**摆到同一张表上，并消除「DB 侧 `ORDER BY` 会把真胜者截掉」这一真实缺口：

1. **逐维比对**：把 Python 侧 `_select_shortest_path` 的 7 维键与 `_cypher_paths()` 的
   DB 侧 `ORDER BY` **逐维**列出（哪一维一致、哪一维缺失、哪一维粒度不同），
   产出必须是**机器可复跑**的（登记 + 断言），不是人眼复查；
2. **消除已查实的不一致**（见 §3 比对表第 1 / 2 维）——这不是"理论风险"，
   第 1 维两侧**当前就不等价**；
3. **一条候选 > 400 的用例**：同一批真图数据、同一条生产查询，只换 `ORDER BY` 子句，
   对照「旧键丢真胜者 / 新键不丢」；
4. **回登**两侧口径文档 + P6-U 遗留登记，避免下一人只改一边。

## 2. Non-goals（9 条）

1. **AI 不得代填任何 `correct` 值**（A3）——永久红线。
2. **不动 P6-V 的成果**：七条读路径的继承读，不得为了排序而改视野逻辑
   （读口径与排序口径是两件事）。
3. **不改 rubric / 题集 / 判分**（P6-T 仍 `UNKNOWN`，人是瓶颈）。
4. **不改 `frontend/`**（除非用户点名要一并修 X-5，那时才允许）。
5. **不改契约** —— `export_openapi.py --check` 零 diff 为判据；**包括描述文本**。
6. **不夹带**：不许把 `fetch_evidence_chunks` 的继承读、M2 token 落点（P6-V2）、
   跨版本边（P5H-6）并进来 —— 各自有批次，已在 `changes/P6-V/integration-log.md` §9 登记。
7. **不许"改一边就完了"**：动 DB 侧排序键 ⇒ 必须同时把两侧口径写成文档 + 断言，
   否则下一次有人只改一边，又回到同款 bug。
8. **不改 `docs/sprint-calendar.md` 的方针**。
9. **不顺手改 `_temporal_verdict` 的 `None` 口径**（它当前只检查 `valid_froms` 的
   `None`、不检查 `valid_tos`）——看着像漏，但改它会动既有行为，**登记传承，本批不动**。

> ⚠️ 若实现中必须触碰某条 Non-goal ⇒ **先缩范围再报告**（哪份文档哪一行 / 改什么 / 为什么绕不过 / 试过的替代方案）。

## 3. 工量证据（2026-10-09 机械查实，**两侧逐维比对**）

| 维 | Python 侧（`_select_shortest_path` sort key） | DB 侧（`_cypher_paths()` ORDER BY） | 结论 |
|---|---|---|---|
| 1 | `0 if terminal == TERMINAL_PRIORITY_TYPE else 1`（**只** `POLICY_CLAUSE`） | `CASE WHEN types[-1] IN $prio_types THEN 0 ELSE 1 END`（`prio_types = (POLICY_CLAUSE, LEGAL_PERSON)`） | ❌ **不等价**：`LEGAL_PERSON` 终点 DB 侧算 0、Python 侧算 1 |
| 2 | `_TERMINAL_RANK.get(terminal, len)`（8 档，`BUSINESS_TRIP=0`…`ACCESS_RECORD=7`） | **无此维** | ❌ **DB 侧缺失** |
| 3 | `len(rels)` | `size(rels)` | ✅ 一致 |
| 4 | `_TEMPORAL_RANK[verdict]`（整链时序三值档） | **无此维** | ❌ **DB 侧缺失** |
| 5 | `_AS_OF_EVIDENCE_RANK[...]`（最后一跳 as-of 位次） | **无此维** | ❌ **DB 侧缺失** |
| 6 | `tuple(ids)`（**整链** id 元组） | `ids[-1]`（**仅终点**） | ⚠️ 粒度不同（tie-break 用，不改变解释力层级） |
| 7 | `position`（原始位次） | 无稳定保证 | ⚠️ DB 侧无 |

**当前未触发只是运气**：`changes/P6-U/13-as-of-evidence-rank.md` §遗留记着真机候选最多
**165 行**，够不着 `_PATH_CANDIDATE_LIMIT = 400`。

坐标（已复核在原位）：

| 坐标 | 位置 |
|---|---|
| DB 侧排序 | `backend/app/services/reasoning.py:242-245`（`_cypher_paths()` 的 `ORDER BY … LIMIT $limit`） |
| Python 侧精排 | 同文件 `_select_shortest_path()`（`:679-708` 建键 + 排序） |
| 终点档位常量 | `_TERMINAL_RANK`（`:124`）/ `TERMINAL_PRIORITY_TYPE`（`:80`）/ `PRIORITY_TERMINAL_TYPES`（`:170`） |
| 队列定义 | `docs/delivery-plan.md` §9.2 序 5b |

## 4. 决策表

| # | 决策 | 结论 |
|---|---|---|
| **W1** | DB 侧要不要把 7 维全搬进 Cypher | **不全搬**（采纳提示词建议）：DB 侧做**前 3 维**（终点档位 / 跳数 + `ids[-1]` tie-break）。理由见 §5 |
| **W1-a** | 维 1+2 怎么搬 | **合并成一个「终点档位」表达式**，值由 **Python 常量派生**（`$prio_type` + `$terminal_rank` map 参数）⇒ 不在 Cypher 里硬写类型名，不产生第二份常量 |
| **W1-b** | 维 4（时序档）/ 维 5（as-of 位次）为何不搬 | ① 搬维 5 而**跳过**维 4 会破坏「DB 键 = Python 键**连续前缀**」的性质 ⇒ 反而**新引入**截断错误；② 连维 4 一起搬，就得在 Cypher 里重写 `_temporal_verdict` 的 max/min 三值语义 ⇒ **把同一判断散写成两份**（`_cypher_paths()` docstring 记着的真机事故正是这么来的）。残留风险登记于 §6 |
| **W2** | 是否动 `_PATH_CANDIDATE_LIMIT = 400` | **不动**。判据 2 的用例证明"丢真胜者"的根因是**排序键不对**，不是限制太小；改限制只会把 bug 藏得更深 |
| **W3** | X-5（契约描述文本） | **本批不动**（跨角色 ⇒ 升级用户第 3 类） |
| **W4** | 判据进不进 CI | 进 —— 纯函数 + 真图（CI 已有 Neo4j service，G-9 保证），不需要 live LLM |

## 5. 为什么「DB 键必须是 Python 键的连续前缀」

Cypher 侧的 `LIMIT 400` 是**截断**，Python 侧精排只对「截断后的幸存者」生效。
要保证真胜者不被截掉，DB 侧排序必须是 Python 排序的**加粗（coarsening）**：
若 A 在 Python 键里先于 B，则 A 在 DB 键里**不许**后于 B。
「DB 键 = Python 键前 k 维 + 任意 tie-break」是该条件的**充分**形式；
**跳维**（如做 1,2,3,5 而跳过 4）会破坏它 ⇒ 宁可少做，不可跳做。

## 6. 残留风险（**不许被读成"已完全对齐"**）

- DB 侧覆盖前 3 维 ⇒ 当**前 3 维全打平**的候选数 > 400 时，DB 侧按 `ids[-1]` 截断，
  仍可能丢掉靠维 4 / 5 胜出的那条。
- 此时丢的是**同档内的次优**（同样有解释力、同样短），**不改变答案的解释力层级**，
  故按 W1 不搬；要彻底收口，正道是**让截断可观测**，而不是复制判断。
- 本批顺带把截断**打进既有日志**（`reasoning_path_temporal_verdict` 加字段），
  不新增日志语句、不新增配置。

## 7. 执行顺序（每步一个 Conventional Commit）

1. `reasoning.py`：登记两侧排序键（单一事实源 + 前缀断言）+ 生成 DB 侧 `ORDER BY`
2. 修正模块注释里「两者口径一致」这句**过期口径**
3. 新增测试：逐维比对 / 前缀 / 真图 > 400 对照（旧键丢、新键不丢）
4. 回登：P6-U 遗留登记 + 本批 `integration-log.md`

## 8. 验收判据（每条要能贴机器输出）

1. 两侧排序键**逐维比对**的输出（哪一维一致 / 不一致 / 为什么）；
2. **一条候选 > 400 的真图用例**：同一批数据、同一条生产查询，只换 `ORDER BY`
   ⇒ 旧键丢真胜者、新键不丢（对照两条断言）；
3. `pytest` **不降**（基线 1167 passed / 5 skipped，以动工前实测为准）；
4. `ruff check` / `ruff format --check` / `check_seams` / `export_openapi --check` 四项读数不变；
5. 回登：`changes/P6-V1/integration-log.md` + `changes/P6-U/13-as-of-evidence-rank.md` §遗留。
