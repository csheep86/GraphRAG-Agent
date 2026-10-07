# P2-C — 真实登录（DR-D9 前半）+ 席位可量 + `users.status` 接 RBAC

> 状态：**执行中**（无人值守，用户已授权）。上一批 P4（License）已归档，三轮 CI 全绿。
> 本批**不**从零探索：坐标表与决策表见 `new-session-prompt.md` §5 / §6，本文件只记**为什么做 / 改什么 / 影响面 / 不做什么**。

---

## 1. 为什么做（三条机械理由，不得被外推）

1. **P4 唯一"建好了却量不出来"的口子**：席位按 `activated_at IS NOT NULL AND disabled_at IS NULL`
   计数（`ADR-0006:115/121`），而 `activated_at` 由**首次成功登录**回填 ⇒ 登录不做则全表 NULL ⇒
   `count_seats()` **恒 0**（唯一消费者 `app/services/license/policy.py:57-74`）⇒ `max_seats` 判据永远触发不了。
2. **增量最小**：`users` 表（`models.py:779`）、接缝 1（`AuthProvider`）、身份解析入口
   （`app/core/auth.py:35/75`、`middleware.py:216-239`）**都已就位**，缺的只是"首次登录"这一个回填点。
3. **P2 的三笔挂账移交到这里**：R30 跨租户引用、孤儿 actor、`disabled` 账号仍有权限
   （`changes/P2/integration-log.md:285-287`/`:423-426`、`docs/dev-doc-status.md:107/313/314`）。

---

## 2. 改什么（实现面）

| # | 改动 | 落点 |
|---|---|---|
| 1 | **口令校验**（P6-P1 明写"算法终选归 P2-C"） | `app/services/auth/password.py`（**新增**）：PBKDF2-SHA256 / 600k / **stdlib**，沿用 `seed_dev_rbac.py` 已有的 `pbkdf2_sha256$iter$salt$hash` 格式 ⇒ **零新增依赖、零迁移**；`hmac.compare_digest` 恒定时间比对。`seed_dev_rbac.py` 改为 import 它（消除两份实现） |
| 2 | **登录查找**（RLS 下的受控旁路） | `app/db/rls.py` 新增 `app.find_login_user(p_username)`（`SECURITY DEFINER`，属主 `rls_probe`，只认 `public.users`）+ Python 包装 `find_login_user()`。**为什么必须旁路**：登录时还没有认证态 ⇒ 无 org ⇒ RLS 谓词为 NULL ⇒ 一行都查不到；这与 A7 `tenant_row_exists` 是同一形态（"看不见"不是"绕过"） |
| 3 | **JWT 签发 / 校验** | `app/services/auth/token.py`（**新增**）：HS256，**stdlib `hmac`+`hashlib`**（零新增依赖）。载荷 `sub` / `org` / `iat` / `exp` / `iss`；**不**带 roles（角色唯一真源是 `user_roles`，塞进 token 会让"库里已撤权、token 还说有"） |
| 4 | `parse_bearer_token` 认 JWT | `app/core/auth.py`：非 `dev.` 前缀先试 JWT；失败仍抛 `UNAUTHORIZED / "Unsupported bearer token"`（现有参数化用例的 message 不变）。`IdentitySource` 加 `"jwt"` |
| 5 | **`POST /api/v1/auth/login` 进契约** | `app/api/v1/routes/auth.py`（**新增**）+ `app/schemas/auth.py`（**新增**）+ `router.py` 注册。契约 paths **27 → 28** |
| 6 | `activated_at` **唯一回填点** | `app/services/auth/login.py`（**新增**）：仅"首次**成功**登录"回填；失败 / 目录同步 / 导入**不**回填（D3）。写入走 `open_session(org_id=user.org_id)`（RLS `WITH CHECK` 要求带 org） |
| 7 | `users.status` 接 RBAC（D4） | `app/services/rbac/service.py` 新增 `account_disabled` 拒绝原因；`rbac/deps.py` 在 RBAC 判定**之前**查一次。**有 `users` 行且非 active ⇒ 拒**；**无行 ⇒ 沿用现状**（孤儿主体不因本批变红——那是 R30 的收法，不是多拦一道） |
| 8 | R30 严格视图孤儿 = 0 | `tests/conftest.py` 为每个租户各播**一个独立主体**（`users.id` 是 PK ⇒ 同一 UUID 不可能在两个 org 各占一行，`cross_tenant_headers` 的 actor 因此改为 org B 自己的主体）；新增机械断言 `tests/test_identity_anchor.py` |
| 9 | 外部身份字段（子任务 ②） | `users.issuer` / `users.subject`（**nullable，不进契约**）+ Alembic 迁移；按 CODEBUDDY「功能预留原则」登记到 `docs/adr/0004-integration-seams.md` |

