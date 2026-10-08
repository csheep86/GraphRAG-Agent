# 新会话开场提示词 · P5-F（M6 批次 C：**增量重算**——三端点唯一剩余的硬前置）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。详见 §1。
>
> 📦 **本文件自包含**：上一批（P5-E）已收口（`main` = `aa32bd2e`，CI run `37724227049` 四 job 全绿）、
> 不会再回来。开工所需坐标、命令、基线、陷阱都在本文里。唯一需要你额外读的是 §0.5 的**五份仓库内文件**。
>
> ⚠️ **本提示词含一条对上一版指针的更正**（§2.2）：「M6 第一批 B = `applied` 枚举 + 契约同步五步」
> **已被 P5-C 做掉大半**，别照抄那条去做。
>
> 复制本文件**全文**到新会话作为第一条消息。

---

## 0. 本批一句话

**把 `specs/m6-ontology-incremental.md` §3.3 验收 6 / 7 的「增量重算」从零做成真的**：
校正动作触发后**只重写受影响子图、不重建全图**，产出**新的文档级 `kg_version`**
（`writing → active`，不全局翻），并把它回填进 `ontology_actions.result_kg_version`。

**不做**的三件事：**merge / split / rename 三个端点的实现**（仍留占位骨架，下一批）、
成本仪表盘（批次 D）、任何 GUI。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`changes/P5-E/integration-log.md`** | 上一批实录。**重点 §2.1（P5E-1~4 四处 spec 未写清处的处置）**、§5（为什么 loguru 侧走到了 patcher）、§11（本批的来历与指针更正） |
| 2 | **`specs/m6-ontology-incremental.md`** | **v1.0 已定稿**。重点 **§1.1 第 3 项（`:24`）**、**§3.3 验收 6 / 7（`:74-77`）**、**§4.2 `ontology_actions` 表（`:117-127`）**、**§6 配置项（`:266` `INCREMENT_REBUILD_BATCH_SIZE`）** |
| 3 | **`backend/app/services/kg/versioning.py:79` `KgVersioningService`** | `kg_versions` 状态机的**现行真源**。增量重算必须在它上面产出新版本，**不得**另起一套状态机 |
| 4 | **`backend/app/db/models.py:1021` `OntologyAction`** + **`:258` `KgVersion`** | 前者是本批要回填的 `result_kg_version`（`:1071`）；后者是版本行。`result_kg_version` 现在**恒为 NULL**（无写入方） |
| 5 | **`backend/app/api/v1/routes/ontology.py:179 / 200 / 223`** | merge / split / rename 的**占位骨架**（契约已铺、`response_model=OntologyActionResponse`、summary 明写"占位骨架"）。本批**不实现**它们，但要读一遍，理解增量重算将来被谁调用 |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

**替代真源映射**（沿用 P5-B/C/D/E 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（**文件已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-F/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | 本批**预期零契约改动**（增量重算不进 API）。**若**你发现必须动契约 ⇒ 按 §5 **D6** 走完同步五步，**这不算升级** |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

**角色隔离**：

| 段 | 角色 | 允许改的范围 |
|---|---|---|
| 增量重算服务 + 测试 | **后端开发 B** | **只允许** `backend/` + 跑脚本 |
| 契约与前端生成物**再生**（**仅当 D6 判定为必要**） | 仍是 B（**不写前端业务代码**） | 只允许 `contracts/openapi.yaml`（导出产物）与 `frontend/src/types/api.d.ts`（`npm run gen:api` 产物） |

**分支**：沿用 P4 / P2-C / P5-B/C/D/E —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P5-F / 为什么是这一刀

### 2.1 三条机械理由

1. **它是 M6 三端点唯一**剩余**的硬前置**：`specs/m6` §3.2 验收 3 / 4 / 5 三条**都**写着
   「**AND** 触发增量重算」+ §4.4 第 166 行「未走完前 5 步，`/api/v1/ontology/merge` 端点不得对外实现」。
   实读确认：契约侧 `/ontology/merge` `/split` `/rename` **三条路径已在** `contracts/openapi.yaml`
   （`:5006` / `:5146` / `:5076`）、`status: const: applied` **已在契约**（`:2535`）、
   DB 侧 `entity_merge_candidates.status` 的 CheckConstraint **已含 `applied`**（`models.py:524-525`）
   ⇒ 五步里只剩「升版 M2 spec」这一条文档动作（见 §2.2），**真正的代码前置只剩增量重算**。
