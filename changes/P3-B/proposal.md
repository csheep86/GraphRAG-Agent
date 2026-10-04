# P3-B 提案 —— 图谱侧（Neo4j）跨 org 隔离真验 + T1 补齐 + G-9 转正

| 项 | 内容 |
|---|---|
| **批次** | P3-B（P3 的第二子批；P3-A = PG 侧 RLS 已完成并推送） |
| **日期** | 2026-10-04 |
| **状态** | 🟡 **进行中**（本批由我在开工时按 P3 提案 §3 的拆分裁决执行，不再另请裁决） |
| **执行顺序出处** | `changes/P3/proposal.md` §3 表：**P3-B = 图谱侧真实用例 + CI Neo4j + G-9 补齐**；出口 = **G-9 全部转正** |
| **前置** | P3-A 已完成（PG 侧 14 张表 RLS + G-26 + CI 双角色 + 部署形态收口），全部门禁绿（879 passed） |

---

## 0. 起跑状态（**实测**，本批开工前逐项查证）

| 项 | 实测结果 | 证据 |
|---|---|---|
| CI 的 services | **只有 `postgres`**，**无 neo4j** | `.github/workflows/ci.yml:60-77`（services 块只有 postgres） |
| 测试里的 Neo4j | conftest **强制指向不可达端口** `bolt://127.0.0.1:1`，图谱用例一律**打桩** | `tests/conftest.py:52-58`；`tests/test_agent_fail_closed.py:34-85`（`_patch_graph` 打桩 `validate_kg_version_tenant_boundary` / `fetch_active_kg_version` / `fetch_evidence_chunks`） |
| 图谱侧隔离实现 | 服务层**有**：`GraphService.validate_kg_version_tenant_boundary`（`app/services/graphs.py:1021-1051`），Cypher `_QUERY_..._LEAK` 统计「同 kg_version 内 org_id ≠ 当前」的节点 | 同上 |
| 图谱数据里的租户维度 | 节点 / 关系**都带 `org_id`**（`kg/builder.py` stage-1/2/3 每个 MERGE 都写 `n.org_id = $org_id`）；Neo4j 社区版**无 RLS** | `app/services/kg/builder.py:142/179/198/215/241/312/328/…` |
| G-9 在护栏报告里 | **不出现**：`check_startup_readiness.py` 按 `test_g<N>_` 函数名或模块 docstring 首行 `G-<N>` 认护栏 ⇒ 当前**没有任何 G-9 归属的测试** | `scripts/check_startup_readiness.py:44-51 / 160-164` |
| T1 四对象覆盖 | `documents` ✅（`tests/test_documents.py:147` 403）、`audit_log` ✅（`tests/test_audit.py:163`）、**`qa_logs` ❌**、**`storage_key` ❌**、**图谱侧 ❌（打桩）** | 检索 `def test_.*(cross_tenant\|tenant\|storage_key\|qa_log)` |
| `qa_logs` / `storage_key` 有无路由 | **均无 API 路由**（只在服务 / 数据层存在）⇒ T1 只能在**服务 / 数据层**验 | `app/api/v1/` 下 grep `storage_key\|qa_log` = 0 命中；`app/storage/local_fs.py:54-62` 的 `get(key, *, org_id)` 有 org 前缀校验（ADR-0003 §3.5） |
| 本地可用性 | 已起 `neo4j:5.26-community`（与 `deploy/docker-compose.yml:44` 同 tag），bolt 7687 | `docker ps` |

---

## 1. 权威口径（逐字要点，本批不重开已决问题）

| 出处 | 要点 |
|---|---|
| **ADR-0003 §4.1** | T1（跨 org 越权 → 空或 403）、T2（并发不串租户）为**必补**两类测试 |
| **DR-B11** | 图谱侧（Neo4j）**没有 RLS** ⇒ **应用层过滤是唯一防线**（不是冗余防线） |
| **基线 §169（G-9 行）** | 图谱侧仍为**集成测试**：**「在 CI 起 Neo4j 之前，该部分不得声称『已由 CI 验证』，须独立环境留证」** |
| **基线 §303** | 图谱侧隔离 = **给 `ci.yml` 的 backend job 加 `neo4j` service** ⇒ 由「独立环境留证」升格为**真 CI 必过**；❌ 继续以「CI 无 Neo4j」为由停在留证却宣称已验证 |
| **基线 G-25 行** | 与 G-9 图谱侧**共用同一个 `neo4j` service + 同一份受控种子数据**，但**护栏登记两条**（需求不同：DR-B11 隔离 vs DR-D10 评测） |
| **R-9 恒绿即失效** | 用例若在本地 skip、CI 上又没 Neo4j ⇒ 等于没跑 ⇒ 必须**机械保证 CI 上真跑**（skip 即红） |

