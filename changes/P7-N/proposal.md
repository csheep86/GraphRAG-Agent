# P7-N · 前端登录链路接通（P7-D 遗留 F-P7D-3 升级项）

> **日期**：2026-10-13 ｜ **来源**：`changes/P7-D/integration-log.md` §5 F-P7D-3，**性质经核实后升级**
> **一句话**：后端早就有了真登录，前端还没有人去调用它 —— 补上这一条线，客户才能在自己的部署里真正进系统。
> **优先级**：P7-E 完成后立即（早于 P7-F/G）。

## 0. 为什么不是"加个页面"这么简单（**纠错记录**）

P7-D 收口时把它登记成「已知 UI 缺口」，那是**写轻了**。补查之后的三个事实：

| 事实 | 坐标 |
|---|---|
| 后端登录是**真实现**：校 `users` 表口令哈希（PBKDF2），签发 HS256 JWT，且是**席位计数（`activated_at`）的唯一来源** | `app/api/v1/routes/auth.py:53,68`；`app/services/auth/login.py:74`；`app/db/rls.py:348 find_login_user` |
| 前端**完全没有 token 链路**：无登录页、无 `Authorization` 头、无 token 存储（全仓仅命中生成物 `api.d.ts` 的注释与类型） | `frontend/src` 全量检索；`client.ts` 的 `request()` 只发 `Accept` / dev 态 `X-Org-Id` / `Content-Type` |
| P7-C 已把 dev token / dev header 收口为**生产不可达**（护栏 G-27 钉住） | P7-C 集成日志；`core/auth.py:67-83` |

⇒ 三者叠加：**生产环境里前端没有任何可用身份入口**。它不是"少个页面"，是**交付后客户进不去**。

**后端测试其实已经有了**（`tests/test_login_flow.py` 7 处命中、`test_openapi_contract.py` 4 处）
⇒ 本批补的是**前端接线**，不是重新做整个登录。

## 1. 起点与坐标

| 项 | 坐标 |
|---|---|
| 登录端点 | `POST /api/v1/auth/login`（契约已有；`TENANT_PROTECTED_PATHS` 里**唯一**被豁免的非探针端点） |
| 请求/响应模型 | `app/schemas/auth.py` `LoginRequest` / `LoginResponse`（含 `access_token` / `expires_at` / `user_id` / `org_id`） |
| 角色**不**来自令牌 | `core/auth.py:103`：`actor_id = claims.user_id`，roles 另由 `user_roles` 表判定 |
| 前端请求层 | `frontend/src/api/client.ts` 的 `request()`：当前**没有** `Authorization`；`ApiError` 已能带 `.status` / `.code` |
| Mock 白名单 | `/api/v1/auth/login` **已在**白名单内（P7-D 纳管）⇒ `USE_MOCK=false` 时它已经走真接口，**这块不用再动** |
| 页面现状 | `frontend/src/app` 下 14 个 `page.tsx`，**无 login** |
| 出错处理 | 401 一律 `{code:"UNAUTHORIZED", message:"用户名或口令不正确"}`（**不区分**账号不存在 / 口令错 / 停用，防账号枚举） |

## 2. 做什么

1. **登录页**：最小表单（用户名 + 口令），失败按后端返回的 message 显示，**不**自行区分原因。
2. **token 承载**：登录后存 `sessionStorage`，`request()` 带 `Authorization: Bearer <token>`。
   > **用户裁决（2026-10-13）**：采用 **`Authorization` 头 + `sessionStorage`**。
   > 理由：契约已把 JWT 的携带方式写死为 `Authorization: Bearer`（`api.d.ts` 的 `LoginResponse` 描述）；
   > 改 HttpOnly cookie 要动后端登录响应 + CSRF 防护 ⇒ 属"改后端行为"，越出本批边界。
   > 选 `sessionStorage` 而非 `localStorage`：少一层长期驻留。登记风险见 §6。
3. **401 统一处理**：请求层收到 401 ⇒ 清 token + 回登录态（不静默重试、不假装成功）。
4. **登出**：清 token 并回到登录态。
5. ~~首个账号从哪来~~ —— **不在本批出口**（见 §5 第 1 条改判）。

## 3. Non-goals（**改一条都要先回来登记理由**）

