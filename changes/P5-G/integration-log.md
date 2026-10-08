# P5-G · M6 批次 B'：**三端点接线** merge / split / rename —— 收口结语

> **日期**：2026-10-08　**分支**：`main` 直推　**执行模式**：无人值守
> **边界**：[`proposal.md`](./proposal.md) §3（**11 条** Non-goals）｜**花销**：¥0
> **任务拆解**：[`tasks.md`](./tasks.md)

---

## 0. 结论：**三端点已从 501 占位做成真的**

`merge` / `split` / `rename` 各自完成 图操作 → 写 `ontology_actions` →
**调 P5-F 的增量重算** → 回 `{kg_version, status: "applied"}`。
同批兑现了三个前几批登记等着兑现的债：RBAC 登记、`entity_merge_candidates.status = applied`、
升版 `specs/m2-extract-kg.md`。

**CI run [`37742495195`](https://github.com/csheep86/GraphRAG-Agent/actions/runs/37742495195) 四 job 全绿**，
后端 pytest **1118 passed / 5 skipped / 0 failed**。

| 维度 | 结果 |
|---|---|
| 花销 | **¥0**（图操作 + PG 写入，不调 LLM） |
| 提交 | **3 笔**（后端 / 契约+前端生成物 / spec+矩阵），+ 本文件 1 笔 |
| 新增文件 | `app/services/kg/correction.py`、`tests/test_ontology_correction_actions.py`（12 条） |
| 新增配置 | **0**（D2 未触发） |
| 新增错误码 | **0**（Non-goal 7 守住：跨 org 复用 `FORBIDDEN`，缺实体 `ENTITY_NOT_FOUND`，无基线 `KG_VERSION_NOT_ACTIVE`） |
| 契约 | **26 路径不变**；三路径的 `summary` / `description` / `responses` 变了 ⇒ 走完 D6 同步五步，`--check` 零 diff |
| 遗留 | **P5F-4 / P5G-2 / P5G-3 / P5G-6** 四条已登记缺口（§6） |

---

## 1. 批次坐标

- **上游**：`main` = `70513cf7`（P5-F 收口，CI run `37732319117` 全绿）
- **本批 HEAD**：`676035a6` → 本文件提交后再推一笔
- **spec**：`specs/m6-ontology-incremental.md` §3.2 验收 3 / 4 / 5、§4.4 第 166 行、§4.5
- **契约**：`contracts/openapi.yaml`（三条路径 + `status: const: applied` 本就在，本批只改错误语义）

---

## 2. 与 P5-F 的衔接：三端点接线

P5-F 落地的 `rebuild_incrementally` 在此之前**只有测试引用它**（P5-F §4 登记的 S5 状态）。
本批起它有了唯一的生产入口，且**一行未改**。

### 2.1 顺序即纪律（P5G-1）

```text
1. 读 PG active（= ready）版本作 base
2. probe：目标实体存在且属于本 org      ← 跨 org ⇒ 403 FORBIDDEN（不降级）
3. 落 ontology_actions（拿 action_id）   ← 审计先于变更
4. rebuild_incrementally(受影响集) → 新版本 ← 旧版本一条不动
5. 在新版本上施加校正变换                ← 不回写旧版本（ADR-0002）
6. merge：候选行 human_review → applied
```

**为什么变换落在新版本而不是旧版本**：spec §3.2 验收 3 的文本顺序是「更新 `:Entity` 节点 →
触发增量重算」。照字面实现会去改**旧版本**的节点，直接违反 ADR-0002「历史版本不删不改」
与 P5-F「旧版本一条不动」的判据。且 split 拆出的 N 个新节点**在 base 里根本不存在**——
先改图的话 incremental 的 probe 会把它们判成 `ENTITY_NOT_FOUND`。
⇒ 唯一自洽的顺序是「先产新版本、再在新版本上变换」。

### 2.2 ⚠️ 契约同步五步里有**三步在本批不适用**（逐条写明，别让后来者以为漏做了）

| 五步里的步骤 | 实读（2026-10-08） | 为什么不适用 |
|---|---|---|
| ① 升版 M2 spec（§4.5 枚举加 `applied` + §3 验收 3 补一条） | M2 §4.5 注脚 `:132-136` 已预留，但仍是「M6 前向预留、本阶段不实现」口径 | ✅ **本批做了**（§5）。只改注脚 / 表内括注 / 验收 3 末句注，**不重排编号**（R5） |
| ② 改 Pydantic `EntityMergeStatus` 枚举 | **该枚举在本仓不存在**（`grep EntityMergeStatus` 全仓 0 命中）；`entity_merge_candidates` **只写不读、不进契约**（`models.py` 既有裁决：不为"走出 diff"而造端点） | ❌ **无对象**。不新造一个不进契约的枚举去让五步"看起来走完"——那正是 R-9 要拦的。③ 的位置改由**代码动作**（真写 `status='applied'`）兑现 |
| ③ 重导契约 / ④ `gen:api` / ⑤ CI 零漂移 | 三条路径 + `const: applied` 在契约先行批次**已做** | 本批因 `summary` / `responses` 变化**重跑**了③④⑤（见 §7），但那是 **D6** 触发的，不是这一步的兑现 |

### 2.3 受影响集为什么带 1 跳邻居（P5G-7，本批新发现）

原本设计成 `affected = {被校正实体}`，写完测试才发现**不行**：
`incremental` 只迁移「两端都在受影响集内」的关系 ⇒ 新版本里的该节点**一条边都没有**，
merge 会把外部关系全丢掉、split 更是无从迁移。
⇒ 改为 `被校正实体 ∪ 其 1 跳同 org 邻居`。1 跳**仍然**远小于全图，
P5-F 的「不重建全图」判据依旧成立（测试里新版本 1 个节点 vs 旧版本 5 个）。

---

## 3. 改动清单

| 文件 | 改动 | 判据 |
|---|---|---|
| `app/services/kg/correction.py` | **新增**：三动作服务层（编排 + 三个变换 + 作用域 probe + 邻居查询） | 1 / 2 / 3 / 4 / 7 / 8 |
| `app/api/v1/routes/ontology.py` | 三端点由 `raise _placeholder(...)` 换为真实现；删 `_placeholder` / `_BLOCKED_BY` / `_SPEC` 与 `PLACEHOLDER_NOT_IMPLEMENTED` 导入（已无消费点）；挂 `require_permission`；模块 docstring 同步 | 1 / 6 |
| `tests/test_rbac.py` | `PROTECTED_ENDPOINTS` **6 ⇒ 9**（`merge` / `rename` / `split`） | 6 |
| `tests/test_ontology_placeholder_endpoints.py` | 三行从 `PLACEHOLDERS` **移入** `IMPLEMENTED`（不删行）；反向守卫收紧为「**501 且 `detail.blocked_by` 含 `P5-M6`**」才算退回占位 | 1 / 6 |
| `tests/test_ontology_correction_actions.py` | **新增 12 条**（真 Neo4j + 真 PG） | 1 / 2 / 3 / 4 / 7 / 8 / 9 |
| `contracts/openapi.yaml` + `frontend/src/types/api.d.ts` | D6 触发的重导 + `npm run gen:api` 再生 | 10 |
| `specs/m2-extract-kg.md` | §4.5 表 + 注脚 + §3 验收 3 末句注升版（**不重排编号**） | 5 |
| `docs/acceptance-traceability-matrix.md` | M6 行追加本批状态与三条不许外推的缺口 | — |

---

## 4. 五个回切点判据（**机器输出在 `docs/...`，不在记忆里**）

| 判据 | 结果 | 说明 |
|---|---|---|
| **S1** | ✅ **11 条** Non-goals | 逐条对照 §3 |
| **S2** | ✅ 3 文件 | ⚠️ **沿用 P5-F §4 的同款说明**：`correction.py` 是 `??` 未跟踪新文件 ⇒ `git diff` 不含它，**无法如实反映本批真实体量** |
| **S3** | ✅ 无事 | 本批**没有**新增 `config.py` 字段（D2 未触发） |
| **S4** | ⚠️ 命中，正当 | 改了 `routes/` ⇒ 按提醒跑 `export_openapi.py` + `gen:api`，已跑 |
| **S5** | ✅ 0 命中 | ⚠️ **同 P5-F §4**：未跟踪新文件不在 diff 里 ⇒ **S5 的"0 命中"是假阴性**，必须自己答：新模块被 `routes/ontology.py` 直接引用（有真实消费者，非提前写） |

**自己答的三句**：

1. **有没有顺便做的？** 没有。多做的唯一一处是「受影响集带 1 跳邻居」（P5G-7）——
   它不是顺手，是**写完测试才发现原设计会让 merge 丢掉全部外部关系**，属判据 2 的必要修正。
   `test_correction_action_leaves_an_audit_row` 也不是顺手，是 D8 明确要求的「实测确认有一条」。
2. **有没有为躲坑绕路？** 有**两处差点绕**：
   ① 断言"旧版本没动"时，一开始把后状态读图写在 `finally: _wipe()` **之后** ⇒
   读到空集，差点把「夹具清空」误判成「回归」——已在测试里就地注释钉死；
   ② split 的关系迁移一开始是「先建后删」，而删除只按 `rid` 定位 ⇒
   把刚挂到新节点上的那条一起删了（迁移变成"搬丢了"）—— 已改为**先删后建**，
   并在 `correction.py` 里留了 `⚠️` 注释。
3. **验收判据是真跑出来的？** 是：12 条新用例真连 Neo4j（`bolt://localhost:7687`）
   与真 PG；判据 3 / 4 / 8 的断言都是**PG 读回值**，判据 2 的断言是**图里的节点 / 属性 / 边**，
   不是响应体。

---

## 5. 升版 `specs/m2-extract-kg.md`（**架构师**角色，判据 5）

- §4.5 表 `:128`：`（另有 M6 前向预留值 applied…）` → `（M6 已启用第 5 个值 applied…）`
- §4.5 注脚 `:132-136`：标题由「M6 前向预留值（本阶段不实现）」改为「M6 已启用（2026-10-08 升版，P5-G 批次）」，
  并补一段 ⚠️ 说明原「契约同步 5 步」里 ② 无对象、③④⑤ 已做的实读修正
- §3 验收 3 `:48` 末句注同步：「本验收不涉及」→「该处置动作已落地，本验收只管 M2 产出候选」
- **编号一律未重排**（守 `dev-doc-status.md` **R5**）

---

## 6. P5F-4 裁决与登记（D9，判据 9）

**裁决**：取**建议最小形态**，不解决、不绕过、不假装它不存在。

```
新版本只承载「受影响子图 ∪ 1 跳邻居」 ⇒ 消费侧（M3 / M4）按新 kg_version 读图
会只看到被校正的那一小撮节点，看不到未受影响的远处节点。
```

**为什么不解决**：解决它 = 把全图复制进新版本 ⇒ 直接打掉 P5-F 的
**P5F-3「增量重写节点数 = 校正节点数」**这条机械判据。两者不可兼得，本批选"保增量判据"。

**已做的两件事**：

1. **显式断言** `test_new_version_carries_only_the_corrected_subgraph`——把它从"没人说的隐含行为"
   变成"测出来的已知事实"：`assert new_nodes == {f"{base}-e1"}`，并断言旧版本 5 个节点一条不动；
2. **缺口登记**：本文件 §6 + `docs/acceptance-traceability-matrix.md` M6 行。

**版本链读侧**（新版本缺的节点要不要从 base 回补）归后续批次。

### 6.1 其余三条登记缺口

| # | 缺口 | 为什么本批没做 |
|---|---|---|
| **P5G-2** | 新版本 `source_doc_ids` **留空数组** | 校正是**实体级**动作；填"受影响文档集"需要 `:Chunk-[:MENTIONS]->:Entity` 反查，本批**没有判据要求** ⇒ 编一个测不出的数据不如留空并登记 |
| **P5G-3** | split 的关系迁移只取「**默认同名**」一条规则 | spec §4.5 写「按规则匹配：曾用名 / 同名 / 其他，默认同名」，后两条没有定义。取最小可证形态：**匹配得上才迁（保方向）、匹配不上留在原节点**（不丢、不猜）。§10 第 2 类三步自检：① 不在 Non-goal 里 ② 可整体缩小到一条规则并登记 ③ ⇒ **不升级** |
| **P5G-6** | 变换失败后的**半成品版本**处置 | 变换在增量重算**成功之后**执行，此时 `result_kg_version` 已有值；失败时本模块**只抛错**（端点随之报错），**不**回滚 / **不**置 `failed` —— 那需要一套补偿语义，本批没有判据覆盖，**不写**未测的补偿代码 |

---

## 7. 门禁（**实测**，非推断）

| 命令 | 结果 |
|---|---|
| `uv run ruff check .` | ✅ All checks passed |
| `uv run ruff format --check .` | ✅ 261 files already formatted |
| `uv run python scripts/export_openapi.py --check` | ✅ **零 diff**（26 路径不变） |
| `uv run python scripts/check_seams.py` | ✅ ERROR **0** / WARN **0** / OK **12** |
| `uv run python scripts/check_startup_readiness.py` | ✅ `[OK]` **17** / `[~~]` **0** / `[--]` **0**（判据 11） |
| `uv run pytest -q`（本地，真图 env） | ✅ **1116 ~ 1117 passed / 4 skipped / 2 failed** = 基线 1102/4/2 + 本批**净 +14~15**（新增 12 条 + `PROTECTED_ENDPOINTS` 6⇒9 的参数化用例 − 占位路径迁移掉的用例） |
| `uv run pytest tests/test_rbac.py tests/test_ontology_placeholder_endpoints.py -q` | ✅ **48 passed**（`PROTECTED_ENDPOINTS` 9 条 × 参数化拒绝用例自动覆盖，判据 6） |
| CI run `37742495195` | ✅ 四 job 全绿，后端 pytest **1118 passed / 5 skipped / 0 failed**（判据 12 / 13，≥1103 / 5 / 0） |

**本地那 2 条失败**（实测 `FAILED` 行，不是推断）：

```text
FAILED tests/test_eval_ci_gate.py::test_g25_real_graph_detection_is_not_empty
FAILED tests/test_eval_corpus_a8.py::test_g25_v2_corpus_meets_thresholds_by_confidence_bound
```

即基线备注里的「g25（真实语料缺失）」那两例 —— 依赖**未提交的大评测语料**，
CI 上必 skip（CI 实测 0 failed）。**不是**本批引入的。

### 7.1 D6 触发：契约同步五步走完

三端点的请求 / 响应模型**零改动**，但 `summary` / `description` / `responses` 必然变
（去掉「占位骨架」、新增 404 / 409、501 描述改为「基础设施不可用」）⇒ 契约真的漂移了。

1. ① schema：**无对象**（三个请求 / 响应模型本就在契约里）
2. ② 代码：三端点真实现（`routes/ontology.py`）
3. ③ 重导：`uv run python scripts/export_openapi.py`（diff = 3 路径 × summary/description/responses）
4. ④ `npm run gen:api`：`frontend/src/types/api.d.ts` **+67**（路径描述进了生成物）
5. ⑤ CI 零漂移：**run `37742495195` 的「契约校验」job 绿**

---

## 8. 给下一批的指针（按优先级）

1. **版本链读侧**（P5F-4 的另一半）：新版本缺的节点/边要不要从 base 回补、怎么回补。
   本批已把"缺"钉成显式事实，缺口登记在 §6 与矩阵 M6 行。
2. **`source_doc_ids`**（P5G-2）：校正产的新版本目前没有文档归属；
   若后续的成本 / 回放判据需要它，才做 `:Chunk-[:MENTIONS]->:Entity` 反查。
3. **split 关系迁移的另两条规则**（P5G-3）：「曾用名」「其他」至今无定义，
   等 GUI 批次把人工选择界面定下来再补。
4. **GUI / 前端**：三端点已可用（`summary` / `description` 已在契约里），可以直接接。
5. **批次 D 成本仪表盘**：`COST_RATIO_ALERT_THRESHOLD`（TBD-7）Sprint 13 才收敛，别提前做。

---

## 9. 提交与推送

| # | SHA | 标题 |
|---|---|---|
| 1 | `7124a46f` | `feat(M6): P5-G 三端点接线 merge / split / rename` |
| 2 | `8ea5604a` | `chore(contract): 三端点由 501 占位改为真错误语义（契约同步五步 ③④）` |
| 3 | `676035a6` | `docs(M6): M2 spec §4.5 注脚升版 + 矩阵 M6 行追加（P5-G）` |
| 4 | （本文件） | `docs(P5-G): integration-log 收口（CI run 37742495195 四 job 全绿）` |

推送一次成功（`70513cf7..676035a6`），**没有**遇到 P5-F §11 记的 `Connection was reset`
故障 ⇒ 也未复现「推送到 `github.com` 需要系统代理」那条（P5-F 已修正：HTTP/1.1 本批失效，默认重试即通）。
