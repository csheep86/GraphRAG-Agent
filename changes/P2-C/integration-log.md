# P2-C 集成日志 —— 真实登录（DR-D9 **前半**）+ 席位可量 + `users.status` 接 RBAC

> 上一批：P4（License 商业化底座），已归档 `changes/archive/2026-10-07-P4/`，三轮 CI 全绿。
> 边界与任务清单见同目录 `proposal.md` / `tasks.md`（SDD 事前已做）。
> 执行模式：无人值守（`unattended-sprint-execution`）；分支沿用 P4 做法 —— **在 `main` 上直推**。

---

## 1. 为什么是这一批（三条机械理由）

1. **P4 唯一"建好了却量不出来"的口子**：席位按 `activated_at IS NOT NULL AND disabled_at IS NULL`
   计数（ADR-0006:115/121），而 `activated_at` 由**首次成功登录**回填 ⇒ 登录不做 ⇒ 全表 NULL ⇒
   `count_seats()` **恒 0**（唯一消费者 `app/services/license/policy.py:57-74`）⇒ `max_seats`
   判据**永远触发不了**。P4 已登记「不得宣称席位端到端生效」。
2. **增量最小**：`users` 表、接缝 1、身份解析入口都已就位，缺的只是"首次登录"这一个回填点。
3. **P2 的三笔挂账移交到这里**：R30 跨租户引用、孤儿 actor、`disabled` 账号仍有权限。

---

## 2. 做了什么（按子任务）

| # | 内容 | 落点 |
|---|---|---|
| T1 | 口令校验（P6-P1 遗留的「算法终选」） | `app/services/auth/password.py`；`seed_dev_rbac.py` 改为 import 它 |
| T2 | 登录查找的**受控旁路** | `app/db/rls.py::app.find_login_user` + `find_login_user()` |
| T3 | JWT 签发 / 验签 + `parse_bearer_token` 认 JWT | `app/core/token.py`、`app/core/auth.py`、`config.py`、`.env.example` |
| T4 | `POST /api/v1/auth/login` 进契约（27 → 28） | `schemas/auth.py` / `routes/auth.py` / `router.py` / `contracts/openapi.yaml` / 前端生成物 |
| T5 | `activated_at` **唯一**回填点 | `app/services/auth/login.py` |
| T6 | `users.status` 接 RBAC（D4） | `services/rbac/service.py` + `rbac/deps.py` |
| T7 | R30 严格视图孤儿 = 0 | `tests/conftest.py` + `tests/test_identity_anchor.py` |
| T8 | 外部身份预留列 | `users.issuer` / `users.subject` + 迁移 + ADR-0004 §2.2.1 |

---

## 3. 判据（**真跑出来的**，不是读代码得出的）

| # | 判据 | 实测 |
|---|---|---|
| 1 | 一次真实登录成功后 `users.activated_at` **非 NULL**（查库） | ✅ `test_login_flow.py::test_login_backfills_activated_at_and_seat_is_countable` |
| 2 | 上述前提下 `count_seats()` **≥ 1**（**P4 时恒 0 = 差分证据**） | ✅ 同上（同一用例内断言） |
| 3 | 第二次登录**不改写**首次时间（回填点只有一个） | ✅ `test_second_login_does_not_rewrite_activated_at` |
| 4 | 签发的令牌**真的**被受保护端点接受 | ✅ `test_token_from_login_is_accepted_by_protected_endpoint`（`/api/v1/audit` 非 401） |
| 5 | 口令错 ⇒ 401 且**不**回填 | ✅ `test_wrong_password_is_rejected_and_does_not_activate` |
| 6 | `disabled` ⇒ 登录 401 + 新请求 403（`reason=account_disabled`）+ `count_seats()` 回落 **0** | ✅ `test_disabled_account_is_rejected_on_login_and_on_every_request` |
| 7 | 接缝门禁 ERROR 0（本批**未新增**实现） | ✅ `check_seams.py` ERROR 0 / OK 12 |
| 8 | 契约零漂移（paths 28）+ 前端无漂移 | ✅ `export_openapi.py --check` 零 diff；`npm run gen:api` 生成物同批提交 |
| 9 | 测试基线不回归 | ✅ 本地 **1006 passed / 4 skipped / 2 failed**（999 基线 **+7** 新增；2 条失败 = 改动前**逐条相同**的语料相关用例） |
| 10 | CI 四 job 全绿（R-10：CI 才是终裁） | ⏳ 见 §5 |

---

## 4. 决策与代价（按 `new-session-prompt.md` §5 执行，未改道）

| # | 决策 | 执行情况 / 连带代价 |
|---|---|---|
| **D1** | 不新增 `AuthProvider` 第二实现 | ✅ 执行。`check_seams.py` 仍 ERROR 0。**⇒** 子任务 ① 顺延；`delivery-plan.md:77`④「登记接缝 1 第二实现」**仍挂起，不得宣称达成** |
| **D2** | 登录端点进契约 | ✅ 三件事同批做完：`CORE_PATHS` 27→28 + operationId 计数 28 + `TENANT_PROTECTED_PATHS` 排除（**写明理由与失效条件**）+ 前端生成物。**额外**连带：RBAC 的「契约端点 → 资源」双向锁（`test_rbac.py`）也要登记 ⇒ 补 `/auth/login → auth`，四档 `_NONE`（含义是「RBAC 不参与」，已写失效条件） |
| **D3** | 仅"首次成功登录"回填 | ✅ 执行。`backfill_activated_at()` 带 `WHERE activated_at IS NULL`（并发幂等）；失败 / 目录同步 / 导入**均不**回填 |
| **D4** | `disabled` 立即失效 | ✅ 收。`REASON_ACCOUNT_DISABLED` 在**权限判定之前**拦。**刻意的例外**：查不到 `users` 行 ⇒ **放行**（孤儿主体的处置权在 R30，不在这里——改"查不到即拒"会让上千条既有用例为与己无关的原因集体变红） |
| **D5** | SSO 不做 | ✅ 未做。DR-D9 状态保持 ⏳ |

