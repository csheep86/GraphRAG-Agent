# P4 · License 商业化底座（**DR-C1** / **G-23** / ADR-0006）—— 集成记录

> **状态**：进行中。**T0 已闭环（已提交）**，T1~T10 待做。
> ⚠️ **为什么先写这份**：T0 的实测证据原先只活在执行会话的上下文里 ——
> 换会话即丢 ⇒ 本文件是它的**持久化落点**（同时也是 T1 起每个任务的追加点）。
> 边界见 `proposal.md`；任务勾选见 `tasks.md`；交接提示词见 `new-session-prompt.md`。

---

## 1. T0 · 清 ADR-0006 `:108` 的 TBD-L1（验签库选型）

> ADR-0006 §2.3 原话：**验签库「未落选前不得先写代码」**。这条不清，License 就不能动 ——
> 而 License 又必须**真验签**（§2.3「验签失败 = License 无效，不做宽松通过」，
> §2.4「禁止实现成恒 true（那是'假做'）」）⇒ 这是本批真正的第一步。

| # | 实测动作 | 读到的结果 | 结论 |
|---|---|---|---|
| 1 | `uv run python -c "import cryptography / nacl / jwt"`（加依赖**前**） | `cryptography: False` / `nacl: False` / `jwt: False` | venv 内**两者皆无** ⇒ 必须新增依赖，没有"顺手用现成的"这条路 |
| 2 | 选型：**ADR 的 4 条判据**（①纯 `uv` 可装 ②无原生编译依赖 ③无网络回调 ④支持 Ed25519） | `pynacl` 与 `cryptography` **四条全部满足** —— 判据本身**分不出优劣** | 用**生态地位**打破平局：选 **`cryptography`**，避免额外引入 libsodium |
| 3 | `pyproject.toml` 加 `"cryptography>=44,<47"`（注释写明选型判据）+ `uv lock` | **Resolved 92 packages**；新增 `cryptography v46.0.7` / `cffi v2.1.1` / `pycparser v3.0` | 锁文件已重配（不重配 ⇒ CI 拿不到该依赖） |
| 4 | Ed25519 **功能回路**实测：生成密钥 → 签正文 → 验签；再验「正文被改」与「换一把公钥」 | 回路 ✅ ／ **篡改可检出** ✅ ／ **错钥匙拒签** ✅ ／ 签名 **64 字节**、base64 **88 字符** | 后两条是关键：**验签必须是"会因篡改而失败"的**，否则等于没验；64B/88 字符与 §2.2 的 detached base64 形态一致 |
| 5 | 连带回归（加依赖后） | `check_seams` **ERROR 0 / WARN 0 / OK 10**；契约 **zero diff**；`test_guardrails_compliance.py` **4 passed, 2 xfailed**；自检 `[--]` **仍仅 G-23**（2 条断言） | 依赖入场**没有连带破坏**，G-23 如期仍红 |
| 6 | 提交 | `a39e7e25` `build(p4): 新增 cryptography 依赖（清 ADR-0006 TBD-L1 验签库选型）` | **刻意独立成一笔**：离线 wheelhouse 装不上时可整笔回退重新选型 |
| 7 | 边界文档 + 交接提示词 | `f45a5215` `docs(p4): P4 边界文档 + 新会话开场提示词（12 条 Non-goals）`； drift 回切点实测 **S1 读到 12 条** | 边界已生效，来源 `changes/P4/proposal.md` |

### 1.1 T0 的未验项（**必须记到底，不许遗忘**）

- **离线 wheelhouse 下 CI 能否从 `uv.lock` 装出 `cryptography`** —— 本地是**联网**解析成功的，
  **CI 尚未判**。这是本批第一个重量级未知。
  ⇒ 若 CI 装不上：**回退 `a39e7e25` 整笔并重走选型**，不要硬推。

---

## 2. T1 · 接缝 9 登记（**下一个动作**）

### 2.1 撞到的结构冲突（本批最需要小心的一处）

ADR-0006 §4 要求「`check_seams.py` 新增登记行 `LicenseProvider → [DevLicenseProvider]`（`max_impls = 1`）」，
但同一节的另一句写「**ADR-0004 §2.1 的八个接缝数量与编号不变**」。
而 `check_seams.py:572-588`（判据 4）对每条规则都去 **ADR-0004 §2.1 的同号行**找登记字样 ⇒

