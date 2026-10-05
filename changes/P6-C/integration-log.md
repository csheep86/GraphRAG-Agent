# P6-C · 集成日志（A1：dense top-k 基线 + 双侧判分 + 反向守卫）

> **日期**：2026-10-05 ｜ **起始提交**：`7d447046`（P7-A 已推送）
> **依据**：`changes/P0-m6-eval/integration-log.md` **L10-A1 裁决**（条款 1–6）
> **结果一句话**：**C1 的 scaffolding 全部到位了，但这一批仍拿不到 C1 的数字**——两个阻塞点都是真的、且互相独立，详见 §4。

---

## 1. 先说清楚：这批"钉住"了什么

L10-A1 的关键判断是 **C1 的风险不在算法，而在"谁选基线"**：相对指标
`(图谱 − 基线) / 基线` 里基线自选 ⇒ 选一个弱基线就能刷出 >10%。故本批做的是
**先把除"检索方式"以外的变量全部钉死**，并给每个"刷绿入口"配一道**会红的断言**。

| L10-A1 条款 | 本批的落实方式 | 落点 |
|---|---|---|
| ① 共因冻结 | `BaselineSpec` + **池指纹**：两侧必须同池、同 k（基线**不得更小**）、同生成模型、同 prompt 版本 | `app/evaluation/baseline.py::comparability_error` |
| ② 基线 = dense top-k | `DenseTopKRetriever`（**余弦 / top-k**，不是 BM25、不是 LLM 重排）；零新增依赖（复用现有 `langchain-openai` 的 `OpenAIEmbeddings`） | 同上 + `OpenAICompatibleEmbedder` |
| ③ 分数 = 受控问题集答对率，两侧都需人工判分 | `RunnerContext.baseline_judgements` **独立判分通道**；缺任一侧 ⇒ UNKNOWN（**不是 0、不是 PASS**） | `runner.py` |
| ④ 反向守卫（三条） | ① 基线分随 `graph_accuracy` 一并落 `detail`；② `baseline_spec` 进报告；③ 见下方 §3 五项变异 | `baseline.py` + `runner.py` + `tests/test_eval_baseline_a1.py` |
| ⑤ 不进产品路径 | 基线模块在 `app/evaluation/` 内，**契约零 diff**（`export_openapi.py --check` 绿）；唯一产品侧改动是**新增**（不改写）两个图侧能力 | 见 §2 |
| ⑥ 基线非客户系统 ⇒ G5 声明 | `Provenance.notes` 明确写"基线 = 项目内自建 dense top-k，**非客户现有系统** ⇒ 增益只对该基线成立" | `runner.py::eval_graph_gain` |

## 2. 改动清单

| 文件 | 性质 | 说明 |
|---|---|---|
| `app/evaluation/baseline.py` | **新增** | 检索器 / 池指纹 / `BaselineSpec` / `comparability_error` / 基线侧答案生成 |
| `app/evaluation/runner.py` | 改 | `baseline_judgements`、`answered_indices`（判分对齐）、`eval_graph_gain` 真 evaluator、C_GAIN 注册替换 `PlaceholderEvaluator` |
| `app/services/graphs.py` | **仅新增** | `EVIDENCE_CHUNK_LIMIT` 对外别名、`_QUERY_CHUNK_POOL` + `fetch_chunk_pool()`；**既有检索行为一行未动** |
| `app/core/config.py` | 新增字段 | `eval_embedding_base_url` / `eval_embedding_api_key` / `eval_embedding_model` / `eval_baseline_top_k`（**均有消费者行**，seams OK 10 继续绿） |
| `backend/.env.example` | 同步 | S3 会拦，已同步 |
| `tests/test_eval_baseline_a1.py` | **新增 20 条** | 纯逻辑为主，**刻意不含 LLM 调用** ⇒ CI 每次提交必过 |
| `tests/test_eval_acceptance_cli.py:73` | **改 1 处断言** | 见下方 ⚠️ |

