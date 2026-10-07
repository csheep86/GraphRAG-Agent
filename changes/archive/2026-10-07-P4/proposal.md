# P4 · License 商业化底座（**DR-C1** / **G-23** / ADR-0006）

> **日期**：2026-10-06 ｜ **上游**：`changes/P6-P0`（缺口量化）+ `changes/P6-P1`（补 `users` 主体锚点）
> **关联**：DR-C1 / 护栏 **G-23** / ADR-0006（唯一真源）/ ADR-0004 §3（配置消费者、接缝门禁）
> **定位**：**纯新建子系统**（`backend/app/services/license/` 目前不存在），不是改造
> ⚠️ **草案**（2026-10-06 由执行代理起草），每条都带实测坐标

---

## 1. 为什么做（三条机械理由，非偏好）

| # | 理由 | 实测坐标 |
|---|---|---|
| ① | **它是唯一挡在 GA 前的护栏**。<br>`check_startup_readiness.py` 实读：`[~~]部分生效 = 0 条`、`[--] = 1 条`，该 1 条即 **G-23**（两条断言：`test_g23_license_assets_exist` / `test_g23_missing_license_blocks_requests`） | `delivery-plan.md:186-188` 的「零缺口」裁决：**GA 门槛 = 所有 G 进 🟢，一条不放行** |
| ② | **开工前置恰好全亮**：P6-P1 已把 `users` 从 0 行补到 1 行（`--check` 判缺机制有效） | `delivery-plan.md:197` 前置 = `users` 表（席位）+ A6 镜像 + G-15；自检显示 `[OK] users 表已存在（DR-B13）` |
| ③ | **P6-P0 / P6-P1 是为它铺路的**：P6-P0 的结论就写着「License 若先于主体锚点开工 ⇒ 席位数只能落空或造假」 | `docs/dev-doc-status.md` §8 R29 行；P6-P1 实测 `users` 已 **0 行 ⇒ 1 行** |

**为什么此批不能拆成小块**：ADR-0006 §3.2 的 6 个 `settings.*` **必须有消费者才能提交**
（ADR-0004 §3 第 5 条；判据见 `check_seams.py:359` `_collect_setting_consumers`，扫 `app/` + `scripts/`）。
分批落地 ⇒ 迁移 / 配置先落到库里、消费点却在下一批 ⇒ 门禁直接判「无消费者配置」⇒ **CI 红**。
⇒ 必须一次把「配置 ⇄ 消费点」同批落地（详见 §3.1 决策 **P4-D4**）。

## 2. 要交付什么

| # | 资产 | 现址 / 要求 |
|---|---|---|
| 1 | `licenses` 表 ORM | `class License`（`models.py`）；**实例级、RLS 豁免** ⇒ 加进 `RLS_EXEMPT_TABLES`（`models.py:83`），照 G-24 的 `test_g24_roles_rls_exemption_is_declared_and_bounded` 同款被 Conclusion check 盯住 |
| 2 | `LicenseProvider` 抽象 + `DevLicenseProvider` | 收口在 `backend/app/services/license/`；**必须真读文件 + 真校验**（`DevLicenseProvider` 禁止写成恒 true） |
| 3 | `LicenseMiddleware` **纯 ASGI** | 类**不得**继承 `BaseHTTPMiddleware`；挂载点 = `main.py:78` 与 `:79` **之间**（`add_middleware` 后加者在外层 ⇒ 得到 `审计 → License → 限流 → 路由`） |
| 4 | 6 个 `LICENSE_*` 契约码 | `LICENSE_MISSING` / `_INVALID` / `_FINGERPRINT_MISMATCH` / `_EXPIRED` / `_LIMIT_EXCEEDED` / `_MODULE_DISABLED`；HTTP **403（不用 402）** |
| 5 | `GET /license/status` | 归入豁免清单，无 License 时**必须仍可访问**（现场要能自检） |
| 6 | `license-cli fingerprint` | `scripts/` 下；输出指纹 + 组件明细 |
| 7 | **行为围栏** | 移除 license ⇒ 受保护端点 403 `LICENSE_MISSING`，且**拒绝必须落 `audit_log`**（`action = license.denied`）；`LICENSE_ENFORCE=false` 放行但落 `license.bypass` |
| 8 | **users 迁移两列** | `activated_at` / `disabled_at`（席位口径，P6-P0 实测两列缺失 ⇒ 不算 License 也算不出席位） |

## 3. 决策表（无人值守下采纳；带依据，可推翻）

