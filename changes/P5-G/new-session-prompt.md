# 新会话开场提示词 · P5-G（M6 批次 B'：**三端点接线** merge / split / rename）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。详见 §1。
>
> 📦 **本文件自包含**：上一批（P5-F）已收口（`main` = `b581e240`，CI run `37731281218` 四 job 全绿）、
> 不会再回来。开工所需坐标、命令、基线、陷阱都在本文里。唯一需要你额外读的是 §0.5 的**五份仓库内文件**。
>
> ⚠️ **本批含一个必须先答的裁决**（§5 **D9** / §2.4）：**P5F-4「新版本图的完整性」**——
> 三端点一旦真接线，M3 / M4 消费新 `kg_version` 会**只看到被校正的那一小撮节点**。
> 本批不许绕过它，也不许假装它不存在。
>
> 复制本文件**全文**到新会话作为第一条消息。

---

## 0. 本批一句话

**把 `specs/m6-ontology-incremental.md` §3.2 验收 3 / 4 / 5 的三个校正端点从「占位骨架」做成真的**：
`POST /ontology/merge` / `/split` / `/rename` 各自完成图操作 → 写 `ontology_actions` →
**调用 P5-F 落地的增量重算** → 回 `{kg_version, status: "applied"}`。

**同批必做的三个附加动作**（都是前几批明确登记、等着本批兑现的债）：
① `require_permission` + `PROTECTED_ENDPOINTS` 登记（P5-C §11 第 1 条的 RBAC 债）；
② `entity_merge_candidates.status = applied`；
③ **升版 `specs/m2-extract-kg.md` §4.5 注脚 + §3 验收 3**（M2 spec 自己点名要求，见 §2.2）。

**不做**：GUI / 前端（另一批）、成本仪表盘（批次 D）、`alert` 表（P2）。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`changes/P5-F/integration-log.md`** | 上一批实录。**重点 §2.2（登记的 5 条 P5F-1..5）**、**§2.3（P5F-4 是本批必须先答的裁决）**、§4（S5 说明）、§8 指针第 1 条 |
| 2 | **`backend/app/services/kg/incremental.py`** | 本批要接线的**增量重算服务**（P5-F 产出）。**重点**：签名 `rebuild_incrementally(db, org_id, action_id, affected_entity_ids, source_doc_ids, trace_id, graph_service, batch_size)` 与失败语义（返回 `status="failed"`，**不**抛） |
| 3 | **`backend/app/api/v1/routes/ontology.py:122-241`** | 三端点的**占位骨架** + `:144` confirm 端点的 `dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)]`（**照抄这个形态**）+ `:60 _placeholder` |
| 4 | **`backend/app/schemas/ontology.py:179/215/240/258`** | `OntologyMergeRequest` / `OntologySplitRequest` / `OntologyRenameRequest` / `OntologyActionResponse`（`:273` `status: Literal["applied"]`）——**契约侧已齐，本批不该动它们** |
| 5 | **`backend/app/db/models.py:504 EntityMergeCandidate`** + **`specs/m2-extract-kg.md:119-136`** | 前者 `status` 的 CheckConstraint **已含 `applied`**（`:524-525`）；后者是**本批要升版**的地方（§4.5 注脚 `:132-136` + §3 验收 3 `:48`） |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

**替代真源映射**（沿用 P5-B/C/D/E/F 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（**文件已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-G/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | **预期零契约改动**（三个端点的请求/响应模型契约里全有）。**若**你发现必须动契约 ⇒ 按 §5 **D6** 走完同步五步，**这不算升级** |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

**角色隔离**：

| 段 | 角色 | 允许改的范围 |
|---|---|---|
| 三端点 + 服务 + 测试 | **后端开发 B** | **只允许** `backend/` + 跑脚本 |
| **升版 `specs/m2-extract-kg.md`** | **架构师**（同一会话内换帽子） | 只允许 `specs/m2-extract-kg.md` 的 §4.5 注脚 + §3 验收 3 两处，**只追加/改写注脚，不重排编号**（守 `dev-doc-status.md` **R5**） |
| 契约与前端生成物**再生**（**仅当 D6 判定为必要**） | 仍是 B（**不写前端业务代码**） | 只允许 `contracts/openapi.yaml`（导出产物）与 `frontend/src/types/api.d.ts`（`npm run gen:api` 产物） |

