# P3-B 任务清单 —— 图谱侧（Neo4j）跨 org 隔离真验 + T1 补齐 + G-9 转正

> 边界与裁决见同目录 `proposal.md`（**开工前先读它的 Non-goals**）。
> 出口判据见 `proposal.md` §2；本批起跑：`pytest` **879 passed / 3 skipped / 3 xfailed**。

---

## B1 —— CI 起 `neo4j` service（与 G-25 共用的工程项）

- [x] **B1-1** `.github/workflows/ci.yml` 的 backend job 加 `neo4j` service：
  - image tag **与 `deploy/docker-compose.yml` 的 neo4j 一致**（现 `neo4j:5.26-community`）⇒ 漂移由守卫判红；
  - `NEO4J_AUTH` 用**固定**口令（CI 一次性容器，非密钥）；
  - `options` 带 `--health-cmd "cypher-shell … 'RETURN 1'"` + `start-period`（Neo4j 冷启动慢，没有 health check 会随机红）；
  - 端口映射 `7687:7687`。
- [x] **B1-2** job 级 env 加**真连接开关**（**不**覆盖既有 `NEO4J_URI`——全局改成可达会让上千条「确定性降级」用例漂移）：
  - `GRAPH_REAL_NEO4J_URI` / `GRAPH_REAL_NEO4J_USER` / `GRAPH_REAL_NEO4J_PASSWORD`
- [x] **B1-3** 测试侧真连接 fixture：URI / 口令来自上述 env；**CI 上不可达 ⇒ `pytest.fail`**（不是 skip）；本地未设 env ⇒ skip
- [x] **B1-4** **静态守卫**（必须能红）：断言 `ci.yml` 的 backend job
      ① 声明了 `neo4j` service；② 设了 `GRAPH_REAL_NEO4J_URI`；③ neo4j tag == `deploy/docker-compose.yml` 的 tag
      ⇒ 任一日后被删，图谱用例会在 CI 上**静默不跑**（恒绿失效，R-9）
- [x] **B1-5** `ci.yml` 末尾「本地复现」摘要同步：补「起 Neo4j + 真图用例怎么跑」

---

## B2 —— 图谱侧**真实**跨 org 用例（新文件 `backend/tests/test_guardrails_graph.py`）

- [x] **B2-1** 模块 docstring **首行**写 `G-9 / DR-B11：…`（`check_startup_readiness.py` 靠它认护栏 ⇒ 本批结束后报告里要出现 G-9）
- [x] **B2-2** 真图 fixture：写入同一 `kg_version` 内的 **A / B 两个 org** 的 Entity 节点，用例结束 **DETACH DELETE** 清理（唯一 version ⇒ 并发 / 重跑不互相污染）
  - 实测：版本号取 `g9-<uuid4().hex>`（随机）⇒ 重跑 / 并发不互相污染；`finally` 里 `MATCH (n {kg_version:$version}) DETACH DELETE n`
- [x] **B2-3** `test_g9_1_…`：同版本混入 B 节点 ⇒ `validate_kg_version_tenant_boundary(current_org=A)` 返回 **False**（fail-closed 检出泄漏）
- [x] **B2-4** `test_g9_2_…`：同版本**只有** A 节点 ⇒ 返回 **True**（不误报；否则合法租户被拒答 = 另一种事故）
- [x] **B2-5** `test_g9_3_…`：**应用层过滤是唯一防线**（DR-B11）⇒ 带 `org_id=A` 的图谱查询**不得**返回 B 的节点
- [x] **B2-6** `test_g9_4_…`：**真图泄漏**下问答链路 ⇒ 抛 **`AgentTenantLeakError`**（路由层转 403 `KG_TENANT_LEAK`，该映射由既有 `tests/test_agent_fail_closed.py:225` 覆盖）
  - ⚠️ **实测口径（与任务书不同，登记）**：走的是**服务层**而非 TestClient——只桩 LLM 与 active 版本、图谱走真库；路由层 403 映射与"打桩图谱"那条是**同一条分支**，再写一遍只是重复，故本条补的是"真图真泄漏时这套链路真的会拦"
- [x] **B2-7** `test_g9_5_…`：**诚实登记**——裸 Cypher（不带 org 过滤）**确实能**读到对方 org 的节点
      ⇒ 把「Neo4j 社区版无 RLS、隔离强度弱于 PG 侧」断言成事实，防止「G-9 绿」被读成「图谱侧有强隔离」
- [x] **B2-8** 反向验证：把泄漏查询改成恒返回 0 / 把 B 节点写成 A 的 org ⇒ B2-3 / B2-5 / B2-6 各自**变红**（逐条记录到集成日志）

---

## B3 —— T1 补齐（`documents` / `qa_logs` / `storage_key`）

> 这三个对象的现状：`documents` 已有**详情 403**（`tests/test_documents.py:147`）、`audit_log` 已有（P1-C）；
> `qa_logs` / `storage_key` **完全没有**跨 org 用例，且二者**无 API 路由** ⇒ 只能在服务 / 数据 / 存储层验。

- [x] **B3-1** `qa_logs`：以 A org 的会话查 `qa_logs` ⇒ **看不到** B 的行（**裸连接**口径，绕开 conftest 的「默认租户绑定」脚手架——与 G-26 判据 3 同款理由）
- [x] **B3-2** `storage_key`：用 **B 的** `storage_key` + A 的 `org_id` 读存储 ⇒ `StorageKeyError`（`app/storage/local_fs.py:54-58` 的 org 前缀校验，ADR-0003 §3.5）
- [x] **B3-3** `documents`：**列表**口径 ⇒ A 的列表**不含** B 的文档（与既有「详情 403」互补，不是重复）
- [x] **B3-4** 反向验证：去掉 org 过滤 / 去掉 org 前缀校验 ⇒ B3-1 / B3-2 / B3-3 各自**变红**

---

## B4 —— 文档与登记

- [x] **B4-1** `docs/delivery-requirements-and-guardrails.md`：**G-9 行**更新（图谱侧已由 CI 真验、四个对象齐全、CI 必过），并写明**它不覆盖什么**（图谱侧无 RLS，见 B2-7）
- [x] **B4-2** 同文件 **DR-B11 行**：登记「CI 已起 Neo4j ⇒ 独立环境留证作废」
- [x] **B4-3** `docs/delivery-plan.md`：P3 行 / G-25 行同步（G-25 本体归 P3-C，工程项已建）
- [x] **B4-4** 写 `changes/P3-B/integration-log.md`：实测前后数字、真图用例真值、反向验证逐条、未决事项
- [x] **B4-5** 收束门禁全绿：`pytest`（passed 不减）/ ruff 双绿 / `check_seams.py` OK 10 / `export_openapi.py --check` 零漂移 / `check_startup_readiness.py` 出现 **G-9 [OK]**

---

## 不做（**逐条对照 proposal.md §4，改完回头看一遍**）

1. G-25 本体（种子语料 / 基线容差 / 空图守卫）→ P3-C
2. 改 ADR-0003 原文
3. 改契约 / 新增端点
4. 顺手收紧图谱 Cypher 的 org 过滤（除非 B2 实测发现**真缺口**，那时先登记再改）
5. 摘既有图谱用例的打桩
