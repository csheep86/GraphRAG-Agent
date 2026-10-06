**P4 · License 商业化底座（DR-C1 / G-23 / ADR-0006）新会话开场提示词**

边界文档已落，T0 已完成，直接整段粘贴即可开工。

你是本仓库的执行代理。新批次任务：**P4 · License 商业化底座**（DR-C1 / 护栏 **G-23** / ADR-0006）——
**唯一挡在 GA 前的阶段**（见下方「为什么是它」）。

**第一步（必做）**：用 use_skill 加载 **unattended-sprint-execution** 技能，全程按其协议执行
（免请求自动提交、决策点默认采纳文档建议项，仅 4 类情况升级用户）。

**确认起点**：`git log --oneline -4` 应能看到 **`build(p4):`**（新增 cryptography 依赖）与
**`docs(p4):`**（边界文档 + 本文件）两个提交。看不到 ⇒ 说明没从正确基线开工，先同步。

**任务来源**：`changes/P4/proposal.md` + `tasks.md`（⚠️ **草案**）。按 tasks.md 推进，**顺序不能反**：
**T0 已完成（勿重做）** → **T1 接缝 9 登记** → T2 迁移 → T3 ORM 与 RLS 豁免 → T4 Provider + 6 个
settings → T5 纯 ASGI 中间件 → T6 契约 → T7 CLI → T8 行为围栏（摘 xfail）→ T9 P95 → T10 提交回登。

---

## 0. 为什么是它（三条机械理由，非偏好）

① 开工自检实测 `[~~]部分生效 = 0`、`[--] = 1 条` ⇒ 这唯一一条就是 **G-23**；
② `delivery-plan.md:186-188` 的「零缺口」裁决：**GA 门槛 = 所有 G 进 🟢，一条不放行**；
③ `:197` 的开工前置（`users` 表席位 + A6 镜像 + G-15）**全部已亮** —— `users` 那一条由上一批
P6-P1 补的主体锚点翻绿（`[OK] users 表已存在（DR-B13）`）。

⇒ **P4 是唯一挡在 GA 面前的阶段**。⛔ **不得**因为任何理由转向 P2-C SSO 或 P6 收尾
（SSO 此刻不可机械验证：需自建 IdP 真机 Keycloak + Samba AD DC，`:183-184` 明写 mock 不算完成）。

---

## 1. 开工自检（结论只能来自**脚本输出**，不能凭文档表格）

    cd backend && uv run python scripts/check_startup_readiness.py

确认：**`[--]` 只有 G-23**（两条断言），且 `[OK] users 表已存在（DR-B13）` 仍在。

## 2. 边界纪律（Non-goals **12 条**，proposal §4）

每个子任务收尾跑回切点：

    cd backend && uv run python scripts/check_session_drift.py

**S1 必须读到 12 条**边界，且来源必须是 `changes/P4/proposal.md`。报「没有 Non-goals」⇒ 立即停下，
且必须写成**编号列表**（表格读不到）。注意草案目录必须是"最近活跃"批次，否则会拿别的批次边界
来对照本批改动 —— **报告看起来正常，对照的却是错的边界**（2026-10-01 实踩过）。

## 3. 已查证的坐标（**不要重做 recon**，直接用）

| 项 | 落点 |
|---|---|
| **中间件挂载** | `main.py:63-80`，`add_middleware` **后加者在外层** ⇒ 现有 `TraceId → Audit → RateLimit → CORS`。要实现 ADR §2.6 的 `审计 → License → 限流 → 路由`，**必须插在 `RateLimit`（:78）之后、`Audit`（:79）之前** |
| **必须纯 ASGI** | 既有 `AuditMiddleware`（`core/middleware.py:89`）是**普通类**（不继承 `BaseHTTPMiddleware`）。`test_guardrails_compliance.py:104` 会判「继承 BaseHTTPMiddleware」= 不达标 |
| **豁免清单** | 先例：`core/limiter.py:49` 的 `EXEMPT_ROUTE_NAMES`（形态 = `模块名.函数名`） |
| **配置消费者门禁** | `check_seams.py:359` `_collect_setting_consumers`，扫 `app/` + `scripts/`（`config.py` 被 `SKIP_FILES` 排除；`Settings` 内的 `self.<字段>` 由 `:381` 兜住）⇒ **6 个 `LICENSE_*` 必须逐个配到真实消费点** |
| **接缝登记表** | `check_seams.py:135-169`（现只有接缝 1/2/5/6）；判据 4 在 `:555-608`；ADR 真源常量 `:78` |
| **RLS 豁免** | `models.py:83` `RLS_EXEMPT_TABLES = frozenset({"roles"})` ⇒ 追加 `licenses`；由断言 `test_guardrails_compliance.py:218` 盯住（豁免清单 ⇄ 实际模型必须相等） |
| **G-23 两条断言** | `test_guardrails_compliance.py:85`（静态侧六项资产）与 `:133`（行为侧 403 + 落审计），均为 `strict=True` 的 xfail |

## 4. 六个决策（已采纳，带依据；可推翻但要登记）

- **P4-D1 验签库 = `cryptography`**（已落地，见 §5 T0）。ADR 的 4 条判据 `pynacl` 同样全满足 ⇒
  用「生态地位」打破平局，避免额外引入 libsodium。
