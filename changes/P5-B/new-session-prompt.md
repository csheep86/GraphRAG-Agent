# 新会话开场提示词 · P5-B（J3 前端虚线 + 演示图谱恢复 + G3 回归 + D4 收口）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。详见 §1。
>
> 复制本文件全文到新会话作为第一条消息。
> 上一批：**P5-A**（D4 解冻裁决）—— 它以「**依据失效，停下升级**」收尾，
> 证据链在 `changes/archive/2026-10-07-P5-A/integration-log.md`，**开工前先读它**，
> 本批的 §6 坐标表是它的续篇。（P5-A 已归档，因为它以「依据失效、停下升级」收尾。）
> 用户 2026-10-07 在 P5-A 的升级报告上裁决：**P5-B**。

---

## 0. 本批一句话

**先把 J3 做完（¥0、不依赖图谱），再把演示图谱恢复起来跑 G3，最后 D4 收口。**

- **J3** = 推理路径上 `valid_to` 已过期的跳，前端画成**虚线置灰**，不再与有效边同色。
- **图谱恢复** —— 本地演示环境已被整体清掉（详见 §6），这是 G3 与 J3 端到端验收的**硬前置**。
- **G3** = 受控题集回归（`eval_controlled_qset.py`，40 题），比对 P6-H 的基线 **C1 = 0.0294**。

---

## 1. 执行模式：**无人值守**（用户已预授权，本批全程不打断）

遇到"需要拍板"的点，按下面 §5 决策表已裁决的项直接执行；文档里已有建议项的一律**采纳建议项**
并在 `integration-log.md` 登记；只有 §10 列的四类情况才停下来找我。

