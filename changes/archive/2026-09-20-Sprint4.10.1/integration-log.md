# Sprint 4 阶段十 · 10.1 联调记录：环境准备 + /health 探活

**批次**：Sprint 4.10.1
**执行时间**：2026-09-18（UTC+8）
**基线 tag**：v0.3.0
**分支**：feature/sprint-4
**执行人**：CodeBuddy（auto）
**前置批次**：无（10.0 系列已完成契约零漂移 + pytest 87 passed）

---

## 1. 验收三件套

| 项 | 目标 | 实测 | 结论 |
|---|---|---|---|
| HTTP 状态码 | 200 | **200** | ✅ |
| trace_id 贯通 | 响应头 `X-Trace-Id` 与 body `trace_id` 一致 | **均 `bcbc971f-1178-4614-92ee-9df2886b4a8a`** | ✅ |
| 业务字段 | `status="ok"`, `checks.database="up"` | **status=ok, database=up, version=1.0.0** | ✅ |

---

## 2. 真实环境依赖校验

### 2.1 Neo4j

| 检查项 | 命令 | 结果 |
|---|---|---|
| 容器存在 | `docker ps -a \| findstr "neo4j"` | 存在 `a4e3f48f0e3e neo4j:latest` |
| 容器状态 | `docker ps` | 发现是 `Exited (255) 6 minutes ago`——已停止，异常退出 |
| 启动容器 | `docker start neo4j` | 成功，`Up About a minute` |
| HTTP 探活 | `Invoke-WebRequest http://127.0.0.1:7474/` | 200，返回 neo4j HTTP API 元数据 |
| Bolt 端口 | `netstat -ano \| findstr ":7687"` | 监听（PID 11728 neo4j） |

### 2.2 Neo4j 数据

| 检查项 | 命令 | 结果 |
|---|---|---|
| 总节点数 | `MATCH (n) RETURN count(n)` | **24** |
| 标签分布 | `MATCH (n) RETURN DISTINCT labels(n), count(*)` | `["Entity"] × 23`, `["KgVersion"] × 1` |
| KgVersion 状态 | `MATCH (k:KgVersion) RETURN k.version, k.status` | `version="20260917T090000Z-phase09", status="active"` |

> 用户原描述期望 ≈ 23 节点——实测 23 Entity + 1 KgVersion = 24，符合阶段九 import 产物；KgVersion 状态 `active`，可被消费层检索。

### 2.3 DeepSeek Key

| 检查项 | 命令 | 结果 |
|---|---|---|
| 配置存在 | `uv run python -c "from app.core.config import get_settings; print(bool(s.deepseek_api_key))"` | `True`（key len=35，**未打印完整值**） |
| Key 有效性 | `Invoke-WebRequest https://api.deepseek.com/v1/models -Headers @{Authorization="Bearer sk-..."}` | **HTTP 200**（响应体长度 153 字节，含模型列表） |

### 2.4 后端配置自检

通过 `get_settings()` 读取：

```
deepseek_key_set=True
app_env=development
allow_dev_org_header=True
neo4j=bolt://localhost:7687
database=sqlite:///./dev.db
```

### 2.5 端口占用

| 端口 | 期望 | 实测 |
|---|---|---|
| 7687 (Neo4j Bolt) | LISTENING | ✅ |
| 7474 (Neo4j HTTP) | LISTENING | ✅ |
| 8000 (FastAPI) | 启动前空 → 启动后 LISTENING | ✅ |
| 3000 (Next.js) | 未启动 | 未占用 |

---

## 3. uvicorn 启动

### 3.1 命令

```powershell
Start-Process -FilePath "uv" -ArgumentList "run","uvicorn","app.main:app","--reload","--host","127.0.0.1","--port","8000" `
  -WorkingDirectory "d:/AIProject/GraphRAG-Agent/backend" `
  -RedirectStandardOutput "d:/AIProject/GraphRAG-Agent/changes/Sprint4.10.1/uvicorn.out.log" `
  -RedirectStandardError  "d:/AIProject/GraphRAG-Agent/changes/Sprint4.10.1/uvicorn.err.log" `
  -WindowStyle Hidden -PassThru
```

### 3.2 进程清单

