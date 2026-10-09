# P6-S · 集成日志（A1 向量基线 + 双侧出卷：**让 C1 的分母可判**，判分仍归 P6-T）

> **日期**：2026-10-09 ｜ **边界文档**：[`proposal.md`](./proposal.md)（Non-goals **10 条**）
> **计划真源**：[`docs/delivery-plan.md` §9.2 队列第 2 项](../../docs/delivery-plan.md)
> **一句话**：把 C1 从「不知道被什么挡住」推到「**两侧 40 题答卷齐了、双侧共因清单机器可读、
> 只差人工判分**」。
>
> **≡ 引用本批结论时的硬前置**：本批**没有新增任何判据数字**——两趟 live 报告的
> `value` 都是 `None`。新增的是「**判分之前**就能看懂两侧怎么比」这件事。
> 出数 ≠ 达标：C1 的分数在 **P6-T（纯人工判分）** 之前不存在。

---

## 1. 本批做了什么（四件，全部可复跑）

| # | 产物 | 花费 |
|---|---|---|
| ① | **第一趟 `--live --criteria c1_graph_gain`** ⇒ 查实 D1 + 出卷（`p6s-c1-01.json`） | 40 HTTP + 40 基线 LLM |
| ② | **代码改动 2 处**（`runner.py` 重排闸门 / `_load_judgements` 严格布尔）+ 一处文案订正 | ¥0 |
| ③ | **新增 1 个脚本 + 8 条单测**（导出 4 条 / 判分值 2 条 / C1 闸门 2 条） | ¥0 |
| ④ | **第二趟 `--live`** 取证（`p6s-c1-02.json`）+ 导出判分材料 | 40 HTTP + 40 基线 LLM |

> **Non-goals 第 2 条核销**：全流程一次都没让脚本算过「对 / 错」。

## 2. 开工自检（结论只来自脚本）

| 项 | 读数 | 与 §7 基线 |
|---|---|---|
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** | 一致 |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** | 一致 |
| `export_openapi.py --check` | **零 diff** | 一致 |
| `gh run list --limit 1` | run **37890683002** completed **success**（commit `101773e7`） | 起点绿 |
| `tests/test_eval_baseline_a1.py`（改动前） | **20 passed** | 一致 |
| 容器 | `graphrag-neo` / `graphrag-pg` 均 Up | — |

## 3. ⚠️ 环境事实：上一批留下的后端是**旧进程**

- `127.0.0.1:8002` 上的 uvicorn **启动于 13:33:13**，而 P6-R 的 `temperature=0` 提交在 **13:46:03**
  ⇒ 它跑的是**钉采样之前**的旧代码。直接复用会让两侧与 P6-R 的读数**不同源**（D4 当场失守）。
  **处置**：杀掉重启。
- `127.0.0.1:8009` **未监听** ⇒ 本地 embedding 服务没起（同 P5-B §3 第 4 条的环境债）。
  **处置**：起 `scripts/local_embedding_server.py --port 8009`，冒烟 **dim=512 / n=2**。

> 这两条不处理的后果不是报错，而是**静默**：第一趟跑出来的要么是旧采样、要么是「embedding 未配置」，
> 报告照样落在盘上、看着一样完整。

## 4. D1 查实：C1 的阻塞项**不是**「基线协议没建」

`blocked_by` 原文（`reports/eval/p6s-c1-01.json`，`git_hash=101773e7`）：

> `A3：图侧没有一题被人工判分（用 --judgements 提供）；脚本不自动判分 ⇒ 不判就等于没跑`

同一趟证明两侧**都能出数**：

| 侧 | 条数 | 拒答 | 说明 |
|---|---|---|---|
| `awaiting_graph` | **40** | **4** | 与 P6-R 的 `asked=40 / answered=36 / refused=4` **逐位一致** ⇒ 同源性初步成立 |
| `awaiting_baseline` | **40** | **9** | dense top-k 真的召回并生成了作答（不是 fixture、不是空表） |

⇒ `dev-doc-status.md` A1 行那句「`BaselineRunner` 协议**并未建立**（`backend/` 内**零匹配**）」
**已过期**：`app/evaluation/baseline.py` **494 行**在库里，且基线侧跑出了真实答案。
同一过期口径的第二落点（`runner.upgrade_todo()` 的「需要 RAG 基线检索的定义与实现（A1 待裁决）」）
一并订正为「需要两侧各 40 题的**人工判分**（A3：脚本不代判 ⇒ P6-T）」。

