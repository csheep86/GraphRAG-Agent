# P0 · M6 spec v1.0 定稿 · 实测日志（integration-log）

> **本文件是事后实测证据**，与 [`tasks.md`](./tasks.md)（事前计划）**不可互相替代**。
> 只写"已完成"不写证据 = 没做完。

---

## F1 — schema-suggestion 端到端 PoC（P1-5 硬闸门）

**结论：通路跑通（fake 确定性 + 真机各一次）**。风险 **R2「schema-suggestion 模式未实测验证」由此解除**。

### 1.1 开工前实测（决定 PoC 形状的既有事实）

| 探测量 | 实测 |
|---|---|
| `ontology_schemas.status` 合法值 | **只有 `active` / `superseded`**（`models.py::ONTOLOGY_SCHEMA_STATUS_VALUES`）⇒ **不存在"候选"这一档** |
| 既有消费链路 | `ontology.py::load_active_ontology` / `extraction_type_vocabulary`，**已被** `tasks/registry.py:60`、`graphs.py:2320` 真消费 |
| LLM 注入位 | `extraction/langextract.py::_default_llm_invoke`、`providers/llm.py::build_chat_model`（**接缝 3**） |

⇒ 「未确认即生效」在结构上就写不出来：**`suggest_ontology_types` 的签名里没有会话参数**，
它只能返回建议对象，落库只能走确认路径（`POST /ontology/confirm`，**归 P5-M6 批次**）。
这是验收 1「未确认的 schema **不写入**」的**机械落实**，不是靠注释自觉。

### 1.2 落了什么

| 文件 | 内容 |
|---|---|
| `prompts/ontology_suggest_v1.md` | 新增 Prompt 版本（域描述 → 类型建议，只输出 JSON） |
| `app/services/ontology.py` | `suggest_ontology_types()` + `OntologySuggestion` + `OntologySuggestError` + 解析/规范化/截断；默认调用走接缝 3 |
| `tests/test_ontology_suggest.py` | 5 条（全 fake）：规范化 / 围栏容忍 / **解析失败报错而非静默回落** / **不落库** / **建议结果可被抽取词表消费** |
| `scripts/probe_ontology_suggest.py` | 真机留证脚本（**不进 CI**，每次执行 = 一次计费调用） |

### 1.3 真机留证（1 次定向调用，deepseek-chat）

输入域描述：`企业考勤与工时合规管理：员工、考勤记录、请假与加班、制度条款`

产出 **12 实体类型 + 12 关系类型**（**双双命中上限** ⇒ 截断逻辑真实生效，也说明模型倾向给满）：

```text
entity_types : EMPLOYEE / DEPARTMENT / ATTENDANCE_RECORD / SHIFT_SCHEDULE / LEAVE_REQUEST /
               OVERTIME_REQUEST / WORK_HOUR_STAT / COMPLIANCE_POLICY / POLICY_CLAUSE /
               APPROVAL_FLOW / VIOLATION_EVENT / COMPLIANCE_CASE
relation_types: BELONGS_TO / MANAGES / HAS_RECORD / HAS_SHIFT / SUBMITS / SUM_OF /
               DERIVED_FROM / GOVERNED_BY / CONTAINS_CLAUSE / USES_FLOW / VIOLATES / INVOLVES
```

**质量观察（供 M6 实现批次参考，不粉饰）**：

- ✅ 类型名**全部**符合 `英文大写下划线` 约束 ⇒ 可直接进抽取词表；
- ✅ `head_types` / `tail_types` **全部引用了自身给出的实体类型**，无一悬空引用；
- ⚠️ 12 条正好卡在上限 ⇒ **上限就是"实际产出量"**，M6 实现时要决定：是放宽上限，
  还是在 GUI 上让用户自己砍（我倾向后者——类型越多，抽取误配率越高）。

### 1.4 ⚠️ 差异登记：验收 1 点名的 Prompt 与语义不符（**定稿增补项，F3 裁决**）

`specs/m6-ontology-incremental.md` §3.1 验收 1 原文写：

> 系统调用 **`kg_qa_v1.md`**（轻量 LLM 调用，**不修改 prompt**）建议一组 entity_types / relation_types

**实测判断：这句在草案期是"就地复用"的写法，语义错配** —— `kg_qa_v1` 是**问答**模板，
拿它生成本体建议，建议质量无法归因（答不好分不清是模板问题还是模型问题）。