### 4.1 三个"顺带放大"的受控面（已登记，非放宽）

1. **受控 RLS 函数 2 → 3**：`app.find_login_user` 是**第一个会返回列数据**（含 `password_hash`）
   的受控函数。代价写在常量 `LOGIN_LOOKUP_TABLE` 旁：把「任意口令的在线猜测」从不可能
   放宽到**受 60/min 限流约束**——这是登录功能不可分的一部分（不取哈希就无处校验）。
   G-26 判据 6 **未放宽**：仍是「函数集合恰好相等」+「每个函数只碰自己被点名的表」，
   只是把**一个全局白名单**改成**逐函数白名单**（否则新函数要么进不去，要么被迫挤进
   `PROBE_TABLES` 把 `tenant_row_exists` 的探测面一起扩大——那才是真的放宽）。
2. **`users` 的第一批真实读者**：`USERS_CONSUMER_MODULES` 由 1 → 3
   （`services/license/policy.py` + `services/auth/login.py` + `services/rbac/service.py`）。
   登记处已交代归属 DR、所需列、是否新增接缝实现、对应护栏四条。
3. **口令算法偏离 spec**：`specs/m5-permission-audit.md` §4.1 写的是 bcrypt / argon2，
   本批**终选 PBKDF2-SHA256（stdlib）**。理由登记在 `app/services/auth/password.py`
   模块 docstring：① 零新增依赖（为一条 `NOT NULL` 列引入 `passlib` 属无消费者依赖）；
   ② 沿用 P6-P1 已有串格式 ⇒ 零迁移；③ 迭代数随串落地 ⇒ 将来上调不必一次性重算全表。
   若客户审计点名要 argon2id ⇒ 届时做**增量轮换**，不重写历史。

### 4.2 三个刻意的"不做"（不是遗漏）

1. **不写登录审计**：登录**失败**时拿不到 org（用户名都不存在），而审计行的 `org_id`
   是隔离键、不可填空（`middleware.py` 对匿名请求的处理同此口径）。只给成功的一半写、
   失败的一半不写，比都不写更容易被读成"全都有痕" ⇒ **整体不做**，在此登记为缺口。
2. **不做刷新令牌 / 吊销列表 / 登出端点**：会话管理不在边界内（Non-goal 9）。
   ⇒ 当前令牌**无状态、有效期内不可撤回**，这是已知上限。
3. **不把角色塞进令牌 / 响应**：唯一真源是 `user_roles`，塞进去就有「库里已撤权、
   手里还写着有」的窗口。

### 4.3 一个被脚本拦住的现场（`check_session_drift.py`）

S2 报「改动 699 行 > 阈值 600」⇒ 已按提示**拆成 4 个提交**（口令+旁路 / 契约+JWT /
回填+RBAC 门 / 锚点+预留列），每个提交可独立读、独立回滚。
S1 读到 **12 条 Non-goals**；S3 配置同步 `[OK]`；S5 无孤独模块。

---

## 5. CI 终裁（R-10）

> 本地绿不算，CI 才是终裁。

| run | 结论 |
|---|---|
| 待回填 | 四 job 全绿 / 红 |

---

## 6. 不许外推（**完成本批 ≠ 以下任何一条**）

- **登录可用 ≠ SSO 可用**：`delivery-plan.md:194` 明写「真机登录可用（OIDC 用 Keycloak/Dex，
  AD 起 Samba AD DC）—— **mock 跑通不得宣称完成**」。本批只做前半（本地口令），
  后半（接缝 1 第二实现 + 真机 SSO）**继续挂账**。
- **P2 批次出口只达成一半**：`delivery-plan.md:77`④「`check_seams.py` 登记接缝 1 第二实现」
  **未达成**（D1 顺延）。
- **DR-D9（SSO / AD）无对应 G 护栏编号** ⇒ 无论做到哪一步都**不得宣称完成**，只能登记状态。
- 登录做完 ≠ 账号体系完成：用户 CRUD、授权管理界面、MFA、会话管理**都不在内**。
- `activated_at` 能回填 ≠ 席位合规：`max_seats` 是否**真的拦得住**超限，需另做实测判据
  （`count_seats()` 目前**没有生产调用方**，只被测试与判据直接调用）。
- 本批**未**触碰 ADR-0006，也未因席位改动 License 的任何判据口径。

---

## 7. 遗留（带坐标，不伪装）

| # | 遗留 | 坐标 |
|---|---|---|
| 1 | 登录留痕（成功 / 失败）未做 | §4.2 第 1 条 |
| 2 | 令牌无吊销能力（无状态、有效期内不可撤回） | §4.2 第 2 条 |
| 3 | R30 的 ②③（`documents.uploaded_by` / `audit_log.actor_id` 随机 UUID）属**演示库数据**，原文已明写「不补」 ⇒ 保持登记不动数据 | `docs/dev-doc-status.md` §8 R30 |
| 4 | `users.issuer` / `subject` **0 消费者**（启用条件 = 接缝 1 第二实现） | `docs/adr/0004-integration-seams.md` §2.2.1 |
| 5 | 子任务 ①（扩写 ADR-0004 §2.1 再改 `get_auth_provider()`）顺延 | D1 |
