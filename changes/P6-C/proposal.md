# P6-C · A1 兑现：dense top-k 向量基线 + 双侧判分 + 反向守卫

> **依据**：`changes/P0-m6-eval/integration-log.md` **L10-A1 裁决**（2026-10-03）裁决条款 1–6；
> 同文档的 **L11(a)** 把「A1 实现」明列为 P6 第一步的实现清单首项。
> **日期**：2026-10-05 ｜ **前置**：P7-A 已推送（`7d447046`）， local 实测环境已重建
> （`postgres:16-alpine` + 真 `neo4j:5.26-community`，全量 pytest 930 passed）

---

## 1. 为什么现在做

**C1「图谱增益 ≥10%」当前连分母都没有**：`runner.py:870-878` 把 `c1_graph_gain`
注册成 `PlaceholderEvaluator(blocked_by="baseline-not-implemented")`，报告里永远是 `BLOCKED`。

L10-A1 的关键判断是：**C1 的风险不在算法，而在"谁选基线"**——
`(图谱 − 基线) / 基线` 是相对指标，基线越弱增益越高 ⇒ **选一个弱基线就能刷出 >10%**。
这与 **R-9「恒绿失效」**同源：判据存在，但绿不绿由选基线的人决定。

所以本批第一优先级**不是把 C1 算出来**，而是**按 L10-A1 的裁决把变量钉死**，
让增益只能归因于检索方式。

**现状核查（2026-10-05 实读代码）**：

| L10-A1 条款 | 现状 | 缺口 |
|---|---|---|
| ① 共因冻结：同 chunk 池 / 同 k / 同模型 / 同 prompt / 同判分 | 已有约定：**Neo4j `:Chunk` 节点是唯一 chunk 池**（图侧经 `-MENTIONS->(:Entity)` 反查，上限硬编码 `_EVIDENCE_CHUNK_LIMIT=32`）；但**没有任何指纹或断言**能证明两侧取的是同一份池 | **无池指纹 ⇒ 「同池」无法被证伪** |
| ② 基线 = dense top-k（**不以 BM25 为主**） | **零向量设施**（全库搜 `embedding/vector/pgvector/faiss` 0 命中） | **完全没有实现** |
| ③ 分数 = 受控问题集答对率（**基线侧也需人工判分**） | 只有图侧 `judgements` 入口 | **无基线侧判分通道** |
| ④ 防刷绿三条（基线分落盘 / `baseline_spec` 进报告 / 反向守卫） | 落款无 spec、无反向守卫 | **三条全缺** |
| ⑤ 归属 = P6 开工第一步，**不进产品路径** | —— | 实现时必须落在评测侧，**不碰 API 契约** |

## 2. 做什么

| # | 动作 | 落点 |
|---|---|---|
| 1 | **`DenseTopKRetriever`**：复用现有 `langchain_openai.OpenAIEmbeddings`（**零新增依赖**，与 `providers/llm.py` 同一 package）+ cosine top-k | 新增 `app/evaluation/baseline.py` |
| 2 | **chunk 池抽干函数**：按 `kg_version` + `org_id` 取全部 `:Chunk`，产出**池指纹**（chunk id 排序后哈希）⇒ 「两侧同池」从口号变成**可证伪的断言** | 同上 |
| 3 | **基线侧问答**：同 `build_chat_model` + 同 `prompts/kg_qa_v5.md` + 同 `k`，产出与 `/api/v1/agent/query` 同形状的 `AnswerRecord` | 同上 + `runner.py` |
| 4 | **双侧判分同一批改**：一次运行对两侧用**同一份 rubric / 同一批 Answers 对象**计ppa分；图侧答案仍来自产品 API（**不重复付 LLM 调用**，与 A6 同源共用一次的纪律一致） | `runner.py` |
| 5 | **`BaselineSpec` 进报告**：检索方式 / embedding 模型与维度 / **池指纹** / `k` / 生成模型 / prompt 版本 / 判分人 | metrics + report detail |
| 6 | **反向守卫**：① `graph_gain` **保号**（负数不得被 `abs()` 抹平）；② 基线侧 `k` **不得小于**图侧；③ 两侧模型 / prompt 版本必须一致 ⇒ 不符即 `INDETERMINATE` + 显式 `regression_warning` | `metrics.py` / `baseline.py` / 测试 |
| 7 | **C_GAIN 换成真 evaluator** 并在 `_register_builtin_criteria` 里替换 `PlaceholderEvaluator` | `runner.py` |
| 8 | **判分通道**：`RunnerContext` 增 `baseline_judgements`；缺侧-unpack ⇒ `UNKNOWN` + 明确 `blocked_by`（**不得静默成 0 或 PASS**） | `runner.py` |
| 9 | 测试（纯逻辑优先）：负增益保号 / 池指纹一致性 / k 反向守卫 / 双侧同源判分 / 缺判分 ⇒ UNKNOWN | `tests/test_eval_baseline_a1.py` |
| 10 | **反向验证**（逐条）：把负增益取绝对值、偷换 prompt 版本、缩小基线 k、两侧换池 ⇒ 各自判红 | 临时脚本 + 日志登记 |

## 3. 不做什么（**本批边界 = Non-goals**）

1. **不调 C1 的 10% 阈值**（TBD-7 未校准，归阶段 ⑤），也不给裸 PASS——阈值来源仍按规则标注。
2. **不动 C2-a / C2-b / C2-c 既有口径**（含 A6 刚定的两档输出与 `refusal_false_refusal` 的 0 阈值）。
3. **不做 L2 端到端**（阶段 ③ 另批）；本批语料层显式标 `corpus_layer`。
4. **不改 API 契约**：基线**不新增端点、不改 `AgentQueryRequest`**（⇒ 契约零 diff，`export_openapi.py --check` 仍绿）。
   基线实现落在 `app/evaluation/` 内部，**不进 `app/services/agents.py` 的产品路径**（L10-A1 条款 5）。
5. **不改 `app/services/graphs.py` 的既有检索行为**（不替换 `-EVIDENCE_CHUNK_LIMIT` 那条链路）。
6. **不新增第三方依赖**：embedding 走现有 `langchain-openai` 的 `OpenAIEmbeddings`（同 ChatOpenAI 一个 package）。
7. **不给 CI 加 C1 门禁**：它吃 LLM（双侧 ⇒ 双倍调用）⇒ flaky，沿用 P0-m6-eval §「B 类不进 CI」的裁决。
8. 不顺手修 `ingest_attendance_policies.py` 的 GOVERNED_BY 连边问题（另一条线，只登记）。

## 4. 出口判据

1. `pytest` **passed 不减**（930 ⇒ ≥930，新增 ~12）；
2. 新增断言**逐条反向验证判红**；
3. **真链路实测**：起后端 + 起 embed endpoint 跑一次 `--live --criteria c1_graph_gain`
   出真值两侧分数 ⇒ 若 embed endpoint 或 ready kg_version 拿不到，**如实登记「未实测 + 卡在哪一步」**，
   **禁止拿单测或构造值冒充实测**；
4. `ruff check` / `ruff format --check` / `check_seams` / `export_openapi.py --check` /
   `check_session_drift` S1–S5 全绿（**S3：新增 Settings 字段须同步 `.env.example`**）。
