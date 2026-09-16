# ADR-0001 · 异步任务后端选型：FastAPI `BackgroundTasks` + `TaskManager` 抽象层

| 项 | 内容 |
|---|---|
| **ADR 编号** | ADR-0001 |
| **对应 TBD** | **TBD-1**（异步任务后端选型） |
| **状态** | **Accepted（已接受）** |
| **决策日期** | 2026-09-16 |
| **决策者** | 架构师 |
| **关联模块** | M1（主）、M4（复用）、M5（审计） |
| **关联规格** | [`specs/m1-async-ingest.md`](../../specs/m1-async-ingest.md) §3 / §4.1 / §5.5、[`specs/m4-affiliation-detection.md`](../../specs/m4-affiliation-detection.md) §3 验收 7 / §4.4 |
| **关联硬约束** | **H1**（状态机 `pending → processing → completed / failed`）、**H8**（tenacity 指数退避 ≤ 3 次） |
| **上游依据** | `CODEBUDDY.md`「异步任务规范」 |

---

## 1. 背景（Context）

M1 要求「上传接口立即返回 `task_id`，后端异步执行解析」（M1 §1.1 功能点 2），M4 复用同一异步形态（M4 §3 验收 7）。因此必须回答「**由谁执行异步任务**」。

候选方案及其实质差异：

| 候选 | 任务持久化 | 重试语义 | 新增依赖 | 运维成本 |
|---|---|---|---|---|
| FastAPI `BackgroundTasks` | ❌ 进程内 | 进程内（tenacity） | **零** | 零 |
| Arq | ✅（Redis） | 队列级 | Redis | 中 |
| Celery | ✅（broker） | 队列级 | Broker + Worker | 高 |

**关键约束**：`CODEBUDDY.md` 要求 **MVP 阶段零新增外部依赖**（不引入 Redis / Broker），但同时 **H1 要求状态机必须真实可观测**。

**核心矛盾**：`BackgroundTasks` 的执行队列**存在于进程内存**，进程重启即丢失——若不处理，`documents.status` 会永久卡在 `processing`，形成「**僵尸任务**」，**直接击穿 H1 与 M1 §3 验收 5**。

---

## 2. 决策（Decision）

**采用 FastAPI `BackgroundTasks`，并叠加一个独立的 `TaskManager` 抽象层；状态持久化于 PostgreSQL；启动时执行「孤儿任务回收」。**

三条不可妥协的要求：

1. **启动回收**：FastAPI 启动（`lifespan` startup）时扫描 **PostgreSQL**，将遗留的 `pending` / `processing` 任务标记为 `failed`。
2. **抽象隔离**：`TaskManager` 以接口形式定义，业务代码只依赖接口，确保未来可无缝替换为 Arq / Celery。
3. **状态持久化**：任务状态**只**以 PostgreSQL 为准（`documents.status` / `affiliation_tasks.status`），**严禁**保存于进程内存字典。

> **为什么扫描源选「数据库」而非「本地 JSON」**：要求 3 已规定状态必须持久化于 DB；若状态在 DB、而恢复清单在本地 JSON，就会出现**双真值源**，二者不一致时无法判定谁对。**单一真值源 = PostgreSQL**，故回收扫描也必须读 DB。

---

## 3. 实现要求（Mandatory）

### 3.1 `TaskManager` 接口

```python
class TaskSpec(BaseModel):
    task_type: Literal["document.parse", "affiliation.detect"]
    payload: dict
    trace_id: str

class TaskManager(Protocol):
    def submit(self, spec: TaskSpec) -> str: ...           # 返回 task_id（UUIDv4）
    def get_status(self, task_id: str) -> TaskStatus: ...   # 读 PostgreSQL，不读内存
    def recover(self) -> RecoveryReport: ...                # 启动时调用，回收孤儿任务
```

- `submit()` 只做两件事：**（a）将 `status = pending` 落入 PostgreSQL；（b）向 `BackgroundTasks` 注册执行体**。
- `TaskManager` **自身不持有状态**，状态读写统一走 repository。

### 3.2 启动回收（解决「僵尸任务」）

在 `lifespan` startup 阶段调用 `TaskManager.recover()`，执行：

```sql
-- documents 与 affiliation_tasks 各执行一次
UPDATE documents
SET status        = 'failed',
    error_code    = 'TASK_INTERRUPTED',
    error_detail  = 'process restarted while task was in-flight',
    updated_at    = now()
WHERE status IN ('pending', 'processing');
```

- 回收事件**必须**写 M5 审计（`action = task.recover.orphan`，含 `trace_id`），否则「任务为何失败」无从追溯。
- **新增错误码 `TASK_INTERRUPTED`**，需登记进统一错误码表，并补入 `contracts/openapi.yaml` 的错误码枚举（见 §8）。

