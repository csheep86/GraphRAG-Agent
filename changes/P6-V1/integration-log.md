# P6-V1 集成日志（2026-10-09）

- **批次**：[`docs/delivery-plan.md` §9.2 序 5b](../../docs/delivery-plan.md)
- **主题**：as-of 排序口径对齐（`_cypher_paths()` 的 DB 侧 ↔ Python 侧精排键）
- **起点**：P6-V 收口；开工自检 17/0/0 + seams OK 12 + openapi 零 diff 三项**当场重跑**对上
- **状态**：✅ 队列三条判据全部达成；⚠️ **残留风险登记在 §5，不许读成「已完全对齐」**
- **收口 CI**：run **37937718815 四 job 全绿**（含 CI 上的真图用例 —— 判据 2 不是只在本机成立）

---

## 1. 本批做了什么（按提交顺序）

| # | 提交 | 内容 |
|---|---|---|
| 1 | `feat(reasoning)` | 两侧排序键**登记**（`PATH_SORT_DIMENSIONS` / `DB_ORDER_BY_DIMENSIONS`）+ Cypher 档位表达式改为**读 Python 同一份常量**（不再下发 `prio_types`）+ 截断打进既有日志 |
| 2 | `test(reasoning)` | 新增 6 条用例（含真图 **401 候选**对照）+ 既有守卫同步（`test_agent_reasoning_path.py` 的 `prio_types` 断言） |
| 3 | `docs(changes)` | 回登 `changes/P6-U/13-as-of-evidence-rank.md` §遗留 + 本批日志 + 逐维比对探针 |

**修法一句话**：不是"把 Python 的口径抄进 Cypher"，而是**让 Cypher 去读 Python 的常量**
（`$prio_type` / `$terminal_rank` 由 `TERMINAL_PRIORITY_TYPE` / `_TERMINAL_RANK` 下发）。
抄一份类型表，抄的当天一致，第二天就漂——本次就是这么漂出来的。

## 2. 判据 1：两侧排序键**逐维比对**（机器输出）

跑 `uv run python ../changes/P6-V1/probe_sort_key_alignment.py`（backend 目录）：

```
--- Cypher 侧 ORDER BY（从 _cypher_paths() 解析，共 3 项） ---
  1. CASE WHEN types[-1] = $prio_type THEN 0 ELSE 1 + coalesce($terminal_rank[types[-1]], $terminal_rank_default) END
  2. size(rels)
  3. ids[-1]

--- 逐维比对 ---
维   Python 侧           DB 侧           结论
1   terminal_priority  $prio_type     一致  [DB]
2   terminal_rank      $terminal_rank 一致  [DB]
3   hops               size(rels)     一致  [DB]
4   temporal_verdict   --             DB 侧不做（残留风险）  [  ]
5   as_of_evidence     --             DB 侧不做（残留风险）  [  ]
6   path_ids           ids[-1]        粒度不同（粗化）  [  ]
7   position           --             DB 侧不做（残留风险）  [  ]

--- 前缀性质 ---
  DB_ORDER_BY_DIMENSIONS = ('terminal_priority', 'terminal_rank', 'hops')
  PATH_SORT_DIMENSIONS[:3] = ('terminal_priority', 'terminal_rank', 'hops')
  -> [OK] 连续前缀成立
  DB 侧未覆盖的维：['temporal_verdict', 'as_of_evidence', 'path_ids', 'position']
```

**改前 vs 改后**（这才是本批的实际 delta，不是"对齐了"三个字）：

| 维 | 改前 Cypher | 改后 Cypher |
|---|---|---|
| 1 | `types[-1] IN $prio_types`（把 `LEGAL_PERSON` 也算优先，与 Python 只认 `POLICY_CLAUSE` **不等价**） | `types[-1] = $prio_type`（值来自 `TERMINAL_PRIORITY_TYPE`） |
| 2 | **无此维** | 合并进第 1 个 `CASE`（`1 + coalesce($terminal_rank[...], default)`，值来自 `_TERMINAL_RANK`） |
| 3 | `size(rels)` | 不变 |

方向是 **Cypher 向 Python 对齐**，不是反过来给 Python 加 `LEGAL_PERSON` 优先权——
那会动 P6-V 刚接线的关联方域既有排序结果（`test_python_side_gives_no_priority_to_affiliation_terminal` 钉住）。

## 3. 判据 2：候选 > 400 时真胜者**不被** DB 侧截断（真图）

`backend/tests/test_reasoning_db_order_by.py`（6 条全绿，真图那条真的跑了，不是 skip）：

```
tests/test_reasoning_db_order_by.py::test_db_dimensions_are_a_continuous_prefix_of_python_dims PASSED
tests/test_reasoning_db_order_by.py::test_cypher_renders_the_registered_order_by_expression PASSED
tests/test_reasoning_db_order_by.py::test_cypher_order_by_references_only_supplied_params PASSED
tests/test_reasoning_db_order_by.py::test_db_sort_params_come_from_the_same_constants_as_python PASSED
tests/test_reasoning_db_order_by.py::test_python_side_gives_no_priority_to_affiliation_terminal PASSED
tests/test_reasoning_db_order_by.py::test_db_truncation_drops_true_winner_only_under_legacy_key PASSED
```

构造（**真 Neo4j，401 条候选**）：锚点一跳连到 400 个 `ACCESS_RECORD`（`_TERMINAL_RANK` 排 **7**，最末）
+ 1 个 `BUSINESS_TRIP`（排 **0**，最前，id 字典序**最大**）。
同一批数据、同一条生产查询（含生产 `WHERE` 谓词），**只换 `ORDER BY` 子句**：

