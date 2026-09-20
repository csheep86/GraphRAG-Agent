# Sprint 4 阶段十 · 10.1.5 联调记录：前端 dev-only `X-Org-Id` 注入补丁

**批次**：Sprint 4.10.1.5
**执行时间**：2026-09-18（UTC+8）
**基线 tag**：v0.3.0
**分支**：feature/sprint-4
**执行人**：CodeBuddy（auto）
**前置批次**：Sprint 4.10.1（uvicorn PID 10644 / reloader 12416 / server 11992 持续运行）

---

## 1. 背景与目标

### 1.1 问题
前端 `frontend/src/api/client.ts` 的 `request()` 仅发 `Accept` + `Content-Type`，**不发任何认证头**。
后端 `backend/app/core/auth.py:84` 在 `X-Org-Id` 与 `X-Actor-Id` 都为 None 时直接 `return None`，触发 `deps.get_current_identity` 抛 `UNAUTHORIZED`。
联调阶段 UI 切到 `USE_MOCK=false` 后所有真实接口会被 401 拒绝，无法做端到端验证。

### 1.2 目标
在不引入正式鉴权的前提下，让前端在 `NEXT_PUBLIC_APP_ENV === "development"` 时自动注入 `X-Org-Id`：
- 默认值与 `backend/.env.development` 的 `DEFAULT_ORG_ID` 同步
- prod build 不注入（防 fallback 误触）
- FormData 与 JSON 走同分支（X-Org-Id 与 multipart boundary 无关）
- 调用方仍可通过 `init.headers` 覆盖默认头（spread 在最后）

---

## 2. 修改清单

### 2.1 `frontend/src/api/client.ts`

**改动 1**（行 14-19）：新增 dev-only 默认 org_id 常量
```typescript
// dev-only 默认 org_id：与 backend/.env.development DEFAULT_ORG_ID 同步。
// 仅当 NEXT_PUBLIC_APP_ENV 显式 === "development" 时注入 X-Org-Id；
// 读 raw env 而非 APP_ENV 常量，避免 prod build 忘设 env 时被 fallback 误注入。
const DEV_DEFAULT_ORG_ID =
  process.env.NEXT_PUBLIC_DEV_DEFAULT_ORG_ID ||
  "00000000-0000-4000-8000-000000000001";
```

**改动 2**（行 57-64）：在 `request()` 的 headers 中注入 `X-Org-Id`
```typescript
headers: {
  Accept: "application/json",
  ...(process.env.NEXT_PUBLIC_APP_ENV === "development"
    ? { "X-Org-Id": DEV_DEFAULT_ORG_ID }
    : {}),
  ...(isFormData ? {} : { "Content-Type": "application/json" }),
  ...init.headers,
},
```

**净变化**：+7 / -0（Hunk 1-A）+3 / -0（Hunk 1-B）= +10 / -0

### 2.2 `frontend/.env.development`

**新增**（行 9-11，紧跟 `NEXT_PUBLIC_API_BASE_URL` 之后）：
```bash
# dev-only 默认 org_id（联调 10.1.5）：与 backend/.env.development 的
# DEFAULT_ORG_ID 保持一致；改后者必须同步改这里，否则 dev 认证头与后端默认租户错配。
NEXT_PUBLIC_DEV_DEFAULT_ORG_ID=00000000-0000-4000-8000-000000000001
```

**净变化**：+4 / -0（2 行注释 + 1 行赋值 + 1 行空行）

### 2.3 新建文件 `frontend/.env.local`（gitignored，不提交）

```
NEXT_PUBLIC_USE_MOCK=false
```

> **根 `.gitignore` 已含 `**/.env.local`，本文件不会被提交。**
> 验证：`findstr /i "env.local" .gitignore` 返回 `**/.env.local` 与 `**/.env.local.*`。

---

## 3. 静态验证

### 3.1 命令
```powershell
cd d:/AIProject/GraphRAG-Agent/frontend
npm.cmd exec tsc -- --noEmit
npm.cmd exec eslint src -- --max-warnings=0
npm.cmd run build
```

### 3.2 结果

| 项 | 结果 |
|---|---|
| `tsc --noEmit` | ✅ exit 0 / 0 error |
| `eslint src --max-warnings=0` | ✅ exit 0 / 0 error / 0 warning |
| `next build` | ✅ `Compiled successfully in 6.9s` / TypeScript `Finished in 2.5s` / 9 静态页生成（/、/_not-found、/audit、/documents、/graph、/qa、/settings） |