| 进程 | PID | 角色 |
|---|---|---|
| `uv` | 22908 | wrapper（已退出，PID 已找到） |
| `uvicorn`（PID 10644） | main | uvicorn server（Windows 进程名） |
| WatchFiles reloader | 12416 | 监听 backend/ 变更 |
| Server process | 11992 | SpawnProcess-1，跑 lifespan |
| Listener PID | 12416 | 监听 127.0.0.1:8000 |

### 3.3 启动日志关键摘要（uvicorn.out.log）

```
INFO:     Will watch for changes in these directories: ['D:\\AIProject\\GraphRAG-Agent\\backend']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12416] using WatchFiles
INFO:     Started server process [11992]
INFO:     Waiting for application startup.
{"message": "task_recover_orphan_noop", "extra": {"reclaimed": 0}, ...}
{"message": "application_startup", "extra": {
  "app_env": "development",
  "app_version": "1.0.0",
  "db_driver": "sqlite",
  "dev_org_header_enabled": true,
  "task_recover_reclaimed": 0
}, ...}
INFO:     Application startup complete.
```

> loguru JSON 格式符合 CODEBAGASTY.md「日志与可观测性规则」；`db_driver` 字段只输出驱动名（不打印 DB URL 全值），符合「安全底线」。

---

## 4. /api/v1/health 探活

### 4.1 命令

```powershell
$resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -Method GET -TimeoutSec 5 -UseBasicParsing
```

### 4.2 响应（完整结构化）

```json
{
  "status": "ok",
  "version": "1.0.0",
  "checks": { "database": "up" },
  "time": "2026-09-18T04:00:27.975761Z",
  "trace_id": "bcbc971f-1178-4614-92ee-9df2886b4a8a"
}
```

### 4.3 关键字段

| 字段 | 值 |
|---|---|
| HTTP status | 200 |
| Header `X-Trace-Id` | `bcbc971f-1178-4614-92ee-9df2886b4a8a` |
| Body `trace_id` | `bcbc971f-1178-4614-92ee-9df2886b4a8a`（与 header 一致 ✅） |
| `status` | `ok` |
| `checks.database` | `up` |
| 端到端耗时 | **98.57 ms** |
| body `time` | `2026-09-18T04:00:27.975761Z`（UTC） |

### 4.4 验收

- ✅ HTTP 200 + 业务字段完整
- ✅ trace_id 响应头与 body 一致（TraceIdMiddleware 已贯通）
- ✅ 数据库连接 up（init_db + check_database 通过）
- ✅ 响应耗时 < 100ms（健康检查应在 100ms 内返回）

---

## 5. 本次未触碰的项目（合规确认）

| 项 | 状态 |
|---|---|
| `contracts/openapi.yaml` | **未修改** |
| `frontend/src/**` | **未修改** |
| `backend/app/**` | **未修改** |
| `backend/pyproject.toml` / `backend/uv.lock` | **未修改** |
| `frontend/.env.local` | **未创建**（按本批约束） |
| `frontend/.env.development` | **未修改** |
| `backend/.env.development` | **未修改** |
| `CODEBUDDY.md` / `frontend/CODEBUDDY.md` / `backend/CODEBUDDY.md` | **未修改** |

新增的 4 个文件均位于 `changes/Sprint4.10.1/`：
- `integration-log.md`（本文件）
- `uvicorn.out.log`（启动标准输出）
- `uvicorn.err.log`（启动错误流）

---

## 6. 接口对齐清单

无漂移——`/api/v1/health` 实测响应字段与 `contracts/openapi.yaml` 中 `HealthResponse` schema 完全一致：
- `status ∈ {ok, degraded}` ✅ 实测 `ok`
- `version: string` ✅ 实测 `"1.0.0"`
- `checks.database ∈ {up, down}` ✅ 实测 `"up"`
- `time: string (datetime)` ✅
- `trace_id: string (uuid)` ✅

---

## 7. 下一步

- **10.1.5**（待执行）：前端 `client.ts` 注入 dev 默认 `X-Org-Id`（**前置修复**，让 UI 端到端联调可走）
- **10.2**：POST /documents/upload + GET /documents/{id}/status
- **10.3**：GET /documents/{id}/graph（依赖 Neo4j 已就绪 ✅）
- **10.4**：POST /agent/query（依赖 DeepSeek Key 有效 ✅）

uvicorn 进程保留运行（PID 10644 + reloader 12416 + server 11992），方便 10.2 复用。