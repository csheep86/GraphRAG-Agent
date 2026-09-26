# Tasks: Sprint 8.4 批次 E —— 集成接缝收口（`ExportSink` + `log_export` 占位）

> **状态**：**已实现并过门禁**（2026-09-24），证据见 [`integration-log.md`](./integration-log.md)。
> **为什么必须先做**：plan §7.2 要求「**8 个接缝全部落地**」+「ADR-0004 已定稿」才能收尾；
> 且 `check_seams.py` 接缝 6 的 `required_from = 1.4.0`——**bump 到 1.4.0 的那一刻它就从 WARN 变 ERROR**。
> 先 bump 再补 = CI 必红（proposal 原话：「1.4.0 到期，bump 时转 ERROR，**别拖到最后一天**」）。
> **范围**：plan §7.1 批次 E 四项；不动契约、不 bump `app_version`（bump 属收尾单独一步）。

## 0. 事前核实

- [x] **核实门禁规则真源**（`scripts/check_seams.py`）：接缝 6 `ExportSink` `required_from=1.4.0`、`min_impls=max_impls=1`、`adr_tokens=("JSON/CSV 实现",)`；PRESENCE 还要求 `app/services/export/` 目录存在 ⇒ **实现只能有 1 个类**
- [x] **核实 ADR §2.1 第 6 行**已含 "一个 JSON/CSV 实现" ⇒ 判据 4（登记表一致）在实现落地后自动 OK，但仍**补写实现类名**提升可核性
- [x] **核实"要不要 HTTP 端点"**：ADR §3 第 1 条——走端点即**集成**（须进契约 + 鉴权 + 审计），与"只预留不做集成"冲突 ⇒ **不做端点**，`export_openapi.py --check` 保持零漂移
- [x] **核实合规占位口径**（ADR §3 第 5 条例外登记）：`settings.log_export` 必须「**有读取代码行 + 显式报未实现**」，禁止静默无效

## 1. 实现

- [x] `app/services/export/base.py`：`ExportSink` 接口 + `ExportPayload` / `ExportResult` + `EXPORT_FORMATS` + `ExportFormatError`（未登记格式 → `UNSUPPORTED_MEDIA_TYPE` / 415，**不静默回落**）
- [x] `app/services/export/json_csv.py`：`JsonCsvExportSink`——**一个类同时提供 json / csv**（拆成两个类会让实现数变 2，撞 `max_impls=1`）
- [x] `app/services/export/__init__.py`：`build_export_sink()`（登记集合恰好 1 个实现）
- [x] `config.py` 新增 `log_export: bool = False`（唯一消费点 `core/logging.py`）+ `.env.example` 同步 `LOG_EXPORT=false`
- [x] `core/logging.py::setup_logging(..., log_export=...)`：置 true 时抛 `AppError(NOT_IMPLEMENTED)`；`main.py` 传入 `settings.log_export` ⇒ 形成真实消费点
- [x] ADR-0004 §2.1 第 6 行补实现类名 `JsonCsvExportSink` + §4 补"当前实现 / 扩写纪律"
- [x] `backend/CODEBUDDY.md` §4 接缝清单：8 个接缝**全部已落**

## 2. 测试（+5）

- [x] `tests/test_export_seam.py`：json 渲染（多余键丢弃）/ csv 表头与行数 / 未登记格式显式 415 / 构造返回唯一登记实现 / `log_export=true` 显式报 `NOT_IMPLEMENTED`

## 3. 门禁（2026-09-24 实测）

- [x] `ruff check .` → All checks passed；`ruff format .`（1 file reformatted）→ `--check` 125 files already formatted
- [x] `pytest -q` = **392 passed**（387 + 新增 5）
- [x] `check_seams.py` = **ERROR 0 / WARN 0 / OK 9**（接缝 6 两项由 WARN 转 OK ⇒ **WARN 归零**，比基线更好）
- [x] `export_openapi.py --check` 零漂移；`gen:api` 无 diff（未动契约 / 前端）

## 4. 收尾（下一步，不属本批次）

- [x] bump `app_version` 1.3.0 → 1.4.0（`config.py:92` + `.env.example:9` + **本地 `.env`**）→ **重导契约**（`info.version`）
  - **2026-09-26 已执行**：`config.py` / `.env.example` / `.env` 三处同改（`.env` 会**覆盖**默认值，不改则本地导出仍是 1.3.0）；重导后 `git diff contracts/openapi.yaml` **仅 `version: 1.3.0 → 1.4.0` 一行**，`--check` 通过。
  - **门禁复核（bump 后）**：`pytest -q` **392 passed**；`check_seams.py` **ERROR 0 / WARN 0 / OK 9**，**`--strict` exit 0（全周期首次全绿）**——接缝 6 两项由 WARN 转 ERROR，因本批次已提前落地故不红；`ruff check` 全过 / `format --check` 125 files；`export_openapi.py --check` 零漂移；`gen:api` 无 diff。
- [x] release notes v1.4.0（含 Demo-MVP 达成声明 + 已知限制）
  - **2026-09-26 已执行**：`docs/release-notes/v1.4.0.md`；**§6 对 plan §7.2 十条逐条对账 = 7 达成 / 2 部分 / 1 未达成**（未达成 = 受控问题集 NOT PASS，语料漂移，A15 如实登记不重造）；§7 登记 8 项已知限制。
  - 同步刷新：`docs/sprint-calendar.md`（§5 S8 行 + §6 v1.4 变更记录）、`docs/dev-doc-status.md`（收尾登记行）、`docs/acceptance-traceability-matrix.md`（M5 行 / H7 行 / 黄金路径步骤 6 / M3-3）。
- [ ] tag `v1.4.0`；PR #3 转正式 → CI 绿 → Merge 到 `main`
- [ ] 归档 `changes/Sprint8.{2,3,4}`
