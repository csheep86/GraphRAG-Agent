# Sprint 7.4 批次 D —— 集成日志（事件出口 / 接缝 5）

> **状态**：**已完成并通过真机验收**（2026-09-24）。
> 对照任务清单见 `tasks.md`；决策点见 `proposal.md`。

## 章节 ↔ 任务对照表

| 本节 | 对应 `tasks.md` | 真机证据要求 |
|---|---|---|
| §1 基线 | —（开工前快照） | ✅ `app_version` = 1.2.0、门禁改前 WARN 原文 |
| §2 事前核实 | §0 | ✅ `check_seams.py` 改前基线 + ADR 第 5 行 + flush 必要性 |
| §3 决策签字 | `proposal.md` | ✅ D1–D7 结论表 |
| §4 表与模块 | §1 / §2 | ✅ ORM 声明 + 模块文件清单 + ruff |
| §5 首个真实事件源 | §3 | ✅ 真机跑检测 → PG 落 10 行 |
| §6 测试 | §4 | ✅ 4 条新增用例，全量 368 passed |
| §7 门禁 | §5 | ✅ 接缝 5 WARN→OK、契约零漂移、pytest 全绿 |
| §8 收尾 | §6 | ✅ 本日志 + `dev-doc-status.md` 登记 |

## 1. 基线（开工前快照）

```
backend/app/core/config.py:92   app_version = "1.2.0"   # < 1.3.0 ⇒ 接缝 5 规则为 WARN（未到期）

$ uv run python scripts/check_seams.py（改前）
  [WARN] 接缝 5 事件出口 EventSink：实现数 0 < 登记下限 2（接口尚未定义）；
         登记的就是本地 db + log 两个实现，不是 1 个 [未到期：1.3.0]
  [WARN] 接缝 5 事件出口：表 domain_events 未在 ORM 模型声明 [未到期：1.3.0]
  汇总：ERROR 0 / WARN 4 / OK 7
```

## 2. 事前核实（§0）

| # | 核实项 | 结论 |
|---|---|---|
| 1 | 门禁基线 | ✅ 接缝 5 两条 WARN（见 §1）；目标是转 OK |
| 2 | ADR-0004 §2.1 第 5 行含 `db` / `log` | ✅ 已含（"仅 `db` / `log` 实现"）⇒ 判据 4 天然满足，**本批次未改 ADR** |
| 3 | 实现数判定方式 | ✅ `check_seams.py:428-457` 按**数量**判定（`min=max=2`），AST 扫 `app/` 下基类名 ⇒ 接口类名必须叫 `EventSink`，继承它的类**恰好 2 个** |
| 4 | 插入点形状 | ⚠️→✅ `record.id` 在 `add_all()` 后**仍是 None**（UUID 是 INSERT 时才生成的 Python 默认值）⇒ 必须先 `flush()` 再拼事件，否则 `aggregate_id` 为空 |
| 5 | 建表方式 | ✅ 全仓无 Alembic / 无 .sql，靠 `init_db()` 的 `create_all` ⇒ 只需声明 ORM 类 |

## 3. 决策签字（D1–D7，均按建议采纳）

| 编号 | 裁决 | 结论 |
|---|---|---|
| D1 | 四个事件类型 | 枚举**定义**四个，但**只发** `risk.suspect_created`（其余三类无真实触发点，发即假事件） |
| D2 | 接口形状 | `EventSink.emit(event: DomainEvent)`，`DomainEvent` 为 Pydantic |
| D3 | 两实现协作 | `EventBus` 持有 `[DbEventSink, LogEventSink]` 逐个 emit；**不新增 `settings.*` 配置项**（无消费者的配置不得提交） |
| D4 | 事务边界 | db sink 与业务**同 session**、**不自己 commit**；log 立即打 |
| D5 | 粒度 | **每条疑点一条事件**，`aggregate_type="affiliation_suspicion"`、`aggregate_id=疑点 id` |
| D6 | 插入点 | `persist_detection_result`（`affiliation.py`，`add_all` → `flush` → emit → commit） |
| D7 | ADR 是否改 | **不改**（登记行已含 db/log） |

