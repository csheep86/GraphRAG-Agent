# 新会话开场提示词 · P5-H（M6 批次 C'：**版本链读侧** = P5F-4 消费侧完整性）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。详见 §1。
>
> 📦 **本文件自包含**：上一批（P5-G）已收口（`main` = `67347970`，CI run `37743119955` 四 job 全绿）、
> 不会再回来。开工所需坐标、命令、基线、陷阱都在本文里。唯一需要你额外读的是 §0.5 的**五份仓库内文件**。
>
> ⚠️ **本批修的是 P5-F / P5-G 引入的一个真实功能缺陷**：一次校正之后，active `kg_version`
> 变成「只含受影响子图 ∪ 1 跳邻居」的新版本 ⇒ **M3 合规 / M4 问答 / 图谱概览会几乎读空**。
> 这不是优化，是缺陷。spec 依据见 §2.1。
>
> 复制本文件**全文**到新会话作为第一条消息。

---

## 0. 本批一句话

让**读侧**在「校正产出增量新版本」之后仍能看到**完整图谱**：新增「**版本继承读**」解析
（active ∪ 其祖先版本），把首批读路径从

```cypher
WHERE n.kg_version = $kg              -- 单值
```

换成

```cypher
WHERE n.kg_version IN $kgs            -- 有序版本列表，同 id **链上最新者胜**
```

**同批必做的两个附加动作**：① 落一份 **ADR**（版本继承读的口径与链的真源）；
② 升版 `specs/m6-ontology-incremental.md` §5.1 注脚（把"active 版本 = 单值"这个隐含前提写明）。

**不做**：GUI / 前端（另一批）、成本仪表盘（批次 D）、`alert` 表（P2）、写侧（P5-F 的增量重算**一行不改**）。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`changes/P5-G/integration-log.md` §6 / §6.1 / §8** | 上一批实录。**重点 §6（P5F-4 的裁决与缺口登记）**、§2.1（顺序即纪律）、§2.3（P5G-7：受影响集带 1 跳邻居）、§8 指针第 3 条（就是本批） |
| 2 | **`backend/app/services/graphs.py:1209 / 1359 / 2012 / 2149 / 2261 / 2350 / 2400`** | `fetch_active_kg_version`（:1209）+ 六条「按单一 `kg_version` 读图」的入口：`fetch_all_subgraph`（:1359）/ `fetch_graph_overview`（:2012）/ `fetch_entity_detail`（:2149）/ **`fetch_reasoning_path`**（:2261，M4 问答）/ `scan_attendance_compliance`（:2350，M3 合规）/ `list_attendance_anomalies`（:2400） |
| 3 | **`backend/app/services/kg/versioning.py:203 get_active`** + **`backend/app/db/models.py:283-306 KgVersion`** | **实读结论**：`get_active` 按 `ready_at DESC` 取一条；`KgVersion` 表**没有** `parent_version` 列 ⇒ 版本链只能**反推**，这是本批最大的设计约束 |
| 4 | **`backend/app/services/kg/correction.py::_run_action`** | 写侧现状：**先**增量重算（受影响集 + 1 跳邻居）→ **再**在新版本上变换。本批**不动**它，但读侧规则要跟它对得上 |
| 5 | **`specs/m6-ontology-incremental.md:207`** | §5.1 上游依赖第 3 条：「M6 校正动作触发后，**问答结果应能立即反映**新图谱（沿用 M3 §3 验收 6 对 `kg_version` active 的消费）」——**本批的 spec 依据就这一句** |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

**替代真源映射**（沿用 P5-B/C/D/E/F/G 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（**文件已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-H/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | **预期零契约改动**（本批改的是读路径内部，不改任何请求 / 响应模型）。**若**发现必须动契约 ⇒ 走完同步五步，**不算升级** |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

**角色隔离**：

