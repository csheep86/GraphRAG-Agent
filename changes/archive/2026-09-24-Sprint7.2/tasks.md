# Tasks: Sprint 7.2 批次 B —— M4 疑点持久化与对外端点

> **状态**：**待签字，代码未动工**。签字后按本文件顺序执行，每项须在 `integration-log.md` 留真机证据（命令 + 输出）。
> **前置**：`changes/Sprint7.1` 已收尾（真机 10 条疑点可用）；开工前先读 `proposal.md` 决策点表全文，**B1 / B2 / B3 / B4 / B5 / B6 / B7 必须已拍板**。
> **纪律**：勾选 ≠ 通过；与 plan 的分工——plan §6.2 / §6.3 是 Sprint 级范围与验收，本文件是批次级拆解与勾选。

## 0. 事前核实（**未完成不得往后走**）

- [x] **B1 已签字（2026-09-24）**：以 `/affiliation/suspicions` 为准；已同步改 `plan.md:275` / `plan.md:289`，`Sprint7.1/proposal.md:48` 加口径消歧（历史正文不改）
- [x] **B2 已签字**：表加 `task_id`；**已同步补 spec** —— `specs/m4-affiliation-detection.md` §4.3 增列 + 文末「字段变更登记」注记（含 JSONB→JSON 降维说明）
- [x] **B3 / B4 / B5 / B6 / B7 已签字**：① 每次 detect 新建任务 / `reviewed_by` 取 `X-Actor-Id` / `unaligned_subjects` 只建表不写 / 接缝 7·8 拆 sub-batch / 不动自动投递
- [x] **状态机核实（B7 技术依据）**：`TaskManager.submit()` 用请求级 `BackgroundTasks`（`tasks/manager.py:97`）→ 对「显式触发的终点阶段」足够，**无需**队列；证据 `integration-log.md` §2.2
- [x] **SQLite 类型惯例核实**：全仓**无** `JSONB` / `ARRAY` / `TypeDecorator`；既有写法 = `kg_versions.source_doc_ids` 用跨方言 `sqlalchemy.JSON` + str(UUID) + 服务层双向转换（`db/models.py:151-153`）→ 本批次四列一律照抄，证据 `integration-log.md` §2.3
- [x] **B8（实施期发现，已定）**：`TaskManager.submit()` 硬绑 `payload["document_id"]` 且 task_id 恒为 `documents.id`（`tasks/manager.py:75-104`）→ **扩展为双分支**：payload 携带 `affiliation_task_id` 时走新分支，**现有 document 类路径零改动**（不另起第二个任务投递真值源，ADR-0001 要求 2）
- [x] **顺手纠一处既有漂移**：`app/tasks/types.py:16` 的 `TaskType` Literal **未含 `risk.detect`**（已登记却不在 Literal 里）→ 加 `affiliation.detect` 时一并补上，单独一个 commit 段好 review
- [x] **核实 ADR-0003 登记**：三表已在该 ADR 第 54–56 行列为「补 `org_id`」对象 → 本批次照做，**无需新裁决**

## 1. 契约先行（**必须先于实现**）

- [x] 先改 `backend/app/schemas/affiliation.py`（Pydantic 模型是契约唯一真源）：四个端点的请求 / 响应模型
- [x] 端点语义按 spec §5.5：`POST /affiliation/detect` → **202** `{task_id, status:"pending"}`；`GET /affiliation/tasks/{id}` → `{task_id, status, result_summary?}`；`GET /affiliation/suspicions`（query `severity? / type? / status?`）；`PATCH /affiliation/suspicions/{id}`（`dismissed` / `confirmed`）
- [x] `uv run python scripts/export_openapi.py` 重导出；**禁止手改 `contracts/openapi.yaml`**
- [x] `npm run gen:api` 重新生成前端类型
- [x] **登记 `CONTRACT_COVERED_PATTERNS`**（`frontend/src/api/client.ts:32-38`）——S6 批次 B 在此栽过：漏登记 = 关 Mock 下仍走 Mock

## 2. 后端：PG 三张表（**表名逐字对齐 spec §4.3–4.5**）

- [x] `affiliation_tasks`（§4.4）：含 `id / org_id / doc_ids / status / retry_count / error_code / error_detail / result_summary / trace_id / created_at / updated_at / completed_at`
  - **核对**：§4.4 第 109–111 行**已含** `retry_count` / `error_code` / `error_detail`（ADR-0001 §「需变更点」第 2 条已执行，无需再补 spec）
- [x] `affiliation_suspicions`（§4.3）：含 `suspicion_type / severity / entities / evidence / kg_version / trace_id / status / reviewed_by / reviewed_at` +（**若 B2 选①**）`task_id`
- [x] `unaligned_subjects`（§4.5）：建表，**不写数据**（B5 ②）
- [x] 三表**索引一律以 `org_id` 打头**（ADR-0003）；应用层查询全部带 `org_id` 条件（RLS 未启用期间）
- [x] 迁移落 development SQLite + PG 两侧可用，单测覆盖

