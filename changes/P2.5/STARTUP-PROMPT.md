# P2.5 开工提示词（**无人值守 / 新对话专用**）

> **用法**：开一个全新对话，把下面《提示词正文》整段粘进去即可开工。
>
> **为什么需要这个文件**：新对话**没有上下文**，本项目横跨 30+ 份文档与 25 条护栏，
> 靠临场摸索极易跑偏（例如照需求基线 §300 把变体命名成 `default` ⇒ G-14 结构性假红；
> 或换个"看起来更合理"的插件 ⇒ 撞上 ADR-0004 的登记外实现红线）。
> 本文件把「读什么 / 做什么 / 边界在哪 / 卡住怎么办」一次性钉死。
>
> 生成于 2026-10-04（P2.5 开工前）。若后续规格变更，**必须回来更新本文件**。

---

## 提示词正文（整段复制）

你是在 `GraphRAG-Agent` 仓库里执行 **P2.5（第 1 个真插件 + 变体骨架：DR-A1 / A2 / A3 + G-14）** 批次。
这是**无人值守**批次：**没有对话上下文，没有人在线答疑**。所有需要的信息都在仓库里，请自行查证。

### 0. 先读这些（按顺序，不要跳）

1. `CODEBUDDY.md`（根目录）——项目总纪律，尤其**开工自检**与**红线**部分
2. **`changes/P2.5/tasks.md`** ——本批**唯一**的任务清单（含三条裁决记录与起跑基线）
3. **`changes/P2.5/proposal.md`** ——候选淘汰过程与两个坑的查证证据（避免重复踩）
4. `docs/adr/ADR-0007-plugin-delivery.md` §3.1 / §3.2 / §3.5 / §3.6——插件与变体的权威规格
5. `docs/adr/0004-integration-seams.md` §2.1 第 6 行 + §3 第 4 条——接缝登记集合与越界判据
6. `backend/tests/test_guardrails_delivery.py`——G-12 / G-14 / G-22 的**实际判据**（读代码，别只读文档）
7. `changes/P1/tasks.md` 第 173-191 行——E / F 组的**历史记述**（只读不改，守 R5）

### 1. 环境（漏了这步 pytest 会全红，而且看起来像代码坏了）

`backend/tests/conftest.py` 已把测试库写死为 PostgreSQL 的固定库 `graphrag_test`。
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

**起跑基线（实测 2026-10-04）**：`pytest` = **850 passed / 3 skipped / 6 xfailed**；
6 条 xfailed = G-10 / G-12 / G-14 / G-22 / G-23 ×2。
`plugins/`、`deploy/variants/`、`contracts/plugins/` **均不存在**。

### 2. 本批要做的 4 项（见 tasks.md，逐条打勾）

| # | 项 | 出口 |
|---|---|---|
| **E1 / DR-A2** | `plugins/json-csv-export/plugin.yaml` | `test_g22_plugin_source_exists` 转正 |
| **E2 / DR-A1** | `deploy/variants/baseline.yaml` | `test_g14_customer_token_source_exists` 转正 |
| **E3 / DR-A3** | Dockerfile 构建期 `COPY plugins`（改 compose build.context 为仓库根） | `docker compose build backend` 成功 |
| **F / G-14** | 随首个插件并入，黑名单非空 | 同 E2 |

### 3. 三条裁决已定（**不要重开讨论**）

| # | 裁决 | 为什么（已查证，别改） |
|---|---|---|
| **1** | 第 1 个真插件 = **`json-csv-export`**（接缝 6，`JsonCsvExportSink`） | 五个候选里**唯一**「已在登记集合 + 已有真实实现 + 天然 A 类」。`ldap-auth` / `oa-webhook` 被 ADR-0004 §3 第 4 条**点名**为登记外实现（越界）；`IngestionSource` 为 0 实现 ⇒ 必是空壳，撞 GA 硬门槛 |
| **2** | 变体命名为 **`baseline`** | `_customer_tokens()` 用**子串**匹配契约文本。实测契约词频：`default` **10 次**、`demo` **3 次**、`baseline` **0 次** ⇒ 照需求基线 §300 的字面命名（`demo` / `default`）会**结构性假红**。`internal-demo` 含 `demo`，同样假红 |
| **3** | E3 改 **compose `build.context` 为仓库根** | `PLUGIN_ROOT` = 仓库根 `plugins/`，而现 context 为 `../backend` ⇒ `COPY plugins` 无源，构建必失败 |

