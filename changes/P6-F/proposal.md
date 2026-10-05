# P6-F · 解锁 C1 图谱增益（embedding 接通 + 双侧判分，**首次出数**）

> **日期**：2026-10-05 ｜ **状态**：第一步（**只写文档，不改代码**）
> **判据**：`c1_graph_gain`（阈值 **10%**，provisional）｜ 当前 **UNKNOWN（blocked_by = 缺 embedding）**
> **上游**：④ P6-E（`8e7d88b6`）让 `\agent/query` 与演示图可用 ⇒ C1 的链路侧阻塞已解除

---

## 1. ⚠️ 先订正我上一轮的建议

我上一轮说「**先补 embedding 解锁 C1**」。**这句话只对了一半**，本批先把话说全：

| C1 出数的必要条件 | 现状 | 归属 |
|---|---|---|
| ① **embedding 可用**（dense top-k 基线） | ❌ 缺 | **外部依赖，需用户拍板**（见 §5） |
| ② **双侧独立人工判分**（图侧 + 基线侧各一份） | ❌ 未做 | 本批任务 T4 |
| ③ 唯一变量 = 检索方式（同 chunk 池 / 同 k / 同生成模型 / 同 prompt / 同判分rubric） | ✅ 代码已就位（`comparability_error()` 运行时复判） | 已有 |

⇒ **只补 embedding，C1 照样出不了数**（会卡在"无已判分答案 ⇒ INDETERMINATE"）。
② 的依据：`RunnerContext.baseline_judgements` 的注释（A1 裁决 3）——
**两侧共用一张判分表 = 替基线"预设答案"，增益失去意义**。

## 2. 已核实的事实（**逐条可验，不是推断**）

| # | 事实 | 验证方式 |
|---|---|---|
| F1 | `EVAL_EMBEDDING_BASE_URL / _API_KEY / _MODEL` 三个配置项**已存在**；`_MODEL` **刻意无默认值**（注释：嵌入模型与对话模型必然不同，给默认值会把错误推迟到跑数据那天） | `app/core/config.py:57-67` |
| F2 | 消费者唯一落点 `baseline.py::build_default_embedder` → `OpenAICompatibleEmbedder`（用已在依赖里的 `langchain_openai`，**零新增主依赖**） | `baseline.py:164-241`；实测 `OpenAIEmbeddings` 可导入 |
| F3 | 失败模式是 **抛** `EmbedderUnavailable`，**不许**静默退化成关键词检索（注释写明：退化 = 把 dense 悄悄换成 BM25 ⇒ 中文长文档偏弱 ⇒ 增益虚高 ⇒ **刷绿**） | `baseline.py:52-57` |
| F4 | **现有 DeepSeek key 用不了**：`POST https://api.deepseek.com/embeddings` ⇒ **HTTP 404** | 本批实测（2026-10-05） |
| F5 | 本机**没有任何**本地推理服务：11434 / 8000 / 8080 / 5000 / 9997 **全 closed** | 本批实测 |
| F6 | **CLI 缺口**：`scripts/eval_acceptance.py` 只有 `--judgements`（图侧），**没有基侧判分入口** ⇒ `baseline_judgements` 目前只能靠 Python API 传 | 本批核实；属本批要补的一处（T3） |
| F7 | C1 报告要写 `corpus_layer`（P6-D 已给 C1 接上），本批出数时须一并核对层号是否 L2 | `runner.py` C1 provenance |

## 3. embedding 来源：三条路的取舍（**待用户拍板**，§5）

| 方案 | 需要什么 | 代价 | ⚖️ 对 C1 的影响 |
|---|---|---|---|
| **S-a** 云端 OpenAI 兼容 embeddings 网关 | 一个 key（哪家由你定） | 零代码改动，只填 `.env` 三行 | ⚠️ 云端模型可能**静默换版本** ⇒ 今天的增益值三个月后不一定能比 |
| **S-b（推荐）** 本地起**薄 wrapper**服务，暴露 OpenAI 兼容 `/v1/embeddings`（模型走 CPU/ONNX，不引入 torch） | 新增 **dev-only** 依赖 + 一次模型下载 | 一个 `scripts/` 下服务脚本 | ✅ 模型版本**钉死** ⇒ 历史可比；离线可复现；被测链路**零侵入** |
| **S-c** 本地 `sentence-transformers` + torch 全家桶 | 同上 + torch | Windows 下 **~2–3GB** 依赖 | 同 S-b，但依赖太重，与项目"轻量 + 少依赖"倾向冲突 |

**为什么 S-b 比"新写一个 Embedder 类"好**：走 HTTP 兼容端点 ⇒ 现有
`OpenAICompatibleEmbedder` 一行不用改，服务进程像 Neo4j / PG 一样属**外部基础设施**，
评测侧不需要知道它是本地还是云端。

