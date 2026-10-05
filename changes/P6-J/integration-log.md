# P6-J · 集成日志（M1：轻量 lexical 重排 —— 让 `question` 参与图侧证据选择）

> **日期**：2026-10-05 ｜ **边界文档**：`changes/P6-J/proposal.md`（Non-goals 9 条已冻结）
> **拍板**：D1 **M1** / D2 接受「改名 + 40×2 全判」/ D3 越过 10% 认可但报告须写明换了一代
> **一句话**：三条目标 chunk 从「**全被切掉**」变为「**全部进场**」⇒ 40 题上 C1 由 **8.82% → 17.65%**（3 遍一致，首次越过 10%）；
> 但**这 8.82pp 的增量依赖新增的词面重排** ⇒ 本报告 §5 明确写了「图结构 / 重排」各占多少，**说不清的部分直说说不清**。

---

## 1. 红灯基线（复现脚本先复现，再动手）

脚本 `backend/_tmp_probe_recall.py`（**收尾已删**，见 §4.3）直接调产品的
`_QUERY_EVIDENCE_CHUNK_INDEX` + `select_evidence_chunks`，不重写规则：

```
kg_version = attendance-demo-v1
实体总数 = 500 | 子图采样 = 500 | 锚点 = 0 ⇒ entity_ids = 500
候选 chunk = 213 条 ⇒ select_evidence_chunks(limit=32)

Q20 月标准工时   chunk-cc75924988e4  ❌ 被切掉   （doc 2b721483, mentions=7, 桶内 rank 3/4）
Q22 审批程序     chunk-eb5f28fb5e2a  ❌ 被切掉   （doc 2b721483, mentions=5, 桶内 rank 4/4）
Q26 预警处置     chunk-80577ef6ea9a  ❌ 被切掉   （doc 58f16d89, mentions=6, 桶内 rank 4/4）

文档桶数 = 15 ⇒ floor = 32 // 15 = 2      ← 保底只有 2 条，rank 3/4 与 4/4 必被切
```

与 `_probe_recall.txt`（上一会话的结论）**完全吻合** ⇒ 红灯基线成立，且三条目标
**都在 213 条候选里**（缺的是排序，不是数据 —— 与证据 1 一致）。

## 2. 实现障碍与裁决（proposal §3 第 2 条预判的那一件）

`_QUERY_EVIDENCE_CHUNK_INDEX` 刻意**不带 `text`**（注释：全文是最大字段，全量回传浪费）
⇒ 没有文本就做不了词面打分。裁决：**只补片段、不补全文**。

| 选项 | 回传量（1000 条上限） | 结论 |
|---|---|---|
| 回传全文 | ≈1.2MB / 次问答（本语料全文 p50≈881、max 1204 字符） | ❌ 违背原注释的取舍 |
| **前 400 字** | ≈400KB（约 1/3） | ✅ 采纳 |
| 前 200 字 | ≈200KB | 本语料**结果相同**，但余量薄 |

400 是**实测选的，不是取整**：三条目标的关键字落点分别是第 24 字（Q26「5 个工作日」）、
第 257 字（Q22「劳动行政部门」）、第 **489** 字（Q20「174」——**两档都在窗外**，
它靠的是同段里「标准工时 / 工时制」这类词面命中）。200 / 400 两档实测**三条都进**，
分值差异 Q20 0.333→0.444 / Q22 0.294→0.353 / Q26 0.545→0.545 ⇒ 取 400 留余量。
理由已写进 `_EVIDENCE_CHUNK_SNIPPET_CHARS` 的注释，**不是默默改**。

## 3. 落地了什么（4 个产品文件 + 1 个测试文件 + 1 处文档登记）

| 文件 | 改动 |
|---|---|
| `app/services/graphs.py` | ① `_EVIDENCE_CHUNK_SNIPPET_CHARS = 400`（含决策理由）；② 索引 Cypher 加第 6 列 `snippet`；③ 新增 `_bigrams` / `_lexical_overlap` / `_lexical_scores`（**纯标准库，零新依赖**）；④ `select_evidence_chunks` 加 `question` / `snippets` 两个**关键字**入参，排序键变为 「词面分 → 热度 → 文档序 → chunk_id」；⑤ `fetch_evidence_chunks` 加 `question` 并透传；⑥ 订正 `_EVIDENCE_CHUNK_LIMIT` 上方那句已失效的「question 不参与检索」 |
| `app/services/agents.py` | `fetch_evidence_chunks(...)` 多传 `question=request.question`（**子图采样部分未动**） |
| `app/evaluation/baseline.py` | `RETRIEVER_GRAPH`：`graph_mentions` ⇒ **`graph_mentions+lexical_rerank`** |
| `app/evaluation/runner.py` | 图侧 spec 的 docstring 同步新标识（仅注释） |
| `tests/test_evidence_selection.py` | 新增 **9 条**（见 §4.3） |
| `docs/dev-doc-status.md` | R22 追加「方向① 已落地轻量版，**本条不关闭**」+ 两代数字不得混用 |

