# P6-F · 集成日志（解锁 C1 图谱增益）

> **日期**：2026-10-05 ｜ **边界文档**：`47c140c9`（第一步，只写文档）
> **embedding 方案**：**S-b 本地薄服务**（本机 CPU / ONNX Runtime，**无 torch**）——用户已拍板
> **一句话结论**：`c1_graph_gain` **首次出数 = 0.0909**（图谱 12/14 vs 基线 11/14）
> ⇒ 阈值 10% ⇒ **FAIL（provisional）**。跑 **3 遍数值完全一致**，`corpus_layer = L2`。

---

## 1. 为什么这一次能出数（三条依赖逐条打通）

| C1 的依赖 | 打通前 | 本批 |
|---|---|---|
| ① embedding（dense top-k 基线） | DeepSeek `/embeddings` = **404**；本机 11434/8000/8080 全 closed | 本地 OpenAI 兼容 `/v1/embeddings` 服务（**512 维**，BGE-small-zh） |
| ② **双侧独立人工判分** | 无判分表；且脚本连「要判什么」都摊不出来 | 两张各 14 题的表，按 `rubric-v1` 判 |
| ③ 可比性前置断言 | 代码已有，此前从未跑过 | 实跑 `comparability_error() = None`（§4） |

### 1.1 embedding 落地的三个坑（均已写进脚本 header / 注释，可复现）

1. **`huggingface.co` 直连超时** ⇒ `HF_ENDPOINT=https://hf-mirror.com`；
2. **HF 的新 xet 存储在未登录时 401**（`cas-server.xethub.hf.co`）⇒ `HF_HUB_DISABLE_XET=1`；
3. **`langchain_openai` 默认把文本切成 token id 数组再发**（`check_embedding_ctx_length=True`），
   OpenAI 自家服务认这个格式，**OpenAI 兼容网关普遍不认**（本地服务直接 `422`）⇒ 已关掉。
   副作用是**更安全**的：原本超长文本会被 langchain **静默跳过** ⇒ 返回条数变少，
   而 chunk_id 按位置对齐 ⇒ **整批向量错位**；关掉后少条数会由 `EmbedderUnavailable` 显式炸出来。

权重（94.8 MB 的 `model_optimized.onnx`）进入本地 HF 缓存后，服务可 `HF_HUB_OFFLINE=1`
**完全离线**启动 —— 这正是 S-b 想要的：**模型版本钉死、历史可比、不依赖外网**。

## 2. C1 首个数字（**跑 3 遍，逐遍记录**）

| 遍次 | value | graph | baseline | corpus_layer | verdict |
|---|---|---|---|---|---|
| final | **0.09090909** | 0.8571（12/14） | 0.7857（11/14） | **L2** | FAIL |
| rerunA | **0.09090909** | 0.8571 | 0.7857 | **L2** | FAIL |
| rerunB | **0.09090909** | 0.8571 | 0.7857 | **L2** | FAIL |

- 定义见 `metrics.graph_gain` = `(图谱 − 基线) / 基线`：`12/14 ÷ 11/14 − 1 = 9.09%`；
- 阈值 **10%**，`threshold_source = provisional`（**未校准，属阶段 ⑤ TBD-7**）；
- `graph_judged = 14, baseline_judged = 14` ⇒ 两侧都真判了，不是靠某侧缺省凑分母；
- `regression_warning = null`（图谱未反超 ⇒ 保号守卫未触发）。

### ⚠️ 灵敏度警告（**必须和数字一起念**）

14 题 ⇒ **单题翻转 = ±7.1 个百分点**，而本判据离阈值只差 **0.9 个百分点**。
§5 里任意一题改判（尤其 #7 那种苛刻要点），结论立刻从 FAIL 变 PASS。
⇒ 这个数字只能表述为「**在本次演示语料、本自建基线、本判分下表观未达标**」，
**不能**当作 MVP 准入线的结论。

## 3. 反向验证 2 次（**故意破坏，确认拦得住**）