**分支**：沿用 P4 / P2-C / P5-B/C/D/E/F —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P5-G / 为什么是这一刀

### 2.1 四条机械理由

1. **前置已全部兑现**：`specs/m6` §4.4 第 166 行「未走完前 5 步，`/api/v1/ontology/merge` 端点不得对外实现」。
   实读：契约侧三条路径（`contracts/openapi.yaml` `:5006` / `:5146` / `:5076`）与
   `status: const: applied`（`:2535`）**已在**；DB 侧 `entity_merge_candidates.status` 的
   CheckConstraint **已含 `applied`**（`models.py:524-525`）；**增量重算（唯一的真代码前置）P5-F 已落地**
   ⇒ 五步里只剩「升版 M2 spec」这一个**文档动作**，而它按 M2 spec 注脚的原文
   「**M6 落地时**须先升版本表」应当**与代码同批**（本批）。
2. **三端点是「契约承诺了却没实现」的最大一块**：`routes/ontology.py:179/200/223` 的 summary
   明写「占位骨架」，恒返回 501。每多留一批，"契约里有、实际没有"的面就大一分。
3. **它是 M6 用户故事的主干**：§2 第二条用户故事（"把识别错误的两实体合并、一实体拆两个、给实体改名"）
   与第三条（"校正触发增量重算、不要全量重建"）**都**要靠这三个端点落地；没有它们，
   P5-F 的增量重算就永远"只有测试引用它"（P5-F §4 已登记的 S5 状态）。
4. **本批 ¥0 且判据可机械**：三个动作都是**图操作 + PG 写入**，不调 LLM；判据是
   「节点数变化」「`status=applied`」「`result_kg_version` 非空」「无授权 ⇒ 403」这些可计数的事实。
   CI 已具备 `postgres:16-alpine` + `neo4j:5.26-community` 两个 service。

### 2.2 ⚠️ 契约同步五步里**有三步在本批不适用**（别照抄去做）

M2 spec §4.5 注脚（`:136`）与 m6 §4.4（`:159-164`）都写着「契约同步 5 步」。**实读**（2026-10-08）：

| 五步里的步骤 | 现状 | 本批处置 |
|---|---|---|
| ① **升版 M2 spec**（§4.5 枚举加 `applied` + §3 验收 3 补一条） | M2 §4.5 表 `:128` 与注脚 `:132-136` 已**预留**，但仍是「M6 前向预留、本阶段不实现」口径 | ✅ **本批做**（与 ② 的代码动作同批，避免先改文档后无代码兑现）。**只改注脚与验收 3 的那句注**，**不重排编号** |
| ② 改 Pydantic `EntityMergeStatus` 枚举 | **该枚举不存在**（`grep EntityMergeStatus` 全仓 0 命中）；`entity_merge_candidates` **只写不读、不进契约**（`models.py:516-518` 注释明写「不为走出 diff 而造端点」） | ❌ **无对象**——不要为了让五步"看起来走完"而新造一个不进契约的枚举。③ 的位置改由 **② 的代码动作**（真写 `status='applied'`）兑现 |
| ③ 重导契约 / ④ `gen:api` / ⑤ CI 零漂移 | 契约里三条路径 + `const: applied` **都在**，CI 契约 job 绿 | ✅ 用 `export_openapi.py --check` **证明零 diff** 即可（**26 路径不变**） |

⇒ **五步里真正要落地的只有 ①（文档）+ ②的代码动作 + ⑤的证明**。三条不适用的要在
`integration-log.md` 里**逐条写明为什么不适用**，不要让后来者以为"漏做了"。

### 2.3 为什么**不是**这三条

| 候选 | 不做的原因 |
|---|---|
| **本体校正 GUI（前端）** | 属**另一批**（m6 §1.1 批次 B 的 GUI）；本批连前端都不碰（Non-goal 1） |
| **`GET /cost/dashboard` + `cost_metrics`**（批次 D / MVP 准入 C3-a·C3-b） | 属**另一条**价值链；`cost_ratio` 阈值（TBD-7）**Sprint 13 才收敛**，现在做拿不到"显著 < 1.00"的判据 |
| **`alert` 表**（M5 §3 验收 5 的 P2） | spec 自己标 P2，**已连续四批**有意不做，本批继续不做 |