## 4. Non-goals（**边界先定死，不许边写边定**）

1. **不许因为 embedding 缺失就退化成关键词 / BM25 检索** —— L10-A1 明写那是**刷绿**（中文长文档上关键词偏弱 ⇒ 增益虚高）；宁可 `UNKNOWN` 也不假出数；
2. **不许给 `eval_embedding_model` 编一个默认值** —— 现有"刻意无默认值"是护栏，填一个好看的默认值就是把它拆了；
3. **双侧判分不许共用一张表**（A1 裁决 3）；
4. **不许拿本批的 C1 实测去倒推改阈值** —— 阈值校准属阶段 ⑤ TBD-7，本批只出数、不校准；
5. **不许为让 C1 达标而挑题 / 改题集 / 改 `top_k`**（`eval_baseline_top_k` 有下限守卫：不得小于图侧 `EVIDENCE_CHUNK_LIMIT`）；
6. **不改被测链路**：`agents.py / graphs.py / prompt`，embedding 属评测侧基础设施；
7. **不进主依赖**：任何新增依赖只落 **dev / extras**，并在本文登记；
8. **不顺手修**在案的其他项：H6 引用回溯 403、制度入图器「条款数一致」自检恒 FAIL、P7-B readiness 静默 skip 盲区 ⇒ 只登记。

## 5. 需要用户拍板的唯一事项

> **embedding 用哪家 / 哪种？**（S-a 云端 key / S-b 本地薄服务 / S-c torch 全家桶 / 暂不动）
>
> 我的默认推荐 **S-b**：判据值要**跨时间可比**（今天测的 10% 要能和下次比），
> 云端模型静默升级会让这个判据失去意义；且不依赖外网。
> 代价是**新增一个 dev-only 依赖 + 一个脚本**，故须你点头。

## 6. 任务

| 任务 | 内容 | 出口证据 |
|---|---|---|
| **T1** | 接通 embedding：按拍板方案配置 `EVAL_EMBEDDING_*`；冒烟——单次 embed 成功、**维度固定**、同一输入两次结果一致 | 冒烟记录（含模型 id / 维度） |
| **T2** | **反向验证**：把 `base_url` 指向不存在的端口 ⇒ 必须是 `UNKNOWN + blocked_by`，**不许**退化成关键词出一堆数 | RED 记录 |
| **T3** | 补 CLI 缺口 `--baseline-judgements`（F6），并两侧的 `--judgements` 各其结节 + 1 条测试 | CLI help 有该参数 + 测试 |
| **T4** | 生成**双侧答案**等比对这些（图侧 vs dense 基线），产出判分表**草稿**交用户确认（A3：脚本不自动判分） | 14 题 ×2 侧答案 + 判分草稿 |
| **T5** | 带两份判分表跑 C1 ⇒ **首个数字**（并记录 `corpus_layer` / 两侧 `retriever` / 池指纹是否一致） | 报告 JSON + 两个数字 |
| **T6** | 日志：记录 C1 首值 + **付出什么代价**（新增依赖 / 一次模型下载 / 跑一轮耗时）+ 双侧是否真做到"唯一变量 = 检索方式" | 集成日志 |

## 7. 出口判据

1. `c1_graph_gain` 首次出现**数值或明确 blocked_by**（不许停在"不知道为什么没有"）；
2. 若出数：报告里能读到 `corpus_layer`（核对为 **L2**）、两侧 `retriever` 不同（graph_mentions vs dense_top_k）、`pool_fingerprint` **两侧一致**（换了池 ⇒ 结论无效）；
3. `comparability_error()` 在实跑中为 `None`（唯一变量成立）；
4. T2 反向验证判红 ≥1 条；
5. 门禁数字照旧（pytest passed **不减** / ruff / format / seams / openapi / drift S1–S5）。

## 8. 已默认采纳项（用户可推翻，均已在本文登记）

| 采纳 | 依据 |
|---|---|
| embedding 走 **HTTP 兼容端点**，而非新增 Embedder 类 | 被测链路零侵入；现有消费者一行不改 |
| 新增依赖（若有）只进 **dev / extras** | 主依赖是被交付物，评测工具不是 |
| embedding 不可用 ⇒ **`UNKNOWN` + 抛出**，不兜底关键词 | `baseline.py` 注释 + L10-A1「不许刷绿」 |
| 双侧判分**各一张表**，不许互相套用 | `RunnerContext.baseline_judgements` 注释（A1 裁决 3） |
| 本批**只出数、不校准阈值** | 阈值校准属阶段 ⑤ TBD-7 |