---

## 2. 本批范围（B1~B4）

| # | 内容 | 落点 |
|---|---|---|
| **B1** | **CI 起 `neo4j` service**（与 deploy 同 tag）+ 真连接开关 + **CI 未起 Neo4j 即红的静态守卫** | `.github/workflows/ci.yml`、新测试文件里的守卫 |
| **B2** | **图谱侧真实跨 org 用例**：真 Neo4j 里同 `kg_version` 混入两个 org 的节点 ⇒ ① fail-closed 校验检出泄漏；② 应用层过滤（唯一防线）不带回对方节点；③ `/agent/query` 真图泄漏 ⇒ **403 `KG_TENANT_LEAK`**；④ **诚实登记**：裸 Cypher 直读**确实能**跨租户读到（无 RLS 的事实） | `backend/tests/test_guardrails_graph.py`（模块 docstring 首行 `G-9 / DR-B11：…`） |
| **B3** | **T1 补齐**：`documents`（列表口径）/ `qa_logs`（数据层）/ `storage_key`（存储层跨 org key）三个对象的跨 org 越权用例 | 同上文件 |
| **B4** | 文档与登记：基线 G-9 行 / DR-B11 行、`delivery-plan.md`、`changes/P3-B/integration-log.md`；`check_startup_readiness.py` 因此显示 **G-9 已生效** | docs + 本目录 |

### 出口判据

1. `uv run pytest -q` **passed 不减**（879 起跑），xfailed 数不增；
2. `check_startup_readiness.py` 出现 **G-9 且为 `[OK]` 已生效**（当前根本不出现）；
3. B2 / B3 的每条新用例都做过**反向验证**（破坏 ⇒ 红），并在集成日志里逐条写下；
4. CI 上**有** `neo4j` service，且图谱用例在 CI 上**真跑**（静态守卫盯住；CI 里不可达 ⇒ **fail 不 skip**）。

---

## 3. 拆分裁决（本批我在开工时定的，登记备查）

**G-25（评测判据进 CI）本体不在本批。**

- 依据：`changes/P3/proposal.md:117` 写明 P3-B 的**出口 = G-9 全部转正**，G-25 是「**共用同一工程项**」的另一条护栏；
- 基线 G-25 行的五条判据（受控种子语料 / `--live` 出真值 / 只判不退化 / 空图守卫）属**评测域（DR-D10）**，与隔离域（DR-B11）混做会让出口模糊；
- 本批**只把共用工程项（CI 的 `neo4j` service）建好** ⇒ G-25 本体归 **P3-C**（紧随本批），它不再需要重新申请 CI 资源。

---

## 4. Non-goals（本批**不做**）

1. ❌ **不做** G-25 本体（种子语料 / 基线值与容差 / 空图守卫）——归 P3-C，见 §3；
2. ❌ **不改** ADR-0003 原文（守 **R5**，差异追加登记）；
3. ❌ **不改契约**（`contracts/openapi.yaml` 零漂移；本批不新增 / 不改端点）；
4. ❌ **不新增**图谱侧 Cypher 的 org 过滤改造——**除非** B2 实测发现现网查询里存在**真的**跨租户缺口（那属本批正当范围，须先登记再改，不得顺手）；
5. ❌ **不做**图谱侧 RLS / 企业版特性（Neo4j 社区版无 RLS，DR-B11 已裁定靠应用层过滤）；
6. ❌ **不摘**既有图谱用例的打桩（`test_agent_fail_closed.py` 等）——它们验的是**服务层分支**，与本批「真图」互补；本批**新增**真图用例，不改旧用例语义；
7. ❌ 不做 P2-C（SSO）/ P4（License）/ G-23。

---

## 5. 已知要**诚实登记**的事实（不掩盖）

- 图谱侧隔离强度 ≠ PG 侧：Neo4j 社区版**没有 RLS**，且**裸 Cypher 直读可以跨 org 读到**（只要 `kg_version` 相同）⇒ 隔离**完全依赖**应用层过滤 + `validate_kg_version_tenant_boundary` 的 fail-closed 校验。本批会用一条用例把这件事**断言成事实**（而不是藏在文档里），避免日后有人把「G-9 绿」读成「图谱侧有强隔离」。
- 若干查询的 org 过滤是 **fail-open** 写法：`($org_id IS NULL OR properties(n)['org_id'] IS NULL OR properties(n)['org_id'] = $org_id)`（`graphs.py:743-744` 等）⇒ 节点**缺 `org_id` 属性时会被放行**。本批先**登记**，是否收紧属 §4 第 4 条的判断（B2 实测后再定，不在开工前预设结论）。