### 2.4 本批的四刀（建议范围）

1. **三端点实现**（图操作 → `ontology_actions` → 增量重算 → 响应）：
   - `merge`：`:Entity` 合并（`MERGE` 幂等键 `(id, kg_version)`，ADR-0002 §3.1）；受影响 = 左右两个实体；
   - `split`：创建 N 个新 `:Entity`（`new_entities[]` 至少 2 个）并把原节点的关系迁移过去，原节点置 `status='split'`（m6 §4.5）；受影响 = 原节点 + N 个新节点；
   - `rename`：改 `:Entity.canonical_name`，旧名写入 `:Entity.aliases`（沿用 M2 §4.3）；受影响 = 该实体。
2. **RBAC 接线**：三端点各加 `dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)]`
   （照 `ontology.py:144` 的形态），并在 `tests/test_rbac.py:62 PROTECTED_ENDPOINTS` 登记三条
   ⇒ 参数化拒绝用例**自动**覆盖它们（该文件的设计就是为此）。
3. **`entity_merge_candidates.status = applied`** + **升版 M2 spec**（§2.2 ①）。
4. **裁决并落地 P5F-4**（§5 **D9**）——见下。

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
⚠️ 本机 PostgreSQL / Neo4j 容器**可能是停的**（P5-F 开工时 `graphrag-neo` 为 `Exited`）。
先 `docker ps -a` 看一眼，停了就 `docker start graphrag-neo`（**本批判据依赖真图**；
本机 Neo4j 凭据 `neo4j/ci-graph-pw-2026`，`7687`）。

---

## 4. 边界纪律 · Non-goals（**11 条，逐条对照**）

| # | Non-goal | 说明 |
|---|---|---|
| 1 | **不做 GUI / 前端业务代码** | m6 §1.1 批次 B 的 GUI 是另一批；本批**只**在 D6 判定必需时再生 `api.d.ts` |
| 2 | **不改 `specs/m6-ontology-incremental.md`** | M6 规格齐全（验收 3 / 4 / 5 写得很具体），要改 ⇒ §10 第 2 类升级。⚠️ **升版 `specs/m2-extract-kg.md` 是本批必做项，不属本条**（§2.2 ①） |
| 3 | **不动 RLS / RBAC 的**判定逻辑** | 只做「端点挂上 `require_permission`」这个接线动作；判定逻辑（`rbac/deps.py:54`）一行不改。⚠️ 若你动到隔离路径 ⇒ 见 §11 最后一条 |
| 4 | **不碰成本仪表盘 / `cost_metrics` / `COST_RATIO_ALERT_THRESHOLD`** | 批次 D，另一条价值链 |
| 5 | **不动 P5-F 的增量重算**状态机语义**与 P5-E 的脱敏器 / P5-D 的私域守卫** | 三批刚收口；本批**调用**增量重算，**不重写**它 |
| 6 | **不新增第三方依赖** | 现有 `neo4j` 驱动 + 标准库即可 |
| 7 | **不新增错误码**（预期） | 跨 org 复用 `FORBIDDEN`；实体不存在复用 `ENTITY_NOT_FOUND`；增量重算失败沿用 P5-F 的落库码。若确有必要 ⇒ `errors.py` **四处**字典齐加，漏一处 `export_openapi.py` 直接 `KeyError` |
| 8 | **不改 `kg_versions` / `entity_merge_candidates` 的状态机取值** | 复用既有 CheckConstraint（`applied` 已含），**不**加新取值 |
| 9 | **不做"全量重建兜底"** | 沿用 P5-F 同一条纪律：校正失败就**显式失败**并落 `error_code`，不得静默回落全量重建 |
| 10 | **不做成本度量 / token 打点** | 属批次 D |
| 11 | **不动契约**（除非 D6 判定必需） | 三个端点的请求 / 响应模型契约里全有；`export_openapi.py --check` 必须零 diff |