## 3. 后端：`risk.detect` 产物落库 + 任务状态机

- [x] 新增 `app/services/affiliation.py`（PG 侧服务）：算法返回的 `Suspicion` → `affiliation_suspicions` 行；**保持 `app/services/kg/affiliation.py` 纯算法，不掺 PG 依赖**
- [x] `affiliation.detect` 执行体登记 `EXECUTOR_REGISTRY`（复用 `risk.detect` 的算法调用）；一次执行 = 一条 `affiliation_tasks`
- [x] 状态流转写回 `affiliation_tasks`：`pending → processing → completed / failed`；失败写 `error_code` / `error_detail`（**`error_detail` 属敏感字段，日志禁输出**）
- [x] `retry_count` 在 tenacity 重试回调与 completed 分支回写（照 B1 同款纪律：有列必须有消费者）
- [x] **`TaskManager.recover()` 扩到 `affiliation_tasks`**（ADR-0001 第 73 行：启动把遗留 `pending` / `processing` 置 `failed` + `TASK_INTERRUPTED`），并写单测
- [x] `result_summary` 完成后填 `{total, by_type, top_5_severity}`
- [x] **幂等**：按 B3 结论实现（① 每次新建任务）
- [x] `trace_id` 贯穿：`detect` 任务的 `trace_id` 与写下的每条疑点 `trace_id` 同值（照 S7.1 §7.3 的四段同值标准）

## 4. 后端：四个端点

- [x] `POST /affiliation/detect`：校验 `doc_ids` 归属当前 org（越权 → **403/404，不降级空结果**）；返回 202
- [x] `GET /affiliation/tasks/{id}`：跨租户 → 404（不泄露存在性）；`failed` 时回 `result_summary = null` + 错误语义
- [x] `GET /affiliation/suspicions`：按 B2 结论过滤（默认当前 org）；`task_id?` query 可选
- [x] `PATCH /affiliation/suspicions/{id}`：`reviewed_by` 取 `X-Actor-Id`（B4 ①），`reviewed_at` 写当前时间；非法状态迁移 → 400
- [x] 错误响应统一 `{code, message, detail, trace_id}` + HTTP 与业务码分离（根 CODEBUDDY §错误响应规范）

## 5. 接缝 7 / 8（**B6 ②：B 尾段独立 sub-batch**）

- [x] 接缝 7：`external_refs` 表（`object_type` / `local_id` / `external_system` / `external_id` 等，按 ADR-0004 §4 字段清单），**nullable 且不进契约**
- [x] 接缝 8：`app/services/external_data/`（导入文件 schema JSON/CSV + 手工导入 CLI，**不建表**）
- [x] 两项均已核对 **ADR-0004 §2.1 登记行**：第 7 / 8 行早已登记 `external_refs` 表与外部数据导入接缝 → **无需改动即可通过**；`check_seams.py` 的 `PresenceRule` 判据由 WARN 转 OK，实测见 `integration-log.md` §7

## 6. 前端（**只做两件事，UI 归批次 C**）

- [x] `npm run gen:api` 后的 `api.d.ts` 提交
- [x] `CONTRACT_COVERED_PATTERNS` 登记四个新路径（`{id}` 用 `[^/]+` 占位）
- [x] **不写**疑点列表页 / 证据高亮交互（批次 C）

## 7. 验证

- [x] `uv run pytest -q` 全绿；新增测试集中在：表模型 / 状态机与启动回收 / 四端点行为与越权 / 契约零漂移
- [x] `uv run python scripts/export_openapi.py --check` **无 diff**
- [x] `uv run python scripts/check_seams.py`（接缝 7 / 8 落地后应转为 OK，不得仍是 WARN）
- [x] **真机端到端**：沿用 Sprint7.1 的 6 片 + `v-s71a-fe1c4dc3` 版本 → `POST /affiliation/detect` → 任务 completed → `GET /affiliation/suspicions` 取回疑点条数与 §7.3 的 10 条**一致** → PATCH 一条 → 再 GET 校验状态流转落库
- [x] `uv run ruff check . && uv run ruff format .`
- [x] **不 bump `app_version`**（仍 `1.2.0`）

## 8. 收尾

- [x] 补 `integration-log.md`（基线 / 事前核实 / 契约 / 建表 / 端点 / 接缝 / 真机）
- [x] 更新 `backend/CODEBUDDY.md` §4：**S7.1-6 标记为已偿还**；新增本批次暴露的缺口（含 `unaligned_subjects` 空表登记的 **S7.2-x**）
- [x] `docs/dev-doc-status.md` / 承接矩阵同步（新增契约端点属矩阵级事实）
- [x] **本批次未新增 `settings.*` 配置项**（若确实需要，必须能指出读取它的代码行）