**本次处置**：新增 `prompts/ontology_suggest_v1.md`，并把「不修改 prompt」理解为
**不篡改既有 prompt**，而非「不许新增版本」——PRD H9 约束的是 **P2 之前**的模块，
M6 在 P5，允许新增版本号。

⇒ **F3 定稿时必须就这一句给出裁决**（改验收 1 的点名 / 或登记为"草案原文保留 + 实现口径见本日志"），
**不许**默默按新 prompt 实现却让 spec 继续写着 `kg_qa_v1`。

### 1.5 收尾三件套

| 项 | 结果 |
|---|---|
| `uv run pytest -q` | **718 passed / 3 skipped / 7 xfailed**（上批 713 ⇒ +5 新增；**无失败**） |
| `ruff check` + `ruff format --check` | 全过（format 曾报 1 文件待格式化，已修） |
| `check_session_drift.py` | ✅ 未发现漂移 |
| `check_seams.py` | ERROR 0（接缝 1 等 OK） |
| `export_openapi.py --check` | **[OK] 与后端模型一致**（本批未动端点 ⇒ 契约零 diff） |

### 1.6 遗留（照实登记）

| # | 遗留 | 处置 |
|---|---|---|
| 1 | 真机调用**实际执行 2 次**——第 1 次输出被终端截断，为取回完整产出又跑了一次 | 记在此处，不粉饰成 1 次；后续探针应直接落盘（`> out.json`） |
| 2 | 本机 Docker Desktop 本次**未启动**（pg 容器是 `--rm` 的，上次会话后已消失） | 已拉起并重建 `graphrag-pg`；测试库 `graphrag_test` 由 conftest 自建 |
| 3 | `prompts/ontology_suggest_v1.md` 的**质量阈值**未定（类型数上限 12 是拍的） | 归 P5-M6 批次实测调；已写入 §1.3 观察 |
| 4 | 验收 1 的 Prompt 点名差异 | F3 裁决（§1.4） |
| 5 | `USERS_CONSUMER_MODULES` 与本批无关，但下次动 `app/` 引用 `User` 仍须登记 | 判据已在（P2-A 建的），不动它 |

---

## F2 — 契约先行（§5.5 的 7 个端点进契约）

**结论：契约 19 → **26** 路径，零漂移。** spec §10 ④「契约漂移核验」的**前置条件已具备**
（勾选仍归 F3）。

### 2.1 为什么必须先落骨架（决策点 D2 的实测依据）

契约**不是手写**的：`contracts/openapi.yaml` 由 `scripts/export_openapi.py` **从 app 导出**
（`app.main:app` 的 Pydantic 模型是唯一真源）。⇒ **端点不注册路由就进不了契约**，
前端 `gen:api` 也就拿不到类型。所谓"契约先行"在本仓的**机械含义** = 先有路由骨架。

**占位一律 501，不返回 200 空结果**：空结果会被前端读成「接口可用」，
那是本项目反复拦的"假做"（业务没实现却报成功）。`detail.blocked_by` 写明
「实现归 P5-M6 批次」，让排障的人能分清「还没做」与「基础设施挂了」。

### 2.2 落了什么

| 文件 | 内容 |
|---|---|
| `app/schemas/ontology.py` | 6 个 ontology 端点的请求 / 响应；与 F1 的 `OntologySuggestion` **同构** |
| `app/schemas/cost.py` | `GET /cost/dashboard` 响应 |
| `app/api/v1/routes/ontology.py` | 6 个端点，共用 `_placeholder()` 抛 501 |
| `app/api/v1/routes/cost.py` | 1 个端点 |
| `app/core/errors.py` | 新增 `SCHEMA_VERSION_NOT_ACTIVE`（409；重复确认 / 无 active schema） |
| `app/api/v1/responses.py` | 新增 `SCHEMA_VERSION_NOT_ACTIVE` + `PLACEHOLDER_NOT_IMPLEMENTED` 声明 |
| `app/api/v1/router.py` / `core/openapi.py` | 注册 + `ontology` / `cost` 两个 tag 说明（含"当前恒 501"警告） |
| `tests/test_ontology_placeholder_endpoints.py` | **15 条**新测试 |
| `tests/test_openapi_contract.py` | 路径集 19 → 26、operation_id 计数 19 → 26 |
| `contracts/openapi.yaml` + `frontend/src/types/api.d.ts` | 重导产物 |