> **回切点**：每个子任务收尾跑 `uv run python scripts/check_session_drift.py`，
> S1 必须读到**本文件这 11 条**；S5 命中要答得出归属哪条需求。
> ⚠️ **本批 S5 不该再命中**——三端点的消费者是 HTTP 层，且 P5-F 的 `incremental.py`
> 在本批被真正接线后**不再是孤儿**。若仍命中 ⇒ 说明有东西没接上，**不许当作噪声放过**。
> ⚠️ 本批**预期不新增配置** ⇒ S3 应无事可报；若你发现必须加配置 ⇒ 见 §5 **D2**。

---

## 5. 决策表（**已裁 / 建议采纳项**，逐条有据）

| # | 决策 | 处置 | 依据 |
|---|---|---|---|
| **D1** | 主题 | ✅ 按 §2.1 定 **M6 三端点接线**。若要换主题，改本文件 §2.4 / §4 / §9 三处即可 | §2.1 四条机械理由 |
| **D2** | 是否新增配置 | **预期不新增**。三端点复用既有配置（增量重算的批大小已由 P5-F 落地）。若确需 ⇒ 三条硬约束：① 必须有真实消费者（`check_seams.py` 判据 2）；② 必须同步 `.env.example`（S3）；③ 不得是占位 | ADR-0004 §3 第 5 条 |
| **D3** | 端点的**图操作**在哪实现 | **新增服务层**（建议 `app/services/ontology.py` 内新增，或 `app/services/kg/` 下新文件），**路由层只做编排 + 错误映射**（沿用 `confirm` 端点的分工） | 与 `confirm_ontology_schema` 同款分工；路由层不写 Cypher（既有纪律） |
| **D4** | 动作行怎么落 | **先落 `ontology_actions`（拿 `action_id`）→ 再调增量重算**（P5-F 的 `rebuild_incrementally` 需要 `action_id`）。`target_entities` 按动作给：merge = 2 个 / split = 1+N 个 / rename = 1 个（`models.py:1060-1063` 的现有口径） | `incremental.py` 的签名要求 `action_id` 先存在 |
| **D5** | `kg_version` 字段 | 动作行的 `kg_version` 填**操作时的 active 版本**（不是新版本）；新版本由 `result_kg_version` 承载 | spec §4.2「操作时的 `kg_version`（用于回放）」+ P5-F 的基线一致性校验（`action.kg_version != active` ⇒ 拒绝） |
| **D6** | 契约会不会动 | **预期零改动**：请求 / 响应模型契约里全有。用 `export_openapi.py --check` **证明**；**若**真动了 ⇒ 走同步五步（export → `npm run gen:api` → 提交两生成物 → CI 零漂移），**不算升级** | P5-C 的 B-1 / P5-D 的 D2 / P5-E 的 D6 / P5-F 的 D6 已开先例 |
| **D7** | 跨 org 怎么处理 | 两个实体必须同属当前租户 ⇒ 否则 **403 `FORBIDDEN`**，**不**降级为「只处理同租户的那个」（`ontology.py:186-187` 的 description 已这么写了） | m6 §5.5 + 占位骨架的既有 description |
| **D8** | 审计 | **不**手写 `audit_log`：M5 的 `AuditMiddleware` 已全量写（`action` 由路径推导）。本批只需在 integration-log 登记「三端点的审计由中间件覆盖」并**实测确认有一条** | P5-C / P5-E 的同一口径 |
| **D9** | ⚠️ **P5F-4「新版本图的完整性」**怎么办 | **本批必须给出裁决并落到判据里**，三条候选见 §2.4 第 4 刀与下表注。**建议最小形态**：新版本只含受影响子图（沿用 P5-F），**并新增一条断言把它变成显式事实**——「以新 `kg_version` 读图 ⇒ 只看到被校正的节点」，同时在 integration-log 明写「消费侧图完整性 = 已知缺口，版本链读侧归后续批次」。**若**你判断必须在本批解决 ⇒ 走 §10 第 2 类升级（先缩范围、后报告） | P5-F §2.3 **P5F-4** 明确把它留给了本批 |
| **D10** | 成本敞口 | 本批**预期 ¥0**：图操作 + PG 写入，**不调 LLM** | 沿用 P5-C/D/E/F |

