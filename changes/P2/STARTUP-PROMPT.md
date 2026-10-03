# P2-B 开工提示词（**无人值守 / 新对话专用**）

> **用法**：开一个全新对话，把下面《提示词正文》整段粘进去即可开工。
>
> **为什么需要这个文件**：新对话**没有上下文**，本项目又横跨 30+ 份文档与 25 条护栏，
> 靠模型临场摸索极易跑偏（例如把 P3 的 RLS 当成自己的活、或对 RLS 豁免表自行放行）。
> 本文件把「读什么 / 做什么 / 边界在哪 / 卡住怎么办」一次性钉死。
>
> 生成于 2026-10-03（P2-B 开工前收尾批次）。若后续规格变更，**必须回来更新本文件**。

---

## 提示词正文（整段复制）

你是在 `GraphRAG-Agent` 仓库里执行 **P2-B（DR-B9 RBAC 三粒度）** 批次。
这是**无人值守**批次：**没有对话上下文，没有人在线答疑**。所有需要的信息都在仓库里，请自行查证。

### 0. 先读这些（按顺序，不要跳）

1. `CODEBUDDY.md`（根目录）——项目总纪律，尤其**开工自检**与**红线**部分
2. `changes/P2/tasks.md` 的「⛳ 开工前置」与「P2-B」两节——本批唯一的任务清单与环境前置
3. `specs/m5-permission-audit.md` §4.2（`roles`）/ §4.3（`user_roles`）/ §3 验收 1（**行为判据**）
4. `docs/adr/ADR-0003-tenant-isolation-rls.md` §4.1——`roles` 的 RLS 豁免 + 2026-10-03 履行方式裁决
5. `changes/P2/proposal.md` §6 决策点——历史口径，**避免重复踩已否决的旧结论**

### 1. 环境（漏了这步 pytest 会全红，而且看起来像代码坏了）

`backend/tests/conftest.py` 已把测试库写死为 PostgreSQL 的固定库 `graphrag_test`
（**G-8** 转正后不再用 SQLite——SQLite 既无 RLS 也无 `SET LOCAL`，在它上面跑通的隔离什么都不证明）。

开工第一步必须先起 PG **并等它就绪**：

```bash
docker run -d --rm --name graphrag-pg \
  -e POSTGRES_USER=graphrag -e POSTGRES_PASSWORD=graphrag -e POSTGRES_DB=graphrag_test \
  -p 5432:5432 postgres:16-alpine
until docker exec graphrag-pg pg_isready -U graphrag -d graphrag_test; do sleep 1; done
```

（Windows / PowerShell 请换成等价命令。CI 不需要这段——`ci.yml` 自带 postgres service。）

再跑开工自检：

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

⚠️ **它恒退 0**（只报告、非门禁）⇒ **别把它的输出当成"通过"**，要自己读四档数字。

### 2. 本批要做的 5 项（见 tasks.md 的 P2-B 清单，逐条打勾）

1. `roles` 表（全局字典表，**RLS 显式豁免**）
2. `user_roles` 表（含 `doc_scope` / `scene_scope` JSONB，`org_id` 打头索引）
3. 路由层**强制校验入口**（依赖 / 中间件）——**没有它，权限只是库里的一列装饰**
4. 拒绝时写 `audit_log`（`action=permission.denied`）——§3 验收 1 的显式要求，**只返 403 不留痕 = 未完成**
5. 出口：**`test_g24_rbac_three_granularity_matrix` 转正**

### 3. 边界（自由度已钉死，不要自行发挥）

| 边界 | 规定 |
|---|---|
| **角色集合** | **只有** `admin / auditor / analyst / viewer` 四种，**不得新增** |
| **资源清单** | 只能取自 `contracts/openapi.yaml` 里**已存在**的端点，**不得凭空造资源类型** |
| **契约** | **必须零 diff**——`403 FORBIDDEN` 已在契约中 ⇒ 复用它，**不加端点、不加错误码** |
| **不碰 RLS** | RLS 策略归 **P3**；本批只做 `roles` 的豁免登记，`user_roles` 仅补 `org_id` 与索引 |
| **迁移** | 两张表**必须**带可幂等 Alembic 迁移（DR-E1），**禁手工改客户库** |
| **RLS 豁免怎么确认** | 按 2026-10-03 裁决（用户选 A）：**代码内显式声明 + 机械断言 + 事后 CR 抽检**，三条断言见 `specs/m5-permission-audit.md` §4.2 |
| **矩阵内容** | G-24 **只断言**「矩阵存在 + 强制校验入口存在」，**不断言**具体权限值 ⇒ 具体赋权属实现决策，**但必须在 `changes/P2/integration-log.md` 登记并写明理由** |

### 4. 出口判据（三条全绿才算完成）

- **pytest**：全绿，且数量**不少于开工前基线**（开工前实测 **818 passed / 3 skipped / 7 xfailed**）
- **ruff**：`ruff check .` 全过
- **G-24 转正**：先把 `test_g24_rbac_three_granularity_matrix` 跑到**真通过**，再摘 xfail。
  ⚠️ **只删 xfail 标记不算转正**（proposal 行动指引第 2 条——这是本仓反复强调的一条）

### 5. 红线

- **不许编造**：拿不到的数据写 `UNKNOWN` / `BLOCKED`，**不许填看起来合理的值**
- **不许拔高结论**：G-24 没转正 ⇒ 任何文档都**不得**写「RBAC 已落地」
- **不许篡改历史**：ADR 原文、`tasks.md` 的历史记述、提案里已否决的选项，**一律追加登记，不删不改**（守 **R5**）
- **不许扩大范围**：不碰 P3 的 RLS、不碰 P2-C 的 SSO、不动 `contracts/`

### 6. 卡住怎么办（重要）

**无人值守 ≠ 可以猜**。遇到**真正的歧义或阻塞**（规格没写 / 两条要求冲突 / 测试结果与预期不符且查不出原因）：

1. **停下来**，不要猜着做
2. 把「**问题 + 已查证据 + 可选方案 + 我建议哪一个**」写进 `changes/P2/integration-log.md`，标题标 **`⛔ 阻塞待裁`**
3. 已完成且**确定无误**的部分照常 commit 并 push（勿让一处阻塞卡住整个批次的产出）

### 7. 收尾

- 把「实际做的 vs 计划的差异」「遇到的问题」「各项数字」登记进 `changes/P2/integration-log.md`
- commit 并 push 到 `main`（push 可能超时，**重试一次**即可通）
- 汇报时分**三块**：✅ 已完成（附数字）/ ⚠️ 未完成与原因 / ⛔ 待你裁决——
  **不要把未完成项混进"已完成"里讲**
