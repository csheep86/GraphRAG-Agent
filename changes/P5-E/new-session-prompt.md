# 新会话开场提示词 · P5-E（M5 收尾：`mask()` 统一脱敏 + 「无原文落库」机械判据）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。详见 §1。
>
> 📦 **本文件自包含**：上一批（P5-D）已收口（`main` = `ebbdcb92`，CI run `37718672354` 四 job 全绿）、
> 不会再回来。开工所需坐标、命令、基线、陷阱都在本文里。唯一需要你额外读的是 §0.5 的**五份仓库内文件**。
>
> ✅ **范围已由用户确认（2026-10-08）**：先做完纯 docs 收口（`ebbdcb92`），**再**做本批 M5 收尾。
> 本文件可直接作为新会话第一条消息。
>
> 复制本文件**全文**到新会话作为第一条消息。

---

## 0. 本批一句话

**把 M5 §3 验收 3 / §4.5 / §5.3 的「统一脱敏工具 `mask(field, category)`」从零做成真的**：
八类敏感字段（合同金额 / 发票号 / 税号 / 法人姓名 / 银行账号 / 身份证 / 电话 / 文件名）
按 spec 给的策略脱敏，**接线到 `audit_log.detail` 写入前 + loguru JSON 日志两处**，
并用**单元测试断言「原文不落库、不落日志」**（spec §4.5 最后一段点名的那条机械判据）。

**不做**的三件事：`alert` 表（spec §3 验收 5 自标 **P2**）、M6 第二批（merge / split / rename，
其硬前置是契约同步五步 + 尚不存在的增量重算）、任何"脱敏后可还原"的功能。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`changes/P5-D/integration-log.md`** | 上一批实录。**重点 §4.3（X-3 审计 org 回落偏离）**、§7（M5 七条验收的核对结论）、§11（本批的来历） |
| 2 | **`specs/m5-permission-audit.md`** | **v1.0 已定稿**。重点 **§3 验收 3（`:48`）**、**§4.5 八类策略表（`:137-150`）**、**§5.3 统一组件清单（`:176-179`）**、§1.1 目标 3（`:20`） |
| 3 | **`backend/app/services/audit.py`** | `record_audit_entry`（`:108`）是 `audit_log.detail` 的**唯一**写入口 ⇒ mask 的第一处接线点 |
| 4 | **`backend/app/services/documents.py:69` `hash_filename`** + **`backend/app/services/license/fingerprint.py:69` `build_fingerprint`** | 两个**既有**的 SHA-256 样板：前者是「文件名 → hash」的现行实现，后者是「**加 salt** → SHA-256」的现行形态 ⇒ mask 必须**复用**它们，不得再造第三个哈希实现 |
| 5 | **`backend/app/core/config.py`** | 新增配置项（`mask_salt`）要挨着别的字段落成同一种形态；注意第 5 条「禁止无消费者的配置」由 `check_seams.py` 机检 |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

**替代真源映射**（沿用 P5-B/C/D 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（**文件已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-E/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | 本批**预期零契约改动**（mask 是内部函数、不进 API）。**若**你发现必须动契约 ⇒ 按 §5 **D6** 走完同步五步，**这不算升级** |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

**角色隔离**：

| 段 | 角色 | 允许改的范围 |
|---|---|---|
| mask 工具 + 接线 + 后端测试 | **后端开发 B** | **只允许** `backend/` + 跑脚本 |
| 契约与前端生成物**再生**（**仅当 D6 判定为必要**） | 仍是 B（**不写前端业务代码**） | 只允许 `contracts/openapi.yaml`（导出产物）与 `frontend/src/types/api.d.ts`（`npm run gen:api` 产物） |

**分支**：沿用 P4 / P2-C / P5-B/C/D —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P5-E / 为什么是这一刀

### 2.1 三条机械理由

1. **它是 M5 目前唯一的缺口**：spec §1.1 五项目标里，① RBAC ② 审计+trace_id ④ 私域开关（**P5-D 已于
   2026-10-07 做成**）⑤ 限流 **均已落地**，只有 ③「敏感字段过滤」**零代码**——`grep -rn "def mask" backend/`
   当前无结果。做完它，M5 这幅图第一次能说"齐了"（`alert` 表除外，那是 spec 自己标的 P2）。