**同构是刻意的**：冷启动建议的形状 = `{name, description?}` / `{name, head_types, tail_types, description?}`
= `confirm` 入参形状 ⇒ 建议结果可**原样**交给 confirm，路由层 / 前端**不需要**二次映射
（映射层是错配高发地，能不写就不写）。

### 2.3 收尾三件套（数字）

| 项 | 结果 |
|---|---|
| `uv run pytest -q` | **733 passed / 3 skipped / 7 xfailed**（上批 718 ⇒ **+15**；无失败） |
| `ruff check` + `ruff format --check` | 全过（format 曾报 3 文件待格式化，已修） |
| `export_openapi.py --check` | **[OK] 与后端模型一致**（重导后零 diff） |
| 契约路径数 | **26**（脚本核对：`len(paths) == 26`，7 个新路径全在） |
| `npm run gen:api` + `typecheck` + `lint` | 均通过，无报错 |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 10 |
| `check_startup_readiness.py` | 🟢 已生效 9 / 🟠 部分 2 / 🟡 挂起 4 —— **与本批改动无关**（本批未碰任何护栏） |
| `check_session_drift.py` | S1 ✅ 有 7 条 Non-goals / S3 ✅ / S5 ✅ 无孤儿模块；**S2 ⚠️ 新增 2168 行 > 600** |

**S2 自答**（脚本是报告不是门禁，但必须答）：2168 行里 **2078 行是生成物**
（`contracts/openapi.yaml` +1019、`frontend/src/types/api.d.ts` 重导），
手写的骨架代码约 700 行且**已拆成两个提交**（后端骨架 / 契约+前端类型）分开落账，
不存在"顺手多做"。另三条自检问句：① 无顺便做的东西；② 无绕路实现
（`date` 字段与 `datetime.date` 撞名 ⇒ 用 `dt.date` 标注，是 Pydantic 的硬性要求，不是绕路）；
③ 判据是真跑出来的（733 passed / 26 路径 / `--check [OK]` 均有命令输出）。

### 2.4 ⚠️ 带出的 5 个待裁决项（**F3 处理**，不粉饰）

| # | 项 | 本次处置 | F3 该做什么 |
|---|---|---|---|
| ① | **501 语义冲突**：项目 `ErrorCode.NOT_IMPLEMENTED` 既有口径是「**基础设施不可用**，**不**表示接口未实现」，而 7 个占位用它表示"功能未实现" | 复用 501（HTTP 本义即 Not Implemented），靠 `detail.blocked_by` 区分；新增错误码只用 7 次、实现时必删 ⇒ 不划算 | 裁决：改 `NOT_IMPLEMENTED` 的描述口径 / 或登记「占位期例外」 |
| ② | **6 个响应缺 `trace_id`**：§5.5 只有冷启动列了 `trace_id`，其余 6 个没列，与项目惯例（所有响应都带）冲突 | **按 spec 逐字照抄**（spec 是本批权威）；`X-Trace-Id` 响应头恒回显，不受影响 | 裁决：补 `trace_id` 进 spec，或明确"本体/成本响应不带" |
| ③ | `split.new_entities[]` 的 **`{canonical_name, ...}` 省略号**未展开 | 只落 `canonical_name`；另加 `min_length=2`（本批**推断**：只拆 1 个 = 改名，应走 rename） | 确认 `min_length=2`，并按需补字段 |
| ④ | `cost.by_date[]` **每项字段未定义** | 最小可用：`date` + `token_usage_total` + `single_doc_cost`；**不**发明 `cost_ratio`（那是区间级指标，按天算意义不明） | 确认字段集 |
| ⑤ | 前端 **mock / api 包装未建** | 未建：7 个端点**无 UI 消费**，补 mock 属「强行同步开发」（CODEBUDDY §功能预留原则 1/2） | 确认；M6 实现批次按需增补 |

### 2.5 遗留（照实登记）

| # | 遗留 | 处置 |
|---|---|---|
| 1 | 7 个端点**仍是占位**：调用即 501，无 UI、无实现 | F3 只勾「契约已先行」；**不得**据此宣称 M6 已实现 |
| 2 | 前端 `src/api/ontology.ts` / `src/api/mock/ontology.ts` 不存在 | 等 M6 实现批次；已登记（§2.4 ⑤） |
| 3 | `min_length=2`（split）为本批推断，非 spec 原文 | F3 确认（§2.4 ③） |

