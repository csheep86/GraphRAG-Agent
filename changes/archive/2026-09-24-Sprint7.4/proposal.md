# Sprint 7.4 批次 D —— 事件出口（接缝 5）

## 范围

**唯一真源**：`docs/v1.1.0-demo-mvp-plan.md:277`

> **D 事件出口（由 Sprint 5 移入）** | 建 `domain_events` 表 + `EventSink` 接口（仅 `db` / `log` 实现）；事件：`document.parsed` / `kg.updated` / `risk.suspect_created`（本 Sprint 首个真实事件源）/ `qa.answered`；只落库不派发（1.5 天）

**验收（plan §6.3 第 4 行，逐字）**

> `domain_events` 中出现 `risk.suspect_created`（接缝 5 首个真实事件源）；`EventSink` 实现类仅 `db` / `log` 两个

## 硬约束

1. **角色隔离**：只动 `backend/`。
2. **零契约变更**：`domain_events` 是预留表，**不进 `contracts/openapi.yaml`**（CODEBUDDY §功能预留原则第 4 条；`backend/CODEBUDDY.md:59` 明示）。本批次前端不动，`npm run gen:api` 应无 diff。
3. **实现集合恰好 2 个**：`backend/scripts/check_seams.py:119-127` 的 `InterfaceRule("接缝 5 事件出口", "EventSink", "1.3.0", 2, 2, adr_tokens=("db","log"))`。AST 按**基类名**索引 ⇒ 接口类名必须叫 `EventSink`；继承它的类**恰好两个**，多一个即"越界"，少一个即"少做"。
4. **表判定靠 ORM**：`PresenceRule(..."table", "domain_events", "1.3.0")`（`check_seams.py:143`）扫 `__tablename__`，不查真库 ⇒ 只需在 `app/db/models.py` 声明 ORM 类。全仓**无 Alembic / 无 .sql**（建表靠 `init_db()` 的 `create_all`）⇒ 本批次**不写迁移脚本**。
5. **只落库不派发**：`dispatched_at` 恒 `NULL`（ADR-0004 §2.3 行 100）。
6. **版本闸门**：当前 `app_version = 1.2.0` < `1.3.0` ⇒ 接缝 5 两条规则现在是 **WARN**；bump 到 1.3.0 那一刻自动转 ERROR。Sprint 7 收尾门禁是**默认档 ERROR = 0**（`sprint-calendar.md:43`）。

## 决策点（建议项）

| 编号 | 决策 | 建议 | 理由 |
|---|---|---|---|
| **D1** | 四个事件类型如何处理 | 枚举里**定义**四个，但**只实装 `risk.suspect_created` 的发送** | 文档称其为"首个真实事件源"；其余三个本批次无真实触发点，发了就是**假事件** |
| **D2** | 接口形状 | `EventSink.emit(event: DomainEvent) -> None`（`DomainEvent` 为 Pydantic 模型） | 单一入参便于两个实现各自取用；Pydantic 与全仓校验风格一致 |
| **D3** | 两个实现如何协作 | `EventBus` 持有 `[DbEventSink, LogEventSink]`，`emit` 一次**两边都写**（落库 + loguru JSON） | "db + log 是让事件出口可观测的最小集"（ADR §3 第 4 条）；**不新增 settings 配置项**选哪个 sink——无消费者的配置不得提交（CODEBUDDY §功能预留原则第 6 条） |
| **D4** | 事务边界 | `DbEventSink` 与疑点落库**共用同一 session**（回滚一致）；`LogEventSink` 立即打 | 疑点写失败时事件不应残留在库里；日志不可回滚，属可观测侧 |
| **D5** | 事件粒度 | **每条疑点一条事件**：`aggregate_type="affiliation_suspicion"`、`aggregate_id=疑点 id`；`payload` 含 `task_id` / `suspicion_type` / `severity` / `entity_names` / `evidence_count` / `kg_version` | 一次检测 10 条疑点 = 10 条事件，量级无压力；按疑点订阅是未来 OA/工单的自然粒度 |
| **D6** | 插入点 | `backend/app/services/affiliation.py:255`（`session.add_all(records)` 落库后） | 批次 B 已在此预留形状（`changes/Sprint7.2/proposal.md:52`："事件拼接的时间戳与 trace_id 不能丢"），此处 `trace_id` / `org_id` / `kg_version` 齐备 |
| **D7** | ADR 是否要改 | **不改** §2.1（第 5 行已含 `db` / `log` 子串，判据 4 已满足）；仅在收尾时核对 `check_seams.py` 输出 | 漏改任一侧 CI 必红，但本批次实现集合与登记集合一致 ⇒ 无需改动 |

## 明确不做（边界）

- ❌ 不发 `document.parsed` / `kg.updated` / `qa.answered`（无真实触发点，发即假事件）
- ❌ 不做派发 / 重试 / webhook / 订阅方配置（`dispatched_at` 恒 NULL）
- ❌ 不动 `contracts/openapi.yaml`，不动 `frontend/`
- ❌ 不写迁移脚本、不引入 Alembic
- ❌ 不新增 `settings.*` 配置项

## 风险 / 待确认

- 若 `EventBus` 也被写成继承 `EventSink`，实现数会变成 3 ⇒ 门禁 ERROR。**`EventBus` 不得继承 `EventSink`**（它持有 sink，不是 sink）。
- bump `app_version` 到 1.3.0 属 Sprint 7 **收尾**动作，不在本批次做（与 v1.3.0 tag 同一动作）。