**已知陷阱（省钱用）**：

| 陷阱 | 后果 / 处置 |
|---|---|
| 用"函数返回值"或"mock 图"证明图操作 | **恒绿失效**（R-9）⇒ 必须**真连 Neo4j 前后计数** |
| 为了"契约同步五步"而新造 `EntityMergeStatus` Pydantic 枚举 | 该表**不进契约**，新造的枚举没有消费者 ⇒ 触发 `check_seams.py` / S5 ⇒ 见 §2.2 |
| 先写 `ontology_actions` 再拿 `action_id` 的顺序搞反 | P5-F 的 `rebuild_incrementally` 要求 `action_id` 已存在（它会读该行校验 org 与基线） |
| 增量重算失败时"顺手"回落全量重建 | 直接违反 §4 Non-goal 9；P5-F 已把「不回落」写成机械判据，本批**不得**绕过 |
| 把 `entity_merge_candidates.status` 写成 `applied` 却**没**升版 M2 spec | 文档与代码打架（M2 注脚仍写"本阶段不实现"）⇒ 属 §2.2 ① 的同批要求 |
| 跨 org 时"只合并同租户那一个" | `ontology.py:186-187` 明写这是数据污染，**不**降级 |
| 本机 Neo4j 没起 ⇒ 真图用例 skip | 与 P5-F 同型：**本批核心判据依赖真图** ⇒ 开工前先 `docker start` |

---

## 6. 已查证坐标表（**不要再 recon 一遍**）

> 行号基于 P5-F 收口后的 `HEAD`（`b581e240`），**仅供定位；以代码实读为准**。

| 坐标 | 位置 |
|---|---|
| 需求条目 | `docs/delivery-requirements-and-guardrails.md:114-116` DR-D1 ✅ / DR-D2 🟡 在途 / DR-D3 ✅；⚠️ `:94` DR-B6（T1）/ `:95` DR-B7（T2）仍写「⏳ 零代码」（护栏侧 G-9 / G-10 已 ✅）⇒ **已知 docs 债，本批不做** |
| 排期队列 | `docs/delivery-plan.md:198`（D4 → D2 M6 → D1 → D3/D5/D7/D8） |
| M6 缺口登记 | `docs/acceptance-traceability-matrix.md:55` M6 模块行（P5-F 已追加增量重算进展，仍明写「三端点仍是占位骨架」）⇒ **本批收口时须再追加** |
| Spec 判据 | `specs/m6-ontology-incremental.md:70-72`（§3.2 验收 3 / 4 / 5）、`:74-77`（§3.3 验收 6 / 7，P5-F 已达成）、`:151-166`（§4.4 五步）、`:168-172`（§4.5 Neo4j 节点变更）、`:227-233`（§5.5 三端点草案） |
| **M2 待升版处** | `specs/m2-extract-kg.md:48`（§3 验收 3，末句注已提 `applied`）、`:119-130`（§4.5 表，`:128` status 行）、`:132-136`（**注脚：本批要改的就是这里**）、`:146`（§4.5.1 判据，**不动**）、`:194-195`（S9.11 裁决 D-C 口径） |
| **三端点占位骨架** | `backend/app/api/v1/routes/ontology.py:179`（merge）/ `:200`（split）/ `:223`（rename）；`:60 _placeholder`；`:55-57` `_BLOCKED_BY` / `_SPEC` 常量（**实现后要删掉这三处的 501 措辞**） |
| **RBAC 模板** | `backend/app/api/v1/routes/ontology.py:144` `dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)]`；`:50-51` 已有导入；`app/services/rbac/deps.py:54 require_permission`；**登记表** `backend/tests/test_rbac.py:62 PROTECTED_ENDPOINTS`（现 6 条，须加 3 条 ⇒ 9 条） |
| **契约模型** | `backend/app/schemas/ontology.py:179` `OntologyMergeRequest` / `:215` `OntologySplitRequest`（`new_entities` `min_length=2`）/ `:240` `OntologyRenameRequest` / `:258` `OntologyActionResponse`（`:272` `kg_version`、`:273` `status: Literal["applied"]`） |
| **增量重算（本批要接的）** | `backend/app/services/kg/incremental.py::rebuild_incrementally`；返回 `IncrementalRebuildResult`（`status` in `ready` / `failed`）；前置不成立抛 `IncrementalRebuildError` |
| **动作表** | `backend/app/db/models.py:1021 OntologyAction`（`:1069 kg_version`、`:1071 result_kg_version`、`:1064 target_entities`）；`:504 EntityMergeCandidate`（`:524-525` CheckConstraint **已含 `applied`**） |
| 契约现状 | `contracts/openapi.yaml:5006` `/ontology/merge`、`:5146` `/split`、`:5076` `/rename`、`:2535` `const: applied` |
| 既有正向守卫（**不许改断言**） | `backend/tests/test_kg_versioning.py`、`tests/test_guardrails_graph.py`（9 条，G-9）、`tests/test_guardrails.py:328`（G-10）、`tests/test_kg_incremental_rebuild.py`（**P5-F 新增 9 条，本批必须继续绿**）、`tests/test_rbac.py:62` 起的参数化拒绝用例 |
| 契约出口 | `backend/app/core/openapi.py:129-134`；计数门禁 `backend/tests/test_openapi_contract.py:106-107`（现 **26 路径**）、`:149-152`（enum 与 `ErrorCode` 全等断言） |
| CI 环境 | `.github/workflows/ci.yml:60-71` `postgres:16-alpine` service；`:114-115` `DATABASE_URL=app_rls` / `DATABASE_URL_OWNER=app_owner`；另有 `neo4j:5.26-community` service |
| 三条门禁 | `scripts/check_seams.py` / `check_session_drift.py` / `check_startup_readiness.py` |
| 先例 | `changes/P5-F/integration-log.md` §2.3（登记写法）、§4（S5 说明）、§8（指针）；`changes/P5-C/integration-log.md` §7.4（契约再生处置模板） |