2. **三端点是占位骨架 = 契约承诺了却没实现**：`routes/ontology.py` 的 merge / split / rename
   summary 明写「占位骨架」。这个状态每多留一批，"契约里有、实际没有"的面就大一分。
   拆掉它的**正确顺序**是先补前置（本批），再接线（下一批）——**不是**一口气把四件事凑一批。
3. **本批 ¥0 且判据全机械**：增量重算是**图操作 + PG 写入**，不调 LLM；判据是
   「**节点数增量 = 校正节点数**」「新 `kg_version` 行 + 状态流转」「`result_kg_version` 真被回填」
   三个可计数的事实。CI 已具备 `postgres:16-alpine` + `neo4j:5.26-community` 两个 service（P3-B 落）。

### 2.2 ⚠️ 对上一版指针的**更正**（别照抄去做）

P5-E 提示词 §12 第 1 条与 P5-C 实录 §11 第 3 条都写着
「做 merge 之前必须走完契约同步五步：Pydantic `EntityMergeStatus` 加 `applied` → 重导契约 …」。
**实读发现这条已经大半作废**：

| 五步里的步骤 | 现状（2026-10-08 实读） |
|---|---|
| ① 升版 M2 spec（§4.5 枚举加 `applied` + §3 验收 3 补一条） | **未做**。但 DB CheckConstraint 已含 `applied`，且该表**只写不读、不进契约**（`models.py:516-518` 注释明写「不为走出 diff 而造端点」） |
| ② 改 Pydantic `EntityMergeStatus` 枚举 | **该枚举不存在**（`grep EntityMergeStatus` 全仓 0 命中）。契约里的 `applied` 是经 `OntologyActionResponse.status: Literal["applied"]`（`schemas/ontology.py:273`）落位的，**与 `entity_merge_candidates` 是两个东西** |
| ③ 重导契约 / ④ `gen:api` / ⑤ CI 零漂移 | **已做**（契约里三条路径 + `const: applied` 都在，CI 契约 job 绿） |

⇒ **剩下的真前置只有增量重算**。① 那条 M2 spec 升版本批**不做**（留到真正实现 merge 那一批，
与「更新 `entity_merge_candidates.status`」这个**动作**同批做，避免先改文档后无代码兑现）。

### 2.3 为什么**不是**这三条

| 候选 | 不做的原因 |
|---|---|
| **merge / split / rename 三端点实现** | 与本批凑一起 = 「三端点 + 增量重算 + RBAC 债」四件事一批 ⇒ 典型的摊太大。本批只补前置 |
| **`GET /cost/dashboard` + `cost_metrics`**（批次 D / MVP 准入 C3-a·C3-b） | 属**另一条**价值链（成本取证），与增量重算是并列关系不是前置关系；且 `cost_ratio` 阈值（TBD-7）**Sprint 13 才收敛**，现在做拿不到"显著 < 1.00"的判据 |
| **`alert` 表**（M5 §3 验收 5 的 P2） | spec 自己标 P2，**已连续三批**有意不做，本批继续不做 |

### 2.4 本批的三刀（建议范围）

1. **增量重算服务**：一个函数 / 服务方法，入参 = 受影响的实体（或文档）集合，产出 = 新 `kg_version`
   （`writing → active`，**仅文档级、不全局翻**）+ 重写受影响子图 + 回填 `ontology_actions.result_kg_version`。
   **复用** `KgVersioningService`（`versioning.py:79`），不另起状态机。
2. **配置 `INCREMENT_REBUILD_BATCH_SIZE`**（spec §6 `:266`，默认 100）：**必须有真实消费者**
   （`check_seams.py` 判据 2）+ **必须同步 `.env.example`**（S3）。