| 段 | 角色 | 允许改的范围 |
|---|---|---|
| 版本视图解析 + Cypher 切换 + 测试 | **后端开发 B** | **只允许** `backend/` + 跑脚本 |
| **ADR + 升版 `specs/m6-ontology-incremental.md` §5.1 注脚** | **架构师**（同一会话内换帽子） | 只允许 `docs/adr/` 新文件 与 `specs/m6-ontology-incremental.md` 的 §5.1 注脚，**只追加注脚，不重排编号**（守 `dev-doc-status.md` **R5**） |
| 契约与前端生成物**再生**（**仅当判定为必需**） | 仍是 B（**不写前端业务代码**） | 只允许 `contracts/openapi.yaml`（导出产物）与 `frontend/src/types/api.d.ts`（`npm run gen:api` 产物） |

**分支**：沿用 P4 / P2-C / P5-B/C/D/E/F/G —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P5-H / 为什么是这一刀

### 2.1 四条机械理由

1. **它是 P5-G 收口时登记的第 1 号指针**：`changes/P5-G/integration-log.md` §8 第 3 条
   「版本链读侧（若 D9 未在本批解决）」。P5-G 按 **D9** 取了最小形态（只做显式断言 + 缺口登记），
   **没有解决**它 ⇒ 它现在是在飞的第一顺位。
2. **它是功能缺陷，不是优化**：P5-F 的增量重算把「受影响子图 ∪ 1 跳邻居」写成新版本并置 `ready`，
   而 `KgVersioningService.get_active` 按 `ready_at DESC` 取一条 ⇒ **校正后 active 就是那个小版本**。
   消费侧（`graphs.py` 的 `fetch_graph_overview` / `fetch_reasoning_path` / `scan_attendance_compliance`
   / `list_attendance_anomalies` / `fetch_all_subgraph` / `fetch_entity_detail`，以及
   `documents.py:264`、`agents.py:257`）全部按**单一** `kg_version` 过滤
   ⇒ 校正后它们**几乎读空**。链路已实读，见 §0.5 第 2 项。
3. **它有 spec 依据**：`specs/m6-ontology-incremental.md:207`（§5.1 上游依赖第 3 条）明文
   「校正动作触发后，**问答结果应能立即反映**新图谱」。当前实现**不满足**这一条。
4. **判据可机械**：「未受影响的节点在校正后**仍能被读到**」「被校正的节点读到的是**校正后**的值」
   「跨版本边**不**连出幽灵路径」——都是可以数出来的事实，且**不需要 LLM**（本批 ¥0）。

### 2.2 为什么**不是**这两条

| 候选 | 不做的原因 |
|---|---|
| **本体校正 GUI（前端）** | `changes/P5-G` §8 指针第 1 条，属另一批。**但顺序上必须先做本批**：GUI 一旦上线就会频繁触发校正，而每触发一次就把 active 变成小版本 ⇒ 先把洞堵上再开门 |
| **`GET /cost/dashboard` + `cost_metrics`**（批次 D / MVP 准入 C3-a·C3-b） | 属另一条价值链；`cost_ratio` 阈值（TBD-7）**Sprint 13 才收敛**，现在做拿不到"显著 < 1.00"的判据 |

### 2.3 本批的四刀（建议范围）

1. **版本链解析**：新增 `resolve_read_versions()`（建议落在 `app/services/kg/version_view.py`），
   从 active 版本沿 **`ontology_actions`**（`result_kg_version` → `kg_version`）回溯父链，
   返回**有序**版本列表（新 → 旧）。
2. **读路径切换**（**首批只切 3 条**，见 §5 **D5**）：
   - `GraphService.fetch_graph_overview`（`/graph/overview`，`graphs.py:2012`）
   - `GraphService.fetch_reasoning_path`（M4 问答，`graphs.py:2261`，内部转调 `reasoning.py`）
   - `GraphService.scan_attendance_compliance`（M3 合规，`graphs.py:2350`）
   Cypher 由 `= $kg` 改 `IN $kgs`，并加**同 id 只取链上最新者**的去重规则（§5 **D6**）。
3. **ADR + spec 注脚**：`docs/adr/` 新增一份「版本继承读」ADR（架构师帽），
   并把 `specs/m6-ontology-incremental.md` §5.1 的隐含前提（"active 是单值"）写成注脚。
