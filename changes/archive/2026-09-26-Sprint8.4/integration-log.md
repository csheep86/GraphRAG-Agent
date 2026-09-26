# Integration Log —— Sprint 8.4 批次 E（集成接缝收口）

> **执行日期**：2026-09-24 ｜ **分支**：`feature/sprint-8` ｜ **花费**：**¥0**（纯代码 + 单测，不触 LLM / 不触解析 / 不起真机服务）
> **原则**：勾选 ≠ 通过——下列每条都是命令输出。

## 1. 为什么这一批次排在「Sprint 8 收尾」之前

`scripts/check_seams.py` 里接缝 6 的判据是 `required_from = "1.4.0"`：

```
InterfaceRule("接缝 6 数据输出", "ExportSink", "1.4.0", 1, 1, adr_tokens=("JSON/CSV 实现",))
PresenceRule("接缝 6 数据输出", "path", "app/services/export", "1.4.0")
```

即 **bump `app_version` 到 1.4.0 的那一刻，这两条就从 WARN 变 ERROR**——先 bump 再补 = CI 必红。
proposal.md:81 早写了这条风险：「`ExportSink` 与接缝收口——批次 E（**1.4.0 到期，bump 时转 ERROR，别拖到最后一天**）」。
同时 plan §7.2 验收清单要求「**8 个接缝全部落地**」+「ADR-0004 已定稿」。⇒ 本批次是收尾的**前置**，不是可选项。

## 2. 交付

| 落点 | 内容 |
|---|---|
| `app/services/export/base.py` | `ExportSink` 接口 + `ExportPayload` / `ExportResult` + `EXPORT_FORMATS = ("json","csv")` + `ExportFormatError`（未登记格式 → `UNSUPPORTED_MEDIA_TYPE` / 415，**不静默回落**） |
| `app/services/export/json_csv.py` | `JsonCsvExportSink`——**一个类同时提供 json 与 csv** |
| `app/services/export/__init__.py` | `build_export_sink()` |
| `app/core/config.py` | `log_export: bool = False`（唯一消费点 `core/logging.py`） |
| `app/core/logging.py` + `app/main.py` | 置 true 时抛 `AppError(NOT_IMPLEMENTED)`，由 `setup_logging(log_export=settings.log_export)` 读取 |
| `docs/adr/0004-integration-seams.md` | §2.1 第 6 行补类名 `JsonCsvExportSink`；§4 补"当前实现 / 扩写纪律" |
| `backend/CODEBUDDY.md` §4 | 8 个接缝**全部已落** |
| `backend/.env.example` | `LOG_EXPORT=false` 段（含"未实现，置 true 显式报 501"说明） |

**两个设计裁决（写下来防复发）**：

1. **为什么 json / csv 合在一个类**：ADR 登记「一个 JSON/CSV 实现」，拆成 `JsonExportSink` + `CsvExportSink` 会让实现类变 2 个，撞 `max_impls = 1`（多做即越界）。
2. **为什么不做 HTTP 端点**：导出走端点就是**集成**（要进契约 + 鉴权 + 审计），与 ADR §3 第 1 条「只预留不做集成」冲突；因此无路由、契约零漂移。

## 3. 门禁（命令 → 真实输出）

| 命令 | 输出 |
|---|---|
| `uv run ruff check .` | **All checks passed!** |
| `uv run ruff format .` | `1 file reformatted, 124 files left unchanged` → `--check`：`125 files already formatted` |
| `uv run pytest -q` | **392 passed, 1 warning in 8.28s**（基线 387 + 新增 5） |
| `uv run python scripts/check_seams.py` | **ERROR 0 / WARN 0 / OK 9** —— 接缝 6 的「接口实现集合」与「落点到位」两项均由 WARN 转 **OK**，**WARN 归零**（接缝 6 已提前落地，不等 1.4.0 上闸） |
| `uv run python scripts/export_openapi.py --check` | `[OK] contracts/openapi.yaml 与代码模型一致`（零漂移） |
| `npm run gen:api` + `git diff --stat` | 未动契约 ⇒ 无 diff（本批次未跑，因零后端契约改动；如不放心可复跑） |

## 4. 真机

本批次**无外部依赖**：`ExportSink` 是纯函数式渲染（dict → json / csv），5 条单测即真机判据（¥0）。
未起服务、未调 LLM、未调解析。**未测到的**：真实业务数据（疑点 / 审计）灌入后的大批量导出——那要等调用方出现（当前无调用方，属预留本分）。

## 5. 未擅自处置

- **不 bump `app_version`**（仍 1.3.0）——bump 是收尾单独一步，需连带重导契约 + release notes + tag；
- **不动契约 / 前端**；**不加导出端点**（见 §2 裁决 2）；
- **批次 D 另两项（种子数据集固化 / 演示彩排脚本）仍未做**，待用户裁决（本批次未替用户决定）。