| 变异 | 期望 | 实测 |
|---|---|---|
| `EVAL_EMBEDDING_BASE_URL` 指向不存在的端口 | **不许**退化成关键词出一堆数 | ✅ `value=None / INDETERMINATE`，`blocked_by = 基线侧不可用：… APIConnectionError('Connection error.')` |
| 两侧判分表指向**同一个文件** | 拒绝执行（A1 裁决 3） | ✅ `distinct_judgement_tables` 判红 ⇒ 守卫在位 |

⇒ L10-A1 的「不许刷绿」条款与 A1 裁决 3 **都是活的，不是写在文档里的摆设**。

## 4. 唯一变量是否真的成立（T4.3）

| 项 | 图侧 | 基线侧 | 结论 |
|---|---|---|---|
| `retriever` | `graph_mentions` | `dense_top_k` | ✅ **这就是被测的那一个变量** |
| `pool.fingerprint` | `e36322bb2d86865f`（size 213） | 同 | ✅ 同一个 chunk 池 |
| `top_k` | 32 | 32 | ✅ |
| `generation_model` | `deepseek-chat` | 同 | ✅ |
| `prompt_id` | `kg_qa_v5` | 同 | ✅ |
| `graph_context` | true | false | ✅ 随变量而变，符合预期 |

⇒ `comparability_error()` 返回 `None`，可比性成立。

## 5. 判分（A3：两侧两张表，由人判）

rubric = `data/eval/MANIFEST.json` 的 **`rubric-v1`**：
①拒答判定与 `should_refuse` 一致；②覆盖 `expected_points` 的**全部**要点；③无与语料矛盾的事实；
未判分 ⇒ `null`（不入分母，不是 0）。

| 题 | 图侧 | 基线侧 | 判罚依据 |
|---|---|---|---|
| #1 #2 #3 #4 #6 #8 #9 #10 #11 | ✅ | ✅ | 要点全覆盖 |
| #5 | ❌ | ❌ | 缺要点「依据劳动法第四十一条」（只答了 36 小时） |
| #7 | ❌ | ❌ | 缺要点「已履行审批」（只答了不定时工作制） |
| #12 | ✅ | ❌ | **基线侧拒答**（`INSUFFICIENT_CONTEXT`）⇒ 违反 rubric ①，要点也全缺 |
| #13 #14 | ✅ | ✅ | 库外题正确拒答（rubric ①） |

⇒ 图侧 12/14，基线侧 11/14。两份判分表是**独立文件**（`--judgements` 与
`--baseline-judgements`），且各自携带 `_rubric / _judged_by / _note` 以便事后复核。

**为了让判分有凭据**：本批给 `AnswerRecord` 加了 `answer_text`，并在缺判分时把两侧原文
摊进报告的 `awaiting_graph / awaiting_baseline` —— 此前人只能对着 `refused` 与
`citations` 计数判分，等于盲判，事后也无法复核某题当初答了什么。

## 6. 根因**未修**的缺陷（**如实登记，本批不动**）

| # | 缺陷 | 为什么本批没修 | 风险面 |
|---|---|---|---|
| **D1** | 产品侧 `AgentService._invoke_chat_with_retry` 直接用 `self._chat`，**从不**调用幂等的 `_ensure_chat()` ⇒ **任何绕开 HTTP 路由的调用**都会 `AttributeError: 'NoneType' object has no attribute 'ainvoke'`，且它不是 `AgentUnavailableError` ⇒ 上层读不出真因（本批撞到时报告只显示三题 `AttributeError`） | Non-goals 第 6 条：不动被测链路 ⇒ 只在评测侧显式补 `_ensure_chat()`，让失败至少以可读的 `blocked_by` 呈现 | 任何脚本 / worker / 后台任务直接调 `AgentService` 都会踩 |
| **D2** | `BaselineSpec.embedding_dimension` **恒为 None**：spec 构造早于首次 embed ⇒ 报告里看不到向量维度 | 需要改 spec 的构造时机，超出本批范围 | 「换了嵌入模型能被发现」这条防线目前是空的（只能在服务 `/health` 侧看到 512） |
| **D3** | **判分跨 run**：判分表针对第 N 次生成的答案，而出数发生在第 M 次 ⇒ 两者理论上不是同一批答案实例 | LLM 无 temperature 配置可锁定；本项目既有 A3 流程本就是「先生成后判分」 | 本批 3 遍一致说明当前漂移为 0，但**这不是保证**；每次复测都应重新判或至少核对答案原文 |
| 既有 | H6 引用回溯 403（`no_role_assignment`）、制度入图器「条款数一致」自检多文档恒 FAIL、P7-B readiness 静默 skip 盲区 | Non-goals 第 8 条 | 未动，仅登记 |

