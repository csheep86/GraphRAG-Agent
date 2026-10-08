# P5-F · 集成实录：M6 批次 C **增量重算**

> **日期**：2026-10-08　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-E/integration-log.md`](../P5-E/integration-log.md)（`main` = `489d534c`，CI run `37728846287` 四 job 全绿）
> **边界**：[`proposal.md`](./proposal.md) §3（11 条 Non-goals）｜**任务拆解**：[`tasks.md`](./tasks.md)
> **花销**：**¥0**（全程图操作 + PG 写入，未调任何 LLM）

---

## 1. 起点自检（结论全部来自脚本，**不**来自文档或记忆）

| 命令 | 开工时实读 | 与基线是否一致 |
|---|---|---|
| `check_startup_readiness.py` | 🟢 已生效 **17** 条 / 🟠 部分 **0** / 挂起 **0** | ✅ |
| `check_seams.py` | ERROR **0** / WARN **0** / OK **12** | ✅ |
| `export_openapi.py --check` | `[OK] …一致`（零 diff，26 路径） | ✅ |
| `gh run list --limit 1` | run `37728846287` / `489d534c` **success** | ✅ |

**本机环境**：`graphrag-pg` = Up；`graphrag-neo` = **Exited**（与 P5-E 开工时同型）⇒ 已 `docker start graphrag-neo`
（凭据 `neo4j/ci-graph-pw-2026`，`7687`）。**判据 2 依赖真图**，不能靠 skip 蒙过去（纪律 R-10）。

**pytest 基线（本地口径，带 `GRAPH_REAL_NEO4J_*` 三开关）**：

```text
2 failed, 1093 passed, 4 skipped, 13 warnings in 118.36s
```

⚠️ 那 **2 条 failed 是本地特有的既有环境债**，不是回归：
`test_eval_ci_gate.py::test_g25_real_graph_detection_is_not_empty` 与
`test_eval_corpus_a8.py::test_g25_v2_corpus_meets_thresholds_by_confidence_bound`
依赖 CI 里「导入受控种子语料」那一步（`_LARGE_KG_VERSION = "affiliation-demo-v2"`），
**本机图库没有那份语料** ⇒ 真图连上了却查不到。上一批本地口径是
「1088 passed / 11 skipped」——那是**未设 USER/PASSWORD** ⇒ 11 条真图用例全体 skip，
2 条 g25 也随之 skip；本批把三开关补全后它们**真跑**，于是暴露成本地缺语料。
**CI 上有导入步骤 ⇒ 这 2 条在 CI 上绿**，以 CI 为终裁（R-10）。

---

## 2. 实现（T1 / T2）

### 2.1 落点

| 文件 | 内容 |
|---|---|
| `backend/app/services/kg/incremental.py`（**新增**） | `rebuild_incrementally()` + `IncrementalRebuildResult` / `IncrementalRebuildError` + 5 段 Cypher |
| `backend/app/core/config.py` | `increment_rebuild_batch_size: int = Field(default=100, gt=0)` |
| `backend/.env.example` | 同步 `INCREMENT_REBUILD_BATCH_SIZE=100`（S3 必须不报） |
| `backend/tests/test_kg_incremental_rebuild.py`（**新增**） | 9 条（真 Neo4j + 真 PG 读回） |

### 2.2 一次调用的因果链（**顺序即纪律**）

```text
1. 读 ontology_actions 行（带 org_id 过滤 —— 应用层过滤是常设防线，DR-B5）
2. 取 PG active（= ready）版本作 base；与 action.kg_version 不符 ⇒ 拒绝（不按陈旧基线算）
3. 生成同 org 唯一新版本号 <base>-inc-<suffix>
4. create_pending → mark_building            ← 状态机**复用** KgVersioningService（P5F-1）
5. probe：受影响实体必须存在且属于本 org     ← 跨租户 = KG_TENANT_LEAK，缺失 = ENTITY_NOT_FOUND
6. 分批重写：节点 → 子图内部关系             ← 批大小 = settings.increment_rebuild_batch_size
7a. 成功：mark_ready + 回填 action.result_kg_version + 同步本版本的 :KgVersionMirror
7b. 失败：mark_failed + 落 action.error_code/error_detail，result_kg_version **保持 NULL**
```

**第 7b 是本批最要紧的一条纪律**：失败时**绝不**回落全量重建。一旦悄悄重跑全量导入，
M6 §3.4 的 C3 取证字段（`cost_ratio`）就**永远测不出来**——「增量 vs 全量」会变成两个
都跑全量的数字之比。所以本批把"不回落"写成机械判据：失败后**图里新版本一个节点都没有**，
且旧版本节点数一条不少。

### 2.3 决策补充登记（spec 未写清处，按「先缩范围、后登记」处置）

| # | 冲突点 | 本批取法 | 为什么不算第 2 类升级 |
|---|---|---|---|
| **P5F-1** | spec 写 `writing → active`，代码真源是 `pending → building → ready` | **沿用代码真源**（`ready` 即 PG 的 active 语义，`versioning.py:178` docstring 明写） | 同一状态机的**两套命名**，不是粒度冲突；改代码会让 `test_kg_versioning.py` / 图谱侧既有用例整体变红 ⇒ 最小代价就是"登记映射" |
| **P5F-2** | 「仅文档级 `kg_version`，不全局翻」的机械含义 | ① 新版本 `source_doc_ids` **只含受影响文档**；② 图侧**只重写受影响子图**；③ 镜像**只写本版本**，**不**把其它版本置 `superseded` | 验收 7 要求 active 才可消费 ⇒ 新版本必须可查；「不全局翻」指的是**图数据不重建** |
| **P5F-3** | 「节点数增量 = 校正节点数」在图里的落点 | 新版本下**新增/重写的节点数 = 受影响实体数 M**；旧版本一条不动；M ≠ 全图 N | 这是唯一能让"增量 vs 全量"被**数出来**的形态 |
| **P5F-4** | 新版本图的**完整性**（未受影响节点不在新版本下） | **本批不解决**，登记为下一批裁决项 | 真正的 merge / split / rename 会改变节点集合（合并 = 节点数 −1），"新版本如何包含未受影响节点"须与端点语义同批定义。本批若擅自把全图复制一份到新版本，就直接违反 P5F-3 的判据 |
| **P5F-5** | 服务函数本批**只有测试引用** | 明写归属 = spec §3.3 验收 6，消费者 = 下一批三端点 | 不为"走出 diff"造端点（`models.py:517` 既有裁决口径） |

### 2.4 两处"没顺手做"的（主动刹车）

1. **没有给增量重算开 HTTP 入口**（D3）。三端点仍是占位骨架，开端点 = 提前实现它们 ⇒ Non-goal 1。
2. **没有新增错误码**（D5）。失败复用既有 `ENTITY_NOT_FOUND` / `KG_TENANT_LEAK` /
   `KG_VERSION_NOT_ACTIVE` / `VALIDATION_ERROR` / `NOT_IMPLEMENTED`（基础设施不可用的
   项目既有口径）——未动 `errors.py`，`export_openapi.py` 的 enum 全等断言不受影响。

---

## 3. 测试与判据对账（T3）

新文件：`backend/tests/test_kg_incremental_rebuild.py`（9 条）。

```text
$ uv run pytest tests/test_kg_incremental_rebuild.py -q
.........                                                            [100%]
9 passed, 1 warning in 3.60s
```

| 判据 | 用例 | 断言对象（**不是**函数返回值） |
|---|---|---|
| 1 服务落地且被测试驱动 | 全 9 条直接调 `rebuild_incrementally`（不经 HTTP） | 服务层函数 + 真库/真图结果 |
| 2 不重建全图 | `test_incremental_rebuild_rewrites_only_affected_subgraph` | 真图：新版本节点集 **==** 受影响的 2 个；旧版本 5 个**一条不动**且属性逐条不变；新版本节点数 **≠** 全图 N；关系只迁移两端都在集合内的 1 条（另 1 条跨边界的留在旧版本） |
| 3 新版本落库 + 文档级 | `test_new_kg_version_row_is_ready_and_document_scoped` | PG 读回新增行 `status='ready'`，`source_doc_ids == [受影响文档]` 且 **≠** 全量 3 份 |
| 4 `result_kg_version` 真回填 | `test_result_kg_version_is_backfilled_in_pg` | 新会话读回 `ontology_actions.result_kg_version`（先断言 NULL → 后断言新版本号） |
| 5 失败显式失败 | `test_failure_lands_error_code_without_full_rebuild` / `test_cross_org_entity_is_rejected_not_skipped` | `error_code` = `ENTITY_NOT_FOUND` / `KG_TENANT_LEAK` 落库；`result_kg_version` 仍 NULL；版本行 `failed`；**图里新版本节点集为空**且旧版本节点数不变（= 没有回落全量） |
| 6 配置有真实消费者 | `test_batch_size_from_settings_really_changes_batches` / `test_batch_size_default_comes_from_settings` | 置 `increment_rebuild_batch_size=1` ⇒ `batch_count` 由 2 变 **3**（断言**读到并生效**，不只断言"设了"——`extra="ignore"` 陷阱） |

**判据 5 的失败注入**刻意用「受影响集里掺一个不存在的实体 id」，而不是假 session：
真图 + 真失败路径，才能同时断言"旧版本节点一条没少"。

---

## 4. 门禁与收口（T4）

| 门禁 | 结果 |
|---|---|
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `259 files already formatted`（首次跑报告 2 个待格式化，已 `ruff format .` 收敛） |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12**；「配置消费者」= `Settings 全部 67 个字段均有消费者代码行`（新增配置已计入） |
| `export_openapi.py --check` | `[OK] 与后端模型一致`（零 diff，**26 路径不变**）⇒ **D6 判定：契约零改动，未走同步五步** |
| `check_startup_readiness.py` | 🟢 已生效 **17** / 🟠 部分 **0** / 挂起 **0**（基线一致，未倒退） |
| `check_session_drift.py` | S1 读到**本批 11 条** Non-goals；S2 `2 个文件 / 新增 3 行`（阈值内）；S3 新增 Settings 字段已在 `.env.example` 就位；S4 未触及契约路径；**S5 ✅** |

**S5 为什么显示 ✅（本应命中）**：`check_session_drift.py` 只看 `git diff`，而
`app/services/kg/incremental.py` 在跑脚本那一刻还是**未跟踪文件**（未 `git add`）⇒ 不在 diff 里。
脚本扫不到 ≠ 它有人引用。**按提示词 §4 的要求明写答案**：
`incremental.py` 的归属是 **spec §3.3 验收 6**，本批**只有测试引用它**，
真正的消费者是**下一批**的 merge / split / rename 三端点。

**pytest（本地口径，全量）**：

```text
2 failed, 1102 passed, 4 skipped, 3 warnings in 66.76s
```

= 基线 `1093 + 9`（新增 9 条），**失败条数与基线完全相同**（仍是那 2 条本地缺语料的 g25）。
既有正向守卫（`test_kg_versioning.py` / `test_guardrails_graph.py` / `test_guardrails.py:328`）
保持绿，**一条断言都没为让它绿而改**。

---

## 5. 提交与 CI

| # | 提交 | 内容 |
|---|---|---|
| 1 | `ac20627c` `feat(M6): 增量重算服务 …` | 服务 + 配置 + `.env.example` + 测试（4 文件，1198 行） |
| 2 | 本批文档 | `changes/P5-F/{proposal,tasks,integration-log}.md` + 矩阵 M6 行追加 |

推送沿用 P5-E 收尾实测的解法：`git -c http.version=HTTP/1.1 push origin main`
（**一次即通**；P5-E 那次连丢 4 次、间隔 45/75/120 秒都无效，根因是 git 的 HTTP/2 传输层握手，
不是网络不通）。`-c` 是单次覆盖，**未改 git config**。

**CI（代码）**：run `37730936882` / commit `ac20627c` —— 见 §7 结论。

---

## 6. 本批**没有**做的事（不许外推，逐条）

- **增量重算写了 ≠ 三端点可用**：merge / split / rename **仍是占位骨架**，HTTP 层一行没动。
- **服务函数绿了 ≠ 有调用方**：本批只有测试引用它（§4 的 S5 说明）。
- **"不重建全图"判据过了 ≠ 成本真的低**：本批**不测** token / 耗时 / 成本比（批次 D 的事）。
- **新 `kg_version` 落了 ≠ M3 / M4 已能消费**：验收 7 只要求"可消费"，本批**未验证**下游真实消费链路；
  且 **P5F-4** 明写"未受影响节点不在新版本下"这个完整性缺口未解决。
- **失败会落 `error_code` ≠ 失败可恢复**：本批不做重试 / 回滚语义。
- **`INCREMENT_REBUILD_BATCH_SIZE` 可配 ≠ 已调优**：默认 100 是 spec §6 给的，**没有任何实测依据**。
- **契约零漂移 ≠ 功能可用**：只证明了"契约没被踩歪"。
- **本地绿 ≠ CI 绿**：本机 2 条 g25 失败是缺语料（§1），**以 CI 为终裁**。

---

## 7. CI 结论

**代码提交 run `37730936882` / commit `ac20627c` —— 四 job 全绿**：

```text
契约校验（前后端漂移门禁）  success
前端（lint + gen:api）        success
后端（ruff + pytest）         success
流水线汇总                    success
```

后端 job 实测：

```text
Ruff 静态检查        All checks passed!
Pytest               1103 passed, 5 skipped, 1 warning in 59.41s
```

**判据 8 对账**：基线 CI = **1094 passed / 5 skipped / 0 failed**（run `37723651857`）
⇒ 本批 **1103 passed / 5 skipped / 0 failed**（**+9**，正好等于新增用例数，
**0 failed**）✅。注意 **CI 的 5 skipped 与本地的 4 skipped 差 1**：本地把三开关补全后
少 skip 一条，属同一批真图用例在两地的可达性差异，**不是**新增跳过。

---

## 8. 下一批指针（**按实际结果更新，别照抄**）

1. **M6 三端点接线（merge / split / rename）**：前置已补完，可直接做。同批须补
   ① `require_permission` ② `PROTECTED_ENDPOINTS` 登记（P5-C §11 第 1 条的 RBAC 债）
   ③ 更新 `entity_merge_candidates.status = applied` ④ **升版 M2 spec §4.5**
   （§2.1 第 ① 步，与 ③ 同批做，避免先改文档后无代码兑现）
   ⑤ **裁决 P5F-4**：新版本如何包含未受影响节点（本批刻意未定）。
2. **`GET /cost/dashboard` + `cost_metrics` 表**（m6 §3.4 验收 8 / 9）+ MVP 准入 **C3-a / C3-b**；
   `cost_ratio` 阈值（TBD-7）**Sprint 13 收敛前拿不到判据**。
3. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2；**已连续四批**有意不做）。
4. **DR-B6 / DR-B7 与 G-9 / G-10 的口径对账**（纯 docs 债）：需求侧明细行仍写「⏳ 零代码」，
   而护栏侧均已 ✅ 转正。建议并入任一批次顺手做，**不单独开工**。
5. **多租户出向审计归属**：脱离「一套 compose = 一个租户」时需给 `build_chat_model` /
   `build_default_embedder` 补 org 传递（P5-D 的 X-3 撤回条件）。
6. **D7（`question` 参与检索）/ D5（M4 完整化）/ D8**：算法活，各自单独排。
7. **m6 定稿遗留的另两个配置项**（`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `COST_RATIO_ALERT_THRESHOLD`）：
   本批**只填了 `INCREMENT_REBUILD_BATCH_SIZE`**，另两个在对应批次回填，**别顺手补齐**。
8. **日志 `message` 正文的脱敏**（P5-E 明确不覆盖）：逐个补 `mask()` 调用点，不做值识别。