1. **不做 SSO / AD / LDAP / OIDC**（接缝 1 的第二个实现，DR-D5 顺延）。
2. **不改后端登录逻辑**：不动 `token.py` 的签发、不动 `user_roles` 的判定、不动 401 的消息口径。
3. **不做注册 / 自助找回口令 / 改密 UI**。
4. **不动 RBAC 矩阵与 `require_permission` 语义**（G-24 在盯）。
5. **不做 HttpOnly cookie 迁移**（已裁决放弃，理由见 §2）。
6. **不给 Mock 数据加登录态假象**（Mock 是 dev 开关，本批不为它补登录分支）。

## 4. 出口判据

1. **真跑通一条线**：用真实后端 + `seed_dev_rbac.py` 播出来的账号登录 ⇒ 拿到 token，
   用它调至少一个受保护端点（如 `GET /api/v1/documents`）返回 **200 而不是 401**；贴命令与响应片段。
2. **反向**：不带 token 调同一端点 ⇒ 呈现登录态（**不是**空表格 / **不是**假数据），并有用例或脚本钉住。
3. `tests/test_frontend_contract_coverage.py` 仍 **10 passed**（本批大概率动 `client.ts` ⇒ 这是它第一次有真实机会红）。
4. pytest 不降、`ruff` / `check_seams.py` ERROR 0、`export_openapi.py --check` 零 diff + `gen:api` 幂等。
5. ~~首个账号的创建步骤写进部署文档~~ —— **改判为交付前提，不在本批出口**（见 §5 第 1 条）。
6. push 后 **CI 四 job 全绿**（R-10）。

## 5. 升级用户的四种情况

1. ~~**首个管理员账号怎么给**（必须先裁决）~~ ✅ **已裁决（2026-10-13，用户采纳建议）：本批不动**。
   判定依据：**它是交付前提，不是开发前提** —— 本批（前端接线）只需要"存在一个能登录的账号"，
   本机 `seed_dev_rbac.py --password=` 就能造；而客户环境跑不到它（`install_acceptance.py:538`
   明写只播 dev 默认 org）⇒ 卡的是**交付**，不是本批。
   ⇒ **挂到 P7-H（交付演练）之前**解决，方案占位 **(a)**：交付包里一条幂等的一次性开户命令 + 一行文档，
   复用 `hash_password` 以免口令实现漂移（`seed_dev_rbac.py:42-45` 踩过一次）。
   ⚠️ 唯一会改变 (a) 形态的变量：**客户将来要不要接外部身份源**（SSO / LDAP）。若要接，
   本地口令这条路径（P2-C 已实装）会被**架空而非继承**。目前无信息支持 ⇒ 不为它提前做设计。
2. **token 过期 / 是否需要 refresh**：后端没有 refresh 端点（`LoginResponse` 有 `expires_at`）。
   过期后的 UX 要不要现在处理，还是先登记。
3. **既有页面在未登录时的表现**：全站现在无鉴权访问 ⇒ 接通后所有页都会开始要求登录，
   是否影响演示 / P7-I 端到端演练 ⇒ 发现冲突就停下报告。
4. **CI 红且复核两遍仍红** ⇒ 带 job 名 + 失败行 + 归因。

## 6. 风险登记（**不是 TODO，是本批要写进日志的限制**）

- **`sessionStorage` 挡不住 XSS**：token 仍可被同源脚本读取。缓解口径只做到
  "不引入任何第三方脚本 / 不用 `innerHTML` 渲染外部输入"，真正的加固要走 HttpOnly cookie。
- **CSRF 不适用本形态**：没有 cookie 自动凭证 + CORS 只允许 `127.0.0.1:3000` ⇒ 不额外做 token。
  若将来改 cookie，**必须**同时重判 CSRF。
- **`X-Org-Id` 的 dev 注入要小心**：登录后 `org_id` 由令牌决定（`core/auth.py:103`），
  dev header 那条路**不许**在生产形态下并存。

## 7. 验收时要特别注意的纪律

- 本批**大概率动 `client.ts`** ⇒ 顺手把 **F-P7D-2**（`/agent/query` 写了两次）一起清掉，
  并在集成日志里写明这是"借同文件改动顺带"，不是单独批次（若没动到该处，就留给 P7-E）。
- 不因为"登录页很小"就跳过 401 / 登出这两条反向路径——它们正是"看起来能跑"最容易藏的地方。
