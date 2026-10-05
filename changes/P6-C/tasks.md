# P6-C · 任务清单

> 顺序即执行顺序。每条做完即勾选。

## T1 · 边界与现状勘察

- [x] 读 L10-A1 裁决条款全文（`changes/P0-m6-eval/integration-log.md:491-519`）
- [x] 实读 M3 检索链路：无向量召回；候选 = 实体集合 → `MENTIONS` 反查 `:Chunk` → 确定性排序
- [x] 确认 chunk 池唯一落点 = Neo4j `:Chunk` 节点（PG 无 chunks 表）
- [x] 确认零向量设施；确认现有依赖 `langchain_openai` 已带 `OpenAIEmbeddings`（零新增依赖）

## T2 · 边界文档

- [x] `proposal.md`（含 8 条 Non-goals）
- [x] `tasks.md`（本文件）

## T3 · 新模块 `app/evaluation/baseline.py`

- [ ] `ChunkRecord` / `ChunkPool`（含 `fingerprint`）
- [ ] `load_chunk_pool(kg_version, org_id)`：只读 Neo4j，按 `char_start` 定序
- [ ] `Embedder` 协议 + `OpenAICompatibleEmbedder`（复用现有 langchain-openai）
- [ ] `DenseTopKRetriever.retrieve(question, pool, k)`：cosine top-k，同分按 `char_start` 升序
- [ ] `BaselineSpec` 冻结数据类：检索方式 / 嵌入模型 / 维度 / 池指纹 / k / 生成模型 / prompt 版本 / 判分人

## T4 · `metrics.py` 的保号与可比性守卫

- [ ] `graph_gain` 保号（现状已保号 ⇒ 用测试钉住，禁止将来被取绝对值抹平）
- [ ] `assert_comparable(graph_spec, baseline_spec)`：两侧模型 / prompt 版本 / 池指纹须同；
      基线 k 不得小于图侧 ⇒ 不符返回 reason

## T5 · `runner.py` 换成真 evaluator

- [ ] `RunnerContext` 增 `baseline_judgements`
- [ ] `eval_graph_gain`：双侧同批改分 → `graph_gain(...)`；负增益进 `detail.regression_warning`
- [ ] `_register_builtin_criteria` 用真 evaluator 替换 `PlaceholderEvaluator`
- [ ] 缺判分 / 链路不通 ⇒ `UNKNOWN` + `blocked_by`（不得静默成 0 或 PASS）

## T6 · 配置与模板

- [ ] `Settings` 新增 embedding 相关字段（每项都要有消费者代码行，R-7）
- [ ] `.env.example` 同步（S3 会拦）

## T7 · 测试与反向验证

- [ ] `tests/test_eval_baseline_a1.py`：以纯逻辑为主
- [ ] 反向验证逐条：负增益取绝对值 / 换 prompt 版本 / 缩小基线 k / 两侧换池 / 缺判分当 PASS，各自判红

## T8 · 真链路实测

- [ ] 起后端 + ready kg_version + embedding endpoint ⇒ `--live --criteria c1_graph_gain`
- [ ] 跑不通则如实登记「未实测 + 卡在哪一步」（禁止用单测或构造值冒充）

## T9 · 门禁与提交

- [ ] pytest passed 不减 / ruff / format / seams / openapi / drift S1–S5
- [ ] 收尾三问写进 `integration-log.md`
- [ ] Conventional Commits 提交