---

## F3 — spec 升 v1.0（架构师）

**结论：`specs/m6-ontology-incremental.md` 已由 v0.1 草案升 **v1.0 定稿**（2026-10-02），
§10 checklist **8 项全勾**。**Sprint 12 开工闸门已开**（DR-D2）。**

### 3.1 checklist 逐项证据（**全部是实测，不是"看起来齐了"**）

| # | 项 | 实测结论 |
|---|---|---|
| ① | M2 §4.5 接口对齐 | `specs/m2-extract-kg.md` §4.5 `status` 行**已写**「另有 M6 前向预留值 `applied`」+ 独立注脚（M2 阶段不落该值、`[0.70,0.90]` 仍进 `human_review`、M6 落地前走契约同步 5 步）⇒ **文档侧对齐**。⚠️ **代码 / 契约侧未动** —— `applied` 未进 Pydantic / `contracts/openapi.yaml`，属 M6 实现批次（已入 spec §10.1 第 1 条） |
| ② | PRD §2 / 附录 C | PRD §2 M6 行**实测已是**「**P0（口径修订）**」（2026-09-21 改，R1 闭环）⇒ **无需改**；本次只改**附录 C.0 第 5 行**（v0.1 草案 → v1.0 定稿）+ 头部关联规格行 + §7 冲突登记 |
| ③ | 删 §7 | 草案专属的口径演化正文**已删**，结论并入 PRD §2；**编号位保留**（见 §3.3 第 2 条说明） |
| ④ | 契约漂移 | **F2 证据**：路径 **19 → 26**、`export_openapi.py --check` **[OK] 零 diff**、`gen:api` + `typecheck` + `lint` 通过 |
| ⑤ | 配置项消费者 | ✅ **不适用**：三个配置（§6）**一个都没落 `config.py`** —— 无消费者即不提交。spec 已注明「勾选 = 本批无违规配置项，**不是**配置已就绪」 |
| ⑥ | 版本行 | `v0.1（草案…）` → **`v1.0`（2026-10-02 定稿）**；状态行「草案」→「定稿」；**额外加了「定稿 ≠ 已实现」警告** |
| ⑦ | 回填 dev-doc-status | **P1-3 置 ✅ 2026-10-02**（含证据路径）；同步 §0 汇总表（P1 已完成 2 → **4**、进行中 **1**）与 **R2 置「已闭环」** |
| ⑧ | （spec §10 第 8 项）版本行 / 回填 | 同上 ⑥⑦ |

### 3.2 本批裁决的两组争议

**A. prompt 语义错配（F1 §1.4 登记、PRD §7 点名要求）**

- **裁决**：冷启动的 LLM 载体由 `kg_qa_v1.md` → **新增 `prompts/ontology_suggest_v1.md`**。
  「不修改 prompt」= **不篡改既有 prompt**，≠「不许新增版本」（H9 约束 **P2 之前**的模块，M6 在 **P5**）。
- **三处同步**：spec §3.1 验收 1（改正文 + 加裁决注脚）／ spec §9 关联表／ PRD §7 冲突登记改「已裁决」。
- ⚠️ **这是本批唯一越过 Non-goal「不改 §1~§6 实质内容」的改动**，且**只改一句**。
  理由：PRD §7 原文写明「**m6 spec 升 v1.0 时必须就验收 1 那一句给出裁决**，不许 spec 继续写着
  `kg_qa_v1` 而代码按新 prompt 跑」—— 不改即违反 PRD 硬要求。已在 spec 就地标注为定稿增补。

**B. F2 带出的 5 项（§2.4）** ⇒ 裁决写入 **spec §5.5.1**（4 项契约侧）+ **§10.1**（6 条遗留）：