> build 报告 `- Environments: .env.production`，证明 prod 构建自动加载生产 env，三元表达式 `process.env.NEXT_PUBLIC_APP_ENV === "development"` 在 prod 下为 `false` → **生产包不带 X-Org-Id**（裁决 3 落实）。

### 3.3 后端测试
```powershell
cd d:/AIProject/GraphRAG-Agent/backend
uv run pytest -q
```

**结果**：`87 passed, 1 warning in 0.78s` ✅（与 10.1 baseline 一致，本次未改后端）

---

## 4. 客户端 headers 注入逻辑模拟

### 4.1 脚本（一次性，临时，跑完即删）

创建 `frontend/verify-headers.mjs`（不在仓库保留），复刻 `client.ts` 第 57-64 行的 headers 构造逻辑，遍历 4 个场景并跑 1 次 live probe。

### 4.2 结果

```
Case1 dev+env(JSON)    -> X-Org-Id: 00000000-0000-4000-8000-000000000001
  headers: {"Accept":"application/json","X-Org-Id":"...01","Content-Type":"application/json"}
Case1 dev+env(FormData) -> X-Org-Id: 00000000-0000-4000-8000-000000000001
  headers: {"Accept":"application/json","X-Org-Id":"...01"}
Case2 dev+fallback(env cleared) -> X-Org-Id: 00000000-0000-4000-8000-000000000001
Case3 prod(JSON)       -> X-Org-Id: (absent)
  headers: {"Accept":"application/json","Content-Type":"application/json"}
Case3 prod(FormData)   -> X-Org-Id: (absent)
  headers: {"Accept":"application/json"}
Case4 env-undef(JSON)   -> X-Org-Id: (absent)
  headers: {"Accept":"application/json","Content-Type":"application/json"}
```

| 场景 | 期望 | 实测 |
|---|---|---|
| Case 1 dev + JSON | 注入（env 优先值） | ✅ `00000000-0000-4000-8000-000000000001` |
| Case 1 dev + FormData | 注入（不豁免） | ✅ 同上 |
| Case 2 dev + env 未设 | 注入（fallback 硬编码） | ✅ 同上 |
| Case 3 prod（JSON/FormData） | 不注入 | ✅ absent |
| Case 4 env 完全未设 | 不注入（保守默认） | ✅ absent |

### 4.3 Live probe

```
$status = 200
$trace_id = 43f8d196-0e9a-45d9-87d3-06488ae466a7
$body = {"status":"ok","version":"1.0.0","checks":{"database":"up"},"time":"2026-09-18T04:10:05.587046Z","trace_id":"43f8d196-0e9a-45d9-87d3-06488ae466a7"}
```

| 项 | 实测 |
|---|---|
| HTTP status | **200** |
| 响应头 `X-Trace-Id` | `43f8d196-0e9a-45d9-87d3-06488ae466a7` |
| Body `trace_id` | `43f8d196-0e9a-45d9-87d3-06488ae466a7`（一致 ✅） |
| 业务字段 | `status=ok` / `database=up` / `version=1.0.0` |
| Sent headers | `{"Accept":"application/json","X-Org-Id":"...01","Content-Type":"application/json"}` |

> 脚本已删除（`Remove-Item frontend/verify-headers.mjs -Force`），仓库零临时文件。

---

## 5. 前端 dev server 启动

### 5.1 命令
```powershell
cd d:/AIProject/GraphRAG-Agent/frontend
Start-Process -FilePath "npm.cmd" -ArgumentList "run","dev" `
  -NoNewWindow `
  -WorkingDirectory "d:/AIProject/GraphRAG-Agent/frontend" `
  -RedirectStandardOutput "d:/AIProject/GraphRAG-Agent/frontend/dev.out.log" `
  -RedirectStandardError  "d:/AIProject/GraphRAG-Agent/frontend/dev.err.log" `
  -PassThru
```

> PowerShell 不允许 `RedirectStandardOutput` 与 `RedirectStandardError` 指向同一文件，故拆分为 `dev.out.log` / `dev.err.log` 两个文件。

### 5.2 启动结果（dev.out.log）

```
> frontend@0.1.0 dev
> next dev