2. **零 spec 升级**：spec **已经把签名和策略写死了** —— §5.3 第三个统一组件原文
   「统一敏感字段脱敏工具函数（`mask(field, category)`）」+ §4.5 八类策略表（含变换示例）
   ⇒ 实现它是**兑现已定稿的 spec**，不是新增需求 ⇒ 不触发 §10 第 2 类升级。
3. **排期队列里它现在最便宜**：`delivery-plan.md:198` 的 P5 顺序是
   `D4 → D2 M6 → D1 → D3/D5/D7/D8`——**D4 已收口（P5-B）**、**D2 在途（P5-C 开了第一批）**、
   **D1 已达成（P5-D，2026-10-07）**、**D3 已于 2026-10-02 PoC 真机跑通**（已由 `ebbdcb92` 更正状态行）；
   剩下的 **D5（M4 完整化）/ D7（`question` 参与检索）/ D8** 每一个要么是大块算法活、
   要么要花真钱做评测 ⇒ 排在后面。**M5 收尾是当前唯一不需要先兑现另一个前置的目标**。

### 2.2 为什么**不是** M6 第二批（merge / split / rename）

⚠️ 上一份指针里写过"M6 卡在 spec 仍草案"——**那是过期口径，已于 `ebbdcb92` 更正**：
`specs/m6-ontology-incremental.md` 实为 **v1.0（2026-10-02 定稿）**，硬闸门 **CP-3 已打开**。
但仍然**不建议**本批做，原因是两道**新的**硬前置：

| 前置 | 出处 | 状态 |
|---|---|---|
| **`entity_merge_candidates.status` 加 `applied` 枚举** + Pydantic + 重导契约 + `gen:api` + 零漂移（五步） | `specs/m6-ontology-incremental.md` §4.4 第 159-166 行原文：「**未走完前 5 步，`/api/v1/ontology/merge` 端点不得对外实现**」 | 文档侧已对齐（2026-09-21），**代码 / 契约侧未做** |
| **增量重算** | §3.3 验收 6（节点增量不重建全图 + 新 `kg_version` + 写 `result_kg_version`） | **不存在** |

⇒ M6 第二批 = 「契约同步五步 + 新增枚举 + 增量重算 + 三端点」——**四件事凑一批 = 典型的摊太大**，
按 §2.4 的切法应拆：**先单独做「契约同步五步 + `applied` 枚举」**（那一批很小），再单独做增量重算。

### 2.3 为什么不做 `alert` 表

`specs/m5-permission-audit.md:50` 原文把「累计触发次数超阈值的 IP 写入 `alert` 表」标为 **（P2）** ⇒ 与 P5-D 同一原则：
⇒ 与 P5-D 同一原则：**spec 自己推迟的东西不顺手做**。

### 2.4 本批的三刀（建议范围）

1. **`mask(field, category)` 工具 + 八类策略**：一个函数 + 一张策略表，严格照 spec §4.5 的八行实现；
   **salt 走配置**（见 §5 D2），哈希类策略**复用**既有样板（§0.5 第 4 份文件）。
2. **两处接线**：① `record_audit_entry` 写 `detail` **之前**；② loguru JSON 日志出口。
   再加一条测试基座：**固定一组演示语料**（合同 / 发票 / 凭证三种形态），在其上断言
   「原文既不落库、也不出现在日志里」（见 D8）。
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

---

## 4. 边界纪律 · Non-goals（**11 条，逐条对照**）

| # | Non-goal | 说明 |
|---|---|---|
| 1 | **不实现 `alert` 表 / 限流告警联动** | spec §3 验收 5 自标 **P2** |
| 2 | **不改 `specs/m5-permission-audit.md` / ADR** | 规格齐全（签名 + 八类策略都在），要改 ⇒ §10 第 2 类升级 |
| 3 | **不动 RLS / RBAC / 租户隔离** | DR-B4 / DR-B9 各有门禁；本批只改"值怎么被记下来" |
| 4 | **不碰 P5-C 的三个 ontology 端点与 `ontology_actions` 表** | 它们的偏离已裁决保留，不要再"顺手订正" |
| 5 | **不改 P5-D 的私域守卫（`app/core/egress.py`）** | 上一批刚收口；本批不掺和网络层 |
| 6 | **不新增第三方依赖** | 标准库 `hashlib` / `re` 即可 |
| 7 | **不做"可还原"** | mask 一律**单向**：哈希类加 salt 后不可逆，掩码类丢掉的部分不许留旁路可供拼回 |
| 8 | **不改既有 `documents.filename_hash` 与 `:LegalPerson.id_hash` 的语义** | mask 的「文件名」类必须**产出同一个值**（§5 D4），不得另给一套 |
| 9 | **不重构 loguru 的日志配置** | 只做脱敏接线；**不要**用 patcher / filter 重写整套日志配置，除非 D3 判定必需并在 integration-log 登记理由 |
| 10 | **不做"自动识别字段类型"** | `category` 由调用方**显式**给。让代码去"猜"哪个字段是敏感字段 ⇒ 漏判无处可追责，属典型 scope creep |
| 11 | **不动前端 / 不动契约**（除非 D6 判定必需） | mask 是服务端内部行为 |