| # | 裁决 |
|---|---|
| ① 501 语义冲突 | 占位期**复用 501** + `detail.blocked_by` 区分；M6 实现后不再返 501 ⇒ **不改 `NOT_IMPLEMENTED` 口径**（避免为临时占位改永久语义、并避免再触发一次契约重导） |
| ② 6 个响应缺 `trace_id` | **按 spec 逐字照抄**（不带）；`X-Trace-Id` 响应头恒回显，溯源不依赖响应体 |
| ③ `split.new_entities` 省略号 | **不展开**；`min_length=2` 保留为**本批推断**，§10.1 要求实现批次复核 |
| ④ `cost.by_date[]` 字段 | **最小可用**三项（`date` / `token_usage_total` / `single_doc_cost`）；不给按天 `cost_ratio`（区间级指标） |
| ⑤ 前端 mock 未建 | **不建**（无 UI 消费，建了属强行同步开发）；登记 §10.1 第 4 条 |

### 3.3 两处"没照字面执行"（照实登记）

1. **⑦ 不是"删除 §7"，而是删正文 + 保留编号位**：整节删除会让 §8 / §9 / §10 **编号错位**，
   而 `dev-doc-status.md` **P1-3**、本批 `tasks.md` 等多处锚点指向 **§10**。
   守 `dev-doc-status.md` **R5**（编号定稿后**只追加、不重排**）。§7 现为一行指向 PRD 的注脚。
2. **⑤ 勾选的含义不是"核验通过"**：三个配置项在本批**根本不存在**（没落 `config.py`），
   所以勾选 = 「**本批没有违规配置项**」。已在 spec 该项内写明，避免后人读成"配置已就绪"。

### 3.4 收尾数字（F3 是**纯文档批次**，无代码改动）

| 项 | 结果 |
|---|---|
| `uv run pytest -q` | **733 passed / 3 skipped / 7 xfailed**（与 F2 收尾**一致**，无新增无减少） |
| `export_openapi.py --check` | **[OK] 零 diff**（本批未动代码 / 契约，仅确认未被破坏） |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 10 |
| `check_startup_readiness.py` | 🟢 9 / 🟠 2 / 🟡 4 —— **与 F2 收尾一致**（本批未碰护栏） |
| `check_session_drift.py` | S1 ✅ 有 7 条 Non-goals / S3 ✅ / S5 ✅ 无孤儿模块；S2 无新增代码（文档改动不计入模块行） |

### 3.5 定稿遗留（**spec §10.1 六条**，均非"已做"）

① `applied` 未进代码 / 契约（M6 `merge` 实现前必须走完契约同步 5 步）｜② 7 个端点仍 501 占位｜
③ §6 三个配置无消费者｜④ 前端 `api/ontology.ts` / `mock/ontology.ts` 未建｜
⑤ `split` 的 `min_length=2` 为本批推断｜⑥ `cost.by_date[]` 未与 §4.3 `cost_metrics` 全字段对齐。

**一句话**：**spec 定稿 = 开工闸门已开；M6 尚未实现，任何人不得据"v1.0 定稿"宣称 M6 已交付。**

---

## 附录 A — 定稿后复核（**2026-10-02**，用户三问的处置）

用户在 F3 之后提了三问：① 裁决的争议要不要先处理？② 没照字面执行的两处要不要处理？③ 7 个端点仍是 501 要不要处理？
**处置原则：先把"声称闭合"变成"实测闭合"** —— 复核中发现**两个真缺陷**（都是我自己制造的），已修；其余维持原裁决，理由见下。

### A.1 三问 → 处置一览

| 问 | 处置 | 是否本批做完 |
|---|---|---|
| ① 裁决的争议 | **已裁决**（spec §5.5.1 + §10.1 + PRD §7）；复核时发现**一处描述引用了不存在的配置项** → **已修**（A.2） | ✅ 除 M6 实现侧动作外已闭合 |
| ② 没照字面执行的 2 处 | **维持**，并把理由从"声称"升级为"**实测**"（A.3） | ✅ 已复核 |
| ③ 7 个端点 501 占位 | **本批明确不做**（A.4，批次边界硬约束） | ❌ 归 P5-M6 / Sprint 12 |

### A.2 复核发现的**两个真缺陷**（已修）

**缺陷 1：契约描述点名了一个不存在的配置项（自己撞了自己登记的纪律）**

- **实测**：全仓 grep 三个配置名 ⇒ 只出现在 spec §6 与本批文档，**`config.py` 确实没有** ✓（⑤ 勾选成立）。
- **但**：我在 F2 写的 `CostDashboardResponse.cost_ratio` 描述里写了
  「阈值 `COST_RATIO_ALERT_THRESHOLD`，默认 0.5」——**契约文案点名了一个不存在的配置项**。
  前端同学照着去配 `.env` 会配出一个**完全无效的变量**，且 `check_session_drift.py` S3 / "
  无消费者的配置不得提交"的纪律正是防这个。
