# 新会话开场提示词 · P5-C（D2 / M6 第一批：`/ontology/active` + 冷启动确认闭环）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。详见 §1。
>
> 📦 **本文件自包含**：前一个会话（P5-B）已收口、不会再回来。开工所需的**全部**坐标、命令、基线、
> 陷阱都在本文里。唯一需要你额外读的是 §0.5 列的**五份仓库内文件**（都在库里，`git pull` 后可读）。
>
> ✅ **范围已由用户确认（2026-10-07）**：采纳 §2.3 的三刀切法（ontology_actions 表 + `/ontology/active`
> + 冷启动确认闭环 + 占位测试改写），并把 **D3 / D4 一并裁决**（见 §5）。本文件可直接作为新会话第一条消息。
>
> 复制本文件**全文**到新会话作为第一条消息。

---

## 0. 本批一句话

**把 M6 的读侧与冷启动闭环从 501 占位做成真实现**：`GET /ontology/active`、
`POST /ontology/cold-start`、`POST /ontology/confirm`，并把「断言它必须 501」的那批测试改成真行为测试。

**不做**的三件事（详见 §4）：merge / split / rename（依赖增量重算）、成本仪表盘（依赖 `cost_metrics` 表）、
以及前端校正 GUI —— 这三样各自有未落地的前置，**留到后续批次**。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`changes/P5-B/integration-log.md`** | 上一批实录。**重点 §6 环境债台账**与 §X-1 已裁决的 C1 口径 |
| 2 | **`changes/P5-B/env-restore-checklist.md`** | ⚠️ **先按它的 §0 判断本地环境缺什么**，别到一半才发现 403 / 没有库。含 6 条缺口的可复制命令 |
| 3 | **`specs/m6-ontology-incremental.md`** | **已是 v1.0 定稿**（2026-10-02），不是草案。重点 §3.1（验收 1：冷启动**仅建议、未生效**）、§3.5（验收 12：未确认不生效 / 严禁 LLM 自动改本体）、§4.1 `ontology_schemas`、§4.2 `ontology_actions`、§5.5 端点契约 |
| 4 | `backend/app/services/ontology.py`（428 行） | **读侧与 PoC 已有实质逻辑**，不是空壳。本批就是接线，不是重写 |
| 5 | `backend/app/api/v1/routes/ontology.py`（214 行） | 6 个端点全部 501，**每个处理函数里已经写死了 `real_entry`**（要接的真入口），照它拆任务即可 |

> ⚠️ `docs/delivery-requirements-and-guardrails.md:115` 写着「spec 仍草案」—— **那是过期表述**，
> 与 spec 头部 v1.0 冲突。本批不动它（改 doc 需要单独登记），但不要让这句话骗你去"再判一次闸门"。

---

## 1. 执行模式：无人值守

**替代真源映射**（沿用 P5-A / P5-B 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（文件**已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-C/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | 照做。本批**预期零契约改动**（接口与 schema 均已先行落好，见 §4 Non-goal 1） |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

**角色隔离**（本批若跨前后端，**必须分段执行，不得混改**）：

| 段 | 角色 | 允许改的范围 |
|---|---|---|
| 后端接线 + 测试改写 | **后端开发 B** | **只允许** `backend/` + 跑脚本 |
| （本批建议**不碰前端**） | 前端开发 A | 见 §4 Non-goal 3 |

**分支**：沿用 P4 / P2-C / P5-B 的实际做法 —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P5-C / 为什么是这一刀

### 2.1 三条机械理由

1. **排期队列指向它**：`docs/delivery-plan.md:198` 原文明写 P5 的顺序是
   `D4 承接 Sprint10.5 → **D2 M6** → D1 → D3/D5/D7/D8`，而 **D4 已在 2026-10-07 由 P5-B 收口**
   （CI 四 job 全绿，run id 见 §8，开工时以实读为准）。队列的自然下一项就是 D2。
2. **开工硬闸门已满足，不必再等**：M6 的硬闸门是 `specs/m6` 升 **v1.0**，
   `specs/m6-ontology-incremental.md:3-5` 已是 **v1.0（2026-10-02 定稿）**，`:323` §10 checklist 七项全勾。
   但同一份 spec `:7` 也明写：**「定稿 ≠ 已实现：7 个端点仍为 501 占位骨架」**。
   ⇒ 闸门开着、活还没干，正是动手的时点。