---

## 7. 已完成项（P5-F 及之前）

- ✅ **M6 增量重算**（P5-F，2026-10-08）：`app/services/kg/incremental.py::rebuild_incrementally`
  ——只重写受影响子图（真 Neo4j 前后计数做差 = 校正节点数，**不是**全图节点数）+ 文档级新
  `kg_version`（复用 `KgVersioningService`）+ `result_kg_version` 真回填 + 失败显式失败；
  `INCREMENT_REBUILD_BATCH_SIZE`（默认 100，有真实消费者）；CI **1103 passed / 5 skipped / 0 failed**（+9）。
- ✅ **M5 统一脱敏 `mask(field, category)`**（P5-E）/ **私域出向管控**（P5-D）/
  **M6 第一批（`ontology_actions` 表 + 冷启动 / confirm / active + RBAC）**（P5-C）。
- ⚠️ **本批要兑现的债**：三端点仍是占位骨架（**本批做**）；P5-C §11 第 1 条的 RBAC 债（**本批做**）；
  `entity_merge_candidates.status = applied` + 升版 M2 spec（**本批做**）；**P5F-4 完整性缺口**（**本批须裁决**）。
- ⚠️ **继续有意不做**：`alert` 表（P2）；成本仪表盘（批次 D）；GUI（另一批）；
  DR-B6 / DR-B7 与 G-9 / G-10 的 docs 口径对账。

---

## 8. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1103 passed / 5 skipped / 0 failed**（run `37731281218` / commit `b581e240`，2026-10-08） |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*` 三开关） | P5-F 实读 **1102 passed / 4 skipped / 2 failed**——2 条 failed 是**本地特有的既有环境债**（`test_eval_ci_gate.py` / `test_eval_corpus_a8.py` 的 g25 真图用例依赖 CI 的「导入受控种子语料」步骤，本机图库没有那份语料）。**CI 上有导入步骤 ⇒ 那 2 条在 CI 上绿** |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**26 路径**） |
| `PROTECTED_ENDPOINTS` | `tests/test_rbac.py:62`，现 **6 条**（本批 +3 ⇒ 9 条） |
| 前端 | 未在**本地**跑 `typecheck` / `lint` / `build`；只在 CI 内绿 ⇒ 若触及前端生成物，**以 CI 为终裁** |
| 最近一次绿 CI | **不要照抄写死的 run id**。开工时 `gh run list --limit 1` 实读；本文件成文时是 **run `37731281218` / commit `b581e240`** |

