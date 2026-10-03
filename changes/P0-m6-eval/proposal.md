# F4 · M6 出口判据（C1–C3）评测方案定稿 + 可运行评测体系

| 项 | 内容 |
|---|---|
| **批次编号** | `P0-m6-eval`（沿用 `P0-m6-*` 命名；上批 `P0-m6-finalization` 已于 2026-10-02 归档，**只读，本批不改**） |
| **对应开口项** | `docs/acceptance-traceability-matrix.md` §5.1 的 **TBD-7**（反证条件 F4 单位成本阈值）；`docs/delivery-requirements-and-guardrails.md` **DR-D10**（MVP 准入线 C1–C3 评测，**评测脚本待建**）；矩阵 **H11 / H12** |
| **对应需求** | **DR-D10**（终局判据） |
| **基线 commit** | **`820e6f57`**（2026-10-02，归档完 `P0-m6-finalization` 后的 origin/main），工作区干净 |
| **为什么现在做** | 用户裁决：M6 暂不急于跑起来，优先级是**系统稳定 + 完整版**。⇒ 本批把**评测体系完整地做出来**（口径 / 数据集 / 执行器 / 报告 / 测试），依赖 M6 端点的判据**先挂占位执行点**，等 `P5-M6` 后灌真实数据；能用现有 M3 检索 / 引用链路自证的维度**现在就真跑**，不留黑箱 |
| **序关系** | 方案 **(a)**（用户 2026-10-02 裁决）：本批 = 评测体系；`P5-M6` = 去 501。二者**不互阻** |
| **状态** | 待开工（2026-10-03） |

---

## 0. 开工前实测（**机器结论，不是读旧文档**）

| 探测量 | 实测方式 | 结果 | 对本批的影响 |
|---|---|---|---|
| M6 实现度 | 上批归档 + `routes/ontology.py` / `routes/cost.py` | **7 个端点仍恒 501**（`_placeholder`） | C3-a 真实值 / C3-b **现在无数据可评** ⇒ 占位 |
| `cost_metrics` 表 | `app/db/models.py` 全表扫描 | **不存在**（M6 §4.3 未落） | 同上；本批**不建表**（属 P5-M6） |
| token 落库情况 | `QaLog` 字段表 + `_record_qa_log` | **`qa_logs` 无 token 列**；token 只进 loguru（`langextract.py` / `agents.py`） | C3-a 真实值不可自证，只做**口径 + fixture 自证** |
| RAG 基线 | 全仓 grep `baseline / rag_only / 纯 RAG` | **无任何基线检索实现** | C1 的**分母不存在** ⇒ 基线只出协议 + fixture，登记 **A1** |
| 既有评测资产 | `scripts/eval_controlled_qset.py` + `tests/test_eval_qset.py` | **已存在且是真实现**：14 问（12 库内 + 2 库外）、`qset=v3-2026-09-30`、`kg_version=attendance-demo-v1`、3 条结构守卫测试 | **不重造**：本批在其之上建统一执行器；**不改**原脚本 |
| M4 疑点链路 | `routes/affiliation.py` | `POST /affiliation/detect` 等 **4 个端点已可用**（演示语料 10 疑点 / 42 证据） | C2-a / C2-b 的**被测链路在**，缺的是 gold 标注集 |
| 多跳遍历 | S10.1 落地 `:RELATION*1..3` | 3 跳遍历已实现 | 多跳答对率**链路在**，缺多跳问题集 + gold |
| 基线测试数 | 上批归档登记 + 本批 E1 实测 | **733 passed / 3 skipped / 7 xfailed**（E1 收尾实测 **777** = 733 + 44；E2 收尾实测 **806** = 777 + 29 ⇒ 与上批登记**对得上**，skipped / xfailed **未变**） | pytest **只增不减** ✅ |
| 数据集是否入库 | 读 `.gitignore` | `backend/data/eval/` **未被忽略** ⇒ 换版有 git 痕迹；而 `backend/reports/` **已被忽略** ⇒ 报告产物不入库（正确） | 数据集放 `data/eval/`，报告落 `reports/eval/` |
| 真机可行性 | 探测 PG / Neo4j | Neo4j **有**演示图（`attendance-demo-v1` **224** chunks / `affiliation-demo-v1` 128），但 **PG 13 张表全为 0 行**（上次 `--rm` 容器消失）⇒ `kg_versions` 无 ready 版本 ⇒ `agent/query` 恒 **501** | ⚠️ 见 §4.4：live 判据本批只能到 `UNKNOWN`，**不重建数据、不拿 fixture 冒充** |