4. **不变性守卫**：新增测试钉死「校正后未受影响节点仍可读到」——这是 P5-G 里那条
   **例外断言**（`test_new_version_carries_only_the_corrected_subgraph`）的**反面**，
   两条要**共存**：前者钉「新版本物理上不承载全图」，后者钉「读侧逻辑上能看到全图」。

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check       # 期望：零 diff（26 路径）
uv run pytest -q                                      # 本地口径基线见 §8（须补 GRAPH_REAL_NEO4J_*）
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点是绿的（否则先别动代码）
```

> 本机 Neo4j / PG 容器若停了：`docker start graphrag-neo graphrag-pg`。
> 真图用例的三开关：`GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` /
> `GRAPH_REAL_NEO4J_USER=neo4j` / `GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026`。

---

## 4. 明确不做（**10 条 Non-goals**，逐条对照）

1. **不做 GUI / 前端业务代码**：本批连前端都不碰（除非判定契约必需，才再生 `api.d.ts`）。
2. **不改 `specs/m6-ontology-incremental.md` 的正文**：只追加 §5.1 注脚（架构师帽），**不重排编号**（R5）。
3. **不动写侧**：`app/services/kg/incremental.py` 与 `app/services/kg/correction.py`
   **一行不改**（P5F-3「增量重写节点数 = 校正节点数」的机械判据必须继续成立）。
4. **不动 `KgVersioningService.get_active` 的语义**：它仍返回**一条** active 版本；
   本批新增的是**并列**的 `resolve_read_versions()`，不是替换。
5. **不给 `kg_versions` 加 `parent_version` 列**：需要写迁移并触碰 **G-6 迁移等价性**护栏，
   本批不启动（见 §5 **D4**）。
6. **不碰成本仪表盘 / `cost_metrics` / `COST_RATIO_ALERT_THRESHOLD`**：批次 D。
7. **不新增第三方依赖**：现有 `neo4j` 驱动 + SQLAlchemy 即可。
8. **不新增错误码**（预期）：失败沿用既有码。若确有必要 ⇒ `errors.py` **四处**字典齐加。
9. **不一次切完所有读路径**：~40 处 `kg_version` 过滤点一次性改会触发 `check_session_drift.py`
   的 **S2** 阈值 ⇒ 首批只切 §5 D5 点名的 3 条，其余**登记**为下一批。
10. **不做批量校正 / 撤销栈 / 本体版本对比 GUI**：m6 §1.2 明列 Out of Scope。

---

## 5. 决策表（**本批需要你自己裁决并在 integration-log 登记**）

| # | 决策 | 处置 |
|---|---|---|
| **D1** | 主题 | ✅ 定 **M6 版本链读侧（P5F-4 消费侧完整性）** |
| **D2** | 是否新增配置 | **预期不新增**；若确需 ⇒ ① 有真实消费者 ② 同步 `.env.example` ③ 不得占位 |
| **D3** ⚠️**必答** | 实现形态三选一 | **取 A（读侧版本集合）**：读时用 `active ∪ 祖先` 的有序版本列表。<br>**B（写侧把 base 全量复制进新版本）不选**——直接违反 P5F-3。<br>**C（校正不换 active）不选**——违反 m6 §5.1「校正后问答立即反映新图谱」与 §3.2 验收 3（响应要回新 `kg_version`） |
| **D4** ⚠️**必答** | 版本链从哪来 | **取 A1（沿 `ontology_actions` 反推，无迁移）**：`result_kg_version` → `kg_version` 逐跳回溯，限深度（建议 16）防环。<br>**A2（给 `kg_versions` 加 `parent_version` 列）本批不做**（要迁移 + G-6）。<br>⇒ **必须在 ADR 里写明：版本链的真源是 `ontology_actions`，不是 `kg_versions`** |
| **D5** ⚠️**必答** | 首批切哪几条 | **只切 3 条**：`fetch_graph_overview` / `fetch_reasoning_path` / `scan_attendance_compliance`。<br>其余（`fetch_all_subgraph`、`fetch_entity_detail`、`fetch_anchor_entity_ids`、`list_attendance_anomalies`、`explain_attendance_anomaly`、`fetch_document_subgraph`、`agents.py` 的检索）**本批不动**，逐条登记到 §11 指针第 1 条 |
| **D6** ⚠️**必答** | 同 id 多版本节点怎么去重 | 规则：**有序版本列表（新→旧）中命中越靠前越优先，同 id 只保留一个**。<br>⚠️ 最难的一条是**跨版本边**：一条边的两端可能落在不同版本。<br>取法：**边的版本 = 其两端节点各自被选中版本的较新者**；拼不出来 ⇒ **不连**（宁可少一条链，也不许连出幽灵路径）。<br>若这条在实现中做不到 ⇒ **先缩范围**：只在「两端同版本」时出边，并在 integration-log 登记口径 |
| **D7** | 缓存 | **不引入缓存**：版本链解析是一次 PG 查询，读路径本来就打到 Neo4j，不为它加一层会过期的状态 |
| **D8** | 契约会不会动 | **预期零改动**；若动了 ⇒ 走完同步五步，**不算升级** |
| **D9** | 审计 | 本批不新增审计点；M5 中间件已全量覆盖 |
| **D10** | 成本敞口 | 本批**预期 ¥0** |

---

## 6. 已完成（**前序批次，别重做**）

- ✅ **M6 三端点接线**（P5-G，`main` = `67347970`）：`merge` / `split` / `rename` 真实现
  + RBAC（`PROTECTED_ENDPOINTS` 6 ⇒ 9）+ `entity_merge_candidates.status = applied`
  + **升版 M2 spec §4.5**（M2 那条债已清）。CI run `37743119955` 四 job 全绿。
- ✅ **增量重算**（P5-F）：`rebuild_incrementally` 只重写受影响子图 + 只迁移两端都在集合内的边；
  `INCREMENT_REBUILD_BATCH_SIZE`（默认 100，有真实消费者）。
- ✅ **M5 统一脱敏**（P5-E）/ **私域出向管控**（P5-D）/ **M6 第一批**（P5-C）。
- ⚠️ **本批要兑现的债**：**P5F-4 消费侧完整性**（P5-G 只登记未解决 —— **本批做**）。
- ⚠️ **继续有意不做**：`alert` 表（P2）；成本仪表盘（批次 D）；GUI（另一批）；
  DR-B6 / DR-B7 与 G-9 / G-10 的 docs 口径对账。

---

## 7. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1118 passed / 5 skipped / 0 failed**（run `37743119955` / commit `67347970`，2026-10-08） |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*` 三开关） | P5-G 实读 **1116 ~ 1117 passed / 4 skipped / 2 failed**——2 条 failed 是**本地特有的既有环境债**（`test_eval_ci_gate.py::test_g25_real_graph_detection_is_not_empty` 与 `test_eval_corpus_a8.py::test_g25_v2_corpus_meets_thresholds_by_confidence_bound`，依赖 CI 才有的受控种子语料）。**CI 上有导入步骤 ⇒ 那 2 条在 CI 上绿** |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**26 路径**） |
| `PROTECTED_ENDPOINTS` | `tests/test_rbac.py:62`，现 **9 条**（P5-G 由 6 加上来的） |
| 真图 / 真 PG 用例 | `tests/test_ontology_correction_actions.py` **12 条**、`tests/test_kg_incremental_rebuild.py` **9 条** —— 本批**不许为让它绿而改断言** |
| 前端 | 未在**本地**跑 `typecheck` / `lint` / `build`；只在 CI 内绿 ⇒ 若触及前端生成物，**以 CI 为终裁** |
| 最近一次绿 CI | **不要照抄写死的 run id**。开工时 `gh run list --limit 1` 实读；本文件成文时是 **run `37743119955` / commit `67347970`** |

