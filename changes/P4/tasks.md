# P4 · 任务清单（License 商业化底座 / **DR-C1** / **G-23** / ADR-0006）

> 边界见 `proposal.md` —— ⚠️ **草案**。Non-goals **12 条**（编号列表，须被 S1 读到）。
> **定位**：纯新建子系统（`backend/app/services/license/` 当前不存在）。
> **链路**：P6-P0（量化缺口）→ P6-P1（补 users 主体锚点）→ **本批 P4**（License）。

- [ ] **T0 依赖裁决清零**（ADR-0006 `:108` TBD-L1：验签库未落选不得写代码）
      - [ ] T0.1 选 **`cryptography`**（Ed25519 走 `hazmat.primitives.asymmetric.ed25519`）
      - [ ] T0.2 加进依赖 ⇒ **重配 `uv.lock`**（不重配 CI 必挂）
      - [ ] T0.3 本地 `import` 验通（当前 venv 实测 `cryptography` / `nacl` **皆无**）
- [ ] **T1 接缝 9 登记**（**先文档后门禁**，ADR-0006 §4 + ADR-0004 §3 第 4 条）
      - [ ] T1.1 扩写 **ADR-0006 §4** 的接缝 9 登记行（`LicenseProvider → [DevLicenseProvider]`，`max_impls = 1`）
      - [ ] T1.2 改 `check_seams.py`：`InterfaceRule` 增 **`adr_file`** 字段 ⇒ 判据 4 支持**按规则取 ADR 源**
            （不改 ⇒ 判据 4 会去 **ADR-0004 §2.1 第 9 行**找登记字样，而那里只有 8 个接缝 ⇒ **必红**）
      - [ ] T1.3 **不得**改 ADR-0004 §2.1 的八个接缝数量与编号（Non-goal 5）
- [ ] **T2 迁移**：新建 `licenses` 表（实例级）+ `users` 补 `activated_at` / `disabled_at`
      （后者是席位口径，P6-P0 实测**两列缺失** ⇒ 不算 License 也算不出席位）
- [ ] **T3 ORM 与豁免**：`class License` ⇒ 加进 `RLS_EXEMPT_TABLES`（`models.py:83`）
      - [ ] T3.1 照 G-24 `test_g24_roles_rls_exemption_is_declared_and_bounded` 同款写三条断言
            （豁免清单 ⇄ 实际模型、**不得**出现租户业务列）
- [ ] **T4 `LicenseProvider` / `DevLicenseProvider`**（收口 `app/services/license/`）
      - [ ] T4.1 **真读文件 + 真验签**；`LICENSE_ENFORCE=false` 时放行但**必须**落 `license.bypass`
      - [ ] T4.2 6 个 `settings.*`（`LICENSE_FILE_PATH` / `_PUBLIC_KEY` / `_ENFORCE` / `_FP_SALT` /
            `_STATE_TTL_SECONDS` / `_CLOCK_SKEW_TOLERANCE_DAYS`）**逐个配消费点**
            （门禁 `check_seams.py:359` 扫 `app/` + `scripts/`；**禁止占位**，Non-goal 9）
- [ ] **T5 `LicenseMiddleware`（纯 ASGI）**
      - [ ] T5.1 **不得**继承 `BaseHTTPMiddleware`（`test_guardrails_compliance.py:104` 会判）
      - [ ] T5.2 挂载到 `main.py:78` 与 `:79` **之间**（后加者在外层 ⇒ `审计 → License → 限流 → 路由`）
      - [ ] T5.3 豁免清单：`/health`、`/license/status`（照 `core/limiter.py:49` 的 `EXEMPT_ROUTE_NAMES` 同款）
      - [ ] T5.4 拒绝 ⇒ 落 `audit_log`（`action = license.denied`；**不含** License 正文 / 签名，Non-goal 10）
- [ ] **T6 契约**：`GET /license/status` + 6 个 `LICENSE_*` 错误码
      - [ ] T6.1 走 `export_openapi.py` 生成 ⇒ **不手写** `contracts/openapi.yaml`（Non-goal 12）
      - [ ] T6.2 HTTP 状态码统一 **403**（不用 402，Non-goal 6）
- [ ] **T7 `license-cli fingerprint`**（`scripts/` 下，输出指纹 + 组件明细）
- [ ] **T8 行为围栏**：移除 license ⇒ 受保护端点 **403 `LICENSE_MISSING`** 且拒绝落审计
      ⇒ **摘掉 G-23 的两条 `xfail`**（按 R-9：先有真子系统再摘标记，且**补强判据**）
- [ ] **T9 P95 增量 < 1ms 实测登记**（ADR-0006 R-L4）
- [ ] **T10 收尾三件套 + drift + 提交 + CI 回登**
      - [ ] T10.1 `pytest` 无图口径**不减**（基线 991）/ `ruff check` + `ruff format --check` /
            `export_openapi.py --check` 零 diff / `check_seams.py` **ERROR 0**
      - [ ] T10.2 `check_startup_readiness.py` ⇒ **G-23 进 🟢**、`[--]` 与 `[~~]` **均归零**
      - [ ] T10.3 提交（Conventional Commits）+ push + **CI 四 job 实证回登**（R-10）

## 不许外推（结案时对照）

- License 子系统存在 **≠** 防破解（`:171`：它是合规门槛，安全边界是 ADR-0003 的 RLS）
- 席位两列迁移了 **≠** 席位维度端到端生效 —— `activated_at` 由**首次登录**回填，登录属 **P2-C**
  ⇒ 本批**不得**宣称席位维度已端到端验证（P4-D5）
- G-23 转绿 **≠** P4 全完 —— **C2 补丁纪律**本批**不做**（P4-D3）