## 5. 本批真正修的缺陷：「不可比」要等判完 80 题才暴露

**改动前**的顺序（`graph_spec` / `baseline_spec` 与 `comparability_error` 全排在图侧判分闸门**之后**，
`runner.py:1059` 就 return 了）：

```
mode → _qa_run(40 题 HTTP) → 判分闸门(return) → … → 可比性断言 → 出数
```

三个后果：① 两侧到底可不可比，在人工判分完成前**一个字都看不到** ⇒ 「判完才发现不可比」会让
80 道人工全部作废；② D3 的防刷绿证据当时一条都拿不出来；③ 即便不可比，也照样把 40 次 LLM 的基线侧跑完。

**改动后**：

```
mode → _qa_run → 【双侧 spec + 可比性断言】 → 判分闸门 → 基线侧(付费) → 出数
```

- 缺判分时**照旧不给数字**（`value=None`），但 detail 带上 `graph_spec` / `baseline_spec`；
- 不可比 ⇒ **在此即返回**，不再付钱跑基线侧；
- `embedder is None` ⇒ 显式返回「embedding 未配置」（原本靠下游兜底，重排后会踩空指针）。

**第二趟实测**（`p6s-c1-02.json`，`value` 仍 `None`）：

| 读点 | 图侧 | 基线侧 | 判读 |
|---|---|---|---|
| `pool.fingerprint` / `size` | `e36322bb2d86865f` / **213** | 同左逐字 | **同一池**（A1 条款 1 ①） |
| `top_k` | **32** | **32** | 基线侧**不小于**图侧 ⇒ 反向守卫 ② 通过 |
| `generation_model` | `deepseek-chat` | `deepseek-chat` | 同源 |
| `prompt_id` | `kg_qa_v5` | `kg_qa_v5` | 同源 |
| `graph_context` | `True` | `False` | 唯一变量 = 检索方式，没被淹没 |
| `retriever` | `graph_mentions+lexical_rerank` | `dense_top_k` | 与 A1 裁决一致（非 BM25） |

⇒ **两侧可比**。这条结论在改动前**拿不到**——报告里根本没有 spec。

**残留（如实登记，不在本批洗白）**：`baseline_spec.embedding_dimension` 仍为 `null` ——
spec 在 `answer_with_dense` **之前**构造，那时还没发生过 embed ⇒ 维度未知**而猜出来的更糟**；
`embedding_model` 已落地，不影响可比性判定。`as_of_date` 走 `db=None` 口径的残留同上批
（演示语料全部无 `document_date`）。

## 6. T4：判分表的「值」也要报错

`_load_judgements` 原本做 `bool(value)`：

- `bool(None)` = **False** ⇒ 一张**没判完**的表（留 `"7": null`）会把未判的题**静默判成答错**；
- `bool("false")` = **True** ⇒ 写成字符串时字面写反了也照样被当成答对。

两者都是「表格看着正常、答対率已经是假的」，且与同一函数里既有的「非题号键不许静默通过」
是同一条防线——这次防的是**值**。改为只收真正的 `True/False`，其余报错点名题号。

## 7. T5：把两侧答卷定格成 P6-T 的输入物

`scripts/export_judging_sheets.py`（新增）⇒ `backend/data/eval/judging/c1-sheets-20261009T064241Z.json`：

- 两侧各 **40 题**，补齐了报告里**没有的题干与 rubric 锚点**（`expected_points` / `secondary_points` / `should_refuse`）
  ⇒ 人拿到就能判；
- 落在 `data/eval/judging/`（**跟踪入库**），与 gitignore 的 `reports/eval/` 分置——重建这份卷子要再付 **80 次 LLM**；
- 「同一批改分」（A1 条款 3）的可复核凭据：两侧写在**同一个文件**里，并带 `_git_hash` / `_kg_version` / 两侧 spec；
- 产物**不含任何 correct 值**，也**不能**被 `--judgements` 读（顶层键不是纯题号 ⇒ 直接报错）
  ⇒ 不会有人把试题当判分表喂进去。