### 配置项（两个，均有消费者）

- `auth_jwt_secret`（默认 `DEFAULT_JWT_SECRET`，**生产沿用默认值即启动失败**，同 `_guard_production_sqlite` 口径）
- `auth_jwt_ttl_minutes`（默认 480，唯一读取点 = `token.issue_access_token`）

---

## 3. 影响面（会连带改哪些既有判据）

| 判据 / 文件 | 变化 | 为什么不算放宽 |
|---|---|---|
| `tests/test_openapi_contract.py::CORE_PATHS` | 27 → **28** | 新增端点必须登记（否则 `set(paths) == CORE_PATHS` 红） |
| 同上 `test_operation_ids_are_unique` | 27 → **28** | 同上 |
| 同上 `TENANT_PROTECTED_PATHS` | 排除 `/auth/login` | 登录是**认证态的签发入口**，请求时尚无认证态 ⇒ 不能要求 `bearerAuth`。**失效条件**：响应体一旦开始返回租户业务数据（文档 / 图谱 / 审计），必须立即移回受保护集 |
| `test_guardrails.py::test_g18_users_table_exists` | 列集合 +2 | 新增 `EXTERNAL_IDENTITY_COLUMNS`，与 P4 加 `SEAT_COLUMNS` 同款登记动作；仍是"集合恰好相等" |
| `USERS_CONSUMER_MODULES` | +2（`services/auth/login.py`、`services/rbac/service.py`） | 闸门本意就是"谁开始读 `users` 谁登记"；本批正是第一批真实读者 |
| `test_guardrails_rls.py::test_g26_6` | 受控函数 2 → **3**；表白名单改为**逐函数** | 仍是"集合恰好相等 + 逐条点名"；`find_login_user` 只认 `public.users` |
| `tests/conftest.py::cross_tenant_headers` | actor 改为 org B 自己的主体 | 跨租户用例验的是"org A 的资源在 org B 视野下不可见"，与 actor 是否相同**无关**；且 org B 主体仍授 admin（否则 RBAC 会抢在应用层过滤之前拦掉，验的就不是那一层） |

---

## 4. 不做什么（**12 条 Non-goals**，改一条都要先回来登记理由）

1. **不新增 `AuthProvider` 第二实现**（D1 顺延）——接缝 1 实现集合**恒为 1**，`max_impls=1` 双向锁；`LdapAuthProvider` 属越界。
2. **不改 `AuthProvider.authenticate()` 签名**（G-11 签名冻结）。
3. **不改 `LocalAuthProvider` 语义**——唯一例外：它委托的 `parse_bearer_token` 新增 JWT 分支（**已登记理由**：登录签发了 token 却无人认，等于登录没做）。签名与工厂均未动。
4. **不伪造席位**：`activated_at` **只能**由真实首次成功登录回填（P4-D5 明令）。
5. **不做用户 CRUD / 授权管理界面（UI）**。
6. **不改 RBAC 矩阵取值**（G-24 不断言具体权限值）。
7. **不动 ADR-0006**。
8. **`activated_at` / `issuer` / `subject` / `password_hash` 均不进契约**。
9. **不做密码策略 / MFA / 找回密码 / 会话管理 UI / 登出端点**。
10. **不处理 R30 与孤儿 actor 之外的历史挂账**（那两笔本批收）。R30 的 ②③（`documents.uploaded_by` 随机 UUID / `audit_log.actor_id` 系统触发）属**演示库数据**且原文已明写「不补」，本批保持登记、不动数据。
11. **不做前端页面**（唯一例外：契约漂移触发的 `npm run gen:api` 生成物，机械产物不是设计）。
12. **不顺手改 `app/api/deps.py`**。

---

## 5. 不许外推（**完成本批 ≠ 以下任何一条**）

- **登录可用 ≠ SSO 可用**：`delivery-plan.md:194` 明写「真机登录可用（OIDC 用 Keycloak/Dex，AD 起 Samba AD DC）——**mock 跑通不得宣称完成**」。本批只做前半。
- **P2 批次出口只达成一半**：`delivery-plan.md:77`④「`check_seams.py` 登记接缝 1 第二实现」**未达成**（D1）。
- **DR-D9（SSO/AD）无对应 G 护栏编号** ⇒ 无论做到哪一步都**不得宣称完成**，只能登记状态。
- 登录做完 ≠ 账号体系完成（CRUD / 授权界面 / MFA / 会话管理都不在内）。
- `activated_at` 能回填 ≠ 席位合规：`max_seats` 是否**真的拦得住**超限，需另做实测判据。