3. **同步测试 + 确认零契约漂移**（§5 D6）：契约不该动；用 `--check` 证明它确实没动。

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

**任何一条与 §8 基线不符，先治病，不要带着红底写代码**。
⚠️ 本机 PostgreSQL / Neo4j 容器**可能是停的**（P5-E 开工时 `graphrag-pg` / `graphrag-neo` 均为 `Exited`）。
先 `docker ps -a` 看一眼，停了就 `docker start graphrag-pg`（PG 是 pytest 的硬前提，Neo4j 只影响真图用例）。

---

## 4. 边界纪律 · Non-goals（**11 条，逐条对照**）

| # | Non-goal | 说明 |
|---|---|---|
| 1 | **不实现 merge / split / rename 三个端点** | 它们是占位骨架，接线归下一批。本批只补它们的前置 |
| 2 | **不改 `specs/m6-ontology-incremental.md` / M2 spec / ADR** | 规格齐全（验收 6 / 7 写得很具体），要改 ⇒ §10 第 2 类升级。**含** §2.2 第 ① 步「升版 M2 spec 加 `applied`」——本批不做 |
| 3 | **不动 RLS / RBAC / 租户隔离** | DR-B4 / DR-B9 各有门禁。⚠️ 若你动到隔离路径 ⇒ 见 §11 最后一条 |
| 4 | **不碰成本仪表盘 / `cost_metrics` 表 / `COST_RATIO_ALERT_THRESHOLD`** | 批次 D，另一条价值链；`cost_ratio` 判据现在拿不到 |
| 5 | **不动 P5-E 的脱敏器（`app/core/masking.py`）与 P5-D 的私域守卫（`app/core/egress.py`）** | 两批刚收口 |
| 6 | **不新增第三方依赖** | 现有 `neo4j` 驱动 + 标准库即可 |
| 7 | **不做 GUI / 前端** | 批次 B 的 GUI 是另一批；本批连端点都不做 |
| 8 | **不改 `kg_versions` 的状态机语义** | 复用 `KgVersioningService`；新增版本走既有 `writing → active`，**不全局翻版本** |
| 9 | **不做"全量重建兜底"** | 增量失败就**显式失败**并落 `error_code` / `error_detail`，**不得**静默回落全量重建（那会让"增量/全量成本比"永远测不出来） |
| 10 | **不做成本度量 / token 打点** | 属批次 D |
| 11 | **不动前端 / 不动契约**（除非 D6 判定必需） | 增量重算是服务端内部行为 |

> **回切点**：每个子任务收尾跑 `uv run python scripts/check_session_drift.py`，
> S1 必须读到**本文件这 11 条**；S5 命中要答得出归属哪条需求。
> ⚠️ **本批 S5 大概率会命中**：增量重算服务函数在本批**只有测试引用**（无端点调用它）。
> 这是**已知的、有意的**——它的归属是 spec §3.3 验收 6，消费者是下一批的三端点。
> 请在 `integration-log.md` 里**明写这一条**（照 P5-E §5 的写法：先登记、后提交）。
> ⚠️ 本批新增配置 ⇒ **S3 一定会盯**「`config.py` ⇄ `.env.example`」同步：**这不是误报，是必须完成的动作**。

---

## 5. 决策表（**已裁 / 建议采纳项**，逐条有据）