**打分口径**：字符 bigram（去重集合）覆盖度 `|q ∩ s| / |q|`。
为什么它而不分词/embedding：中文无空格分词，而 Non-goals 第 4 条**禁止引入新依赖**
（装分词器/embedding ⇒ M1 变 M2）。bigram 去重成集合是为了**不把长片段的重复词读成相关性**。

**三条退化路径必须逐字退化为既有行为**（这是刻意的，不是顺带）：
空 `question` / 无命中 / `snippets` 缺失 ⇒ `scores` 为空 ⇒ 排序键落回
`(-mentions, char_start, chunk_id)`，**与 P6-J 之前逐字相同**。

## 4. 验证

### 4.1 正向（三条进场）

```
=== 选出的 32 条（with_question=True, snippet=400）===
Q20 月标准工时是多少小时？        0.444  目标 chunk-cc75924988e4 ⇒ ✅ 选中
Q22 不定时工作制在实施前需要履行什么程序？ 0.353  目标 chunk-eb5f28fb5e2a ⇒ ✅ 选中
Q26 合规预警等级为『高』时…？      0.545  目标 chunk-80577ef6ea9a ⇒ ✅ 选中
```

### 4.2 反向（撤掉修复 ⇒ 重新被切掉）—— 硬验收，做了**两次**

```
--- ① 代码在，但不传 question（= 纯结构口径）---
kg_version=attendance-demo-v1  候选=213
Q20 chunk-cc75924988e4 ⇒ ❌ 被切掉
Q22 chunk-eb5f28fb5e2a ⇒ ❌ 被切掉
Q26 chunk-80577ef6ea9a ⇒ ❌ 被切掉

--- ② git stash 真撤掉 4 个产品文件，回到 P6-I 代码 ---
kg_version=attendance-demo-v1  候选=213
Q20 chunk-cc75924988e4 ⇒ ❌ 被切掉
Q22 chunk-eb5f28fb5e2a ⇒ ❌ 被切掉
Q26 chunk-80577ef6ea9a ⇒ ❌ 被切掉
（随后 git stash pop 还原，工作区与撤前一致）
```

### 4.3 单测 9 条（`tests/test_evidence_selection.py`）

- `test_lexical_hit_takes_a_floor_slot` —— **一条用例同时钉住正反两面**：
  先断言纯结构口径下 target **不在**（否则这条用例没在测什么），再断言带 question 后 **在**；
- `test_lexical_tie_falls_back_to_structural_order` —— 并列（零重叠是**常态**）落回热度→文档序；
- `test_empty_question_degenerates_to_structural` / `test_no_lexical_hit_degenerates_to_structural`
  / `test_missing_snippets_degenerates_to_structural` —— 三条退化路径与不带参结果**完全相等**；
- `test_rerank_is_deterministic` —— 带重排后仍同输入同解；
- `test_lexical_overlap_is_coverage_not_count` / `..._ignores_punctuation_and_case`
  / `..._degenerate_inputs` —— 口径与边界（退化给 `0.0`，**不给 NaN**）。

> ⚠️ 复现脚本按约定**已删**（`_tmp_probe_recall.py` / `_tmp_probe_chars.py` /
> `_tmp_probe_reverse.py` / `_tmp_dump_answers.py` / `_tmp_judge_dump.txt`）。
> 反向验证**没有随之消失**：它由上面第一条单测长期钉住（撤掉重排 ⇒ 该用例红）。

## 5. ⚠️ 归因：这次提升里有多少归图结构、多少归 lexical 重排

```
旧（graph_mentions）            graph 37/40  vs  baseline 34/40  ⇒  C1 =  8.82%
新（graph_mentions+lexical_rerank） graph 40/40  vs  baseline 34/40  ⇒  C1 = 17.65%
                                     ↑ +3 题           ↑ 0 题          ↑ +8.82pp
```

**能说清的部分**：

- 翻转的**恰好是** Q20 / Q22 / Q26 —— 也就是 M1 被造出来要救的那三题，一条不多一条不少；
- 基线侧 34/40 **与 P6-I 完全相同** ⇒ **增益不是靠基线掉分**；
- §4.2 已证明：撤掉重排 ⇒ 这三条**回到被切掉** ⇒ 增量**完全依赖**新增的重排（必要条件）。