⚠️ **改了既有测试，说明清楚（不许悄悄改）**：该断言原本是
`assert "baseline" in blocked["c1_graph_gain"]`——它守护的事实是"A1 未实现"。
**A1 现在实现了**，C1 在 offline 下欠的是**真链路**（与 C2-a / C2-b 同口径点名 `live`）。
断言的**意图不变**（blocked_by 必须点名到底缺什么），缺的东西变了，故按新事实改写，
并把"基线缺失 ⇒ 点名 baseline"的下移成新测试 `test_missing_embedding_blocks_c1_without_number`——
**不是把红改绿**，是把它移到还在拦的位置。

## 3. 反向验证（**逐条破坏，确认判红**）

| # | 变异（故意破坏） | 期望被判红的测试 | 实测 |
|---|---|---|---|
| 1 | `graph_gain` 的返回值套 `abs()` | `test_graph_gain_preserves_negative_sign` | ✅ `1 failed` → 还原后 `1 passed` |
| 2 | `comparability_error` 里"基线 k 不得更小"改成 `if False and …` | `test_smaller_baseline_top_k_is_rejected` | ✅ `1 failed` |
| 3 | 池指纹比对改成 `if False and …` | `test_different_pool_is_rejected` | ✅ `1 failed` |
| 4 | `build_default_embedder` 的模型名 fail-fast 改成 `if False:` | `test_build_default_embedder_fail_fast` + `test_missing_embedding_blocks_c1_without_number` | **⚠️ 第一轮没判红 ⇒ 见下方** |
| 5 | `comparability_error` 开头直接 `return None`（整段关掉） | 4 条可比性测试 | ✅ `4 failed` |

### 3.1 变异 4 的教训（**本批最值钱的一条**）

第一轮变异 4 时测试**照样绿**。原因：断言写成 `"embedding" in error`——但相邻的
"密钥未配置"分支也带 embedding 字样，**判红权被别人抢走了**，等于这条守卫没人盯。

处置两步：

1. 断言从 `"embedding" in error` 收紧到 **`"EVAL_EMBEDDING_MODEL" in error`**（点名缺失项）；
2. 复验**仍绿** ⇒ 说明不止一处掩盖 ⇒ 改为**先坐实相邻分支**（monkeypatch 把 `llm_api_key` 写成 dummy），
   再单独立一条直接测 `build_default_embedder()` 的用例。

第二次复验：**2 failed** ✅。

> 这条教训已写进测试用例的 docstring，避免后来者再松回去。

## 4. 实测结果（**如实登记：拿不到 C1 的数字**）

`pytest --live` 之外的真实链路**没能跑起来**，两个阻塞点**互相独立**，缺任一个都出不了数：

| 阻塞点 | 证据（2026-10-05 实跑） |
|---|---|
| **B-1**：**没有可用于问答的 ready `kg_version`** | 本环境的 Neo4j 里存在的 `kg_version` 只有 `affiliation-demo-v2`（988 chunk）与 `affiliation-demo-v1`（128 chunk）——**QA 演示语料的 chunk 一个都没有**。这与已知问题一致（`ingest_attendance_policies.py` 的 `GOVERNED_BY` 连边为 0 ⇒ 演示图重建卡住）。dev 库 `graphrag` 本次才首次迁移到 head（此前连 `kg_versions` 表都不存在）。 |
| **B-2**：**没有 OpenAI 兼容的 embedding 服务** | 现有配置只有 DeepSeek（`LLM_BASE_URL=https://api.deepseek.com`），它**不提供 `/embeddings`**。配置项 `EVAL_EMBEDDING_MODEL` **刻意无默认值**（嵌入模型与对话模型必然不同，给默认值只会把 404 推迟到跑数据那天）。 |

**能实跑的那一小块已经实跑了**（不是纯推断）：

- 新增 Cypher 在**真图**上验证通过：`fetch_chunk_pool(kg_version="affiliation-demo-v2")`
  ⇒ **988 条 chunk**（与 `MATCH (c:Chunk {kg_version:…}) RETURN count(c)` 的 988 完全一致），
  指纹 `a6a97eea9359b911`；查一个不存在的版本 ⇒ 返回 0 条（不是抛异常）。
- 这是**真池、真表、真连接**，但它是 affiliation 池，**不是 QA 池** ⇒ 不能拿来给 C1 出数。

**结论**：C1 在本次环境下仍为 **`UNKNOWN`**，`blocked_by` 会按正确顺序点名上面两个阻塞点之一：