> **回切点**：每个子任务收尾跑 `uv run python scripts/check_session_drift.py`，
> S1 必须读到**本文件这 11 条**；S5 命中要答得出归属哪条需求。
> ⚠️ 本批新增了配置 ⇒ **S3 一定会盯**「`config.py` ⇄ `.env.example`」同步：**这不是误报，是必须完成的动作**。

---

## 5. 决策表（**已裁 / 建议采纳项**，逐条有据）

| # | 决策 | 处置 | 依据 |
|---|---|---|---|
| **D1** | 主题 | ✅ 按 §2.1 定 **M5 收尾**。若要换主题，改本文件 §2.4 / §4 / §9 三处即可 | §2.1 三条机械理由 |
| **D2** | salt 怎么处理 | **新增配置 `mask_salt`**（默认给一个常量，便于开发与 CI；可通过 env 覆盖）。三条硬约束：① **必须有真实消费者**（`check_seams.py` 判据 2）；② **必须同步 `.env.example`**（S3）；③ **不得是占位**（ADR-0004 §3 第 5 条禁止新增占位配置，占位清单现只剩 `log_export` 一项） | spec §4.5 的税号 / 法人姓名 / 身份证三行均写「**SHA-256 + salt 哈希**」；现存样板：`license_fp_salt` + `build_fingerprint(salt=…)` |
| **D3** | 接线点 | **两处**：① `audit.py::record_audit_entry` 在写 `detail` 之前；② loguru JSON 日志出口。**优先显式调用**，不要先写全局 patcher；如果实测"显式调用有漏"（某些 logger 绕过），**才**补一个 loguru 兜底 filter，并在 integration-log 登记为什么 | spec §5.3：「所有写日志前必须经过脱敏」；§3 验收 3：「写入日志前**自动**脱敏」 |
| **D4** | 文件名类必须复用既有 hash | `mask(file_name, 'filename')` 的产出必须与 `documents.hash_filename()` **逐字节相同**，并写一条测试断言这个等式 | spec §4.5 第 8 行原文：「SHA-256 哈希（**与 `documents.filename_hash` 复用**）」 |
| **D5** | 是否新增错误码 | **预期不新增**。若确有必要 ⇒ `errors.py` **四处**字典齐加（ErrorCode / 状态码映射 / 描述 / 来源），漏一处 `export_openapi.py` 直接 `KeyError` | `app/core/openapi.py:129-134` 遍历全部 `ErrorCode` 取两个字典 |
| **D6** | 契约会不会动 | **预期零改动**：mask 是纯内部函数，不进任何响应体。用 `export_openapi.py --check` **证明**它没动（这是本批判据之一）；**若**真动了 ⇒ 走同步五步（export → `npm run gen:api` → 提交两生成物 → CI 零漂移），**不算升级** | P5-C 的 B-1 / P5-D 的 D2 已开先例：生成物随实现再生是既有流程 |
| **D7** | 成本敞口 | 本批**预期 ¥0**：全程用固定字符串与演示语料做断言，**不调真 LLM** | 沿用 P5-C D6 / P5-D D7 |
| **D8** | 「无原文」怎么才算机械判据 | 断言对象是**已落库的 `audit_log.detail` JSON** 与**运行期捕获的日志输出**，而不是断言"函数返回值不含原文"——后者是恒绿陷阱（R-9） | spec §4.5 末段原文：「**落库前由单元测试断言"无敏感字段原文"**」 |

**已知陷阱（省钱用）**：