| 做法 | 后果 |
|---|---|
| 直接加 `InterfaceRule("接缝 9 …")` | 判据 4 去找「ADR-0004 §2.1 **第 9 行**」——那里只有 8 个接缝 ⇒ **CI 必红** |
| 改 ADR-0004 加第 9 行 | **违背** ADR-0006 §4「数量与编号不变」 |

⇒ 两条 ADR 要求在**当前门禁实现**下互斥。**采纳解法（P4-D2）**：给 `InterfaceRule` 增 **`adr_file`** 字段
（默认 ADR-0004），接缝 9 指向 **ADR-0006 §4** ⇒ 登记仍须逐字可查、两侧不一致仍红（**加强**不是削弱）。

### 2.2 已查证的接入点坐标（**不要重做 recon**）

| 项 | 落点 |
|---|---|
| 中间件挂载 | `main.py:63-80`，`add_middleware` **后加者在外层** ⇒ 要得到 `审计 → License → 限流 → 路由`，必须插在 `RateLimit`（`:78`）之后、`Audit`（`:79`）之前 |
| 必须纯 ASGI | 既有 `AuditMiddleware`（`core/middleware.py:89`）是普通类（不继承 `BaseHTTPMiddleware`）；`test_guardrails_compliance.py:104` 判「继承 BaseHTTPMiddleware」= 不达标 |
| 豁免清单先例 | `core/limiter.py:49` 的 `EXEMPT_ROUTE_NAMES`（形态 = `模块名.函数名`） |
| 配置消费者门禁 | `check_seams.py:359` `_collect_setting_consumers`（扫 `app/` + `scripts/`；`config.py` 被 `SKIP_FILES` 排除，`Settings` 内 `self.<字段>` 由 `:381` 兜住）⇒ **6 个 `LICENSE_*` 必须逐个配到真实消费点** |
| 接缝登记 | `check_seams.py:135-169`（现只有接缝 1/2/5/6）；判据 4 `:555-608`；ADR 真源常量 `:78` |
| RLS 豁免 | `models.py:83` `RLS_EXEMPT_TABLES = frozenset({"roles"})` ⇒ 追加 `licenses`；由 `test_guardrails_compliance.py:218` 盯住（豁免清单 ⇄ 实际模型必须相等） |
| G-23 两条断言 | `test_guardrails_compliance.py:85`（静态侧六项资产）／`:133`（行为侧 403 + 落审计），均为 `strict=True` 的 xfail |

---

## 3. 基础线（已体检，不必重跑）

本地**无图**口径 `pytest` **991 passed**（不减即为通过）；CI 口径 **997 passed**；
容器 `graphrag-pg16` / `graphrag-neo4j` 均 Up；开局自检 `[--]` **仅 G-23**（2 条断言）、`[~~]` **0 条**。

---

## 4. T2~T10 · 实测登记（完成一条、在此追加一条；读数一律来自跑出来的命令）

- **T2** 迁移 `f3a91c2d6b70`：`licenses` 表（实例级、无 `org_id`）+ `users` 补 `activated_at` / `disabled_at`
- **T3** ORM `class License` + RLS 豁免登记 + 豁免三条断言（`test_guardrails_rls.py`）
- **T4** `LicenseProvider` / `DevLicenseProvider` + 6 个 `settings.*` 及其消费点（接缝 9 登记成立）
- **T5** `LicenseMiddleware`（纯 ASGI）+ 挂载 + 豁免清单 + 拒绝落审计
- **T6** `GET /license/status` + 6 个 `LICENSE_*` 契约码（走 `export_openapi.py`，**不手写**契约）
- **T7** `license-cli fingerprint`
- **T8** 行为围栏端到端断言 ⇒ **摘掉 G-23 的两条 xfail**（按 R-9 先有真子系统，且补强判据）
- **T9** P95 增量 **< 1ms** 实测登记（ADR R-L4）
- **T10** 收尾三件套 + drift + 提交 + **CI 实证回登**（见 §5）

### 4.1 本地实测（提交前）

| 判据 | 命令 | 读数 |
|---|---|---|
| 全量测试 | `uv run pytest -q` | **994 passed / 11 skipped / 0 failed** |
| 静态 | `uv run ruff check .` | **All checks passed** |
| 格式化 | `uv run ruff format --check .` | **245 files already formatted** |
| 契约零漂移 | `uv run python scripts/export_openapi.py --check` | **zero diff** |
| 接缝门禁 | `uv run python scripts/check_seams.py` | **ERROR 0 / WARN 0 / OK 12** |
| 开工自检 | `uv run python scripts/check_startup_readiness.py` | G-23 计入 `[OK]`（2 条，xfail 已摘） |
| P95（R-L4） | `test_g23_license_decision_is_sub_millisecond_at_p95` | 1000 次采样，**P95 < 1ms 常驻判据**通过 |