| # | 决策 | 处置 | 依据 |
|---|---|---|---|
| **D1** | 主题 | ✅ 按 §2.1 定 **M6 增量重算**。若要换主题，改本文件 §2.4 / §4 / §9 三处即可 | §2.1 三条机械理由 |
| **D2** | 配置 | **新增 `INCREMENT_REBUILD_BATCH_SIZE`**（默认 100）。三条硬约束：① **必须有真实消费者**（`check_seams.py` 判据 2）；② **必须同步 `.env.example`**（S3）；③ **不得是占位**（ADR-0004 §3 第 5 条，占位清单现只剩 `log_export` 一项） | `specs/m6` §6 `:266` 明写该配置项 |
| **D3** | 触发入口 | **本批不给 HTTP 入口**：做成服务层函数，由**测试直接调用**验证。**不为"走出 diff"造端点**（沿用 `models.py:517` 的既有裁决口径） | 三端点仍是占位骨架；端点归下一批 |
| **D4** | 版本粒度 | **仅文档级 `kg_version`**，**不全局翻**；状态流转 `writing → active`（沿用 ADR-0002 三段式） | `specs/m6` §3.3 验收 6 原文括号：「**仅文档级 `kg_version`，不全局翻**，沿用 ADR-0002 三段式」 |
| **D5** | 是否新增错误码 | **预期不新增**（增量失败可复用既有错误码）。若确有必要 ⇒ `errors.py` **四处**字典齐加（ErrorCode / 状态码映射 / 描述 / 来源），漏一处 `export_openapi.py` 直接 `KeyError` | `app/core/openapi.py:129-134` 遍历全部 `ErrorCode` 取两个字典 |
| **D6** | 契约会不会动 | **预期零改动**：增量重算不进任何响应体。用 `export_openapi.py --check` **证明**它没动；**若**真动了 ⇒ 走同步五步（export → `npm run gen:api` → 提交两生成物 → CI 零漂移），**不算升级** | P5-C 的 B-1 / P5-D 的 D2 / P5-E 的 D6 已开先例 |
| **D7** | 成本敞口 | 本批**预期 ¥0**：增量重算是图操作 + PG 写入，**不调 LLM**；语料用既有的合成 / 演示语料 | 沿用 P5-C D6 / P5-D D7 / P5-E D7 |
| **D8** | 「不重建全图」怎么才算机械判据 | 取**真 Neo4j 的前后节点计数**做差：增量 = 校正动作影响的节点数，**不是**全图节点数。断言对象是**图里的实际计数**与**PG 里读回的行**，不是函数返回值 | `specs/m6` §3.3 验收 6 原文：「增量重算**不重建全图**，仅重写受影响子图（**节点数增量 = 校正节点数**）」 |

**已知陷阱（省钱用）**：

| 陷阱 | 后果 / 处置 |
|---|---|
| 用"函数返回值"或"mock 图"证明不重建全图 | **恒绿失效**（R-9）⇒ 必须**真连 Neo4j 前后计数** |
| `Settings.model_config` 是 **`extra="ignore"`** | 环境变量名拼错会被**静默忽略** ⇒ 用例要断言**读到的值**，不能只断言"设了"（P5-D 已踩过一次，P5-E 沿用了这条断言形态） |
| 增量失败时"顺手"回落全量重建 | 直接违反 §4 Non-goal 9，且会让 `cost_ratio` 永远测不出来 ⇒ **显式失败 + 落 `error_code`** |
| 把 `kg_version` 全局翻了 | 违反 §4 Non-goal 8 / D4；`kg_versions` 已有状态机，改动会让既有图谱用例红 |
| 本机 Neo4j 没起 ⇒ 真图用例 skip | 与 P5-E 同型：本地 11 条 skip 全是 Neo4j / TEMPORAL 环境未注入。**以 CI 为终裁**，但**本批的核心判据不能靠 skip 蒙过去** ⇒ 开工前先 `docker start` 起图库 |
| 为凑"有 diff"而顺手实现 merge 端点 | 直接违反 §4 Non-goal 1 |

---

## 6. 已查证坐标表（**不要再 recon 一遍**）

> 行号基于当前 HEAD（`aa32bd2e`），**仅供定位；以代码实读为准**（行号漂移不影响结论）。