---

## 1. 本批做什么（3 个子任务）

| 子任务 | 内容 |
|---|---|
| **E1** | **指标口径 + 可执行定义**：`app/evaluation/` 指标纯函数（增益 / 召回 / 误报 / 引用覆盖 / 成本）+ **四态状态机** `criteria.py` + 边界单测（空集 / 零除 / 全召回 / 误报为 0 / 并列排序 / 拒答是否入分母） |
| **E2** | **受控问题集（版本化数据）+ gold 标注 + 执行器 + 报告**：`data/eval/` 数据集与 `MANIFEST.json`；`scripts/eval_acceptance.py`（`--offline` 默认 / `--live` / `--criteria` / `--out` / `--compare` / `--calibrate`）；报告 JSON 带 git hash + 时间戳 + 数据集版本 + `provenance` |
| **E3** | **TBD-7 落 config + 判据接线 + 文档回填**：`EVAL_SINGLE_DOC_TOKEN_CEILING` 落 `config.py` 与 `.env.example`（**有消费者**）；矩阵 §5.1 / DR-D10 / `dev-doc-status.md` 回填；**A1–A7 登记项**入档；收尾全量门禁 |

---

## 2. Non-goals（**本批不做**）

- **不实现 M6**：7 个端点去 501 属 **P5-M6**；`cost_metrics` 建表、增量重算、`cost/dashboard` 逻辑**全部不做**
- **不改 `specs/m6-ontology-incremental.md` §1~§6 的实质内容**，**尤其不动 §3.4 的 C1–C3 判据原文**——发现的口径缺陷**一律登记为增补项 A1–A7**（见 §6），由用户在下一批或本节裁决后再改。**这条是硬约束**
- **不动 ADR 原文**（守 `dev-doc-status.md` **R5**：编号只追加、不重排）
- **不改 M6 已定稿的契约字段**：本批**不新增 / 不改任何端点** ⇒ `export_openapi.py --check` 必须**零 diff**，前端 `gen:api` 零 diff
- **不实现产品级 RAG 基线检索**：只出 `BaselineRunner` **协议** + **fixture 基线**，且 fixture 基线**必须标注"非产品基线、仅供评测体系自测"**
- **不删 / 不改既有 `scripts/eval_controlled_qset.py` 及其 3 条守卫测试**（改它 = 动既有行为）
- **不做前端业务改动**（无契约变更 ⇒ 只跑 `gen:api` + `typecheck` + `lint` 确认零 diff）
- **不做 P2 / P2.5 / P3 / P4 / P6** 的任何内容

---

## 3. 决策表（**默认采纳建议项**）

| # | 决策点 | 裁决 | 理由 |
|---|---|---|---|
| **D1** | 「能否自证」怎么表达 | **四态状态机**（`MEASURED` / `MEASURED_PROVISIONAL` / `BLOCKED` / `UNKNOWN`）+ 每值强带 `provenance` | 一句话判断会变成"未完成写成完成"；状态机能被机器判、能被 CI 断言（详见 §4） |
| **D2** | TBD-7 阈值默认值 | **`EVAL_SINGLE_DOC_TOKEN_CEILING = 32_000`**（int，单位 **token/文档**，来源 = 演示语料实测推算，**provisional**）+ **三重防假绿**（详见 §5） | 不用 `None`：`None` = 判据存在但不判，验收时是"既不可 PASS 也不可 FAIL"的死状态，且会被读成"还没配"⇒ TBD-7 永不收敛 |
| **D3** | C3-b（增量/全量比）阈值是否也落 config | **不落** | ① 与 spec §6 的 `COST_RATIO_ALERT_THRESHOLD` 撞名；② **无真实消费者**（无增量重算）⇒ 落了即**幽灵配置**（上批刚犯过）；判定沿用矩阵"显著 < 1.00"，常量写在指标模块内并注明来源 |
| **D4** | RAG 基线怎么办 | **不做实现**，只出协议 + fixture，登记 **A1** | 实现基线 = 新增一条检索路径，属产品能力（P5/P6 议题），在本批做即范围蔓延；且造出的"假基线"会被读成产品能力 |
| **D5** | 受控问题集会不会产生第二真源 | **不改**既有脚本；新数据集 JSON 与 `eval_controlled_qset.QUESTIONS` 之间加**一致性守卫测试** | 复制一份 = 必然漂移（v1→v2→v3 换版已三次栽在这）；守不住的单一真源不如不要 |
| **D6** | 是否拆 Sub-batch | **不拆批**，批内 **E1 / E2 / E3** 三个子任务**分开提交** | 拆批会产出孤儿模块（`check_session_drift` S5）与半截契约；单批分提交即可压住 S2「一次摊太大」 |