- offline ⇒ `需 live 模式（C1 要跑两侧问答链路）；offline 不产出判据数字`
- live 但无 embedding ⇒ `embedding 未配置（EVAL_EMBEDDING_MODEL / *_API_KEY）`
- live 且配置齐 ⇒ 会先撞 B-1（无 ready kg_version / 池为空）

**没有**编造任何 C1 数值，**没有**用构造值或单测冒充实测。

## 5. 门禁实测数字

```
pytest（有真 Neo4j，PG 16.15 + app_rls 受限角色）  950 passed / 3 skipped / 3 xfailed
   └─ 基线 930（P7-A 实测）⇒ +20 条新增，0 回归
ruff check .                                      All checks passed!
ruff format --check .                             226 files already formatted
check_seams.py                                    ERROR 0 / WARN 0 / OK 10
export_openapi.py --check                         [OK] 一致（契约零 diff）
check_session_drift.py                            S1 读到 8 条 Non-goals ✅｜S2 5 文件/+397 ✅｜S3 Settings 字段均已落 .env.example ✅｜S4 未改契约/路由 ✅｜S5 ✅
```

## 6. 收尾三问（自答）

1. **有没有"顺便做的"？属于哪条 DR / G？**
   没有。**唯一的边界外动作**是给 `graphs.py` 加 `fetch_chunk_pool` / `EVIDENCE_CHUNK_LIMIT`
   别名——但它属于 A1 本体（基线需要一个"整池"入口），且**只增不改**；
   发现的两个既有问题（`ingest_attendance_policies.py` 连边、`test_frozen_snapshot_is_committed`
   名实不符）**都没动**，只登记。
2. **有没有为躲坑而绕路的实现？**
   有一处**没绕**：为了让"两侧唯一变量 = 检索方式"成立，基线侧的生成**没有自己重写一套**，
   而是 import 复用产品侧的 `PromptTemplate` / `ChatModel` / `_parse_llm_answer` /
   `_build_citations` / `_grounded_citations`。重写的省事做法会多出若干无意识差异 ⇒ 增益归因全废。
   代价是 eval 侧 import 了几个私有 helper，这个取舍已写进模块 docstring。
   **另有一处明确登记的残留变量**（不许装作没有）：`as_of_date` 走 `db=None` 口径；
   当前演示语料全部无 `document_date` ⇒ 两侧同解为空，一旦语料有日期就会漂移 ⇒ 已写进 C1 报告的 `notes`。
3. **结论是真跑出来的还是读代码得出的？**
   - 新增断言：全部实跑（含 5 次变异的**判红**验证，不是"绿了就算过"）；
   - 新 Cypher：**真图实跑**（988 条 + 指纹）；
   - C1 数值：**没跑出来**，且没有编造 ⇒ 已按"未实测 + 卡在哪一步"登记（§4）。

## 7. 阶段小结

| 项 | 数 |
|---|---|
| 完成子任务 | T1–T9 **除 T8（真链路实测）外全部完成**；T8 部分完成（拿到真池与真实阻塞证据，**未**拿到 C1 数值） |
| 降级登记 | **1**（C1 仍 `UNKNOWN`，理由与证据见 §4）——**非**静默降级，机制本身返回的是 UNKNOWN 而非 PASS |
| 升级用户 | 0（两个阻塞点都落文档既有记录 / 既定建议范围内 ⇒ 不必打断） |
| 新增测试 | 20 条（纯逻辑，CI 必过） |
| 反向验证 | 5 次变异，其中 **1 次第一轮没判红 ⇒ 收紧断言后判红**（见 §3.1） |
| 未决 | 拿到 embedding endpoint + ready QA kg_version 后才能出 C1 数值 |

## 8. 对下一批的建议（**不改出 C1 阈值**）

- 阶段 ③（L2 端到端）会顺带撞同一个 B-1 阻塞：**演示图重建卡在 `ingest_attendance_policies.py`**。
  建议 ③ 的第一步就先确认该脚本能否修好——修不好则 ③ 也只能出 L1 结论（届时如实标 `corpus_layer=L1`）。
- 拿到 C1 数字前，**不得**用任何人造的数替补，也不得把 C2-c 的 1.00 拿出来"佐证" C1（两条判据不许互相顶替）。