| 陷阱 | 后果 / 处置 |
|---|---|
| 只在单测里断言 `mask()` 的返回值 | **恒绿失效**（R-9）：返回值当然没有原文 ⇒ 必须断言**落库后的 JSON** 与**日志输出** |
| `Settings.model_config` 是 **`extra="ignore"`** | 环境变量名拼错会被**静默忽略** ⇒ 用例要断言**读到的值**，不能只断言"设了"（P5-D 已踩过一次） |
| `alert` 表 / `log_export` 占位看起来很像"顺手做" | 都不做：`alert` 是 P2；`log_export` 是 ADR 登记的最后一项占位，碰它要动 ADR |
| mask 改了 `detail` 的形状 ⇒ 既有测试报错 | 既有 `tests/test_audit.py:103`（断言 `filename_hash` 不出现在 detail）、`tests/test_guardrails.py:320`（`password_hash` 不进契约）等**都是正向守卫**，改红就意味着你改坏了它们的语义 ⇒ **先跑 §3 记基线，再动刀** |
| 中文形态（全角数字 / 千分位 / 空格分隔的银行账号） | spec 示例给的是**具体形态**：`1,234,567.89`、`6228 **** **** 1234`、`138****1234` ⇒ 正则要照示例写，且**中文全角数字**应先归一化，否则 mask 漏掉 ⇒ 漏的那部分就是"判据绿但实际漏绕过" |

---

## 6. 已查证坐标表（**不要再 recon 一遍**）

> 行号基于当前 HEAD（`ebbdcb92`），**仅供定位；以代码实读为准**（行号漂移不影响结论）。

| 坐标 | 位置 |
|---|---|
| 需求条目 | `docs/delivery-requirements-and-guardrails.md:114` **DR-D1 ✅ 已达成**（2026-10-07 P5-D，出口判据「PRIVATE_DEPLOY 路径可用」）；**:115** DR-D2 🟡 在途（spec v1.0 + P5-C 第一批）；**:116** DR-D3 ✅ 已达成（2026-10-02 PoC） |
| 排期队列 | `docs/delivery-plan.md:198`（D4 → D2 M6 → D1 → D3/D5/D7/D8） |
| M5 缺口登记 | `docs/acceptance-traceability-matrix.md:175` **H5 行**（🟡 部分；已登记"承接 P5-E"）、`:54` M5 模块行、**`:176` H6 行 ✅（P5-D）** |
| ADR | `docs/adr/0004-integration-seams.md:142` 例外登记（占位清单已由 2 项 ⇢ **1 项**：只剩 `log_export`）；第 5 条禁止新增占位配置 |
| Spec 判据 | `specs/m5-permission-audit.md:48`（验收 3）、`:137-150`（§4.5 八类策略表 + 「落库前断言」约束）、`:176-179`（§5.3 三个统一组件，第 3 个即 `mask(field, category)`） |
| **第一处接线点** | `backend/app/services/audit.py:108` `record_audit_entry`（`audit_log.detail` 的唯一写入口）；`:52` `ACTION_BY_ROUTE_NAME`；`:211` `_assert_valid_status` |
| **第二处接线点** | `backend/app/core/middleware.py`（loguru JSON 出口；同文件 `:106` 已写明「detail 只写结构化字段 —— 本批次无脱敏器」，**本批把这行的口径改掉时要连带更新该注释**） |
| **可复用样板** | `backend/app/services/documents.py:69` `hash_filename`；`backend/app/services/license/fingerprint.py:69` `build_fingerprint(components, *, salt)` （`:79` 是加 salt 的 SHA-256 现行形态）；`backend/app/services/agents.py:724` `_sha256_text` |
| 配置 | `backend/app/core/config.py`（新增 `mask_salt` 挨着 `license_fp_salt:59` 落成同款）；`:42` `extra="ignore"` |
| 既有正向守卫测试 | `backend/tests/test_audit.py:103`（`filename_hash` 不得出现在 detail）、`backend/tests/test_guardrails.py:320`（`password_hash` 不进契约）、`backend/tests/test_guardrails_compliance.py:208`（License 敏感字段不得进审计 detail） |
| 错误码（**若** D5 触发） | `backend/app/core/errors.py`：ErrorCode 枚举 / HTTP 映射（现无新增）/ 描述字典 / 来源字典 —— **四处齐加** |
| 契约出口 | `backend/app/core/openapi.py:129-134`；计数门禁 `backend/tests/test_openapi_contract.py:106-107`（现 **26 路径**）、`:149-152`（enum 与 `ErrorCode` 全等断言） |
| 上一批守卫（**不动**） | `backend/app/core/egress.py`（P5-D，2026-10-07） |
| 三条门禁 | `scripts/check_seams.py` / `check_session_drift.py` / `check_startup_readiness.py` |
| 先例 | `changes/P5-C/integration-log.md` §7.4（B-1 契约再生处置模板）、`changes/P5-D/integration-log.md` §4.3（X-3 偏离登记格式） |