**替代真源映射**（沿用 P5-A / P2-C 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5 | 本提示词 §5 决策表 + §4 Non-goals（顺序不可调换） |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-B/`** |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | 照做。**本批预期零契约改动**（见 §4 Non-goal 1） |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

**角色隔离**（本批跨前后端，**必须分段执行，不得混改**）：

| 段 | 角色 | 允许改的范围 |
|---|---|---|
| T1–T2（J3） | **前端开发 A** | **只允许** `frontend/` |
| T3–T5（图谱 + G3） | **后端开发 B** | **只允许** `backend/` + 跑脚本；`frontend/` 一行不许再动 |

**分支**：沿用 P4 / P2-C / P5-A 的实际做法 —— **在 `main` 上直推**，不另开分支。

---

## 2. 确认起点：为什么是 P5-B（三条机械理由）

1. **用户 2026-10-07 直接指名**：在 P5-A 的升级报告上批「**P5-B**」。
   P5-A 已用四条实测证明「裁决 A 成立与否」这个交付物是 09-30 之前的历史
   （`changes/archive/2026-10-07-P5-A/integration-log.md` §2/§3/§4），
   它自己已提交推送、CI `37579395982` 全绿。
2. **J3 是 D4 唯一剩下的实质缺口**：后端 J1（`valid_to` 非空 69 条）/ J2（`inconsistent` 352）
   / J4（两时点选出的链不同）**均已在 2026-09-30 达成**；
   `13-as-of-evidence-rank.md:59-60` 原文：「`valid_to=2025-12-31` ——
   **这正是前端画虚线需要的那个字段，议题 ② 的渲染前提由此具备**」。
   而 `frontend/src/components/qa/reasoning-path.tsx` **零 `valid_to` 消费**。
3. **J3 是唯一不需要图谱就能做完的一段** ⇒ 可以先以 ¥0 交付，
   不必卡在环境重建上。图谱恢复 + G3 排在它后面，作为**独立可失败的一段**（见 §5 D3）。

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

三条硬规则：① 结论来自脚本输出，不来自文档表格；② `[--]`/`[~~]` 转正的唯一方式是让测试**真的通过**再删
`@pytest.mark.xfail`；③ 反向守卫 `test_g21_production_sqlite_guard_still_present` **必须始终通过**。

**出口期望读数**：`[OK] 17 条 / [~~] 0 / [--] 0`、**地雷 0 项**。
本批若出现任何 🟠 / 🟡 / 地雷，**不得**以"与本批无关"带过，必须定位并登记。

顺带确认：`export_openapi.py --check` zero diff、`check_seams.py` ERROR 0、pytest 基线不降。

---

## 4. 边界纪律 · **10 条 Non-goals**（改一条都要先回来登记理由）

1. **不改契约**：`valid_from` / `valid_to` **已经**在 `ReasoningPathHop` 里
   （`frontend/src/types/api.d.ts:3287` / `:3292`）⇒ 本批预期 `npm run gen:api` 后 `git diff` **为空**。
   出现 diff ⇒ 说明走了弯路，先停下来判断是不是范围蔓延。
2. **不改后端推理逻辑**：逐跳的 `valid_from` / `valid_to` 已由
   `backend/app/services/reasoning.py:425-430` 填好，本批不需要动。
3. **不做 as-of 的前端交互**（时点选择器 / 双时点对比 UI）：J4 是**后端**已达成的判据，
   前端 as-of 输入不在本批。
4. **不引入前端测试框架**（vitest / jest / testing-library）：仓库现状只有 `bundle.test.ts`，
   `package.json` 里没有测试框架。J3 的验收靠 `tsc --noEmit` + `npm run lint` + **真机 HTML 断言**（见 §9）。
5. **不改演示语料**：`demo/attendance/policies/*.md` 与 `corpus/*.docx` 一个字不动。
   （2025 版双文档已是出路 A 的目标形式，见 P5-A §2。）
6. **不做 D2（M6）/ D1 / D3 / D5 / D7 / D8**：`docs/delivery-plan.md:198` 排期在 D4 之后。
7. **不做实体消解 / M4 完整化**（DR-D5，另一阶段）。
8. **不改 `specs/` 与 ADR**：J3 是渲染，不是口径变更；ADR-0005 R4-b / R5 已在 09-30 写入。
9. **不改 `docs/delivery-plan.md` / `delivery-requirements-and-guardrails.md` 的陈旧口径**
   （P5-A Non-goal 11 的延续，留待专门的口径订正批）。
10. **不订正 `_bridge_window.py:3` 的「（待核准记录）」注解漂移**：它已在 P5-A §6 登记，
    属注解不影响行为，**不让本批摊大**，留待口径订正批。

---

## 5. 决策表（**已裁决，按此执行；执行中若发现依据有误 ⇒ 停下升级，不要默默改道**）

| # | 决策点 | 裁决 | 依据（原文） | 代价 / 连带动作 |
|---|---|---|---|---|
| **D1** | J3 虚线的判定口径？ | **`valid_to` 非空 且 `valid_to <= 今天` ⇒ 虚线置灰** | 与后端同构：`reasoning.py:545-546`「`valid_to is not None and str(valid_to) <= as_of` ⇒ unconfirmed」。**不为前端重写一套过滤条件**——13 号记录 §「本次踩到的坑」正是死在这上面 | ⚠️ 契约注释 `api.d.ts:3290` 写的是「非空 ⇒ 前端应画虚线」，省了"在今天已过期"这个前提 ⇒ **两者在当前语料上等价**（`valid_to` 只有 `2025-12-31`），但**严格口径以后端为准**，并在 `integration-log.md` 登记这处措辞差异。**不改契约文本**（Non-goal 1） |
| **D2** | J3 改哪些文件？ | **只改 `frontend/src/components/qa/reasoning-path.tsx`**；判定函数若需复用，可放 `frontend/src/lib/reasoning.ts` | 该文件是推理路径的唯一渲染点（`:44-95`）；S5 会盯新增模块 ⇒ 不新建组件 | 不许顺带改 `attribution-panel` / `evidence-panel` 的 `border-dashed` 空状态卡片（那与失效边无关，P5-A 已实测确认） |
| **D3** | 图谱恢复做不做？做不完怎么办？ | **做**（G3 与 J3 端到端验收的硬前置）。但设**闸门 G0**：若恢复失败或成本明显失控 ⇒ **J3 部分独立收口并提交**，G3 转下一批 | P6-P1 已登记这笔债务；P5-A §1 实测：Neo4j 空、PG 库不存在 | ⚠️ 恢复 ≠ 复刻（`docs/demo-seed-dataset.md:70`：LLM 抽取非确定性，实体/关系数**不会逐字复现**）⇒ 只保证"同源 + 同规则 + 可校验" |
| **D4** | G3 的基线用哪个？ | **P6-H 的 `C1 = 0.0294`**（graph 0.875 / baseline 0.850 / corpus_layer L2 / `controlled-qset-v4`） | `changes/P6-H/integration-log.md:26`，三遍完全一致 | ⚠️ **绝不可**与 v3 的 `0.0909` 比——**分母不同**（14 vs 40），P6-H:35 原话：「不得拿 v4 的 0.0294 去说比 v3 变差了」 |
| **D5** | 环境口令怎么配？ | `.env` 的 `NEO4J_PASSWORD` 改为 **`ci-graph-pw-2026`**（容器 `graphrag-neo` 的 `NEO4J_AUTH`），与 CI 同款 | `docker inspect graphrag-neo` 实测；P5-A §1 已记：当前 `.env` 是 `password`，故认证失败 | ⚠️ `.env` 在 `.gitignore` 里 ⇒ **改它不会进提交**，但要在 `integration-log.md` 登记，免得下一批再踩 |
| **D6** | 恢复图谱要走哪条路？ | **走脚本直连**（`seed_attendance_ontology.py` → `ingest_attendance_csv.py` → `ingest_attendance_policies.py`），**不**走 `demo-seed-dataset.md` §4 的"HTTP 上传 6 个切片"那条路 | 后者是为 `docs/annualreport/` 的招商局系年报设计的，与本批要恢复的 **`attendance-demo-v1`** 不是同一个库 | G3 才需要起 `uvicorn`（`eval_controlled_qset.py` 走 HTTP，默认 `http://127.0.0.1:8002`） |

---

## 6. 已查证坐标表（**不要重做 recon；这是 P5-A §6 的续篇**）

### 6.1 后端侧（**已达成，本批不动** —— 见 Non-goal 2）

| 项 | 坐标 | 要点 |
|---|---|---|
| 逐跳时态已填 | `backend/app/services/reasoning.py:231-232` / `:425-430` | Cypher 带回 `valid_froms` / `valid_tos`；逐跳塞进 `ReasoningPathHop` |
| 三值判定 | `reasoning.py:505` `_TEMPORAL_RANK`；`:562` `_temporal_verdict` | consistent / unknown / inconsistent |
| "那天已失效"口径 | `reasoning.py:545-546` | `valid_to is not None and str(valid_to) <= as_of` ⇒ unconfirmed（**D1 对齐它**） |
| as-of 视图谓词 | `reasoning.py:199-224` | `$as_of IS NULL` ⇒ 不过滤 |
| 契约字段已存在 | `frontend/src/types/api.d.ts:3287` / `:3292` | `valid_from` / `valid_to` 均为 `string \| null`；注释已写明"非空 ⇒ 前端应画虚线" |

### 6.2 前端侧（**本批要改的地方**）

| 项 | 坐标 | 要点 |
|---|---|---|
| J3 唯一落点 | `frontend/src/components/qa/reasoning-path.tsx:44-95` | hop 渲染只读了 `origin` / `relation` / `source` / `target` / `evidence` —— **零 `valid_to` 消费**（P5-A §5 实测） |
| 假阳性排查 | 同上 `:27` / `:36`，及 `attribution-panel.tsx:183` 等 | 命中的 `border-dashed` 全是**空状态卡片**边框，与失效边无关 |
| 判定函数候选地 | `frontend/src/lib/reasoning.ts` | 已有 `entityTypeLabel` / `relationLabel` / `originMeta` / `entitySystem` 等展示层映射 |
| 测试现状 | 仅 `frontend/**/bundle.test.ts`；`package.json` **无** vitest/jest | ⇒ Non-goal 4：不引入框架 |

### 6.3 环境（**P5-A §1 实测，本批 T3 要在这里动手**）

| 项 | 实测 | 坐标 / 命令 |
|---|---|---|
| Neo4j 容器 | `graphrag-neo`（`neo4j:5.26-community`）**Up**，但**空**（0 Entity / `RELATION` 类型不存在） | `docker ps` + `docker inspect` |
| Neo4j 口令 | `NEO4J_AUTH=neo4j/ci-graph-pw-2026` | 与 CI `ci.yml:125` 同款 |
| `.env` 口令 | 明文 `password`（sha256 前缀 `5e884898da28…`）⇒ **不一致**，AuthError | `backend/.env` |
| **PG** | **库 `graphrag` 不存在**（`FATAL: database "graphrag" does not exist`）；容器 `graphrag-pg`（`postgres:16-alpine`）Up | `open_session()` 实测 |
| 缺失语料 | `affiliation-demo-v2` 本地没有（P5-A §8 已登记为环境债） | ⇒ 那 2 条本地 pytest 失败是环境债，非回归 |
| 上次环境还在的时间 | **2026-10-05**（`_clause_doc_scopes.json` 于该日更新；P6-H 当日跑过 3 遍 live C1） | ⇒ 环境是在 10-05 之后被清掉的 |

### 6.4 恢复与 G3 的路径

| 项 | 坐标 | 要点 |
|---|---|---|
| 本体 | `backend/scripts/seed_attendance_ontology.py` | |
| CSV 入库 | `backend/scripts/ingest_attendance_csv.py` | 与制度文档**共用** `attendance-demo-v1`；**先跑它**再跑制度脚本 |
| 制度入库 | `backend/scripts/ingest_attendance_policies.py:105-112` | `POLICY_FILES` 6 份 docx（含两份 2025 版）；MinerU（¥）+ LLM 抽取（¥） |
| 桥接窗口 | `backend/scripts/_bridge_window.py` + `_clause_doc_scopes.json` | R4-b 落地产物；`--force` 会清产物重跑 |
| **不走**的路 | `docs/demo-seed-dataset.md:56-66` | 那是招商局系年报切片的 HTTP 上传流程，**不是** `attendance-demo-v1` |
| G3 | `backend/scripts/eval_controlled_qset.py` | `QSET_VERSION=v4-2026-10-05`、`QSET_KG_VERSION=attendance-demo-v1`、**40 题**；需起后端（`EVAL_BASE_URL`） |
| G3 基线 | `changes/P6-H/integration-log.md:26` | graph 0.875 / baseline 0.850 / **C1 0.0294** / L2 / v4，三遍一致 |
| 非确定性警告 | `docs/demo-seed-dataset.md:70` | 重建会生成**新** `kg_version`，实体/关系数**不会逐字复现**（原库 2855 / 3729） |

---

## 7. 已完成项（不用重做）

- **L2-① 路径时序一致性**（Sprint 10.4：`_temporal_verdict` 三值 + 选链优先级 + 单测）
- **出路 A**（11 号记录：语料逐条写明施行日、重抽 4 份 ⇒ `valid_to` 2→48、`valid_from` 7→108）
- **出路 B / R4-b**（12 号记录：ADR-0005 `:153` + `specs/m2:240/:246` + `_bridge_window.py`
  + `resolve_document_expiry` ⇒ `inconsistent` 259→**352**、`valid_to` 60→**69**）
- **R5 as-of 证据位次**（13 号记录：`reasoning.py` 已落 + 单测 6 条；两时点末端不同）
- **契约字段**（`valid_from` / `valid_to` 已在 `ReasoningPathHop`，无需再改）
- **P5-A 的证据链**（`changes/archive/2026-10-07-P5-A/integration-log.md`，CI `37579395982` 全绿）

---

## 8. 基线（**本批结束不得低于此**）

| 项 | 读数 | 来源 |
|---|---|---|
| pytest（**CI 口径**） | **1007 passed / 5 skipped / 0 failed** | P2-C run `37571415841` |
| pytest（本地口径） | 1006 passed / 4 skipped / **2 failed** | 2 条失败 = **本地环境债**（缺 `affiliation-demo-v2` 语料 + 图谱），改动前逐条相同 |
| 契约 | zero diff（**paths 28**） | P5-A 开工实测 |
| 接缝门禁 | ERROR 0 / WARN 0 / OK 12 | P5-A 开工实测 |
| 护栏 | **`[OK]` 17 / `[~~]` 0 / `[--]` 0**，地雷 0 项 | P5-A 开工实测 |
| CI | `37579395982` 四 job 全绿 | P5-A 收尾 |
| **G3 基线** | **C1 = 0.0294**（graph 0.875 / baseline 0.850） | P6-H，40 题口径 |

⚠️ **本地 vs CI 口径差**：本地整个演示环境已被清掉 ⇒ 那 2 条失败是环境债，不是本批引入。
**验收一律以 CI 为准（R-10）。**

---

## 9. 验收判据（**必须真跑出来，不是读代码得出**）

### T1–T2：J3（¥0，不依赖图谱）

1. **静态**：`frontend/` 下 `npx tsc --noEmit` exit 0、`npm run lint` exit 0。
2. **契约零漂移**：`npm run gen:api` 后 `git diff --stat` **为空**（Non-goal 1）。
3. **行为（真机）**：起后端 + `npm run dev`，跑一次会命中失效跳的问答，
   在渲染出的 HTML / DOM 里断言之：该跳带**虚线**标记，而同一条链上 `valid_to` 为空的跳**不带**。
   ⇒ 这一条**依赖图谱**，放在 T3 之后做；若图谱恢复失败（D3 闸门），改用
   `frontend/src/api/mock/` 的快照做静态渲染断言，并**如实登记**这是降级。

### T3：图谱恢复（¥：MinerU + LLM）

4. PG 建库 + 迁移完成；Neo4j `attendance-demo-v1` 的 `Entity` / `Relation` 计数 **> 0**，
   且 `kg_versions` 行 `status=ready`。⇒ **对照值**（非硬指标，见 D3）：原库 2855 / 3729。
5. **B3 汇合路径可查**：`ingest_attendance_policies.py` 自带的
   `verify_and_close` 四项 `[OK]`（关系无静默丢失 / 条款数一致 / 汇合边一致且非空 / 两链路汇合可查）。

### T4：G3（¥：40 题 LLM）

6. `eval_controlled_qset.py` 跑完，读出 `C1` 与两侧 `graph` / `baseline`；
   与 **0.0294 / 0.875 / 0.850** 比对。判据口径：
   - **不回归** = `graph` 侧不出现**断崖式**下降（≥ 单题灵敏度 2.5pp 需登记并说明）；
   - 若 `QSET_KG_VERSION` 与图上版本不同源 ⇒ **全拒答**，那是环境问题不是回归，先修环境再判。
7. ⚠️ **暴露回归就如实登记，不许压**（见 §10 第 4 类）。

### T5：收口

8. 三条门禁全绿（J6）：`pytest` 不降、`check_seams.py` ERROR 0、`export_openapi.py --check` **零 diff**。
9. 护栏不倒退：`check_startup_readiness.py` 出口仍 **`[OK]` 17 / `[~~]` 0 / `[--]` 0**。
10. **CI 四 job 全绿**（R-10：CI 才是终裁），run id 回登 `integration-log.md`。

---

## 10. 提交推送与升级边界

**提交推送纪律**
- Conventional Commits（`feat` / `fix` / `docs` / `chore` / `refactor` / `test`）。
- **按角色分段提交**：T1–T2 一个（或多个）`feat(frontend)`；T3–T4 归 `chore(backend)` / `test`；
  T5 归 `docs`。**不要在同一个提交里混改前后端**（角色隔离）。
- **每个子任务收尾跑** `cd backend && uv run python scripts/check_session_drift.py`
  （S1 读 Non-goals / S2 摊太大 / S3 配置同步 / S4 契约 / S5 孤独模块）。
  S1 报「没有 Non-goals」⇒ 停下来补边界；**S5 命中必须回答属于哪条 DR/G**，答不上就是顺手做的。
- **P2-C 的现场教材**：被 S2 提示"摊太大"后拆成 4 + 1 个提交；中途红过一次（run `37571248946`）
  只因 **`ruff format` 漏跑** —— `ruff check` 查不出格式，**改完代码两个都要跑**。
  前端侧对应：`tsc --noEmit` 与 `npm run lint` 也**都要跑**。
- 本地检查 → 提交 → **推送后以 CI 为终裁** → 回登 run id。

**升级用户的 4 类**
1. **需要改 spec / ADR**（本批预期不需要；若 J3 的口径分歧 D1 被证明必须写进 spec ⇒ 停下）。
2. **边界冲突**：本批 10 条 Non-goals 与实现路径互斥。
3. **CI 红且根因不明**（先看是不是摊太大，**而不是先改测试让它绿**）。
4. **G3 暴露真实回归**（受控题集答对率下降）—— 业务口径问题，由用户裁决。

**成本提醒（不是升级项，但要知情）**：本批有 **¥** 支出 =
① 图谱恢复：6 份 docx 的 MinerU 解析 + 真实 LLM 抽取；② G3：40 题 live 评估。
若不想花这笔钱 ⇒ 只做 T1–T2（J3，¥0），按 §5 D3 的闸门把 G3 转下一批。

---

## 11. 不许外推（**完成本批 ≠ 以下任何一条**）

- **J3 完成 ≠ as-of 前端交互可用**：那需要前端的时点选择器，Non-goal 3 明确不做。
- **J3 完成 ≠ 知识时效"能用"**：后端 J4 已达成，但用户**看不到**（没有 UI 入口）。
- **`valid_to` 非 0 ≠ 图谱时序完备**：`valid_from` 仍有约 16% 缺失（CSV 派生的边本就无日期列）。
- **图谱恢复 ≠ 复刻原库**：会生成新的 `kg_version`，实体/关系数不会逐字复现
  （`demo-seed-dataset.md:70`）。保证的是"同源 + 同规则 + 可校验"。
- **G3 不回归 ≠ 能力变强**：那是"没搞坏"的判据，不是"变好"。
- **C1 = 0.0294 不可与 0.0909 比**：分母不同（40 vs 14），P6-H:35 有原话。
- **本批不改契约** ⇒ 不得顺带宣称任何对外接口变化。
- **DR-D4 仍然 🟡 在途**：本批走完它剩下的 J3 + G3，但编号改指 P5 的处置仍在
  `delivery-requirements-and-guardrails.md` §6.4 挂着（Non-goal 9，本批不动）。
- **陈旧口径未修**（Non-goal 9）：`delivery-plan.md:173` 与 `requirements:115/:120` 仍会误导下一批
  ⇒ 下一批开工前**必须先读 `changes/archive/2026-10-07-P5-A/integration-log.md` §6**。