---

## 8. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **版本链解析正确** | 单跳 / 多跳（连续 3 次校正）/ 无父链三种情形各一条用例，断言 `resolve_read_versions()` 返回**有序**列表（新 → 旧） |
| 2 | **校正后未受影响的节点仍可读到**（**本批的核心判据**） | 真 Neo4j + 真 PG：5 个节点，rename 其中 1 个 ⇒ 以 active 版本读图**仍能读到全部 5 个**（不是只有 1 个） |
| 3 | **被校正的节点读到的是校正后的值** | 同上：被改名的那个节点读到的是**新名**，且旧名在其 `aliases` 里；被 merge 掉的节点**读不到** |
| 4 | **三条读路径都切了** | `fetch_graph_overview` / `fetch_reasoning_path` / `scan_attendance_compliance` 各一条真图用例，assert 结果与判据 2 / 3 一致 |
| 5 | **不连出跨版本幽灵路径** | 一条用例显式构造「边的一端在新版本、另一端只在旧版本」的情形 ⇒ 按 §5 D6 的取法判定；拼不出来时**不出边**（并在 integration-log 写明取了哪条口径） |
| 6 | **写侧判据没被打掉** | `test_kg_incremental_rebuild.py` 9 条**全绿且断言未改**；`test_ontology_correction_actions.py::test_new_version_carries_only_the_corrected_subgraph` **仍绿**（它钉的是"新版本物理上不承载全图"，与本批的"读侧逻辑上能看到全图"是**互补**的两条，不许删任何一条） |
| 7 | **ADR 已落** | `docs/adr/` 新增一份，写明：版本链真源 = `ontology_actions`、有序继承规则、同 id 去重规则、跨版本边取法、未切换的读路径清单 |
| 8 | **m6 spec §5.1 注脚已升版** | 口径写明「active 版本**不等于**可见全集，读侧按版本链继承」；**编号未重排**（R5） |
| 9 | **契约零漂移** | `export_openapi.py --check` 零 diff、**26 路径不变**（若动了 ⇒ 走完五步并在 CI 证明） |
| 10 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0 |
| 11 | **pytest 不降** | **CI ≥ 1118 passed / 5 skipped / 0 failed**；既有守卫**不许为让它绿而改断言** |
| 12 | **CI 四 job 全绿**，`gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log | |

---

## 9. 本批不许外推（**完成本批 ≠ 以下任何一条**）

- **读侧能看全图 ≠ 写侧可以偷懒**：P5F-3「增量重写节点数 = 校正节点数」必须继续成立，
  本批**不得**为了让读侧好看而把新版本写全。
- **3 条读路径切了 ≠ 全部切完**：`fetch_all_subgraph` / `fetch_entity_detail` /
  `fetch_anchor_entity_ids` / `list_attendance_anomalies` / `explain_attendance_anomaly` /
  `fetch_document_subgraph` / `agents.py` 检索**仍是单版本**，
  必须**逐条登记**到 §11 指针第 1 条，不许宣称"读侧已完整"。
- **`ontology_actions` 能反推链 ≠ 链是真源设计**：这只是**无迁移**前提下的取法（§5 D4），
  长远要不要给 `kg_versions` 加 `parent_version` 列**未裁**，本批不裁。
- **版本链限深 16 ≠ 不会退化**：深度上限是防环的工程兜底，不是语义保证；
  链长超过上限的行为必须登记。
- **本批修好读侧 ≠ GUI 可用**：m6 §1.1 批次 B 的前端界面仍不存在。
- **本批不涉及成本**：不测 token / 耗时 / 成本比（批次 D 的事）。
- **本地绿 ≠ CI 绿**：本机 Neo4j 常是停的，且本地有 2 条 g25 失败（缺 CI 种子语料）⇒ **以 CI 为终裁**（R-10）。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着「pytest 全绿 ≠ 护栏在拦」。
- ⚠️ **本批动的是租户隔离相关路径的读侧**（`kg_version` 是所有读路径的强制过滤键）：
  须带上 **ADR-0003 §4.1** 的两类测试 **T1 跨 org 越权**（G-9，已 ✅，`test_guardrails_graph.py` +
  `test_guardrails_rls.py`）与 **T2 并发串租户**（G-10，已 ✅，`tests/test_guardrails.py:328`）——
  **在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only` 绕过**；它们**已有的断言不许放宽**。
  ⚠️ 特别注意：`IN $kgs` 会**放宽**过滤条件 ⇒ 必须证明版本列表里的每个版本都**同 org**
  （`resolve_read_versions()` 内就要带 `org_id` 过滤，并在测试里显式断言跨 org 版本**不会**混进来）。