3. **服务层已经把活做掉大半**：`app/services/ontology.py` 的
   `load_active_ontology`（读侧）与 `suggest_ontology_types`（冷启动 PoC，真机产出 12 实体 + 12 关系类型）
   **都是可用实现**，且前者已被主链路消费（`app/tasks/registry.py:60`）。
   本批是**接线 + 落 approve 链路**，不是从零写算法。

### 2.2 为什么**不是**一口气做完 M6

三个动作各有未落地的前置，**凑在一起就是本批最典型的"摊太大"**：

| 剩下三件 | 卡在哪 | 归属 |
|---|---|---|
| `merge` / `split` / `rename` | 契约要求**产新 `kg_version` + 增量重算**；`KgVersioningService`（`app/services/kg/versioning.py:79`）有 `create_pending`/`activate_by_version`，但**增量重算本身不存在** | 后续批次，**先做增量重算再谈这三个端点** |
| `GET /cost/dashboard` | 需要 `token_usage` 聚合与 `cost_metrics` 表；同一个缺口也卡着 MVP 准入判据 **C3-a / C3-b** | 后续批次（与 C3 一起做） |
| 前端校正 GUI | 前端 `src/app/` 下**无 ontology 页面**、无 API 封装，只有 `src/types/api.d.ts` 生成类型 ⇒ 零起点 | 后端跑通后单开前端批次 |

### 2.3 本批的三刀（建议范围）

1. **落 `ontology_actions` 审计表**（spec §4.2；当前 `backend/` 下 `grep ontology_actions` **零命中**）
   —— 这是「未确认不生效」可举证的前提，先建它再谈别的行为。
2. **`GET /ontology/active`** 接到 `load_active_ontology`（零算法风险）。
3. **`POST /ontology/cold-start` → `POST /ontology/confirm`** 闭环：
   冷启动**只落 `status='pending'` 的建议**、必须由 confirm 才转 active —— 这本身就是 spec §3.5 验收 12。