---

## 4. 「能否自证」处置方案（**① 的落地**）

> **原则**：把"能否自证"从一句判断，变成**机器可判的状态机**。每个判据 = 一个注册的 `CriterionEvaluator`，输出**四态之一**，而**不是**一个数。

### 4.1 四态定义

| 状态 | 含义 | 报告中的形状 |
|---|---|---|
| `MEASURED` | 真跑出数，且数据集 / 判分口径均已定 | `value=0.93` |
| `MEASURED_PROVISIONAL` | 跑了，但语料 / 基线**非终局**（演示语料、fixture 基线） | `value=0.93, provenance=demo-corpus` |
| `BLOCKED` | 依赖 M6 或 RAG 基线，走占位执行点 | `value=null, blocked_by="P5-M6"` |
| `UNKNOWN` | 口径未定或数据缺失，**不得显示为 0 或 PASS** | `value=null, blocked_by="A2 匹配口径未裁决"` |

### 4.2 三条硬规矩（**防"未完成写成完成"**）

1. **`BLOCKED` 绝不能显示成数字**——`0.0` 会被读成"召回为 0"，直接误触发反证 **F2**。一律 `value=null` + `blocked_by`。
2. **每个值必带 `provenance`**（数据集版本 + 语料 `kg_version` + `offline|live` + git hash）。qset v1→v2→v3 三次换版的教训就是"数字没归因 ⇒ 结论不可比"。
3. **自证要三条全绿才算 `MEASURED`**：① 链路已实现 ② 数据集存在且已标注 ③ 判分口径已定义。缺任一自动降级，且**报告顶部列出"升为 MEASURED 还缺什么"**。

### 4.3 判据 × 依赖 M6 × 能否自证 × 用哪份数据 / 哪个端点（**本批分配**）

| 判据 | 依赖 M6？ | 现在能否自证 | 数据 / 端点 / 脚本 | 本批做到 | 升终局还缺 |
|---|---|---|---|---|---|
| **C2-c** 引用覆盖率 =1.00 | ❌ 否 | ✅ **现在就真跑** | `POST /api/v1/agent/query` + 受控问题集 v3（14 问，既存） | **`MEASURED`**（唯一现在可终局的：结构指标，**不依赖 gold 判分**） | 全量语料（P6） |
| **多跳答对率** ≥0.80 | ❌ 否 | 🟡 半自证 | 同上 `/agent/query`；3 跳遍历已实现（S10.1 `:RELATION*1..3`） | `MEASURED_PROVISIONAL`（新增多跳子集 + gold + rubric） | 全量语料 + gold 扩标 |
| **C1 分子**（图谱版答对率） | ❌ 否 | ✅ 图谱侧可跑 | 同上 | `MEASURED_PROVISIONAL` | 同上 |
| **C2-a** 召回 ≥0.80 | ❌ 否（M4 侧） | 🟡 半自证 | `POST /api/v1/affiliation/detect`（已可用）；演示语料 10 疑点 / 42 证据 | `MEASURED_PROVISIONAL`（新增 gold 标注 v1，同一次运行出两个指标） | gold 扩标 + 全量语料 |
| **C2-b** 误报率 ≤0.15 | ❌ 否（M4 侧） | 🟡 半自证 | 同上（与 C2-a 同源） | 同上 | 同上 |
| **C1 分母**（RAG 基线） | ❌ 否（也不属 M6） | ❌ **不可自证** | 实测：**仓库内无任何基线检索实现** ⇒ 分母不存在 | `BLOCKED`（`blocked_by="baseline-not-implemented"`）+ 协议 + fixture（标注"非产品基线"） | **A1**：基线定义与实现归属待裁决 |
| **C3-a** 单文档成本（TBD-7） | ✅ **是** | ❌ 真实数据不自证 | `cost_metrics` **表不存在**、`qa_logs` **无 token 列** ⇒ token 只进日志 | `BLOCKED`（`blocked_by="P5-M6"`）+ **指标函数用 fixture 真跑**（自证"口径"） | `cost_metrics` 落库（P5-M6） |
| **C3-b** 增量/全量比 | ✅ **是** | ❌ 完全占位 | 无增量重算、无 full rebuild 成本 | `BLOCKED`（`blocked_by="P5-M6"`） | 增量重算（P5-M6） |