| 坐标 | 位置 |
|---|---|
| 需求条目 | `docs/delivery-requirements-and-guardrails.md:114` DR-D1 ✅ / `:115` DR-D2 🟡 在途 / `:116` DR-D3 ✅；**`:94` DR-B6（T1）仍写「⏳ 零代码」、`:95` DR-B7（T2）仍写「⏳ 零代码」—— ⚠️ **这是需求侧明细行与护栏侧不同步**（G-9 / G-10 均已 ✅ 转正），**属已知 docs 债，本批不做** |
| 排期队列 | `docs/delivery-plan.md:198`（D4 → D2 M6 → D1 → D3/D5/D7/D8） |
| M6 缺口登记 | `docs/acceptance-traceability-matrix.md:54` M5 模块行（P5-E 已同步为「完整脱敏已达成」）；M6 模块行仍记 P5-C 第一批 |
| Spec 判据 | `specs/m6-ontology-incremental.md:24`（§1.1 第 3 项）、`:74-77`（§3.3 验收 6 / 7）、`:117-127`（§4.2 `ontology_actions`）、`:266`（§6 `INCREMENT_REBUILD_BATCH_SIZE`）、`:151-166`（§4.4 五步） |
| **版本状态机（复用，不改）** | `backend/app/services/kg/versioning.py:79` `KgVersioningService`；`:175` `activate_by_version`；`:43/:47` 两个异常 |
| **要回填的字段** | `backend/app/db/models.py:1021` `OntologyAction`；`:1071` `result_kg_version`（当前**恒 NULL**，无写入方）；`:258` `KgVersion` |
| **图谱侧** | `backend/app/services/graphs.py:260` `KgVersion`（active 版本投影）；`:1286` `activate_kg_version`；`backend/app/api/v1/routes/graph.py:204` `activate_kg_version` |
| **三端点占位骨架（本批不实现）** | `backend/app/api/v1/routes/ontology.py:179`（merge）/ `:200`（split）/ `:223`（rename）；响应模型 `schemas/ontology.py:258` `OntologyActionResponse`（`:273` `status: Literal["applied"]`） |
| 契约现状 | `contracts/openapi.yaml:5006` `/ontology/merge`、`:5146` `/split`、`:5076` `/rename`、`:2535` `const: applied` |
| 配置 | `backend/app/core/config.py`（新增 `INCREMENT_REBUILD_BATCH_SIZE` 挨着既有的 M6 配置落成同款）；`:42` `extra="ignore"` |
| 既有正向守卫（**不许改断言**） | `backend/tests/test_kg_versioning.py`、`tests/test_guardrails_graph.py`（9 条，G-9 图谱侧）、`tests/test_guardrails.py:328`（`test_g10_t2_concurrent_requests_do_not_cross_tenants`，G-10） |
| 契约出口 | `backend/app/core/openapi.py:129-134`；计数门禁 `backend/tests/test_openapi_contract.py:106-107`（现 **26 路径**）、`:149-152`（enum 与 `ErrorCode` 全等断言） |
| CI 环境 | `.github/workflows/ci.yml:60-71` `postgres:16-alpine` service；`:114-115` `DATABASE_URL=app_rls` / `DATABASE_URL_OWNER=app_owner`；P3-B 起另有 `neo4j:5.26-community` service |
| 三条门禁 | `scripts/check_seams.py` / `check_session_drift.py` / `check_startup_readiness.py` |
| 先例 | `changes/P5-C/integration-log.md` §7.4（B-1 契约再生处置模板）、`changes/P5-E/integration-log.md` §2.1（P5E-1~4 的"登记不升级"写法）、§5（为什么走到 loguru patcher） |

---

## 7. 已完成项（P5-E 及之前）

- ✅ **M5 统一脱敏 `mask(field, category)`**（P5-E，2026-10-08）：八类策略逐字照 §4.5 示例列；
  接线 `audit_log.detail` 写入前 + loguru JSON 出口；判据 = **已落库的 JSON** 与**运行期日志输出**
  均无八类原文；CI **1094 passed / 5 skipped / 0 failed**（+28）。
- ✅ **私域出向管控**（P5-D）/ **M6 第一批（`ontology_actions` 表 + 冷启动 / confirm / active + RBAC）**（P5-C）。
- ✅ **CI run `37723651857`（代码）/ `37724227049`（批次文档）四 job 全绿**。
- ⚠️ **本批继承的债务**：增量重算**零实现**；三端点**占位骨架**；`alert` 表（P2）**有意不做**；
  DR-B6 / DR-B7 需求行**待与 G-9 / G-10 对账**（纯 docs 债）。