**说不清的部分（直说）**：图结构与重排在这里是**乘积关系，不是加法关系** ——
图结构给出 213 条候选，重排决定哪 32 条进场；**没有候选，重排没东西可排；
没有重排，候选里对的那些进不来**。所以**不存在**「图结构 X% / 重排 Y%」这种可加分解。
若一定要给一句话：**这 8.82pp 是「结构性候选集 × 词面重排」的共同产物，
拆不开；能负责地说的是两个必要条件各占一个**。

⚠️ 另一层必须写在脸上：**这是换了一代 retriever 之后的数字**。
`RETRIEVER_GRAPH` 已从 `graph_mentions` 改名 ⇒ 8.82% 与 17.65% **不得相减读成"提升了 8.82pp"**，
只能读成「新一代相对同一基线的读数」。

### 5.1 ⚠️ 这个指标已经到顶了（P6-J 收尾时补记）

```
C1 = (图 − 基) / 基     图侧 = 40/40 = 1.0     基线 = 34/40 = 0.85
⇒ C1 = (1.0 − 0.85) / 0.85 = 17.65%
```

图侧**不可能超过 40/40**；而要让 C1 再涨，唯一的算术路径是**基线掉分** ——
那恰恰是 rubric / 题集纪律明令禁止的动作 ⇒ **17.65% 就是本口径（rubric-v2 +
40 题 + 本语料）下的天花板**。后果要说清楚：**今后任何图侧改进在这个指标上
一律显示不出来**，它已经瞎了，不该再拿它当验收主指标。

顺带把这个刻度本身的噪声也记账：**基线 1 题 ⇒ C1 ±3.4pp**
（33/40 ⇒ 21.2%，35/40 ⇒ 14.3%）。本次三遍一致算是运气好（三遍共用同一份
判分表、且生成结果稳定），但**任何人拿单次读数做 ±1 题级的推断都是自欺**。

⇒ 本批之后的**待拍板项**（不属本批，我不自选）：扩/换题集恢复灵敏度，
或换语料重测泛化性；若都不做，则 C1 应降级为「记过账的历史指标」。

## 6. live 实测（真图 + 真 LLM + 真 PG + 真 embedding，3 遍）

| 遍次 | value | graph | baseline | corpus_layer | provenance.rubric | graph_spec.retriever | verdict |
|---|---|---|---|---|---|---|---|
| r1 | **0.17647059** | 1.000（40/40） | 0.850（34/40） | L2 | `rubric-v2` | `graph_mentions+lexical_rerank` | PASS(provisional) |
| r2 | **0.17647059** | 1.000 | 0.850 | L2 | `rubric-v2` | 同上 | PASS(provisional) |
| r3 | **0.17647059** | 1.000 | 0.850 | L2 | `rubric-v2` | 同上 | PASS(provisional) |

可比性前置断言（`comparability_error`）三遍均为 `None`：两侧池指纹同为
`e36322bb2d86865f` / 213 条、`top_k` 同为 32、`prompt_id` 同为 `kg_qa_v5`、
生成模型同为 `deepseek-chat`、`graph_context` True vs False（唯一变量）。
判分表 `p6j-judge-{graph,baseline}.json` 的 `_judged_by = architect`（**非匿名**）。

**40×2 全量重判的依据**：本批改的是检索 ⇒ 注入片段变了 ⇒ 两侧答案全部重新生成
⇒ P6-I 的旧判分表针对旧答案，**一律作废**。判分对象 = `p6j-dryrun.json` 的
`awaiting_graph` / `awaiting_baseline` 各 40 条原文，**逐条读过答案原文**后判。

- 图侧 false **0 条**；翻转的是 Q20 / Q22 / Q26（三条都从「自陈未检索到 / 答非所问」
  变为直接给出条文 + 引用）；
- 基线侧 false **6 条**（Q12 / Q34 / Q35 / Q36 / Q37 / Q38）：5 条是
  `should_refuse=False` 却拒答（**Q38 答案正文其实写对了** 09:00–18:00 / 8.0 小时，
  但引用闸门后 `citations=0` ⇒ `refused=True` ⇒ 违 rubric①），Q34 答「E004 当日没有
  加班记录」而语料里 `OT0001` 就是该记录 ⇒ 违 rubric②③。

### ⚠️ 一条必须说出口的自证局限