---

## 7. 已完成项（P5-D + docs 收口）

- ✅ **私域出向管控**（P5-D，2026-10-07）：两个配置 + 构造期守卫 + 503 `PRIVATE_DEPLOY_BLOCKED` +
  `private_deploy.violation` 审计；内网 / 回环**天然放行**（本地 embedding `127.0.0.1:8009` 不被误杀）。
- ✅ **CI run `37627112419` / `37628118069` / `37628697386` 四 job 全绿**，pytest **1066 passed / 5 skipped / 0 failed**。
- ✅ **docs 收口（`ebbdcb92`，2026-10-08）**：DR-D1 ✅ / DR-D3 ✅ / DR-D2 🟡、矩阵 H6 ✅ + M5·M6·H5 三行同步、
  ADR-0004 占位清单 2 ⇢ 1。**同时**更正了一处更大的过期口径：m6 spec 实为 v1.0 定稿（不是草案）。
- ⚠️ **本批继承的债务**：M5 §3 验收 3 的 `mask()` **零实现**；`alert` 表（P2）**有意不做**。

---

## 8. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1066 passed / 5 skipped / 0 failed**（run `37718672354` / commit `ebbdcb92`，2026-10-08） |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*`） | **1065 passed / 4 skipped / 2 failed**（2 failed = `affiliation-demo-v2` 语料不在本地，**已知不修**） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0**；反向守卫 `test_g21_production_sqlite_guard_still_present` 恒通过 |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12**（Settings **65** 字段全部有消费者） |
| `export_openapi.py --check` | 零 diff（**26 路径**） |
| 前端 | 未在**本地**跑 `typecheck` / `lint` / `build`；只在 CI 内绿 ⇒ 若触及前端生成物，**以 CI 为终裁** |
| 最近一次绿 CI | **不要照抄写死的 run id**。开工时 `gh run list --limit 1` 实读；本文件成文时是 **run `37718672354` / commit `ebbdcb92`** |

---