- **P4-D2 接缝 9 怎么登记（**坑，不看必踩**）**：`check_seams.py` 的判据 4 对每条规则都去
  **ADR-0004 §2.1 的同号行**找登记字样（`:572-588`）。直接加 `InterfaceRule("接缝 9 …")` ⇒
  它会去找「ADR-0004 §2.1 **第 9 行**」，而那里只有 8 个接缝 ⇒ **CI 必红**；
  反过来改 ADR-0004 加第 9 行 ⇒ **又违背 ADR-0006 §4「八个接缝数量与编号不变」**。
  ⇒ **采纳解法**：给 `InterfaceRule` 增 **`adr_file`** 字段（默认 ADR-0004），接缝 9 指向
  **ADR-0006 §4** ⇒ 登记仍须逐字可查、两侧不一致仍红（**加强**门禁，不是削弱）。
  ⛔ **绝不许**改 ADR-0004 的八个接缝编号（Non-goal 5）。
- **P4-D3 范围**：只做 **C1 License**，**不带 C2 补丁纪律**（C2 无红灯护栏，带上就是摊太大）。
- **P4-D4 批次粒度 = 单批落地**：6 个 `settings.*` **必须与消费点同批**，否则被判「无消费者配置」
  ⇒ CI 红。**不要**试图拆成 P4-A/B/C。
- **P4-D5 席位**：`users` 补 `activated_at` / `disabled_at` 两列**同批做**（两者当前不存在，P6-P0 实测）；
  但 ⚠️ **不得宣称席位维度端到端生效** —— `activated_at` 按 ADR `:121` 由「首次成功登录」回填，
  登录属 **P2-C** ⇒ 本批**只能单测计数函数**。
- **P4-D6 版本号**：HTTP 统一 **403**（不用 402，`:136`）。

## 5. T0 已完成且已验证（**不要重做**）

- `backend/pyproject.toml` 已加 `cryptography>=44,<47`（注释写明选型判据）；`uv.lock` 已重配
  （**cryptography 46.0.7** + cffi 2.1.1 + pycparser 3.0）。
- 功能验通：**签名/验签回路 ✅ / 篡改可检出 ✅ / 错钥匙拒签 ✅**；签名 64 字节、base64 88 字符。
- 连带回归：`check_seams` ERROR 0（OK 10）、契约 zero diff、`test_guardrails_compliance.py`
  4 passed / 2 xfailed、自检 `[--]` 仍仅 G-23。
- ⚠️ **未验的事**：离线 wheelhouse 下 CI 能否从锁文件装出 cryptography —— 只能等 T10 的 CI 实证；
  若 CI 装不上，第一时间**回退本依赖并重新选型**，不要硬推。

## 6. 基线（已体检，不必重跑）

本地**无图**口径 `pytest` **991 passed**；CI 口径 **997 passed**；容器 `graphrag-pg16` /
`graphrag-neo4j` 均 Up。**注**：本地有图口径（需 `GRAPH_REAL_NEO4J_*` + `affiliation-demo-v2` 语料）
为 **999 passed**，由 P6-P1 闭环，**本批不必碰**。

## 7. 验收（7 条，全机械）

① 自检 G-23 由 `[--]` 进 **`🟢 已生效`**，`[--]` 与 `[~~]` **均归零**（= 全场零缺口）；
② 两条 xfail 按 R-9 **先有真子系统再摘标记**，且**补强判据**（只摘标记不算转正）；
③ 移除 license ⇒ 受保护端点 **403 `LICENSE_MISSING`** 且 `audit_log` 有 `license.denied`；
④ `/health` 与 `/license/status` 在**无 License 时仍可达**；
⑤ `export_openapi.py --check` zero diff、无图口径 pytest passed **不减**（991）、
   `ruff check` + `ruff format --check`；
⑥ `check_seams.py` **ERROR 0**（接缝 9 两侧一致：ADR-0006 §4 登记行 ⇄ 门禁规则）；
⑦ **P95 增量 < 1ms** 实测并登记（ADR R-L4）。

## 8. 提交与推送

自动提交（Conventional Commits）。`git push origin main` 失败就**重试**（本机 GitHub 连接时好时坏、
**非 DNS**；历史上一批重试到第 19 次才成功）。仍失败就把命令给用户，**不要**改用 `--force` 或其它远程。

## 9. 升级用户的 4 类情况

① 需要越出范围做 **C2 补丁纪律 / SSO / 登录回填 `activated_at`**（= 撞 Non-goals 或 P4-D3/D5，停下）；
② 需要**改 Non-goals 任一条**；
③ **判据无法机械达成**（典型：P95 实测不出 < 1ms、或拒绝无法落审计）；
④ **§3 的行号坐标大面积失效**、无法就地订正（草案状态不适合靠猜推进）。

## 10. 不许外推（结案时逐条对照）

- License 子系统存在 **≠** 防破解 —— `:171` 明写它是**合规门槛**，安全边界是 **ADR-0003 的 RLS**；
- 两列迁移了 **≠** 席位维度端到端生效（见 P4-D5）；
- G-23 转绿 **≠** P4 全完 —— **C2 补丁纪律本批不做**；
- **禁止**把 License 正文 / 签名写进 `audit_log`（`:138`），**禁止**任何「占位」配置（Non-goal 9）。

**收尾**：报告写入 `changes/P4/integration-log.md`，勾选 `tasks.md`，并同步 `docs/dev-doc-status.md`
（§8 表；若结论改变既有登记）。
