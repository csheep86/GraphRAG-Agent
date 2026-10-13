# P7-N · 集成日志（前端登录链路接通）

> 日期：2026-10-13 ｜ 起点 HEAD `5799cb1`（P7-E 收干净，CI run **38396222568** 四 job 全绿）
> 性质：**P7-D 遗留 F-P7D-3 的升级项** —— 后端早就有了真登录，前端没有人去调用它。

## 0. 结论（先给机器读数）

| 项 | 读数 |
|---|---|
| 登录能拿到 token | ✅ `LOGIN_OK token_len=279`，`user_id/org_id` 回显正确，`expires_at` 约 12 小时 |
| token 真的能开**受保护**端点 | `/api/v1/documents` 不带 token **401** ／ 带 token **200** |
| 生产形态下"门"有没有拦住 | 首页 SSR **44410 → 10359** 字节，侧栏标记「文档管理」**消失** ⇒ 拦住了 |
| dev 形态有没有被误伤 | dev 形态同一份代码 SSR **47233** 字节、侧栏标记**仍在** ⇒ 直通，14 个页面不受影响 |
| 登录表单有没有进客户端包 | `.next/static/chunks/*.js` 命中「登录 GraphRAG Studio」x1、`graphrag.auth.session` x1、`Authorization` x1 |
| `test_frontend_contract_coverage.py` | **10 passed**（本批删了一条重复 pattern，见 §2.5 —— 它第一次有机会红，没红） |
| 本地 pytest | **1272 passed / 46 skipped / 0 failed** |
| `ruff` / `check_seams.py` / readiness | All checks passed / 299 files formatted ｜ ERROR 0 / WARN 0 / OK 12 ｜ 🟢 **16** |
| `export_openapi.py --check` / `gen:api` | 零 diff / 幂等 |

## 1. 改动清单

| 文件 | 作用 |
|---|---|
| `src/api/session.ts`（新） | 会话存储与失效判定；`AUTH_REQUIRED` 的判定口径 |
| `src/api/auth.ts`（新） | `login()` / `startSession()` / `logout()` |
| `src/api/client.ts` | 请求挂 `Authorization: Bearer`；401 ⇒ 清会话；顺带清重复 pattern |
| `src/components/auth/use-session.ts`（新） | 订阅会话（三态） |
| `src/components/auth/auth-gate.tsx`（新） | 整站登录门 |
| `src/components/auth/login-form.tsx`（新） | 登录表单 |
| `src/components/layout/top-bar.tsx` | 把假账号区接真会话（见 §2.4） |
| `src/app/layout.tsx` | `AuthGate` 套在 `AppShell` **外层** |

**依赖方向是单向的**：`client.ts` → `session.ts` ← `auth.ts`。
之所以要抽出 `session.ts`，是因为 `client.ts` 发请求时要读 token，而 `auth.ts` 要靠 `client.ts`
的 `request()` 去登录 —— 直接互相 import 会成环。

## 2. 几个必须写下来的取舍

**2.1 门的位置在布局层，不是路由。** 现有 14 个页面共享同一个 RootLayout，拆路由会牵动全部页面；
而在布局层挡一道还能保证**未登录时连侧栏 / 顶栏都不渲染** —— 渲染出来就是"能点导航但每个接口都 401"
那种半成品状态，最容易让人以为"大概能用"。

**2.2 三态而不是二态**（`undefined` = 还没读）。`sessionStorage` 在 SSR 阶段不存在，
把"还没读到"当成"没有"会让每次刷新都闪一下登录页。

**2.3 `AUTH_REQUIRED` 只在 `APP_ENV === "production"` 时为真。** 这是本批唯一一个会波及日常开发的开关：
dev 走的是 `X-Org-Id` / dev token 那条兜底路，14 个页面的本地开发都靠它 ⇒ 一开强制登录，开发当场进不去。
而 P7-C 已把那条路收口为生产不可达（G-27）⇒ **生产不要求登录就没有任何入口**，两边正好咬上。
（§3 的 dev 形态读数是在确认这条没副作用。）

**2.4 顺带收掉顶栏的假身份。** 顶栏原本硬编码「林默 · 管理员」，且「退出登录」**点了没反应**
—— 那是一处既有的"看起来能跑"UI，正好落在本批的界线上：现在有会话显示**真实用户名**、退出真生效；
dev 兜底形态显示「开发态」而不是冒充某个具体的人。
⚠️ 菜单里「个人资料 / 偏好设置」两项**仍是占位且点击无反应**，本批没动 ⇒ 见 §6 F-P7N-3。

**2.5 顺带清掉 F-P7D-2**（`/agent/query` 在白名单里登记了两次）。按 proposal §7「借同文件改动顺带」，
本批确实动了 `client.ts`；批次信息（C3 问答端点）已挪到保留的那一条上，没丢。

**2.6 401 一律按"会话不在了"处理**（登录端点自身的 401 除外，那是口令不对）。
不做静默重试 —— 重试成功会掩盖事实；也不留着坏 token 让每个请求再挨一次 401
（症状是到处 loading / 到处红，很难归因）。

**2.7 错误文案原样显示。** 后端把「账号不存在 / 口令错误 / 已停用」压成同一句 401 文案（防账号枚举），
前端一区分就把那道防护抹了。

## 3. 真机读数（**这些都跑了，不是推断**）

**后端侧**（本机后端 `uvicorn :8010` + `seed_dev_rbac.py --password=…` 播出来的账号）：

