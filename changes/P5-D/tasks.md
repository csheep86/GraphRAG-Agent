# P5-D · 任务清单（D1 第一批：私域出向管控 + 内网双轨）

> 边界见 [`proposal.md`](./proposal.md) §3（11 条 Non-goals）。
> 收尾一律跑 `uv run python scripts/check_session_drift.py`，S1 读到那 11 条才算对得上账。
> ⚠️ 本批 **S4 一定会报"动了 contract/schema"** —— 那是预期内（D2 契约再生）。
> 实录见 [`integration-log.md`](./integration-log.md)。

## T1 · 配置落地（spec §4.6） ✅

- [x] `app/core/config.py` 增 `private_deploy_enabled`（默认 `false`）/ `allowed_egress_hosts`（`list[str]`，
      默认 `[]`）+ 归一化 validator（空串 ⇒ 空表，**不得**解析成 `['']`）
- [x] `backend/.env.example` 同步两段注释（字段名逐字照抄 spec §4.6；标注「生产置 `true`」）
- [x] 两个字段**各自**有真实消费点（接缝判据 2）

## T2 · 错误码 `PRIVATE_DEPLOY_BLOCKED`（动四处，D5） ✅

- [x] `app/core/errors.py`：ErrorCode 枚举 / `ERROR_HTTP_STATUS`(503) /
      `DEFAULT_MESSAGES` / `ERROR_CODE_DESCRIPTIONS` / `ERROR_CODE_SOURCES` 四处齐加

## T3 · 构造期出向守卫 ✅

- [x] 新增 `app/core/egress.py`：纯函数 `is_egress_allowed`（host 解析 / 内网判定 / 白名单匹配）
      + `guard_egress`（读 settings、违规写审计 + 抛 AppError）
- [x] 三个出向面接线：`build_chat_model`（LLM）、`registry._do_parse`（MinerU）、
      `build_default_embedder`（评测 embedding，内网 8009 走这条）
- [x] `app/services/audit.py` 文档头登记**第 ⑤ 个** `record_audit_entry` 调用方

## T4 · 测试（¥0，全程不联网） ✅

- [x] 新增 `tests/test_private_deploy_egress.py`：解析 / 内网放行 / 开关关闭照旧 /
      公网阻断 503 / 白名单精确匹配（含 `host:port` 端口不符 ⇒ 阻断）/ 空串当空表 /
      构造期零出向（monkeypatch 断言客户端构造未发生）/ 审计行落库

## T5 · 契约同步五步（D2，单独一笔提交） ✅

- [x] `export_openapi.py`（**不加** `--check`）→ `npm run gen:api` → 提交
      `contracts/openapi.yaml` + `frontend/src/types/api.d.ts` → `--check` 零 diff

## T6 · M5 其它验收**只核对不补**（Non-goal 7） ✅

- [x] integration-log 给出 §3 验收 1–7 逐条达成情况（含证据），缺的登记进 §11

## T7 · 收口 ✅

- [x] 三条门禁 + pytest（本地口径需补 `GRAPH_REAL_NEO4J_*`）+ ruff 两件套全跑
- [x] Conventional Commits 分段提交（配置 / 错误码 / 守卫接线 / 测试 / 契约再生）
- [x] 推送 + `gh run watch --exit-status` = 0，run id 回登 §8.3
- [x] `integration-log.md`：X-3 偏离登记、D8/D9 登记、§11 下一批指针