> **占位执行点 = 与 P5-M6 的交接面**：占位实现为 `PlaceholderEvaluator(blocked_by=...)`。
> P5-M6 之后**只替换 evaluator 实现**，**不动指标函数、不改报告格式**（交接清单见 §10）。

### 4.4 ⚠️ 实测结论（2026-10-03，**与 4.3 的计划对照**）

计划表里的「本批做到」是**开工前的判断**；下面是**跑完之后的实际情况**——
两者不一致的地方**以实测为准**（这正是"未完成写成完成"最容易发生的地方）：

### 第一次跑（重建数据前）：全部 `UNKNOWN`

| 判据 | 计划（§4.3） | 首次实测 | 差异原因 |
|---|---|---|---|
| C2-c / 多跳 / C1 分子 | `MEASURED*` | **`UNKNOWN`** | 链路不可用：**14/14 HTTP 501**（PG 13 张表行数全 0 ⇒ 无 ready `kg_version`） |
| C2-a / C2-b | `MEASURED_PROVISIONAL` | **`UNKNOWN`** | gold 的 id 空间**写错了**（`supplier_id` 只是节点**属性**，真机输出是图节点 id）⇒ 比对必然 0 命中 ⇒ **不出数** |

### 第二次跑（**重建数据 + id 空间核对后，2026-10-03 终值**）

| 判据 | **实测值** | 状态 | 说明 |
|---|---|---|---|
| **C2-c 引用覆盖率** | **1.00**（11 作答全部有引用；含 span 口径亦 1.00） | `measured_provisional` / **PASS** | 请求失败 0；⚠️ **1 条拒答误伤**（Q8「标准工时制核心在岗时段」期望回答、实际拒答） |
| **C2-a 隐性关联召回** | **1.00**（9/9 逐组命中） | `measured_provisional` / **PASS(provisional)** | 阈值走 provisional：**A8 语料规模不足** ⇒ 达标也**不作 spec 验收结论** |
| **C2-b 误报率** | **0.00**（0 条误报 / 9 条检出） | `measured_provisional` / **PASS(provisional)** | 同上 |
| 多跳答对率 | `UNKNOWN` | — | 仍需**人工判分**（A3，脚本不自动判分） |
| C1 分子 | `UNKNOWN` | — | 同上（走同一批问答） |
| C1 分母 / C3-a / C3-b | `BLOCKED` | — | A1（基线未实现）/ P5-M6（cost_metrics 未落） |

⇒ **三条判据拿到真值，两条仍 `UNKNOWN`（缺人工判分，不是缺链路），三条 `BLOCKED`。**
`UNKNOWN` 与 `BLOCKED` 的 `value` 恒为 `null`，**没有** 0 冒充当中的任何一个。

---

## 5. TBD-7 阈值与三重防假绿（**(b) 的落地**）

### 5.1 默认值与推算依据（**不拍数，算得出**）

```python
# backend/app/core/config.py
# -- 评测准入线（TBD-7 / DR-D10；消费者：scripts/eval_acceptance.py）--
# 单位 = **token / 文档**（**不是**元）。来源 = 2026-10-03 演示语料推算，**provisional**：
#   单次抽取 LLM 调用 1799 tokens（矩阵 §3.4 M2-7 真机） × 约 13 chunk/文档
#   （attendance-demo-v1 = 230 chunks，CSV 派生约占 77%，4 份 docx ⇒ ≈53 chunks）
#   ≈ 23.4k token/文档 × 1.35 余量 ⇒ 取整 32 000。
# ⚠️ **不是达标线**：TBD-7 正式收敛在 P6。须经 `eval_acceptance.py --calibrate` 校准。
eval_single_doc_token_ceiling: int = Field(default=32_000, gt=0)
```