4. **同步改写测试**（见 §4 Non-goal 6）：把「断言必须 501」的那批改成断言真行为。

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 条，见基线 §8
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0
uv run python scripts/export_openapi.py --check       # 期望：零 diff
uv run pytest -q                                      # 本地口径基线见 §8（注意 §0.5 第 2 份文档的环境变量）
Get-NetTCPConnection -LocalPort 8009 -State Listen    # embedding 服务（跑 C 类判据才需要）
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点是一片绿的（否则先别动代码）
```

**任何一条与 §8 基线不符，先治病，不要带着红底写代码** —— 否则你无法分辨 CI 红是自己改的还是本来就红的。
（P5-B 就是这个原因先补了 dev License，才没把 403 误判成回归。）

---

## 4. 边界纪律 · Non-goals（**11 条，逐条对照**）

| # | Non-goal | 说明 |
|---|---|---|
| 1 | **不改 `contracts/openapi.yaml`** | 7 个端点的契约已先行落好（路径 19 → 26）。要改 ⇒ 触发契约同步三件套，那是另一批的事 |
| 2 | **不碰 `merge` / `split` / `rename`** | 前置「增量重算」不存在 |
| 3 | **不做前端页面 / 不写前端 API 封装** | 本批若确需前端，单独开新会话并换角色 A |
| 4 | **不引入新的测试框架** | 沿用 pytest；无前端测试框架（禁令沿用 P5-B） |
| 5 | **不重建 / 迁移演示图谱** | 图谱已在 P5-B 恢复（`attendance-demo-v1` ready）；除非 §0.5 第 2 份文档 §0 指向重建 |
| 6 | ⚠️ **不删除占位测试来让它绿** | `test_ontology_placeholder_endpoints.py` 在实现落地当天**必然变红**。处置是**改写成断言真行为**（见 §6 决策 D2），删文件等于拆护栏 |
| 7 | **不新增依赖**（后端不引 Black，只用 Ruff） | G-1 护栏；装 Black 会与 `ruff format --check` 互相改写 |
| 8 | **不为 M6 新增别名 / 兼容层** | 有多套叫法属于历史债，本批不顺手 |
| 9 | **不改 `seeds/ontology_schema.json` 的实体/关系定义** | 它是本体唯一真源（`seed_attendance_ontology.py:13` 明文），改它等于改语料 |
| 10 | **不顺手订正 `delivery-requirements-and-guardrails.md:115`** 的过期表述 | 值得改，但要单独登记；混在本批里就成了"顺手做" |
| 11 | **不碰 `entity_merge_candidates` 与 `applied` 枚举的契约同步五步** | `applied` 只服务于 `/ontology/merge`（`specs/m6-ontology-incremental.md:166` 明文），而 merge 已由 Non-goal 2 排除 ⇒ 见 §5 **D3 已裁决**。那五步（Pydantic 枚举 → 重导契约 → 提交生成物 → `gen:api` → CI 零漂移）**整体顺延**，本批不开这个口子 |

> **回切点**：每个子任务收尾跑 `uv run python scripts/check_session_drift.py`，
> S1 必须读到**本文件这 11 条**；S5 命中要答得出归属哪条需求。

---

## 5. 决策表（**已裁 / 建议采纳项**，逐条有据）

| # | 决策 | 处置 | 依据 |
|---|---|---|---|
| **D1** | 闸门是否满足 | ✅ **满足**，直接开工 | spec v1.0 + checklist 七项全勾 |
| **D2** | 占位测试怎么写 | **改写成真行为测试**，不删不 skip | `test_ontology_placeholder_endpoints.py:69` 注释本就写着「返回 200 空结果 = 前端会以为接口可用（假做）」；护栏三档规则要求反向守卫常驻 |
| **D3** | 是否先升 M2 spec 加 `applied` | ✅ **已裁决：本批不动 spec / 契约、不触发 §10 第 2 类**。三条横竖证据：① `applied` 是 **`entity_merge_candidates.status` 的第 5 值**，**只服务于 `/ontology/merge`** —— `specs/m6-ontology-incremental.md:166` 原文：「未走完前 5 步，**`/api/v1/ontology/merge` 端点不得对外实现**」；② M2 spec **文档侧早已包含该预留**（`specs/m2-extract-kg.md:128` 的 status 行「另有 M6 前向预留值 `applied`」+ `:134-136` 独立注脚），由 P0-m6-finalization 批次完成 ⇒ **不需要再"升版"一次**；③ merge 已在 §4 Non-goal 2 排除 ⇒ 契约同步 5 步**整体顺延**到做 merge 那批。真正没动的只有**代码 / 契约侧**（Pydantic 枚举与 `openapi.yaml` 里没有 `applied`），那同样是 merge 的前置 | 见上述三处原文 |
| **D4** | `/api/v1/cost/dashboard` 的 RBAC | ✅ **已裁决：本批只登记、不动 `rbac/policy.py`**。该端点**恒 501 ⇒ 当前没有可访问面 ⇒ 没有越权面**；在 integration-log 明确登记为已知即可。**不要**去改 RBAC 表（那是代码改动，且 RBAC 完整性另有门禁看着）。⛔ 这条债务**必须跟着端点走**：将来谁实现 `/cost/dashboard`，谁必须同批补 RBAC 登记 —— 已写进 §11 指针 | `app/services/rbac/policy.py:75-80` 只登记了 6 个 `/ontology/*`，**未含 cost** |
| **D5** | C1 判据口径 | 沿用 **X-1 裁决**（P5-B，2026-10-07）：P6-H 的 0.0294 **只作历史数字**；引用时必须同时写明判分表版本与 `graph_spec.retriever` | `changes/P5-B/integration-log.md` §8 |
| **D6** | 成本敞口 | 本批**预期 ¥0**（不调 LLM 做冷启动实测；只测接线与契约）。若确需跑真实冷启动 ⇒ 先说明再花 | — |

---

## 6. 已查证坐标表（**不要再 recon 一遍**）

> 行号是当前 HEAD 的值，**仅供定位；以代码实读为准**（行号漂移不影响结论）。

| 坐标 | 位置 |
|---|---|
| 7 个端点契约 | `contracts/openapi.yaml`：`/ontology/active` 4814、`cold-start` 4884、`confirm` 4957、`merge` 5033、`rename` 5103、`split` 5173、`/cost/dashboard` 4019 |
| 路由占位（6 个） | `backend/app/api/v1/routes/ontology.py`：`_BLOCKED_BY` L43、`_placeholder()` L48-65、`real_entry` 锚点 **L90 / L120 / L142 / L165 / L186 / L212** |
| 第 7 个占位 | `backend/app/api/v1/routes/cost.py:65`（`get_cost_dashboard` L48） |
| 注册 | `backend/app/api/v1/router.py:59` |
| RBAC | `backend/app/services/rbac/policy.py:75-80`（6 个 `RESOURCE_ONTOLOGY`）、`:149` viewer `_ALL_READ`、`:162` 另一角色 `_NONE` |
| **服务层（已有实现）** | `backend/app/services/ontology.py`：`load_active_ontology` L74、`extraction_type_vocabulary` L94、`OntologySuggestion` L150、`suggest_ontology_types` L166（**不接会话参数 ⇒ 结构上不可能写库**，这是验收 1 的结构保证）、`entity_type_categories` L387、护栏常量 L60-61（12/12） |
| Schema（纯契约） | `backend/app/schemas/ontology.py`：`OntologyConfirmRequest.version` L158、`OntologySplitRequest.new_entities` min 2 L231 等 |
| DB 模型 | `backend/app/db/models.py:722` `OntologySchema`（表 `ontology_schemas`，复合主键 `(org_id, version)`，`:714` status 仅 `active/superseded`）⚠️ **`ontology_actions` 表未建** |
| 版本管理（可复用） | `backend/app/services/kg/versioning.py:79` `KgVersioningService`（`create_pending` L87 / `mark_ready` L129 / `activate_by_version` L175）；已落地端点参考 `backend/app/api/v1/routes/graph.py:179` `POST /graph/versions/{version}/activate` |
| 本体真源 | `demo/attendance/ontology_schema.json`（13 实体类 / 14 关系类），由 `backend/scripts/seed_attendance_ontology.py:48-56` 读取 |
| 测试（**无 xfail / skipif** ⇒ 真在拦） | `backend/tests/test_ontology_placeholder_endpoints.py`（`:81` 断言 501、`:84` 断言 detail 含 `P5-M6`）、`backend/tests/test_ontology.py`（应用层已覆盖）、`backend/tests/test_ontology_suggest.py`（`:114`「建议不写库」硬约束） |
| 契约路径计数门禁 | `backend/tests/test_openapi_contract.py:41-49` 与 `:106-107`（现 **26 路径**） |
| **`applied` 枚举的三份口径**（§5 D3 的依据，别重新查） | `specs/m6-ontology-incremental.md:166`「未走完前 5 步，**`/api/v1/ontology/merge` 端点不得对外实现**」；`specs/m2-extract-kg.md:128` status 行含「另有 M6 前向预留值 `applied`」+ `:134-136` 注脚；`changes/archive/2026-10-02-P0-m6-finalization/integration-log.md:175`「**文档侧对齐**，⚠️ 代码 / 契约侧未动」 |

---

## 7. 已完成项（P5-B，2026-10-07）

- ✅ **J3 前端虚线**（¥0）：过期跳画虚线置灰；判定单点在 `frontend/src/lib/reasoning.ts`。
- ✅ **演示图谱恢复**：Entity 2855 / Relation 3643、`attendance-demo-v1` = ready、`verify_and_close` 四项 OK。
- ✅ **D4 收口**：CI 四 job 全绿（收口时最近一次绿 run `37598886121`，开工时用 §8 的命令实读最新）。
- ✅ C1 = 0.1765（graph 1.000 / baseline 0.850）；**X-1 裁决**见 §5 D5。

---

## 8. 基线（**下列数值全部来自脚本 / CI 的实际输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1007 passed / 5 skipped / 0 failed** |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*`） | **1006 passed / 4 skipped / 2 failed**（2 failed = `affiliation-demo-v2` 语料不在本地，**已知不修**） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0**，反向守卫 `test_g21_production_sqlite_guard_still_present` 恒通过 |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 |
| `export_openapi.py --check` | 零 diff（**26 路径**） |
| 前端三条 | `typecheck` / `lint` / `build` 均 exit 0；`gen:api` 后 git diff 为空 |
| 最近一次绿 CI | **不要照抄本文档写死的 run id**（每次提交都会产生新 run，抄了必然过期）。开工时用 `gh run list --limit 1` 实读：P5-B 收口时点的值是 **run `37598886121` / commit `7f82d34d`**，之后的以实读为准 |

---

## 9. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **`ontology_actions` 表已建**（spec §4.2） | 迁移后有该表；`grep ontology_actions backend/` 不再零命中 |
| 2 | **`GET /ontology/active` 返回真本体**（不再是 501） | 真机请求返回 `attendance-demo-v1` 那套 13 实体 / 14 关系 |
| 3 | **冷启动只建议、未生效**（spec §3.1 验收 1） | `cold-start` 后 `ontology_schemas` 里**没有** `status='active'` 的新行；`test_suggest_writes_nothing_to_database` 仍绿 |
| 4 | **confirm 后才转 active**（spec §3.5 验收 12） | `confirm` 前后该行 `status` 变化可举证，且**变化被写进 `ontology_actions`** |
| 5 | **占位测试已改写而非删除** | `test_ontology_placeholder_endpoints.py` 针对本批实现的端点改为断言真行为；**仍成立的部分（未实现端点必须 501）保留** |
| 6 | **契约零漂移** | `export_openapi.py --check` 零 diff；`test_openapi_contract.py` 的 26 路径计数不变 |
| 7 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0 |
| 8 | **pytest 不降** | CI 口径仍 ≥ 1007 passed / 5 skipped / **0 failed** |
| 9 | **RBAC 债不丢、不裸奔** | 按 §5 **D4 裁决**：本批**只登记、不动 `rbac/policy.py`** —— integration-log 里写明「`/cost/dashboard` 恒 501 期间无访问面；将来实现该端点者必须同批补 RBAC 登记」。**不许**既不处理也不登记，**也不许**顺手去改 RBAC 表 |
| 10 | **CI 四 job 全绿**，`gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |

---

## 10. 提交推送纪律 + 升级我的四类情况

**提交**：按 backend / frontend 分段 Conventional Commits；跨侧改动**不得混在一个提交**。
推送后 **以 CI 为终裁**（R-10），CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。
推送偶发网络失败，重试 3 次再报告。

**只在以下四类停下找我**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §8 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完下面的三步自检再报告**） | 本已裁决的 D3（`applied`）、D4（cost RBAC）**都不属此类**；真踩到的例子是「confirm 链路非加不可一个新状态」 |
| 3 | **边界冲突** | 实现过程中发现必须触碰 §4 的某条 Non-goal（如不得不改契约） |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

报告之前**依次答完这三步**，答完仍绕不过去才算真的踩到第 2 类：

1. 卡住的那个**端点 / 动作，是不是本来就在 §4 Non-goal 里**？
   —— D3 就是标准样本：`applied` 只卡 `/ontology/merge`，而 merge 被 §4 第 2 条排除了 **⇒ 它根本不该触发升级**。
2. 能不能把它**整体推到下一批**，而不是在本批给 spec 开一个变更口子？
   —— `/cost/dashboard` 与 RBAC 就是这么处理的（端点不动 ⇒ 债不动，随端点一起走）。
3. 真不行了 —— **报告时带上**：哪份 spec 的哪一行、要加/改什么、为什么绕不过去、
   以及**你试过的替代方案**。不接受"spec 没写所以做不了"这种笼统结论。

**为什么这么定**：动 spec 的代价比推迟一个端点高一个量级（要连带契约同步五步 + 前端重导 + CI 零漂移校验），
而本仓库历史上多数"必须改 spec"最后都被证明是**范围没切干净**。

不在上述四类范围内的：按 §5 决策表已裁决的项**直接执行**，
文档里已有建议项的**采纳建议项**并在 `integration-log.md` 登记。

---

## 11. 不许外推（**完成本批 ≠ 以下任何一条**）

- **三个端点通了 ≠ M6 完成**：merge/split/rename、成本仪表盘、前端校正 GUI **一件都没做**。
- **`GET /ontology/active` 通了 ≠ 本体管理可用**：没有 GUI、没有审批流，只有 API 与审计表。
- **冷启动通了 ≠ LLM 建议质量达标**：本批不评估建议质量（那要花钱跑多轮并人工判）。
- **`ontology_actions` 建了 ≠ 可举证**：没往里写东西的审计表等于没建。
- **本地 pytest 绿 ≠ CI 绿**：本地口径还有 2 条 `affiliation-demo-v2` 的已知 fail。
- **`/cost/dashboard` 的 RBAC 债登记了 ≠ 债还了**：恒 501 期间它没有访问面；一旦谁实现它，
  必须同批补 RBAC 登记（随端点走的债，见 §9 判据 9）。
- **D3 / D4 已裁决 ≠ 那条 spec 要求作废**：`applied` 契约同步五步仍然必须走，
  只是**跟着 merge 端点走** —— 本批没做 merge 所以没触发。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己说过" pytest 全绿 ≠ 护栏在拦"。