### 3.3 执行与并发

- 执行体通过 `anyio.to_thread.run_sync` / `asyncio` 投递，**禁止在事件循环中执行同步阻塞的解析调用**（MinerU / LangExtract 为 IO + CPU 密集）。
- 以 `asyncio.Semaphore`（可配置，默认 `N = 2`）限流，防止解析任务饿死 API 事件循环。

### 3.4 重试（对齐 H8）

- tenacity 部署在 `TaskManager` 执行体内部（初始 1s、倍数 2、上限 3 次）。
- **每次重试必须将 `retry_count` 写回 PostgreSQL**，使重试进度可观测、且重启后可判定。

### 3.5 未来替换路径

替换为 Arq / Celery 时，**只允许新增一个 `TaskManager` 实现**，业务代码零改动；`recover()` 语义由目标队列的持久化机制承担。

---

## 4. 状态机

```
pending ──submit 执行体启动──▶ processing ──成功──▶ completed
   │                              │
   │                              └──失败（tenacity ≤ 3）──▶ failed
   └──进程重启（recover）─────────┴──进程重启（recover）──▶ failed (TASK_INTERRUPTED)
```

> 状态取值**严格**限定为 `pending / processing / completed / failed`（H1）。**新增任何状态都必须先更新本 ADR 与规格。**

---

## 5. 备选方案与取舍

| 方案 | 拒绝理由 |
|---|---|
| **Arq** | 需引入 Redis，违反 MVP「零新增依赖」；Redis 亦为私有化部署增加组件。**保留为未来升级目标**。 |
| **Celery** | 需 Broker + 独立 Worker，部署拓扑复杂、运维成本高，对 MVP 的 5 个模块而言**过重**。 |
| **纯 `BackgroundTasks`（无抽象层）** | 状态易被写成内存字典（违反要求 3），且未来替换需改动所有业务调用点。 |
| **同步解析（不做异步）** | 违反 M1 §3 验收 1（P95 ≤ 500ms 立即返回）。 |

---

## 6. 后果（Consequences）

### 正面
- ✅ **零新增依赖**：无需 Redis / Broker，私有化部署组件最少。
- ✅ **消除僵尸任务**：重启后所有在途任务被显式标记 `failed`，`processing` 不再「卡死」。
- ✅ **可替换**：`TaskManager` 接口隔离了未来迁移成本。
- ✅ **可观测**：`retry_count` / `error_code` / 回收审计全部落库。

### 负面（已知并接受）
- ⚠️ **无真正队列**：任务在 API 进程内执行，**无法水平扩展**（多实例下任务无法跨进程分发）。
- ⚠️ **无 at-least-once 语义**：进程崩溃即丢任务；本 ADR 以「标记 `failed` + 支持重投」替代「不丢」。
- ⚠️ **需要并发限流**：否则解析任务会抢占 API 事件循环（§3.3 已缓解）。

---

## 7. 重新评估的触发条件（Exit Criteria）

出现以下任一情况，**必须**新开 ADR 并切换到 Arq（首选）或 Celery：

1. 需要 **多实例 / 水平扩展** 部署；
2. 出现 **单任务耗时 > 5 分钟** 的任务类型，或长任务占比显著上升；
3. 需要 **任务优先级 / 延迟调度 / 定时任务**；
4. 需要 **严格的 at-least-once / at-most-once 投递语义**。

> **触发即判定**：本 ADR 的「单实例 + 进程内」前提不再成立，**继续沿用即为架构债**。

---

## 8. 对既有规格 / 契约的影响（**需同步，勿自动补全**）

| # | 文件 | 需变更点 |
|---|---|---|
| 1 | `specs/m1-async-ingest.md` | §3 验收 4 补充 `TASK_INTERRUPTED` 错误码；§4.1 明确 `status` 由 `TaskManager.recover()` 在启动时批量置 `failed` |
| 2 | `specs/m4-affiliation-detection.md` | §4.4 `affiliation_tasks` 缺 `retry_count` / `error_code` / `error_detail` 字段，需补齐以支撑 H8 |
| 3 | `contracts/openapi.yaml`（实现阶段） | 错误码枚举补 `TASK_INTERRUPTED` |

> 按 `CODEBUDDY.md`「功能预留原则」，**以上变更须经人工确认后执行，不得由 AI 自动补全规格或契约**。

---

## 9. 参考
- `specs/m1-async-ingest.md` §1.1 / §3 / §4.1 / §5.5
- `specs/m4-affiliation-detection.md` §3 验收 7 / §4.4
- `docs/03-prd.md` §4（H1 / H8）、§8（TBD-1）
- `CODEBUDDY.md`「异步任务规范」「错误响应规范」

---

> **ADR-0001 结束。** 状态 **Accepted**，落地前须完成 §8 的规格 / 契约同步。