Next.js 16.3.5 (Turbopack)
- Local:         http://localhost:3000
- Network:       http://192.168.0.21:3000
- Environments: .env.local, .env.development
Ready in 1547ms
Running next.config.ts took 51ms
```

### 5.3 进程清单

| 进程 | PID | 角色 |
|---|---|---|
| `next dev` | 3560 | npm.cmd wrapper（Start-Process 启动） |
| Next.js dev server | （待 PID 抓取） | 监听 localhost:3000 |

> dev server PID 3560 持续运行，方便 10.2 ~ 10.4 复用；日志落 `frontend/dev.{out,err}.log`。

---

## 6. 待执行：浏览器端到端验证（CLI 不可达，转交用户）

作为 CLI agent，无法直接打开浏览器执行步骤 3-6，以下转交：

### 6.1 步骤

| 步骤 | 操作 | 验收 |
|---|---|---|
| 1 | 浏览器打开 `http://localhost:3000` | 页面正常加载 |
| 2 | 打开 DevTools → Network 面板 | 准备观察 |
| 3 | 进入 `/documents`（p02 文档列表页）或触发任一真实接口 | 请求被发出 |
| 4 | 选中该请求 → 查看 Request Headers | 应含 `X-Org-Id: 00000000-0000-4000-8000-000000000001` |
| 5 | 查看 Response Headers | 应含 `X-Trace-Id: <uuid>` |
| 6 | 截图保存到 `changes/Sprint4.10.1.5/network-shot.png`（或类似路径） | 证据留存 |

### 6.2 预期

- `Request Headers` 含：
  - `Accept: application/json`
  - `X-Org-Id: 00000000-0000-4000-8000-000000000001`（本次注入）
  - `Content-Type: application/json`（JSON 请求时）或不含（FormData 时浏览器自动加）
- `Response Headers` 含：
  - `X-Trace-Id: <uuid>`
- 后端返回 200 而非 401（与之前不带 X-Org-Id 的对比）

### 6.3 失败回退

| 现象 | 排查 |
|---|---|
| 请求头无 X-Org-Id | 检查 `frontend/.env.local` 是否生效（`NEXT_PUBLIC_USE_MOCK=false`）；重新 `npm.cmd run dev` |
| 仍是 401 | 检查后端 `backend/.env.development` 的 `ALLOW_DEV_ORG_HEADER=true` 与 `DEFAULT_ORG_ID` UUID 是否一致 |
| CORS 报错 | 浏览器必须用 `localhost:3000`，不能用 `127.0.0.1:3000`（CORS allow_origins 已含 `http://localhost:3000`） |

---

## 7. 本次未触碰的项目（合规确认）

| 项 | 状态 |
|---|---|
| `contracts/openapi.yaml` | **未修改** |
| `frontend/src/types/api.d.ts` | **未修改**（不跑 gen:api） |
| `frontend/src/**`（除 client.ts） | **未修改** |
| `frontend/CODEBUDDY.md` | **未修改** |
| `frontend/.env.production` | **未修改** |
| `frontend/.env.local.example` | **未修改** |
| `frontend/package.json` / `tsconfig.json` / `eslint.config.mjs` | **未修改** |
| `backend/**`（含 `app/**`、`tests/**`、`pyproject.toml`、`uv.lock`） | **未修改** |
| `backend/.env.development` | **未修改**（DEFAULT_ORG_ID 未变；前后端 UUID 同步保持） |
| `backend/CODEBUDDY.md` | **未修改** |
| 根 `CODEBUDDY.md` | **未修改** |

新增的临时文件（已清理）：
- `frontend/verify-headers.mjs`（跑完 `Remove-Item` 删）

新增的运行时文件（gitignored，不提交）：
- `frontend/.env.local`（含 `NEXT_PUBLIC_USE_MOCK=false`）
- `frontend/dev.out.log` / `frontend/dev.err.log`（dev server 输出）

---

## 8. 接口对齐清单

无漂移——本次只新增 dev-only 默认头注入：
- 契约 `contracts/openapi.yaml` 中 `X-Org-Id` 已在 4 个端点的 parameters.headers 中声明为可选 header（`"X-Org-Id"?: string | null`），本次只是由"前端不发"变为"dev 模式下前端默认发"
- HTTP 状态码与契约 100% 一致
- 请求/响应 schema 无变化
- 前端发起的请求体无变化

> 按 CODEBUDDY.md「接口对齐清单触发条件」逐条核对：✅ 无任一项触发。

---

## 9. 下一步

- **10.2**：POST /documents/upload + GET /documents/{id}/status（用 Invoke-RestMethod 跑，浏览器端到端由用户在 6.1 步执行）
- **10.3**：GET /documents/{id}/graph（依赖 Neo4j 已 active ✅）
- **10.4**：POST /agent/query（依赖 DeepSeek Key 有效 ✅）

进程保留：
- uvicorn（10.1 启动）：PID 10644 / reloader 12416 / server 11992
- `next dev`（本批启动）：PID 3560，监听 localhost:3000