## 7. 改动清单（含 3 处边界外，逐一登记）

| 文件 | 改动 | 属边界内？ |
|---|---|---|
| `scripts/local_embedding_server.py` | **新增**：OpenAI 兼容 `/v1/embeddings` + `/health`，`lazy_load`、`--cache-dir` 复用 HF 缓存 | ✅ S-b 本体 |
| `pyproject.toml`（dev group） | `fastembed`；连带 onnxruntime / tokenizers / numpy 等，**无 torch** | ✅ 已承诺只进 dev |
| `scripts/eval_acceptance.py` | `--baseline-judgements` + 同源守卫 + 判分文件允许元信息键 | ✅ T3 |
| `app/evaluation/metrics.py` | `AnswerRecord.answer_text`（默认空 ⇒ 既有构造点全不受影响） | ✅ 判分留证 |
| `app/evaluation/runner.py` | `_to_answer` 带原文；缺判分时摊出两侧原文 | ✅ 判分留证 |
| `app/evaluation/baseline.py` | `check_embedding_ctx_length=False`；`agent._ensure_chat()` | ⚠️ 后者属 **D1 的缓解**（未改产品侧） |
| `tests/test_eval_judgements_cli.py` | **新增 4 条** | ✅ |

## 8. 门禁数字

```
pytest（真 Neo4j / PG + app_rls）   963 passed / 3 skipped / 3 xfailed   ← 基线 959 ⇒ +4，0 回归
ruff check .                        All checks passed!
ruff format --check .               232 files already formatted
check_seams.py                      [OK] 接缝纪律通过
export_openapi.py --check           [OK] 契约零 diff
```

## 9. 收尾三问（自答）

1. **有没有"顺便做的"？** 三处，全部显式登记:

   - `AnswerRecord.answer_text` + 摊出待判答案 —— 不加的话 A3 判分等于盲判，C1 的数字无法复核；
   - 判分文件支持元信息键 —— 否则判分表不可自解释；
   - `check_embedding_ctx_length=False` —— 不加的话本地服务直接 422，且存在向量错位风险。
     **没碰**：H6 403、制度入图器自检、P7-B、D1 的产品侧根因。
2. **有没有为躲坑而绕路的实现？** 有，且已登记：**D1 只在评测侧补装配，没有改产品侧**。
   这是本批最值得被质疑的一处 —— 若后续别的调用方直接调 `AgentService`，还会再炸一次。
   登记它的理由写在 §6：改产品链路属被冻结的边界，且本批目标是出数，**不是为了绕开**。
3. **真跑还是读代码？** 全部实测：3 遍 C1 live（真图 + 真 LLM + 真 PG + 真 embedding 服务）、
   1 次反向验证、服务端向量冒烟（512 维 / 两次一致 / 已归一化），
   两侧 14 题答案均为真机生成并按 rubric 人工判分。

## 10. 话术约束（对外必须照此表述）

> **C1 图谱增益当前测得 9.09%（阈值 10%，阈值未校准）⇒ 表观未达标。**
> 限定语一个都不能省：**演示语料、自建 dense top-k 基线（非客户现有系统）、
> 受控题集 14 题的 `rubric-v1` 判分、`corpus_layer = L2`、未校准阈值 ⇒ provisional。**
> 14 题意味着**单题翻转 = ±7.1 个百分点**，而它离阈值只差 0.9 ⇒
> **不得据此宣称 MVP 准入达标或不达标**，终局需全量语料 + gold 扩标 + 阈值校准（阶段 ⑤）。