---

## 9. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **三端点不再是 501** | 三个端点各一条 200 用例，响应 `{kg_version, status: "applied"}`；**且** `kg_version` **不等于**操作前的 active 版本（是新版本） |
| 2 | **图操作是真的（**真 Neo4j**）** | merge：目标节点合并（受影响节点数 −1 或属性按预期合并）；split：新增 N 个节点且原节点 `status='split'`；rename：`canonical_name` 变了且 `aliases` 含旧名。**断言对象是图里的实际节点/属性，不是响应体** |
| 3 | **增量重算真被触发** | `ontology_actions` 对应行 `result_kg_version` **非空**（真 PG 读回），且 `kg_versions` 新增一行 `status='ready'` |
| 4 | **`entity_merge_candidates.status = applied`** | merge 后对应候选行 `status` 由 `human_review` → `applied`（真 PG 读回） |
| 5 | **M2 spec 已升版** | `specs/m2-extract-kg.md` §4.5 注脚（`:132-136`）与 §3 验收 3（`:48`）的口径已改为「M6 已落地」；**编号未重排**（R5） |
| 6 | **RBAC 生效** | 三端点挂了 `require_permission`；`tests/test_rbac.py:62` 已登记三条 ⇒ 参数化用例**自动**给每条端点一条「无授权 ⇒ 403」；另有一条「有角色无该权限 ⇒ 403」 |
| 7 | **跨 org 403** | 以 A org 身份操作 B org 的实体 ⇒ **403 `FORBIDDEN`**，且**不**产生任何图变更（不是"只处理同租户那个"） |
| 8 | **失败路径显式失败** | 注入一次增量重算失败 ⇒ 端点返回明确错误、`ontology_actions.error_code` 落库、`result_kg_version` 仍 NULL，**没有**回落全量重建（旧版本节点数不变） |
| 9 | **P5F-4 已裁决且有判据**（D9） | 无论取哪条路径，都要有一条**可贴的机器输出**：要么是新版本图完整性的正向断言，要么是「以新版本读图 ⇒ 只看到被校正节点」这条例外的显式断言 + integration-log 的缺口登记 |
| 10 | **契约零漂移** | `export_openapi.py --check` 零 diff、**26 路径不变**（若 D6 判定需改 ⇒ 走完五步并在 CI 证明零漂移） |
| 11 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0 |
| 12 | **pytest 不降** | **CI ≥ 1103 passed / 5 skipped / 0 failed**；既有守卫（含 P5-F 新增的 `test_kg_incremental_rebuild.py` 9 条）**不许为让它绿而改断言** |
| 13 | **CI 四 job 全绿**，`gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log | |

---

## 10. 提交推送纪律 + 升级我的四类情况

**提交**：按 backend / specs（M2 升版）/ 契约+前端生成物**分段** Conventional Commits
（M2 spec 升版单独一笔，便于整笔 revert；契约再生单独一笔）；
跨侧改动**不得混在一个提交**。推送后 **以 CI 为终裁**（R-10），CI 红了先看是不是批次摊太大，
**不许先改测试让它绿**。

> 🔧 **推送故障解法（P5-E 收尾实测 + P5-F 复核一次即通）**：连丢多次是 **git 的 HTTP/2
> 传输层**握手失败，不是网络不通（同刻 `gh api user` 正常返回）。
> 加大间隔**无效**；直接用 **`git -c http.version=HTTP/1.1 push origin main`**
> （`-c` 是单次覆盖，**不改 git config**——本仓库禁止改 git config）。

**只在以下四类停下找我**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §8 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完下面三步自检再报告**） | 真踩到的例子：D9 的三条候选**都不成立**（如新版本图完整性在本批无解且无法登记）、或 m6 §3.2 验收 4 的「关系迁移规则」缺到无法落地 |
| 3 | **边界冲突** | 实现中必须触碰 §4 的某条 Non-goal。**注意**：§5 D6 的契约再生**不属此类** |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？
2. 能不能**整体推到下一批**并登记？（如：某些边界形态 ⇒ 本批取最小可证形态并在 integration-log 登记）
3. 真不行了 —— **报告时带上**：哪份 spec 的哪一行、要加/改什么、为什么绕不过去、**你试过的替代方案**。
   不接受"spec 没写所以做不了"这种笼统结论。

---

## 11. 不许外推（**完成本批 ≠ 以下任何一条**）

- **三端点可用 ≠ GUI 可用**：m6 §1.1 批次 B 的**前端界面**仍不存在，本批连前端都不碰。
- **端点 200 ≠ 本体真的更好**：本批不做任何抽取质量评测；「合并后问答更准」**没有数字**。
- **增量重算被触发 ≠ 成本真的低**：本批**不测** token / 耗时 / 成本比（批次 D 的事）。
- **新 `kg_version` 落了 ≠ M3 / M4 消费完整**：**P5F-4** —— 新版本目前只承载受影响子图，
  消费侧会**只看到被校正的那一小撮节点**。本批要么解决、要么按 D9 把它变成显式断言 + 登记缺口。
- **`status='applied'` 写了 ≠ 人工队列闭环**：`human_review` 队列**仍无读端点**（M2 的 S9.13-2 未闭），
  本批只写 `applied`，**不**补队列读端点。
- **`require_permission` 挂了 ≠ 权限模型完整**：只做了「端点接线」，判定逻辑一行未改；
  三粒度（角色 × 文档 × 场景）的覆盖度未重新评测。
- **契约零漂移 ≠ 功能可用**：判据只证明了"契约没被踩歪"。
- **本地绿 ≠ CI 绿**：本机 Neo4j 常是停的，且本地有 2 条 g25 失败（缺 CI 种子语料）⇒ **以 CI 为终裁**（R-10）。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着「pytest 全绿 ≠ 护栏在拦」。
- ⚠️ **若你在实现中动到租户隔离相关路径**（本批**预期不动**判定逻辑，但三端点确实会写图）：
  须带上 **ADR-0003 §4.1** 的两类测试 **T1 跨 org 越权**（G-9，已 ✅，`test_guardrails_graph.py` +
  `test_guardrails_rls.py`）与 **T2 并发串租户**（G-10，已 ✅，`tests/test_guardrails.py:328`）——
  **在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only` 绕过**；它们**已有的断言不许放宽**。