与 P6-I 同一条：**判分与实现出自同一个人**（我），单人项目里做不了真正的独立复核。
40/40 这个数看起来漂亮，但它只有一层保障：三条翻转的答案都直接引用了条文原文
（chunk id 可核）。**它没有任何独立复核**。

## 7. Non-goals 核销

| # | Non-goal | 是否守住 |
|---|---|---|
| 1 | 不校准阈值 | ✅ 仍 10% provisional，属阶段 ⑤ |
| 2 | 不改增益公式 / 不动 rubric | ✅ 仍是 `(图−基)/基`；rubric 仍 **v2**，一字未动 |
| 3 | 不删敏感 Winter / 不改题面 / 不改 40 题组成 | ✅ 40 题、题面、`should_refuse` 一字未动 |
| 4 | **不引入新第三方依赖**（尤其不给图侧装 embedding） | ✅ 只用了 `frozenset` / `zip` / `str.isalnum`；`pyproject.toml` / `uv.lock` **零改动** |
| 5 | 不改 prompt 版本 / 生成模型 / top-k 配额 | ✅ `kg_qa_v5` / `deepseek-chat` / 32 均未动（报告可核） |
| 6 | 不顺手修 H6 403 / 入图器自检 / P7-B / G-12 / MANIFEST 语料统计 | ✅ 一个没碰 |
| 7 | **不把 `RETRIEVER_GRAPH` 改回去** | ✅ 已改名且在报告 `provenance` 可见；旧数字标为不可混用 |
| 8 | 修复可被**反向验证** | ✅ §4.2 做了两遍（不传 question + `git stash` 真撤代码） |
| 9 | 不动 ingestion / 写入侧 | ✅ 只改读侧；三条目标 span 本就在库 |

## 8. 门禁

```
pytest（真 Neo4j / 真 PG + app_rls）   978 passed / 3 skipped / 3 xfailed   ← 969 ⇒ +9，**0 回归**
ruff check .                           All checks passed!
ruff format --check .                  232 files already formatted
check_seams.py                         ERROR 0 / WARN 0 / OK 10
export_openapi.py --check              [OK] 契约零 diff
check_session_drift.py                 S1 读到 changes/P6-J/proposal.md 的 9 条边界；S2–S5 全 OK
```

（pytest 需先 `set NEO4J_PASSWORD=graphragdev`、`GRAPH_REAL_NEO4J_*` 三项；
本机 `.env` 里写的 `password` 与在跑的 Neo4j 容器不符 —— 那是**本机环境**问题，
本批**不改** `.env`，只在跑测时用环境变量覆盖。）

## 9. 收尾三问（自答）

1. **有没有"顺便做的"？** 有一处需要摊开：`docs/dev-doc-status.md` 的 R22 追加了一段
   「方向① 已落地轻量版，本条**不关闭**」。理由：R22 正是本批修的这个缺口，不登记会让
   文档继续声称一件已部分解决的事。**没有**顺手修任何 Non-goals 第 6 条里的 bug。
2. **有没有为躲坑而绕路的实现？** 有一处**差点**绕：索引不带 `text` 时，最省事的做法是
   直接把全文取回来。我没有那么做（那会把原注释的取舍整个推翻），而是只取前 400 字并
   把取舍写进注释。另有一处**不是**绕路但要说明：排序把词面分放在热度**之前**，
   这是有意的（命中者优先占名额），代价是热度不再是第一优先级 —— 由 §4.3 的三条退化
   用例保证「无命中时行为不变」。
3. **验收是真跑还是读代码？** 全部实测：红灯/绿灯/反向三趟复现脚本（真 Neo4j）、
   40×2 逐条对着答案原文判分、live C1 × 3（真图 + 真 LLM + 真 PG + 真 embedding，
   **不是 offline**）。

## 10. 遗留（已登记，本批不碰）

| # | 事项 | 归属 |
|---|---|---|
| 1 | **候选集仍是结构性窗口**：不在 213 条候选里的目标片段，重排救不回来 ⇒ R22 **未关闭** | 方向② 实体链接 / ③ 向量召回，待排期 |
| 2 | C1 读数含义已变（图结构 + 词面重排），无法拆成可加的两份 | §5 已显式登记；**不**靠改回旧名"救纯度" |
| 3 | 判分跨 run（D3）：判分表针对 dry-run 那轮，出数在 r1–r3 | 本次 3 遍一致，非保证 |
| 4 | 单人判分、无独立复核 | §6 末已声明 |
| 5 | `expected_points` 粒度不均 / MANIFEST 语料统计过期 / H6 403 / 入图器自检 / P7-B / G-12 | P6-D/E/I 遗留 |