## 4. 表与模块

- `app/db/models.py`：`DomainEvent`（`__tablename__ = "domain_events"`），字段逐条对齐 ADR-0004 §2.3，`dispatched_at` nullable 且恒 NULL，索引以 `org_id` 打头，`event_type` 有 CheckConstraint。
- `app/services/events/`：`types.py`（四类取值）、`base.py`（`EventSink` + `DomainEvent`）、`db.py`（`DbEventSink`）、`log.py`（`LogEventSink`）、`bus.py`（`EventBus`）、`__init__.py`（`build_event_bus(session)`）。
- ⚠️ `EventBus` **不继承** `EventSink`：门禁按基类名统计，继承会让实现数变 3 → ERROR。已写入 `bus.py` docstring。

## 5. 首个真实事件源（真机）

```
$ APP_ENV=development uv run python ../changes/Sprint7.2/e2e_detect.py --org … --actor …
[1] POST /affiliation/detect → 202   task_id=0573c98f-e97c-4fad-b127-30390f756d4b
[2] status=completed   result_summary={'total': 10, 'by_type': {'shared_legal_rep': 1, 'shared_address': 9}}
    （日志实时打出 10 条 domain_event emitted … risk.suspect_created）
[4] PATCH → 200 confirmed   被确认的疑点 id = 2c507081-0c4a-4f55-a1dd-1e4738ff99d7

$ 查 PG domain_events
total_rows = 10
null_dispatched = 10        ← 全部 dispatched_at IS NULL（只落不派）
risk.suspect_created | affiliation_suspicion | 2c507081-… | dispatched=None |
    task=0573c98f-… | ev=6 | trace=131a2197-…（与任务 trace_id 同值）
```

要点：**事件条数 = 疑点条数（10 = 10）**；第一条 `aggregate_id` 正是被 PATCH 的那条疑点 ⇒ 事件指向真实实体，不是编数据；`trace_id` 与任务同值。

## 6. 测试

`tests/test_domain_events.py`（4 条，全过）：

1. 每条疑点落一条事件，`aggregate_id` 与真实疑点 id 集合**相等**（验证 flush 生效，不是空串）；
2. 一次 emit 同时走 db（落库）+ log（spy 计数）；
3. 业务 `rollback()` 后事件**不残留**；
4. 无疑点 → 不发事件。

```
$ uv run pytest -q → 368 passed（364 → 368，新增 4）
```

## 7. 门禁（§5）

```
$ uv run ruff format . && uv run ruff check .   → All checks passed
$ uv run pytest -q                              → 368 passed
$ uv run python scripts/check_seams.py          → ERROR 0 / WARN 2 / OK 8
    （接缝 5 两条 WARN 全部转为 OK；剩余 2 条为未到期的接缝 6）
$ uv run python scripts/export_openapi.py --check → [OK] 与后端模型一致（契约零漂移）
```

**契约路径仍为 14**：`domain_events` 是预留表，按 CODEBUDDY §功能预留原则第 4 条不进 `contracts/openapi.yaml`，前端不消费 ⇒ 本批次前端零改动。

## 8. 收尾

- ✅ 本日志已写；`docs/dev-doc-status.md` 已登记批次 D。
- ✅ **未擅自处置声明**：只动 `backend/`。未发 `document.parsed` / `kg.updated` / `qa.answered`（无真实触发点）；未做派发 / 重试 / webhook；未新增 `settings.*` 配置；未改 ADR-0004；未写迁移脚本（全仓无 Alembic）。
- ⚠️ `app_version` 仍为 1.2.0 —— bump 到 1.3.0 与 v1.3.0 tag 是 Sprint 7 收尾动作，**不在本批次做**；届时接缝 5 的两条规则会自动由 WARN 转 ERROR 判据（已实测当前即为 OK，故不会红）。
- ⚠️ 真机副作用（已告知）：重跑检测会产出新一批 10 条 `open` 疑点，列表默认展示最近 completed 任务 ⇒ 此前人工复核的状态从列表上不可见（记录仍在，按旧 `task_id` 可查）。