## 8. 决策登记（D1~D8）

| # | 决策 | 结果 |
|---|---|---|
| **D1** | C1 真实阻塞项 | **判分缺失**（§4）。不是 embedding 缺失、不是协议缺失 |
| **D2** | 完成线划在哪 | **出数不可能**（A3）。完成线 = 两侧答卷齐 + 双侧 spec 进报告 + 三条可贴机器输出；`value` 仍 `None` |
| **D3** | 防刷绿三条 | ② `baseline_spec` 进报告 **本批补齐**；③ 反向守卫 `test_eval_baseline_a1.py` **22 条全绿**（既有 20 条断言**一条未放宽**）；① 基线分落盘通道本就在，待 P6-T 出分 |
| **D4** | 与 P6-R 同源 | 报告 `git_hash=101773e7`（含 T=0）+ 采样未回滚 + 两侧 `generation_model` / `prompt_id` 机器比对同源 |
| **D5** | 过期口径订正 | 已追加三处：`dev-doc-status.md` A1 行、矩阵 §5.1 C1 行、`runner.upgrade_todo()`。**全部只追加不重排（R-5）** |
| **D6** | 判据进不进 CI | **不进**。新增/改动的单测**本来就在 CI**，继续绿 |
| **D7** | 审计 / RBAC | 未动（`PROTECTED_ENDPOINTS` 仍 **10 条**） |
| **D8** | 成本敞口 | 2 趟 ×（40 HTTP + 40 基线 LLM）；每趟都对应一个此前拿不到的结论（§1 表）。**无第三趟** |

## 9. 收尾三问自答

1. **有没有顺便做的东西？** 没有。`upgrade_todo()` 的文案订正属 D5（同一过期口径的第二落点），
   已在 proposal 中列明；`AnswerRecord` / 出数路径 / 阈值 / 既有 detail 字段**一行未改**。
2. **有没有为躲坑而绕路的实现？** 没有。选的是「把守卫提前」而不是「放宽守卫」：
   `comparability_error` 的判定逻辑一个字符没动，被执行时机改了。
3. **验收判据是跑出来的还是读代码得出的？** 判据 1/2/3/4 全部贴 live 报告的**实读输出**（§4 / §5）；
   代码结构类断言（导出物形状、判分值拦截）用单测兜，并在 Q2 里明写是单测而非实测。

## 10. Non-goals 核销（10 条）

| # | 结论 |
|---|---|
| 1 不回滚 P6-R 的 `temperature=0` | ✅ 未触碰 `llm.py` |
| 2 不脚本代判分 | ✅ 导出物无 `correct`，单测锁字段名递归查到最深层 |
| 3 不动题集 | ✅ 未改 `controlled-qset-v4.json` |
| 4 不动 C2-a / C2-b / C2-c 口径 | ✅ 未触碰 |
| 5 不动召回 / 重排 | ✅ 未触碰 |
| 6 不用 BM25 作主基线 | ✅ 连敏感性对照都没跑 |
| 7 不做 L2 端到端 / 演练留证 | ✅ 未做 |
| 8 不动 D4 / Sprint10.5 | ✅ 未触碰 |
| 9 不动前端 | ✅ 未触碰 |
| 10 不新增端点 / 错误码 / `settings.*` | ✅ 无 ⇒ **未触发 S3** |

## 11. 全部门禁（收尾）

| 项 | 读数 |
|---|---|
| `ruff check` | **All checks passed** |
| `ruff format --check` | **270 files already formatted** |
| `export_openapi.py --check` | **零 diff** |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12** |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `pytest`（有图口径：`GRAPH_REAL_NEO4J_*`） | **1154 passed / 3 skipped / 0 failed** = 基线 1146/3 **+ 新增 8 条** |
| `check_session_drift` | S1 读到 **10 条** Non-goals；S2~S5 见 §12 |

## 12. `check_session_drift`（实跑输出，五个判据全 OK）