---

## 8. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1094 passed / 5 skipped / 0 failed**（run `37723651857` / commit `b86bc954`，2026-10-08） |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*`） | 上一批实读 **1088 passed / 11 skipped / 0 failed**（本机只设了 `GRAPH_REAL_NEO4J_URI`、未设 USER/PASSWORD ⇒ 11 条真图用例 skip） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**26 路径**） |
| 前端 | 未在**本地**跑 `typecheck` / `lint` / `build`；只在 CI 内绿 ⇒ 若触及前端生成物，**以 CI 为终裁** |
| 最近一次绿 CI | **不要照抄写死的 run id**。开工时 `gh run list --limit 1` 实读；本文件成文时是 **run `37724227049` / commit `aa32bd2e`** |

---

## 9. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **增量重算服务落地且被测试驱动** | 服务层函数 / 方法存在；测试直接调用它（不经 HTTP，D3） |
| 2 | **不重建全图（**真 Neo4j**）** | 校正动作前后**真连 Neo4j 取节点计数**做差：增量 = 受影响的节点数，**不等于**全图节点数；未受影响的节点 `id` / 属性**逐条不变** |
| 3 | **新 `kg_version` 落库且状态流转正确** | PG 读回：`kg_versions` **新增一行**，状态走 `writing → active`；**既有的 active 版本不被全局翻**（ADR-0002 三段式 + D4） |
| 4 | **`result_kg_version` 真被回填** | `ontology_actions` 对应行的 `result_kg_version` 由 NULL 变为新版本号（**真 PG 读回**，不是函数返回值） |
| 5 | **失败路径显式失败** | 注入一次失败 ⇒ 落 `error_code` / `error_detail`，**且**没有回落全量重建（`error_detail` 敏感 ⇒ 日志禁输出原文，沿用 P5-E 的脱敏口径） |
| 6 | **契约零漂移** | `export_openapi.py --check` 零 diff、26 路径不变（若 D6 判定需改 ⇒ 走完五步并在 CI 证明零漂移） |
| 7 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0 |
| 8 | **pytest 不降** | **CI ≥ 1094 passed / 5 skipped / 0 failed**；既有正向守卫（`test_kg_versioning.py`、`test_guardrails_graph.py`、`test_guardrails.py:328`）**不许为让它绿而改断言** |
| 9 | **配置有消费者且已同步** | `check_seams.py` 仍 **0/0**；`.env.example` 已同步（`check_session_drift.py` S3 不报） |
| 10 | **CI 四 job 全绿**，`gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log | |

---

## 10. 提交推送纪律 + 升级我的四类情况

**提交**：按 backend / 契约+前端生成物**分段** Conventional Commits（契约再生单独一笔，便于整笔 revert）；
跨侧改动**不得混在一个提交**。推送后 **以 CI 为终裁**（R-10），CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。
推送偶发网络失败（本仓库近期 `github.com:443` 间歇性不可达——**`ebbdcb92` 曾连丢 8 次、等约 40 秒后第 2 次等待成功**），
**加大间隔重试到位再报告**；期间**不许**拿估算的 run id 把表格填满。

**只在以下四类停下找我**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §8 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完下面三步自检再报告**） | 真踩到的例子：spec §3.3 验收 6 的「文档级 `kg_version`」与现行 `KgVersioningService` 的版本粒度**对不上**（如它只能建全局版本），且无法用"最小代价 + 登记"绕开 |
| 3 | **边界冲突** | 实现中必须触碰 §4 的某条 Non-goal。**注意**：§5 D6 的契约再生**不属此类** |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？（如：想顺手把 merge 端点做了 ⇒ Non-goal 1）
2. 能不能**整体推到下一批**并登记？（如：某些边界形态 ⇒ 本批取最小可证形态并在 integration-log 登记，
   后续批次再裁决）
3. 真不行了 —— **报告时带上**：哪份 spec 的哪一行、要加/改什么、为什么绕不过去、**你试过的替代方案**。
   不接受"spec 没写所以做不了"这种笼统结论。

---

## 11. 不许外推（**完成本批 ≠ 以下任何一条**）

- **增量重算写了 ≠ 三端点可用**：merge / split / rename **仍是占位骨架**，HTTP 层一行没动。
- **服务函数绿了 ≠ 有调用方**：本批**只有测试引用它**（S5 会命中，已在 §4 预先登记）。
  真正接上端点是**下一批**的事。
- **"不重建全图"判据过了 ≠ 成本真的低**：本批**不测** token / 耗时 / 成本比（批次 D 的事）。
  增量是否真的比全量便宜，**没有数字**。
- **新 `kg_version` 落了 ≠ M3 / M4 已能消费**：验收 7 只要求"可消费"，本批**不验证**下游真实消费链路。
- **失败会落 `error_code` ≠ 失败可恢复**：本批不做重试 / 回滚语义。
- **`INCREMENT_REBUILD_BATCH_SIZE` 可配 ≠ 已调优**：默认 100 是 spec 给的，**没有任何实测依据**。
- **契约零漂移 ≠ 功能可用**：判据只证明了"契约没被踩歪"。
- **本地绿 ≠ CI 绿**：本机 Neo4j 常是停的；**本批核心判据（判据 2）依赖真图** ⇒ 开工前必须先起图库，
  不能靠 skip 蒙过去（R-10）。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着「pytest 全绿 ≠ 护栏在拦」。
- ⚠️ **若你在实现中动到租户隔离相关路径**（本批**预期不动**）：须带上 **ADR-0003 §4.1** 的两类测试
  **T1 跨 org 越权**（G-9，已 ✅，`test_guardrails_graph.py` + `test_guardrails_rls.py`）与
  **T2 并发串租户**（G-10，已 ✅，`tests/test_guardrails.py:328`）——**在 PostgreSQL 上执行、纳入 CI 必过项、
  禁止标 `local_only` 绕过**；它们**已有的断言不许放宽**。

---

## 12. 下一批指针（**本批收口时按实际结果更新，别照抄**）

1. **M6 三端点接线（merge / split / rename）**：本批补完前置后即可做。同批须补
   ① `require_permission` ② `PROTECTED_ENDPOINTS` 登记（P5-C §11 第 1 条的 RBAC 债）
   ③ 更新 `entity_merge_candidates.status = applied` ④ **升版 M2 spec §4.5**（§2.2 第 ① 步，
   与 ③ 同批做，避免先改文档后无代码兑现）。
2. **`GET /cost/dashboard` + `cost_metrics` 表**（m6 §3.4 验收 8 / 9），与 MVP 准入 **C3-a / C3-b** 一起做；
   `cost_ratio` 阈值 TBD-7 **Sprint 13 收敛前拿不到判据**。
3. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2 部分；**已连续三批**有意不做）。
4. **DR-B6 / DR-B7 与 G-9 / G-10 的口径对账**（纯 docs）：需求侧明细行仍写「⏳ 零代码」，
   而护栏侧 G-9 / G-10 **均已 ✅ 转正** —— 与 P7-A 订正的 G-10 同型病。建议并入任一批次顺手做，
   **不单独开工**。
5. **多租户出向审计归属**：脱离"一套 compose = 一个租户"时需给 `build_chat_model` /
   `build_default_embedder` 补 org 传递（P5-D 的 X-3 撤回条件）。
6. **D7（`question` 参与检索）/ D5（M4 完整化）/ D8**：算法活，各自单独排。
7. **m6 定稿遗留的三配置项回填**：`specs/m6` 定稿时记有"三个配置未落 `config.py`，实现时回填"
   （见 P1-3 备注第 ⑤ 项）——本批只填 `INCREMENT_REBUILD_BATCH_SIZE`，
   **另两个**（若确需）在对应批次回填，别在本批顺手补齐。
8. **日志 `message` 正文的脱敏**：P5-E 明确不覆盖。正确路径是**逐个把 `mask()` 调用点补到写敏感值的
   日志语句上**，而不是做值识别。