---

## 10. 提交推送纪律 + 升级我的四类情况

**提交**：按 backend / ADR + spec（架构师）/ 契约+前端生成物**分段** Conventional Commits
（ADR + spec 单独一笔，便于整笔 revert；契约再生单独一笔）；跨侧改动**不得混在一个提交**。
推送后 **以 CI 为终裁**（R-10），CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。

**只在以下四类停下找我**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §7 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完下面三步自检再报告**） | 真踩到的例子：§5 **D6** 的跨版本边取法在 Cypher 里做不到、且缩到「两端同版本」仍会让 M4 问答交白卷；或 m6 §5.1 的注脚改写被判定为要动正文 |
| 3 | **边界冲突** | 实现中必须触碰 §4 的某条 Non-goal |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？
2. 能不能**整体推到下一批**并登记？
   （如：D6 的跨版本边 ⇒ 本批取「两端同版本才出边」并在 integration-log 登记口径）
3. 真不行了 —— **报告时带上**：哪份 spec / ADR 的哪一行、要加/改什么、为什么绕不过去、
   **你试过的替代方案**。不接受"spec 没写所以做不了"这种笼统结论。

---

## 11. 下一批指针（**本批收口时按实际结果更新，别照抄**）

1. **剩余读路径切换**（本批 D5 故意留下的）：`fetch_all_subgraph` / `fetch_entity_detail` /
   `fetch_anchor_entity_ids` / `list_attendance_anomalies` / `explain_attendance_anomaly` /
   `fetch_document_subgraph` / `agents.py` 的检索。