同步写入 `backend/.env.example`（**缺它即 S3 命中**）。

### 5.2 三重防假绿（**开发时必须逐条落实**）

| # | 机制 | 落实点 |
|---|---|---|
| **1** | config 注释写死 `provisional` + 来源 + "非达标线"+ 校准命令 | `config.py` 字段上方注释 |
| **2** | 报告**强制打印** `threshold_source`：`provisional(demo-corpus,2026-10-03)` / `env-override`（`.env` 显式覆盖时）/ `calibrated`（有校准记录时） | `report.py` 每个成本类指标必带该字段 |
| **3** | `--calibrate` 只**输出建议值**（实测 P50 / P90 / 建议 ceiling），**绝不自动改判据**（禁止脚本自己把阈值调松）；`threshold_source=provisional` 时判定标 **`PASS(provisional)`**，并在报告与日志写明「**不构成 TBD-7 收敛证据**」 | `scripts/eval_acceptance.py` + 单测钉住「calibrate 不改 config」 |

> ⚠️ **已知不确定性（照实登记，不粉饰）**：若抽取实际是「每文档一次 LLM 调用」而非「每 chunk 一次」，
> 真实量级会掉到 ~2k/文档，则 32 000 偏松 ⇒ 这正是 `--calibrate` 存在的理由。
> 本批在 `integration-log.md` 登记该假设；**在真实 `cost_metrics` 数据到位前，任何 C3-a 的 PASS 都只算 `PASS(provisional)`**。

### 5.3 为什么不落 C3-b 阈值（D3）

- 与 spec §6 的 `COST_RATIO_ALERT_THRESHOLD`（运行时告警阈值，**尚未落 config**）**语义不同、名字相近**，同批落两个易被后人混用；
- C3-b 当前**无真实消费者**（无增量重算 ⇒ 无 `incremental_cost` / `full_rebuild_cost`）⇒ 落了即**幽灵配置**（上批缺陷 1 的重演）。
- 处置：判定沿用矩阵「显著 < 1.00」，常量写在 `app/evaluation/metrics.py` 内并注明来源；待 P5-M6 有数据后再议是否升为配置。

---

## 6. §1 红线登记项（**只登记，不改 spec §3.4**）

> 评测方案定稿过程中发现的 §3.4 / 矩阵 §5.1 口径缺陷。**一律登记，禁止私下改写 §3.4**。
> 落点：本表 + `integration-log.md` 决策表 + `docs/dev-doc-status.md`（**新编号，不重排**）。