- **修**：描述改为「告警阈值规范见 spec §6；**该配置尚未落 `config.py`**」，`schemas/cost.py` +
  `routes/cost.py` 两处同步；**重导契约 + `gen:api`**（diff 仅 4 行文案）。

**缺陷 2：§10 checklist 项数漂移「七项 vs 八项」（陈述 vs 事实）**

- **实测**：spec §10 实际是 **8 个 checkbox**（含「⑥ 接缝登记核验」），而四处文件写"七项"
  （spec 头部 / `03-prd.md` §2 / `proposal.md` 出口判据 / `tasks.md` 出口判据），
  且 `tasks.md` 的 F3 列表**漏列了"接缝登记核验"**这一条。
- **修**：四处统一为**八项**；`tasks.md` F3 **补上第 ⑥ 接缝项**并重编号（实测 `check_seams.py`
  = ERROR 0 / WARN 0 / OK 10）。`proposal.md` 的立项判据同改，并注明"按事实更正，**不改判据**"。
- ⚠️ 这正是 `dev-doc-status.md` **R5** / `changes/Sprint9/integration-log.md` 反复拦的
  「**陈述 vs git 的事实**」那类错 —— 数字也会被"读得快"骗过去。

### A.3 两处"没照字面执行" → 维持（**给出实测依据**）

| 处 | 原来说辞（声称） | 复核后的实测依据 | 结论 |
|---|---|---|---|
| ③ 删 §7 → 只删正文、留编号位 | 「多处锚点指向 §10」 | **grep `§10` / `§10.1` 全仓 = 26 处 / 9 个文件**，其中本批活跃文档 **6 个文件 23 处**（spec 6、tasks 4、proposal 3、integration-log 6、dev-doc-status 2、PRD 2）⇒ 整节删除并重排会让这 23 处**全部错位** | **维持**（守 R5 编号只追加） |
| ⑤ 配置项勾选 = "不适用" | 「一个都没落 config.py」 | 同上 grep ⇒ **属实** ✓；且已在 spec 该项内写明「勾选含义 = **本批没有违规配置项**，**不是**配置已就绪」 | **维持**（并在 tasks.md 标注为实测） |

### A.4 501 占位：为什么**现在不能做**（批次边界，不是偷懒）

- **Non-goals 第一行**（`proposal.md`）：「**不实现 M6**：冷启动 GUI、人工校正界面
  （merge/split/rename）、增量重算、`cost_metrics` 落库与仪表盘」。
  7 个端点由 501 变可用 = **整个 P5-M6 / Sprint 12 的工作量**（且 §3.2 B 段要求实现前先走完
  `applied` 的契约同步 5 步）。在这批里做 = **批次崩坏**，且失败时找不到是哪一处（S2 的精神）。
- **spec §10.1 已把六条遗留写成可执行清单**，实现批次照单linha：
  ① `applied` 进契约（5 步）② 7 端点实现 ③ 三个配置逐个核消费者 ④ 前端 mock ⑤ `min_length=2` 复核
  ⑥ `by_date[]` 与 §4.3 `cost_metrics` 对齐。

### A.5 收尾数字（本次补丁）

| 项 | 结果 |
|---|---|
| `pytest -q` | **733 passed / 3 skipped / 7 xfailed**（与 F3 一致，无增减） |
| `ruff check` / `format --check` | 全过（193 files unchanged） |
| `export_openapi.py` 重导 + `--check` | **[OK] 一致**（diff **4 行**：cost 描述文案 ×2 处） |
| `gen:api` + `typecheck` + `lint` | 均通过（diff 4 行） |

### A.6 关于 F4（C1–C3 评测方案）

`tasks.md` 的 **F4 标注为「另立一批」**（决策 D3），属**不同的交付单元**：
受控问题集 / TBD-7 阈值落 `config.py` / 评测脚本入口（DR-D10）。
本批（`P0-m6-finalization`）**F1/F2/F3 + 本附录已全部完成**，
建议**另立 `changes/` 批次**开 F4 —— 它要先解决"评测脚本从哪来"（含把
`temporal_poc/run_track_s.py` 之类的判据脚本迁入 `backend/tests/`，见 P1-6 的同类先例）。
