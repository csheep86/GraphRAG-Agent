# Tasks: Sprint 7.4 批次 D —— 事件出口（接缝 5）

> **状态**：草稿待实施（决策 D1–D7 见 `proposal.md`，按建议采纳）。
> **前置**：`changes/Sprint7.3` 已提交（批次 C 前端疑点页验收通过）。
> **角色**：本批次只动 `backend/`。**零契约变更**（`domain_events` 为预留表，不进 OpenAPI）。

## 0. 事前核实（未完成不得往后走）

- [x] **核实 D1–D7 已签字**（或按无人值守默认采纳建议项）
- [x] **核实 `check_seams.py` 当前基线**：跑一次 `uv run python scripts/check_seams.py`，记下接缝 5 的两条 WARN 原文（接口尚未定义 / 表未声明），作为"改前后对比"证据
- [x] **核实 ADR-0004 §2.1 第 5 行**已含 `db` / `log` 子串 → 判据 4 已满足，本批次**不改 ADR**
- [x] **核实插入点形状**：`app/services/affiliation.py:255` 处 `records` 是否已带 `id`（新对象未 flush 时 `id` 可能为空 ⇒ 需在 flush 后取）

## 1. `domain_events` 表（ORM）

- [x] `app/db/models.py` 新增 `DomainEvent`，`__tablename__ = "domain_events"`
- [x] 字段逐条对齐 ADR-0004 §2.3：`id` / `org_id` / `event_type` / `aggregate_type` / `aggregate_id` / `payload`(JSON) / `trace_id` / `created_at` / `dispatched_at`
- [x] `dispatched_at` **nullable 且恒为 NULL**（只落不派），注释写明
- [x] 带 `org_id` 且索引以 `org_id` 打头（对齐既有 6 张表的 ADR-0003 口径）
- [x] **不**写迁移脚本（全仓无 Alembic，靠 `create_all`）

## 2. 事件模块 `app/services/events/`

- [x] `types.py`：四个事件类型常量 / 枚举（D1：定义四个，**只发** `risk.suspect_created`）
- [x] `base.py`：`EventSink`（抽象基类，类名**必须**叫 `EventSink`）+ `DomainEvent`（Pydantic）
- [x] `db.py`：`DbEventSink(EventSink)` —— 写 `domain_events` 表（D4：与调用方共用 session）
- [x] `log.py`：`LogEventSink(EventSink)` —— loguru JSON 一行（不落库）
- [x] `bus.py`：`EventBus` —— **持有**两个 sink 并逐个 `emit`；**不得继承 `EventSink`**（否则实现数变 3，门禁 ERROR）
- [x] 继承 `EventSink` 的类**恰好 2 个**（门禁 `min=max=2`）

## 3. 首个真实事件源：疑点落库

- [x] `app/services/affiliation.py`：疑点落库后对**每条疑点**发一条 `risk.suspect_created`（D5/D6）
- [x] `payload` 含 `task_id` / `suspicion_type` / `severity` / `entity_names` / `evidence_count` / `kg_version`
- [x] `trace_id` 与 `org_id` 取自任务上下文（**不**新造）
- [x] 落库失败 → 事件一并回滚（D4 同 session）
- [x] **不**发其余三类事件（无真实触发点）

## 4. 测试（pytest）

- [x] `risk.suspect_created` 事件确实写入 `domain_events`（`event_type` / `aggregate_type` / `payload` 可断言）
- [x] `dispatched_at` 恒为 NULL
- [x] 两个 sink 都被调用（db 落库 + 日志）
- [x] 疑点落库失败时事件不残留
- [x] 实现集合 = 2（可由 `check_seams.py` 输出佐证）

## 5. 门禁（收尾）

- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run pytest -q`（全绿）
- [x] `uv run python scripts/check_seams.py` → 接缝 5 两条规则由 WARN 转 **OK**，且 **ERROR = 0**
- [x] `uv run python scripts/export_openapi.py --check` → **契约零漂移**（本批次零契约变更）
- [x] 前端 `npm run gen:api` 无 diff（复核零契约变更）

## 6. 收尾

- [x] 补 `changes/Sprint7.4/integration-log.md`（基线 / 核实 / 决策 / 实现 / 真机 / 门禁 / 未擅自处置声明）
- [x] **真机证据**：跑一次检测，查 `domain_events` 表确认出现 `risk.suspect_created` 行（条数 = 疑点数）
- [x] `docs/dev-doc-status.md` 补批次 D 登记
- [x] 不 bump `app_version`（Sprint 7 收尾统一 bump 到 1.3.0 + tag）