| # | 登记项（口径缺陷） | 本批的**临时**处置（不改 spec） |
|---|---|---|
| **A1** | **C1 的"RAG 基线"未定义**：矩阵 §5.1 只有一句 `(图谱 − 基线)/基线`，未定义基线是什么（纯向量 / BM25 / 同 chunk 池 / 是否重排）。G5 只约束了"同数据集 / 同问题集 / 同标注口径"，**没约束基线本身** ⇒ 增益不可归因 | 出 `BaselineRunner` 协议 + fixture 基线（标注"非产品基线"）；C1 分母 = `BLOCKED` |
| **A2** | **C2-a / C2-b 的匹配口径未定**：正确 / 错误识别的判定是按实体 ID？`canonical_name`？`(head, type, tail)` 三元组？方向是否敏感？如何去重？ | 指标函数**参数化**匹配口径，默认用三元组 + 方向敏感 + 去重，并在报告标注 `match_rule` |
| **A3** | **答对率判分 rubric 未定**：既有纪律是"脚本不做关键词判分"（会假达标），gold 由谁判、怎么判未写死 ⇒ 两次运行不可比 | 数据集 `MANIFEST.json` 写死 rubric + 标注人 + 日期；判分结果带 `judged_by` |
| **A4** | **C3-a 单位未定**：spec §3.4 验收 8 计算式是 `token/doc`，而 §4.3 字段名 `single_doc_cost` 又称"成本"（token 与钱混用） | 报告**强制带单位** `unit="token/doc"`；config 名含 `TOKEN` 以钉死单位 |
| **A5** | **`doc_count` 去重口径未定**：同一文档多次重算算几次？失败重试算几次？ | 指标函数参数化，默认"按文档 ID 去重，只计最终成功态"，报告标注 `dedup_rule` |
| **A6** | **C2-c 分母是否含拒答未定**：矩阵写"含可回溯 span 的答案数 / 总答案数"，而**现脚本实测口径是分母排除拒答** ⇒ 字面与实现不一致，属**真缺陷** | 指标函数**显式两档**（`include_refused: bool`），报告同时输出两个值并标注现脚本用哪一档；**不改**现脚本行为 |
| **A7** | **零除定义未定**：基线答对率 = 0、gold 数 = 0、总成本 = 0 时增益 / 召回 / 成本比怎么算 | 一律返回 `None` + `reason`，**严禁**返回 0 或 `inf`；由单测钉住（空集 / 零除） |
| **A8** | **C2-a / C2-b 的语料规模缺口**：spec §3 验收 6 要求 200 合同 / 500 发票 / 100 凭证 / **20 组植入**；而 `demo/affiliation/README.md` §5 明示本语料只有 8 / 60 / 30 / **9 组**，并写明「**不宣称**召回 ≥ 0.80 / 误报 ≤ 0.15」（缺口 S13）⇒ 演示语料上跑出的召回 / 误报**不能**当判据 | 数据集 `MANIFEST.json` 与 `gold-affiliation-v1.json` 均写死该 caveat；gold 的实体 id 空间未与真机核对 ⇒ **不出数**（只自证口径） |
| **A9** | **gold 标注单元与 M4 输出单元不同构**：spec §3.4 未定义"识别正确"的**单元**是什么；M4 的疑点是「**一组**主体 + 一个类型」（持股环可含 2/3/4 个主体），不是二元组 `(head, tail)`。若按二元组拆分，1 条 4 环会变成 4 条边，与检测器输出的 1 条疑点对不上 ⇒ 召回被算成 1/4 | 指标层另立**组级**单元 `Finding(type, entity_ids)`（成员去重 + 排序），与二元组口径 `Relation` **并存**；匹配口径三档参数化，由单测钉住 |

---

## 7. 落点方案（**最终路径**）

```
changes/P0-m6-eval/
  proposal.md · tasks.md · integration-log.md

backend/
  app/evaluation/
    __init__.py
    metrics.py       # 纯函数：增益 / 召回 / 误报 / 引用覆盖 / 成本（含 A2/A4/A5/A6/A7/A9 参数化口径）
                     #   └ 两套单元并存：Relation（二元组）/ **Finding（组级，M4 疑点，A9）**
    criteria.py      # 四态状态机 + CriterionResult + Evaluator 注册表 + PlaceholderEvaluator
    dataset.py       # 版本化数据集加载 + 结构校验
    report.py        # JSON 报告（git hash / 时间戳 / 数据集版本 / provenance / threshold_source）+ diff
    runner.py        # offline（fixture，默认）/ live（HTTP）双模式
  data/eval/
    MANIFEST.json              # 数据集版本 / 来源语料 / kg_version / 标注人 / 日期 / rubric / 脏数据处理口径
    controlled-qset-v3.json    # 受控问题集（与既存 14 问一致，由守卫测试钉住）
    gold-multihop-v1.json      # 多跳问题集 + gold + 跳数标注
    gold-affiliation-v1.json   # M4 隐性关联 gold 标注集
    baselines/fixture-baseline-v1.json   # ⚠️ 非产品基线，仅供评测体系自测
  scripts/eval_acceptance.py   # CLI：--offline（默认）/ --live / --criteria / --out / --compare / --calibrate
  tests/
    test_evaluation_metrics.py     # 边界：空集 / 零除 / 全召回 / 误报 0 / 并列排序 / 拒答入分母与否
    test_evaluation_criteria.py    # 四态：BLOCKED 不得带数字 / provenance 必带 / 降级规则
    test_evaluation_dataset.py     # 数据集结构与 MANIFEST 校验
    test_eval_acceptance_cli.py    # --offline 可跑 + 幂等（两次运行逐字一致，除时间戳）
    test_eval_qset_parity.py       # 新 JSON 数据集 == eval_controlled_qset.QUESTIONS（防第二真源）
```