| 键 | 返回行数 | 真胜者在内？ | Python 精排选中 |
|---|---|---|---|
| 旧键（`(prio, hops, ids[-1])`） | **400**（截断真的发生） | ❌ 不在 | 干扰项 |
| 新键（`(终点档位, hops, ids[-1])`） | 401 → 截断后 | ✅ 在 | **真胜者** |

两条断言缺一不可：只测"新键选中真胜者"考不出截断（候选 < 400 时旧键也能过）；
只测"旧键丢了"考不出修好了没。

## 4. 本批踩到的坑：**`ORDER BY` 那段不是 f-string**

第一次把 `{_DB_TERMINAL_TIER_EXPR}` 接进 `_cypher_paths()` 时，它被当成**字面文本**下发给了 Neo4j
——那段拼接字符串是普通字符串（原来 ORDER BY 是硬写的，不需要插值）：

```
AssertionError: Cypher 的 ORDER BY 用的是别的表达式 ⇒ 登记与实现已经漂移
assert 'CASE WHEN types[-1] = $prio_type THEN 0 ...' in "...ORDER BY {_DB_TERMINAL_TIER_EXPR},..."
```

**是新增断言当场抓住的**，不是人眼复查出来的。这个 bug 在候选 < 400 时**永远不显形**
（真机当前最多 165 行）——正是 P6-U 遗留那句"没触发是运气"的实物证据。
已在源码该处留注释说明原委。

## 5. 残留风险（⚠️ 不许读成「已完全对齐」）

- DB 侧只覆盖前 **3 维**。当前 3 维全打平的候选数 > 400 时，DB 侧按 `ids[-1]` 截断，
  仍可能丢掉靠**维 4（整链时序）／维 5（as-of 证据位次）**胜出的那条。
- 此刻丢的是**同档内次优**（同样有解释力、同样短），**不改变答案的解释力层级**；
  不搬这两维的理由（会把 `_temporal_verdict` 的 max/min 三值语义在 Cypher 里写第二份）
  见 `proposal.md` §4 W1-b。
- 顺带把截断**打进既有日志**（`reasoning_path_temporal_verdict` 增 `candidate_limit` /
  `truncated` 两字段，不新增日志语句、不新增配置）⇒ 静默丢候选不再是黑箱。

## 6. 门禁读数（动工前 vs 收口，**全部实跑**）

| 项 | 动工前 | 收口 |
|---|---|---|
| `check_startup_readiness.py` | 17 / 0 / 0 | **17 / 0 / 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 | **ERROR 0 / WARN 0 / OK 12** |
| `export_openapi.py --check` | 零 diff | **零 diff** |
| `ruff check` / `ruff format --check` | 全绿 | **全绿**（修了 2 处 import 排序 + 1 处格式） |
| `pytest tests`（有图口径） | **1167 passed / 5 skipped** | **1173 passed / 5 skipped**（+6，skipped 不增） |
| `check_session_drift.py` | — | S1 读到 **9 条**边界；S2 2 文件 / 100 行（未超阈值）；S3–S5 全 OK |

有图口径的 env（**三个都要设**，少设 `USER` 会让 `test_eval_ci_gate.py:219` /
`test_eval_corpus_a8.py:305` 静默 skip ⇒ 数字对不上）：

```powershell
$pw = (Select-String -Path .env -Pattern '^NEO4J_PASSWORD=(.*)$').Matches[0].Groups[1].Value
$env:GRAPH_REAL_NEO4J_URI='bolt://127.0.0.1:7687'
$env:GRAPH_REAL_NEO4J_USER='neo4j'
$env:GRAPH_REAL_NEO4J_PASSWORD=$pw
uv run pytest tests -q
```

## 7. 提交 / 推送 / CI

- 三个提交（代码 / 测试 / 文档分列），`main` 直推（`e33155d..6dec46d`）
- CI run **37937718815** 四 job 全绿；后端 job 里 Pytest / 接缝 / 契约冻结 / C2 门禁
  逐条 success ⇒ **真图用例在 CI 上也真的跑了**（CI 有 `neo4j` service 且注入了
  `GRAPH_REAL_NEO4J_*`，由 G-9 判据 0 盯住）

## 8. 自问三句（drift 脚本拦不住，**必须自己答**）

1. **有没有顺手做的？** 有一样擦边：真图夹具（`real_driver`）本处**复制**了一份，
   没有去改共享的 `conftest.py`。判断：本批是小修，动 conftest 波及上千条用例；
   已在测试文件头登记「第三处真图用例时再一并抽到 conftest」。**属技术债登记，不是顺手加功能。**
2. **有没有为躲坑而绕路？** 没有。反面例子是"直接把 LIMIT 400 调大"——那会把 bug 藏得更深，
   W2 明确否掉（`proposal.md` §4）。
3. **验收是真跑出来的还是读代码得出的？** 判据 1 是探针解析**生产 Cypher 字符串**得出的；
   判据 2 是**真 Neo4j** 跑出来的。没有一条来自读代码。

## 9. 下一批指针

- **P6-V2**（`delivery-plan.md` §9.2 序 5c）：M2 抽取侧 token 落点 + `stage` 列（偏离 X-6）。
- **P6-T 判分 86 题**：继续传承（人做主体，AI 不得代填 `correct`）。
- **X-5**（契约描述文本仍写"恒 501"）：跨角色，等用户点名。
- 详见 [`new-session-prompt.md`](./new-session-prompt.md) §12。