2. **本体校正 GUI（前端）**：m6 §1.1 批次 B；三端点可用、读侧修好后即可接。
   同批按需建 `frontend/src/api/ontology.ts`（m6 §10.1 第 4 条：无 UI 消费前建了属强行同步开发）。
3. **`GET /cost/dashboard` + `cost_metrics` 表**（m6 §3.4 验收 8 / 9），与 MVP 准入 **C3-a / C3-b** 一起做；
   `cost_ratio` 阈值 TBD-7 **Sprint 13 收敛前拿不到判据**。
4. **给 `kg_versions` 加 `parent_version` 列**（§5 D4 的 A2）：把版本链从 `ontology_actions`
   反推改成表内真源；需写迁移 + 触碰 **G-6 迁移等价性**护栏 ⇒ 单独一批。
5. **`human_review` 队列读端点**（M2 的 S9.13-2）：有了 GUI 才有消费者。
6. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2；**已连续五批**有意不做）。
7. **DR-B6 / DR-B7 与 G-9 / G-10 的口径对账**（纯 docs）：需求侧明细行仍写「⏳ 零代码」，
   而护栏侧均已 ✅ 转正。建议并入任一批次顺手做，**不单独开工**。
8. **多租户出向审计归属**：脱离「一套 compose = 一个租户」时需给 `build_chat_model` /
   `build_default_embedder` 补 org 传递（P5-D 的 X-3 撤回条件）。
9. **D7（`question` 参与检索）/ D5（M4 完整化）/ D8**：算法活，各自单独排。
10. **m6 定稿遗留的另两个配置项**（`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `COST_RATIO_ALERT_THRESHOLD`）：
    在对应批次回填，**别顺手补齐**。
11. **日志 `message` 正文的脱敏**：P5-E 明确不覆盖。正确路径是**逐个把 `mask()` 调用点补到写敏感值的
    日志语句上**，而不是做值识别。
