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