**出口 wiring（不做孤儿脚本）**：
1. `eval_acceptance.py --offline` 行为由 pytest 钉住（CLI 契约 + 幂等落盘）⇒ **CI 真在跑**；
2. 矩阵 §5.1 各行「判据」列改为**可执行命令**（指到本脚本），DR-D10 行回填脚本路径；
3. `integration-log.md` 写明怎么接进收尾三件套与 `check_session_drift.py`。

---

## 8. 出口判据（一句话）

`changes/P0-m6-eval/` 三件套齐备；`uv run python scripts/eval_acceptance.py --offline` 在**断网 / 无 LLM / 无 Neo4j** 下可跑且**两次运行 JSON 报告逐字一致**（除时间戳），报告中 **C2-c = `MEASURED`**、**C3-a / C3-b = `BLOCKED(blocked_by="P5-M6")`**；`EVAL_SINGLE_DOC_TOKEN_CEILING` 已落 `config.py` + `.env.example` 且**有消费者**（`check_seams.py` ERROR 0）；pytest **只增不减**、`ruff check` + `format --check` 全过、`export_openapi.py --check` **零 diff**、前端 `gen:api` + `typecheck` + `lint` **零 diff**。

---

## 9. 依赖与风险

| # | 风险 | 处置 |
|---|---|---|
| **RK-E1** | **gold 标注的主观性**：召回 / 误报 / 答对率全靠 gold，标注一改结论就变 | rubric 写死进 `MANIFEST.json`（标注人 / 日期 / 判定规则）；数据集**版本化**，报告带版本；换版须登记 |
| **RK-E2** | **演示语料非终局**：在它上面跑出的数被读成"达标" | 强制 `MEASURED_PROVISIONAL` + `provenance=demo-corpus`，报告顶部列出升级条件 |
| **RK-E3** | **provisional 阈值被当达标线**（假绿） | §5.2 三重防假绿；`PASS(provisional)` 显著标注"不构成 TBD-7 收敛证据" |
| **RK-E4** | 新增 `app/evaluation/` 被 `check_session_drift.py` **S5** 判为孤儿模块 | 由 `scripts/eval_acceptance.py` **真实 import**；E1 收尾跑一次 S5 确认 |
| **RK-E5** | **数字漂移**（"七项 vs 八项"那类错） | 所有数字以 **git / 脚本实测**为准；文档中的数字逐条标注来源，禁止凭记忆写 |
| **RK-E6** | 为"跑出个好看的数"而省略边界 | 边界情况（空集 / 零除 / 并列 / 拒答分母）**必须先有单测**再写实现；宁可多一个子任务写清数据来源 |
| **RK-E7** | `--calibrate` 被做成"自动放宽阈值" | 单测钉住：calibrate **只输出建议、不改 config**；阈值变更必须由人改 `.env` |

---

## 10. 与 `P5-M6` 的交接面（**占位执行点 → 实现后替换什么**）

| # | 占位判据 | `blocked_by` | P5-M6 落地后要做的**唯一**动作 |
|---|---|---|---|
| 1 | **C3-a** 单文档成本（真实值） | `P5-M6` | 建 `cost_metrics` 表 + 打点落库 ⇒ 把 `PlaceholderEvaluator` 换成读该表的 evaluator（**不动指标函数**） |
| 2 | **C3-b** 增量 / 全量成本比 | `P5-M6` | 增量重算落 `incremental_cost` / `full_rebuild_cost` ⇒ 同上替换 evaluator |
| 3 | C1 分母（RAG 基线） | `baseline-not-implemented`（**不属 M6**） | 由**基线归属裁决**（A1）后实现 `BaselineRunner` 的真实实现 |
| 4 | gold 数据集扩标 | `full-corpus`（P6） | 全量语料 + gold 扩标 ⇒ 判据由 `PROVISIONAL` 升 `MEASURED` |

> **契约兼容性**：本批**不改契约**（无端点变更）⇒ P5-M6 实现端点时**不会**被本批绊住；
> 反之，本批的 `BLOCKED` 也不会因为 P5-M6 的进度而**自动**变绿——必须**显式替换 evaluator 并留下实测记录**。