| 判据 | 输出 |
|---|---|
| **S1** | `[OK] changes\P6-S\proposal.md 已登记 10 条边界` ⇒ 开工前边界在场 |
| **S2** | `[OK] 6 个文件 / 新增 168 行`（未超阈值）⇒ 没有一次性摊太大 |
| **S3** | `[OK] 未发现 Settings 字段需要同步 .env.example` ⇒ 没加配置项，确实没触发 S3 |
| **S4** | `[OK] 未改动 schemas / routes 等相关文件` ⇒ 契约不用同步 |
| **S5** | `[OK] 新增模块均已被 app 引用或未新增模块` ⇒ 导出脚本属 `scripts/`，且其消费者是 P6-T 的人工判分流程（本身就在 §13 第 1 条登记），**不是顺手写的** |

## 13. 下一批指针（按实际结果更新）

1. **P6-T：两侧各 40 题人工判分**（A3，**纯人工**）——输入物已就位：
   `backend/data/eval/judging/c1-sheets-20261009T064241Z.json`（题干 + rubric 锚点 + 两侧原文 + 两侧 spec）。
   **两条纪律**：① 两侧判分表**必须是两个文件**（`distinct_judgement_tables` 会机检）；
   ② 值只能写 `true` / `false`（留 `null` 现在会**报错**，不会被静默判成错）。

   **写开场提示词时又查实三条（¥0，机械比对 / 读码所得，直接决定 P6-T 的工量）**：

   | # | 事实 | 对 P6-T 的影响 |
   |---|---|---|
   | ① | **旧判分表不得复用**：P6-J 那轮（rubric-v2，graph 40/40、baseline 34/40）与被判对象逐题比对 ⇒ 图侧仅 **9/40**、基线侧仅 **14/40** 答案逐位一致 | 是**重判 80 题**。MANIFEST 的 `monotonicity_note` 说「换 rubric 只需重判 false 的题（80→11）」——那条只对**答案没变**成立，本批是**答案变了**（P6-R 钉采样后重跑），**不许照它外推** |
   | ② | **C1 与多跳共用同一个 `--judgements`**：受控题集 index 1..40、多跳 index 1..6 | 同一次跑会**题号串台**（判分别人头上）⇒ **必须分开跑、分别给判分文件** |
   | ③ | **多跳侧没有答案导出通道**：`eval_multihop_accuracy` 缺判分时 detail 只有 `{"asked":6,"judged":0}`，**不吐答案原文** | 人无从判 ⇒ P6-T 要么补导出通道（照 `export_judging_sheets.py` 扩到多跳），要么只判 C1、多跳推下一批。**这条需裁决** |

   另：**历史 4 轮判分表（p5b / p6f / p6h / p6j）都落在被 gitignore 的 `backend/reports/eval/`**
   ⇒ 判分是 A3 的核心资产却未受版本控制。建议 P6-T 把判分表落 `backend/data/eval/judging/`（跟踪目录）。
2. **P6-U：D4 / Sprint10.5 收口**（知识时效 L2 ②③），同批更正两处过期口径：
   `delivery-requirements-and-guardrails.md` DR-D7 仍写「⏳ 未做」、`delivery-plan.md` P5 出口判据③ 未标已达成。
3. **P6-V：P5-J（M6 剩余读路径）** ⇒ 解开 C3-a / C3-b 的 `BLOCKED`；
   后续顺序 P6-W → P6-X（演练留证，**独立环境 + 双人**）→ P6-Y（L2 端到端）→ P7-B → **P8-Release**（tag `v2.0.0`）。
4. **P6-R 遗留未闭合项**：T=0 下**重新入图**后的 C2-a / C2-b gold 命中**未端到端验证**（P6-R 以图外探针 + 机械论证替代）。
5. **本批新增的遗留项**（顺延，不属本批）：
   - `baseline_spec.embedding_dimension` 恒为 `null`：要落地就得把规格构造挪到**首次 embed 之后**
     （或让 `DenseTopKRetriever` 回填维度）⇒ 属「报告信息完整度」，**不影响可比性判定**，建议与 P6-T 一并处理；
   - 本地 embedding 服务（8009）与后端（8002）的启停没有脚本化 ⇒ 每批开工都可能重复踩 §3 的两个坑。
6. **R27**（注入层 93%）：保持挂起。**R30**（引用口径残留）：P6-P1 登记。
7. **`alert` 表 + 限流超阈值联动**（P2）：**已连续多批**有意不做。
</content>