## 9. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **八类策略逐字照 spec 实现** | 一张表 / 一个映射八项齐全，每项有一条形如 spec §4.5「示例」列的对偶用例（`1,234,567.89` → `***,***.00` 等八组） |
| 2 | **文件名类 = 既有 hash** | `mask(name, 'filename') == documents.hash_filename(name)` 逐字断言（D4） |
| 3 | **salt 可配置且有消费者** | `check_seams.py` 仍 **0/0**（新配置有真实消费点）；`.env.example` 已同步（`check_session_drift.py` S3 不报） |
| 4 | **审计链路无原文（**真落库**）** | 写一条含八类原文的 `detail` ⇒ 落到 PG 后**读回来**断言 JSON 中**无一类原文**（这是 D8 的核心，不许只断言函数返回值） |
| 5 | **日志链路无原文** | 运行期捕获 loguru JSON 输出，断言同样的八类原文**不出现**（spec §3 验收 3 的「写入日志前自动脱敏」） |
| 6 | **契约零漂移** | `export_openapi.py --check` 零 diff、26 路径不变（若 D6 判定需改 ⇒ 走完五步并在 CI 证明零漂移） |
| 7 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0 |
| 8 | **pytest 不降** | **CI ≥ 1066 passed / 5 skipped / 0 failed**（本批新增用例只会让分子变大）；既有正向守卫（`test_audit.py:103` 等）**不许为让它绿而改断言** |
| 9 | **既有行为未被改写** | `filename_hash` 与 `:LegalPerson.id_hash` 的**产出值**与上一版一致（有并置断言）；P5-D 的守卫行为不变 |
| 10 | **CI 四 job 全绿**，`gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log | |

---

## 10. 提交推送纪律 + 升级我的四类情况

**提交**：按 backend / 契约+前端生成物**分段** Conventional Commits（契约再生单独一笔，便于整笔 revert）；
跨侧改动**不得混在一个提交**。推送后 **以 CI 为终裁**（R-10），CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。
推送偶发网络失败（本仓库近期 `github.com:443` 间歇性不可达——**上一批 `ebbdcb92` 曾连丢 8 次、等约 40 秒后第 2 次等待成功**），
**加大间隔重试到位再报告**；期间**不许**拿估算的 run id 把表格填满。

**只在以下四类停下找我**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §8 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完下面三步自检再报告**） | 真踩到的例子：某一类敏感字段的 spec 策略与代码现有语义冲突（如「仅保留后 4 位」遇到短于 4 位的输入）且无法用"最小代价 + 登记"绕开 |
| 3 | **边界冲突** | 实现中必须触碰 §4 的某条 Non-goal。**注意**：§5 D6 的契约再生**不属此类** |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？（如：想顺手把 `alert` 表做了 ⇒ Non-goal 1）
2. 能不能**整体推到下一批**并登记？（如：短输入的截断规则 ⇒ 本批取「不足即全掩码」并在 integration-log 登记，
   后续批次再裁决边界形态）
3. 真不行了 —— **报告时带上**：哪份 spec 的哪一行、要加/改什么、为什么绕不过去、**你试过的替代方案**。
   不接受"spec 没写所以做不了"这种笼统结论。

---

## 11. 不许外推（**完成本批 ≠ 以下任何一条**）

- **mask 写了 ≠ 没有泄露面**：只覆盖了 **spec 点名的八类 + 两处接线点**；第 9 类字段、第三个写入路径照样漏。
- **八类策略全通过 ≠ 真实语料不泄**：单测用的是固定形态；真实抽取结果里的格式变体（全角、换行、OCR 错字）
  本批**不验证**。
- **"无原文"断言过了 ≠ 不可还原**：哈希类（税号 / 法人 / 身份证）**加 salt 后单向、不可逆**
  ⇒ 本批**不做**可逆脱敏，也不评估"加 salt 后是否仍可被彩虹表撞库"。
- **`mask_salt` 可配 ≠ 已做密钥管理**：它是「和 `license_fp_salt` 同款的应用级 salt」，**不是密钥**（ADR-0006 §2.1 同口径），
  不得写成"我们有加密"。
- **H5 行登记了 P5-E ≠ H5 已达成**：矩阵 H5 行仍 🟡，**只有本批判据 4 / 5 双绿、.env.example 与 check_seams 都不红之后**
  才能说"部分 → 完整”；届时也要**同时更新 H5 行 + M5 模块行**，并写明"alert 表仍缺（P2）"。
- **M5 收尾了 ≠ M5 完成**：`alert` 表仍在（P2），M5 §3 验收 5 的 P2 部分依旧是缺口。
- **契约零漂移 ≠ 功能可用**：判据只证明了"契约没被踩歪"。
- **本地 1065 绿 ≠ CI 绿**：本地仍有 2 条 `affiliation-demo-v2` 已知 fail。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着「pytest 全绿 ≠ 护栏在拦」。
- ⚠️ **若你在实现中动到租户隔离相关路径**（本批**预期不动**）：须带上 **ADR-0003 §4.1** 已登记的两类测试 ——
  **T1 跨 org 越权**、**T2 并发串租户**，**在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only` 绕过**。

---

## 12. 下一批指针（**本批收口时按实际结果更新，别照抄**）

1. **M6 第一批 B：`applied` 枚举 + 契约同步五步** —— 很小的一批（`m6 §4.4` 明写它是 `/ontology/merge` 的**前置**），
   做完可为 merge / split / rename 开路。**注意这是 2026-10-08 docs 收口后新判断出来的批次**（上一版指针误写为
   "卡在 spec 草案"，已更正）。
2. **增量重算**（m6 §3.3 验收 6）—— merge / split / rename 的第二个硬前置，**不存在**，属独立批次。
3. **`GET /cost/dashboard` + `cost_metrics` 表**（§3.4 验收 8 / 9），与 MVP 准入 **C3-a / C3-b** 一起做。
4. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2 部分；已连续两批有意不做）。
5. **RBAC 债随端点走**：`merge` / `split` / `rename` / `/cost/dashboard` 谁实现谁同批补
   ① `require_permission` ② `PROTECTED_ENDPOINTS` 登记。
6. **多租户出向审计归属**：脱离"一套 compose = 一个租户"时需给 `build_chat_model` / `build_default_embedder`
   补 org 传递（P5-D 的 X-3 撤回条件）。
7. **D7（`question` 参与检索）/ D5（M4 完整化）/ D8**：算法活，各自单独排。
8. **m6 定稿遗留的三配置项回填**：`specs/m6` 定稿时记有"三个配置未落 `config.py`，实现时回填"（见 P1-3 备注第 ⑤ 项），
   做 M6 第二批时须回头兑现。