⚠️ **P95 的口径边界**：量的是**中间件判断本身**（不含业务处理），即 ADR §2.6「每请求判断」所指的部分；
**不是**端到端请求时延。别拿这个数去回答"接口慢不慢"。

### 4.2 被既有判据抓住的三次（都未绕过，逐条登记）

1. **契约黄金清单** `tests/test_openapi_contract.py::CORE_PATHS` 硬编码 26 路径 ⇒ 新增端点必须登记
   （我一开始误判为"测试间污染"，证据纠正了我）。同步更新 operationId 唯一性断言 `26 → 27`。
2. **受保护路径须声明 401/403**：新自检端点被自动纳入 `TENANT_PROTECTED_PATHS`。
   按 `/health` 同款口径排除，并把**理由 + 失效条件**写进代码：将来它若返回租户数据，必须移回受保护集。
3. **S3 配置模板**：6 个 `LICENSE_*` 未同步 ⇒ 补齐 `backend/.env.example` 后转 `[OK]`。

### 4.3 过程中修掉的一个自埋缺陷（不是既有问题）

`_trace_id()` 原被调用两次 ⇒ **响应体与审计会拿到两个不同的 trace_id**；且它挂在 `TraceIdMiddleware`
**之外**（§2.6 顺序），contextvar 恒空。现改为**一次定值、审计与响应体复用**，并优先采信上游 `X-Trace-Id`。
为什么值得记：不修的话"拒绝落审计"就是**串不进链路的假审计**——排障时看得见一条审计却对不上客户端拿到的 trace。

---

## 5. T10 · CI 实证回登（R-10：CI 才是终裁）

| 轮次 | run id | commit | 结论 | 说明 |
|---|---|---|---|---|
| 第 1 轮 | **37480357477** | `42c75bd1` | **failure** | 后端 / 前端 lint 均 success，**契约校验红** |
| 第 2 轮 | **37562184724** | `ec59e9b7` | **success** | 四个 job 全绿 |

**第 1 轮红因（根因，不是批次摊太大）**：改了 `contracts/openapi.yaml` 却**未按契约同步铁律第 2/4 条**
重生成前端类型。CI 现场证据（`git diff -- frontend/src/types/api.d.ts`）：

- `ErrorCode` 缺 6 项 `LICENSE_*`（MISSING / INVALID / FINGERPRINT_MISMATCH / EXPIRED / LIMIT_EXCEEDED / MODULE_DISABLED）
- 缺 `/api/v1/license/status`（`getLicenseStatus`）与 `LicenseStatus` 结构

修复：`cd frontend && npm run gen:api`（**仅机械生成物**，1 file / +127 −1，无手写改动），提交 `ec59e9b7`。

**第 2 轮四 job 结论**：后端（ruff + pytest）success ｜ 前端（lint + gen:api）success ｜
契约校验（前后端漂移门禁）success ｜ 流水线汇总 success。

✅ **§1.1 的未知已清**：离线 wheelhouse 的 `cryptography` 在 CI **装得上**——后端 job 全绿即为实证
（本地不敢下这个结论，因为它是离线产物）。994 passed 在 CI 环境**复现**，非本地特有。

### 5.1 仍未兑现（本批不做，登记在此，不得宣称完成）

1. **指纹组件交集 ≥2/3 容忍**：ADR §2.2 的 `fingerprint` 只有**单个聚合值**，无组件明细可交集 ⇒ 换网卡需重签。
2. **`max_seen_ts` 未持久化**：§2.7 要求持久化，但 §3.1 字段清单无对应列 ⇒ 加列须先改 ADR。
3. **`LICENSE_FP_OVERRIDE` 未实现**：它附带的义务是必须落 `license.fp_override` 审计；只做旋钮不做义务等于假做。
4. **席位维度无端到端生效**：`activated_at` 由**首次登录**回填，登录属 P2-C ⇒ 此刻全表 NULL、实际席位恒 0。
   License 存在也 **≠** 防破解——安全边界是 ADR-0003 的 RLS，License 是**合规计数**不是安全边界。