```
LOGIN_OK user_id=00000000-0000-4000-8000-0000000000aa
         org=00000000-0000-4000-8000-000000000001
         token_len=279  exp=10/13/2026 21:13:42

NO_TOKEN   /api/v1/license/status            -> 200   ← 公开端点，**不能**用来验登录
WITH_TOKEN /api/v1/license/status            -> 200
NO_TOKEN   /api/v1/documents?page=1&...      -> 401   ← 这才是探测点
WITH_TOKEN /api/v1/documents?page=1&...      -> 200
```

> 侧记：`license/status` 不带 token 也 200 ⇒ 它是公开端点。拿它做验证会得到"登录了没都一样"的假结论。

**前端侧**（同一份代码，两个形态各 build 一次，SSR 输出对照）：

| 形态 | 端口 | 响应体字节 | 侧栏标记「文档管理」 |
|---|---|---|---|
| 旧生产镜像（drill 1.6.0，无登录门） | 3000 | 44410 | True |
| **新 · production** | 3010 | **10359** | **False** |
| **新 · development** | 3011 | 47233 | **True** |

> ⚠️ 关于本机环境：3000 端口一直被用户自己的演练栈占着（保留未动），验证另用 3010 / 3011；
> 另外**本机 dev 库被播了一个账号**（`username=dev-00000000-0000-4000-8000-0000000000aa`，
> 口令 `P7n-probe-2026`，仅本机 dev 用）。

## 4. 出口判据核销

| 判据 | 结果 |
|---|---|
| 1. 真登录拿 token，带它调受保护端点得 200 | ✅ §3 后端读数 |
| 2. 不带 token 呈现登录态，不是空表格 / 假数据 | ⚠️ **部分**：「后端返回 401」✅ 已机械确认；「未登录时不再渲染业务外壳」由 SSR 字节数骤降 + 侧栏标记消失证明 ✅；但**交互后回到登录表单**这一步要浏览器，见 §5 |
| 3. `test_frontend_contract_coverage.py` 仍 10 passed | ✅（删重复 pattern 之后仍绿） |
| 4. 门禁三件套 | ✅ 全绿 |
| 5. 首账号写进部署文档 | ⛔ **已改判**（交付前提，不在本批），见 proposal §5 第 1 条 |
| 6. push 后 CI 四 job 全绿 | 见 §7 |

## 5. 验证限制（**必须由真实浏览器收口，我没收**）

本工程**没有**给 frontend 装测试框架（P7-D 时的裁决：一致性检查放在 `backend/tests`），
所以「hydration 之后是否真的渲染出登录表单」「点了登录头里的 `Authorization` 是否真的发出」
**这两条我没有机械证据**。现有证据止于：

- 生产 bundle 里确实编进了登录表单、session key、`Authorization` 三处代码；
- 生产形态的 SSR 不再渲染任何业务壳內容。

**请在浏览器里确认这四步**（我把它写在这儿，因为没有浏览器的验证不算验证）：

1. 生产形态起服务，打开首页 ⇒ 出现登录卡片（不是骨架一闪而过）；
2. 用上面的 dev 账号登录 ⇒ 进入正常界面，顶栏显示真实用户名（不再是「林默」）；
3. 打开 DevTools Network，看任一 `/api/v1/*` 请求**带上了 `Authorization: Bearer …`**；
4. 点顶栏「退出登录」 ⇒ 回到登录卡片，且此时 sessionStorage 里的 `graphrag.auth.session` 已清空。

## 6. 遗留

- **F-P7N-1｜CSR 交互未被机械验证**（§5）：需要浏览器或给前端装测试框架。后者是 P7-D 裁决过的取舍，本批不翻。
- **F-P7N-2｜首账号仍是交付前提**：挂到 P7-H 之前，方案占位 (a)；变量是"客户要不要接外部身份源"。
- **F-P7N-3｜顶栏「个人资料 / 偏好设置」仍是占位且点击无反应**：本批只换了账号名与退出，
  这两个菜单项没有对应页面 —— 与当初 P7-D 里「已知 UI 缺口」同一类，登记不改。
- **F-P7N-4｜token 过期无 refresh**：后端没有 refresh 端点（`LoginResponse` 只有 `expires_at`）。
  过期后统一按"会话没了"处理 ⇒ 直接回登录态，不做续期。（proposal §5 第 2 条已预判。）
- **F-P7N-5｜角色信息没显示**：顶栏原本写着「管理员」，那是假的。真角色由后端 `user_roles` 判定，
  前端没有拿角色的端点 ⇒ **不猜、不显示**，而不是换个好看的常量。

## 7. CI 读数回填（**R-10：以 CI 为最终裁决**）

| 项 | 读数 |
|---|---|
| CI run | **38405674333**（commit `4c50b2d`） |
| 四个 job | 后端（ruff + pytest）✅ 3m2s ｜前端（lint + gen:api）✅ 37s ｜契约校验（前后端漂移门禁）✅ 34s ｜流水线汇总 ✅ 4s |
| CI 后端 pytest | **1311 passed / 7 skipped / 0 failed**（`Ruff 静态检查 All checks passed!`） |

核销：本批**没新增任何用例** ⇒ 期望与上批持平（1311）。实测正好 1311
⇒ 没有用例被本批的 `client.ts` 改动波及（尤其是 P7-D 那条 10 用例的一致性护栏，
本批删了一条重复 pattern，它的检查仍然通过）。