### 4. 三个已知坑（**开工前就已知，别自己踩一遍**）

| # | 坑 | 处置 |
|---|---|---|
| **1** | `backend/.dockerignore` 只在 backend 下，**改 context 到仓库根后失效**（Docker 只读 context 根的 `.dockerignore`） | **先建仓库根 `.dockerignore`**（必须含 `.env` / `.env.*`——`deployment-spec.md` §3 密钥禁入镜像），**再做 E3**。没做完就不要动 context |
| **2** | G-22 只验 5 个字段非空 ⇒ **写一句假 `entry_point` 也能转绿**（标准空壳假绿，撞 GA 硬门槛） | 加一条断言：`entry_point` 的模块可导入且类存在 |
| **3** | 改 context 后 `backend/Dockerfile` 的 COPY 路径全部要加 `backend/` 前缀 | 逐个改，漏一个就构建失败 |

### 5. 边界（自由度已钉死，不要自行发挥）

| 边界 | 规定 |
|---|---|
| **契约** | **必须零 diff**——A 类插件不碰契约，不加端点、不加错误码 |
| **不搬实现** | `entry_point` 指向**既有** `app/services/export/json_csv.py:JsonCsvExportSink`；实现留在 `app/` ⇒ `check_seams.py` 判据 1 / 4 不受影响 |
| **不新增接缝实现** | 不做 `LdapAuthProvider` / `OaEventSink` / `IngestionSource`（越界或空壳） |
| **变体只产 1 个** | G-12 启用条件写死 `≥ 2`；**不凑第二个**（需求基线 §300 明令禁止捏造客户 / 放宽成 ≥1） |
| **不做 B 类** | 无 `openapi_fragment`、无前端、不建 `contracts/plugins/` |
| **不做运行期装配** | ADR-0007 §3.1 已裁决：构建期烘焙 |
| **不动 ADR 原文** | ADR-0007 / ADR-0004 只追加登记，不删不改（守 **R5**） |

### 6. 出口判据（四条全绿才算完成）

- **pytest**：全绿，passed **不少于 850**，**xfailed 6 → 4**
- **ruff**：`ruff check .` 全过
- **契约**：`export_openapi.py --check` 零漂移
- **两条 xfail 转正**：**先**真通过，**再**摘标记。⚠️ **只删 xfail 标记不算转正**
  （proposal 行动指引第 2 条——本仓反复强调的一条）
- ⚠️ **G-12 仍挂起属预期**（1 < 2 变体），不要为它凑第二个变体

### 7. 红线

- **不许编造**：拿不到的数据写 `UNKNOWN` / `BLOCKED`，**不许填看起来合理的值**
- **不许拔高结论**：两条守卫没转正 ⇒ 任何文档都**不得**写「插件交付已落地」
- **不许篡改历史**：ADR 原文、`changes/P1/tasks.md` 的历史记述、提案里已淘汰的候选，
  **一律追加登记，不删不改**（守 **R5**）
- **不许扩大范围**：不碰 RLS（P3）、SSO（P2-C）、License（P4）、不动 `contracts/`

### 8. 卡住怎么办（重要）

**无人值守 ≠ 可以猜**。遇到**真正的歧义或阻塞**（规格没写 / 两条要求冲突 / 测试结果与预期不符且查不出原因）：

1. **停下来**，不要猜着做
2. 把「**问题 + 已查证据 + 可选方案 + 我建议哪一个**」写进
   `changes/P2.5/integration-log.md`（本批新建），标题标 **`⛔ 阻塞待裁`**
3. 已完成且**确定无误**的部分照常 commit 并 push（勿让一处阻塞卡住整个批次的产出）

**已知可能触发阻塞的点**：E3 的 `docker compose build backend` 依赖拉
`python:3.11-slim` 与 `uv` 镜像，本机可能因网络失败/超时 ⇒ 登记 `BLOCKED` 并继续其余项。

### 9. 收尾

- 把「实际做的 vs 计划的差异」「遇到的问题」「各项数字」登记进 `changes/P2.5/integration-log.md`
- commit 并 push 到 `main`（push 可能超时，**重试一次**即可通）
- 汇报时分**三块**：✅ 已完成（附数字）/ ⚠️ 未完成与原因 / ⛔ 待你裁决——
  **不要把未完成项混进"已完成"里讲**