---

## 12. 下一批指针（**本批收口时按实际结果更新，别照抄**）

1. **本体校正 GUI（前端）**：m6 §1.1 批次 B；三端点可用后即可接。同批按需建
   `frontend/src/api/ontology.ts`（m6 §10.1 第 4 条：无 UI 消费前建了属强行同步开发）。
2. **`GET /cost/dashboard` + `cost_metrics` 表**（m6 §3.4 验收 8 / 9），与 MVP 准入 **C3-a / C3-b** 一起做；
   `cost_ratio` 阈值 TBD-7 **Sprint 13 收敛前拿不到判据**。
3. **版本链读侧**（若 D9 未在本批解决）：让 `fetch_active_kg_version` / 图谱查询支持
   「新版本 ∪ 其基线版本」的继承读，解决 P5F-4 的消费侧完整性。
4. **`human_review` 队列读端点**（M2 的 S9.13-2）：有了 GUI 才有消费者。
5. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2；**已连续四批**有意不做）。
6. **DR-B6 / DR-B7 与 G-9 / G-10 的口径对账**（纯 docs）：需求侧明细行仍写「⏳ 零代码」，
   而护栏侧均已 ✅ 转正。建议并入任一批次顺手做，**不单独开工**。
7. **多租户出向审计归属**：脱离「一套 compose = 一个租户」时需给 `build_chat_model` /
   `build_default_embedder` 补 org 传递（P5-D 的 X-3 撤回条件）。
8. **D7（`question` 参与检索）/ D5（M4 完整化）/ D8**：算法活，各自单独排。
9. **m6 定稿遗留的另两个配置项**（`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `COST_RATIO_ALERT_THRESHOLD`）：
   在对应批次回填，**别顺手补齐**。
10. **日志 `message` 正文的脱敏**：P5-E 明确不覆盖。正确路径是**逐个把 `mask()` 调用点补到写敏感值的
    日志语句上**，而不是做值识别。