| # | 决策点 | 采纳 | 依据 |
|---|---|---|---|
| **P4-D1** | **验签库（清 ADR-0006 `:108` 的 TBD-L1）** | 选 **`cryptography`**（Ed25519 经 `hazmat.primitives.asymmetric.ed25519`） | ADR 的 4 条判据①纯 `uv` 可装 ②无原生编译依赖 ③无网络回调 ④支持 Ed25519 —— `pynacl` 与 `cryptography` **均满足**，判据本身不分优劣 ⇒ 用**装机普及度 / 生态地位**打破：`cryptography` 是 Python 生态事实标准，避免额外引入 libsodium。实测当前 venv **两者皆无**（需加依赖 + 重配 `uv.lock`） |
| **P4-D2** | **接缝 9 怎么登记（本次撞到的结构冲突）** | **扩展 `check_seams.py` 的判据 4 为「按规则取 ADR 源」**：`InterfaceRule` 增 `adr_file` 字段（默认 ADR-0004），接缝 9 指向 **ADR-0006 §4** | 直接加 `InterfaceRule("接缝 9 …")`：判据 4 会去 **ADR-0004 §2.1 第 9 行**找（`check_seams.py:572-588`），而 ADR-0004 只有 8 个接缝 ⇒ **必红**；反过来改 ADR-0004 加第 9 行 ⇒ **违背 ADR-0006 §4「ADR-0004 八个接缝数量与编号不变」**。两条 ADR 要求在**当前门禁实现**下互斥 ⇒ 只能改门禁的取源方式；这是**加强**不是削弱（登记仍须逐字可查、两处不一致仍红） |
| **P4-D3** | 范围 | **只做 C1 License**，不带 **C2 补丁纪律** | C2 无任何红灯护栏，带上就是摊太大 |
| **P4-D4** | 批次粒度 | **单批落地**，不拆 P4-A/B/C | 见 §1 第三条：6 个 `settings.*` 必须与消费点同批，否则「无消费者配置」红 |
| **P4-D5** | 席位相关 | 两列迁移**同批做**；但**不得**宣称席位维度已端到端生效 | ADR-0006 `:121`：席位 = `activated_at IS NOT NULL AND disabled_at IS NULL`，`activated_at` 由**首次成功登录**回填 ⇒ 登录属 **P2-C** ⇒ 本批只能**单测计数函数**，不能端到端验 |

### 3.1 中间件落点（务必照此）

`main.py:63-80`：后加者在外层 ⇒ 现有外层→内层 = `TraceId → Audit → RateLimit → CORS`。
照 ADR-0006 §2.6 要求的 `审计 → License → 限流 → 路由`，**必须在 RateLimit 之后、Audit 之前 add** ⇒
插到 `main.py:78`（`RateLimitMiddleware`）与 `:79`（`AuditMiddleware`）**之间**。

## 4. Non-goals（**编号列表**，S1 须读到）

1. **不做 C2 补丁纪律**（`check_patch_contract_freeze` 属 P4 另一半，本批不碰）
2. **不做 SSO / AD / 登录**（P2-C）；**不回填 `users.activated_at` 造假席位**（`:121` 首次登录才回填）
3. **不改既有中间件语义**（只新增、不重构 `AuditMiddleware` / `RateLimitMiddleware`）
4. **不改 `RLS_EXEMPT_TABLES` 的既有成员**（只追加 `licenses`；删改 `roles` ⇒ G-24 红）
5. **不改 ADR-0004 §2.1 的八个接缝数量与编号**（见 P4-D2）
6. **不用 402**（统一 403，`ADR-0006:136`）
7. **不做**联网激活 / 心跳 / License 服务器 / 远程吊销 / 硬件加密狗 / 按用量计费（`:165-171`）
8. **不承诺防破解**（`:171`：License 是合规门槛，**不是安全边界**，安全边界是 ADR-0003 的 RLS）
9. **不保留任何「占位」配置**（ADR-0004 §3 第 5 条；License 配置**不得**走例外登记）
10. **不把 License 正文 / 签名写进 `audit_log`**（`:138` `detail` 只含错误码与维度）
11. **不摘任何与 License 无关的 xfail**（尤其不得碰 G-23 以外的标记）
12. **不修改 `contracts/openapi.yaml` 手写段**（由 `export_openapi.py` 生成 + `--check` 守）

## 5. 任务

- **T0** 依赖：加 `cryptography` ⇒ `uv lock` / 重配 ⇒ 本地 import 验通（清 TBD-L1）
- **T1** ADR-0006 §4 登记行先扩写 ⇒ 再改 `check_seams.py`（`InterfaceRule.adr_file`）⇒ 两侧必须双向一致（漏一侧即红）
- **T2** 迁移：`licenses` 表 + `users.activated_at` / `disabled_at`
- **T3** ORM `class License` + RLS 豁免登记（ models.py:83 ）+ G-24 同款断言
- **T4** `LicenseProvider` / `DevLicenseProvider` + 6 个 `settings.*` 及其消费点
- **T5** `LicenseMiddleware`（纯 ASGI）+ `main.py` 挂载 + 豁免清单
- **T6** `GET /license/status` + 6 个契约码（走 `export_openapi.py`）
- **T7** `license-cli fingerprint`
- **T8** 行为围栏端到端断言（403 + 落审计）⇒ **摘掉 G-23 的两条 xfail**
- **T9** P95 增量 < 1ms 实测登记（ADR-0006 R-L4）
- **T10** 三件套 + drift + 提交 + CI 回登

## 6. 验收判据（全机械）

| # | 判据 |
|---|---|
| ① | `check_startup_readiness.py` 的 G-23 由 `[--]` 进 **`🟢 已生效`**（`[~~]` 与 `[--]` 均归零 ⇒ **全场零缺口**） |
| ② | 两条 xfail 按 R-9 **先土建真子系统再摘标记**，且**补强判据**（只摘标记不算转正） |
| ③ | 移除 license 文件 ⇒ 受保护端点 **403 `LICENSE_MISSING`** 且 `audit_log` 有 `license.denied` |
| ④ | `/health` 与 `/license/status` 在**无 License 时仍可达** |
| ⑤ | 契约 `zero diff` 由 `export_openapi.py --check` 判；`pytest` 无图口径 **不减**（基线 991） |
| ⑥ | `check_seams.py` **ERROR 0**（接缝 9 两侧一致：ADR-0006 §4 登记行 ⇄ 门禁规则） |
| ⑦ | P95 增量 **< 1ms** 并登记 |

## 7. 状态

- **草案**（2026-10-06）｜ 真源： `docs/adr/ADR-0006-license-control.md` §2 / §3 / §4、`backend/tests/test_guardrails_compliance.py:85,133`、`delivery-plan.md:197`
