# P7-A · 集成日志（DR / G 全量实测对账）

> **日期**：2026-10-05 ｜ **起始提交**：`e4f29d91`（工作区干净，`check_session_drift` 报"自 HEAD 之后没有改动"）
> **性质**：盘点批次，**零产品代码改动**。以下所有数字均为**本次实跑**，不是读文档/读代码得出的。

---

## 1. 机器基准（先于一切结论）

```
check_startup_readiness.py  →  [OK] 已生效 15 条 ｜ [~~] 部分 0 条 ｜ [--] 挂起 2 条（G-12 / G-23）
                               开工地雷 1 项（License 子系统零代码）
check_seams.py              →  ERROR 0 / WARN 0 / OK 10
ruff check .                →  All checks passed!
ruff format --check .       →  224 files already formatted
export_openapi.py --check   →  [OK] contracts/openapi.yaml 与模型一致
```

## 2. 实跑环境（**本机原先没有 PG ⇒ T1 / T2 此前无从实测**）

| 项 | 命令 / 值 |
|---|---|
| PG 容器 | `docker run -d --name graphrag-pg16 -e POSTGRES_USER=graphrag -e POSTGRES_PASSWORD=graphrag -e POSTGRES_DB=graphrag -p 5432:5432 postgres:16-alpine` |
| 实测版本 | `SHOW server_version` = **16.15**（满足 G-8 的 16.x 判据） |
| 测试库 | `graphrag_test`（与 CI 同名） |
| ⚠️ 踩坑 1 | PG 15+ 起 `public` schema **不再默认授予 CREATE** ⇒ 直接 `alembic upgrade head` 报 `permission denied for schema public`。处置：先用超级用户 `GRANT ALL ON SCHEMA public TO app_owner` + `GRANT USAGE TO app_rls` |
| ⚠️ 踩坑 2 | 顺序不能反：先跑 `init_rls_roles.py` 会在空库里走 `Base.metadata.create_all`（脚本逻辑：`not existing` 即建表）⇒ 随后 `alembic upgrade head` 报 `DuplicateTable`。**正确顺序 = 建库 → 授权 → `alembic upgrade head` → `init_rls_roles.py`** |
| 迁移 | 10 个迁移全部跑到 head（含 `8210590e76a5` RLS 策略 / `b7c4e1f9a2d3` `nullif` 谓词） |
| 策略 | `init_rls_roles.py` ⇒ **14 张租户表** ENABLE + FORCE + 策略生效 |
| 业务账号 | `app_rls`（`NOBYPASSRLS`）⇒ 与 CI 同源，避免超级用户绕过 RLS 导致的假绿 |
| 图谱 | 既有容器 `graphrag-neo4j`（`neo4j:5.26-community`，与 CI/deploy 同 tag），口令 `graphragdev` |

**全量 pytest（两次，差异即结论）**

| 环境 | 结果 | 差值说明 |
|---|---|---|
| 有真 Neo4j（CI 等价） | **930 passed / 3 skipped / 3 xfailed**（收集 936） | 3 skipped = `test_temporal_track_s.py` 的 `local_only` 用例（CI 上同样 skip，已显式登记） |
| 无真 Neo4j（本地常态） | **923 passed / 10 skipped / 3 xfailed** | **多 skip 的 7 条** = `test_guardrails_graph.py` 5 条（含 G-9 图谱侧判据 1–5）+ G-25 真图 2 条 |

> 这 7 条的差值就是本批次最重要的发现之一：**它们静默 skip，而 `check_startup_readiness.py`
> 仍把它们报成 `[OK]`**——见 §5。

## 3. 逐条 G 现状总表（**每一格都能 grep 回去**）

**判定规则**：`[OK]` = 无 xfail 且实跑通过（真在拦）；`[--]` = 仍带 `xfail(strict)`（CI 绿但没在拦）；
`🛡` = 反向守卫（必须始终通过）；`n/a` = 作废 / 无机械判据。

### 3.1 G-1 ~ G-7（**readiness 脚本不覆盖**：它们由 CI 步骤而非 pytest 承担）

| # | 护栏 | 判据落点 | 档位 | 本次实测 |
|---|---|---|---|---|
| **G-1** | Ruff 静态检查 + 格式 | `.github/workflows/ci.yml:158-162` | ✅ | `ruff check` 通过；224 文件已格式化 |
| **G-2** | 接缝纪律门禁 | `ci.yml:171` + `tests/test_check_seams.py` | ✅ | `check_seams.py` ERROR 0 / WARN 0 / **OK 10**（含"Settings 51 字段均有消费者"） |
| **G-3** | Pytest | `ci.yml:227` | ✅ | 930 passed（有图）/ 923 passed（无图） |
| **G-4** | 契约零漂移 | `ci.yml:367`（后端 `--check`）+ `ci.yml:399`（前端 `git diff --exit-code`）+ `tests/test_openapi_contract.py` | ✅ | `export_openapi.py --check` 报 OK；漂移时 CI 会打印 diff |
| **G-5** | 前端 ESLint + tsc | `ci.yml:315 / 322 / 325` | ⏳ **本批未实测** | ⚠️ 如实登记：本批未装 `frontend/node_modules`、未跑 lint/tsc ⇒ **不对其现状下结论** |
| **G-6** | 迁移等价性 | `tests/test_migrations_baseline.py`（PG 临时库） | ✅ | 含在全量 930 内通过 |
| **G-7** | 生产禁 SQLite | `app/config.py::_guard_production_sqlite` | ✅ | 由 🛡 `test_g21_production_sqlite_guard_still_present` 反向守住房 `test_guardrails_db.py:139` |

### 3.2 G-8 ~ G-26（readiness 脚本覆盖部分）

| # | 对应 DR | 测试落点 | 弱化标记 | 档位 | 备注 |
|---|---|---|---|---|---|
| **G-8** | B1 / B2 | `tests/test_guardrails.py:99` | 无 | ✅ | 断言 `server_version` 首段为 16（只判 URL 会被换成 15/17 蒙混） |
| **G-9** | B6 / **B11** | `tests/test_guardrails.py:293` + `tests/test_guardrails_graph.py:65/218/253/279/321/376/425/491/512` | 无 | ✅ | 详见 §4.1。**本地无图 ⇒ 5 条 skip** |
| **G-10** | B7 / B8 | `tests/test_guardrails.py:328` | 无 | ✅ | 详见 §4.2 |
| **G-11** | C2 / H16 | `tests/test_seam_signature_snapshot.py:31/45` | 主用例**条件 xfail**（`not SNAPSHOT.exists()`，`strict=False`） | ✅（有旁立守卫） | 见 §5.3 |
| **G-12** | A1 / A3 | `tests/test_guardrails_delivery.py:108` | ✅ `xfail(strict=True)` | **[--] 挂起** | `deploy/variants/` 实测 **1 个**（`baseline.yaml`）⇒ 启用条件写死 ≥2 未满足 |
| **G-13** | A4 | —— | —— | **n/a 作废** | 随 DR-A4 作废（无 B 类插件即无片段可校验） |
| **G-14** | H15 | `test_guardrails_delivery.py:62/80` | 无 | ✅ | 黑名单来源守卫已同步生效 |
| **G-15** | C2 | `scripts/check_patch_contract_freeze.py` + `tests/test_patch_contract_freeze.py` + `ci.yml:192` | 无 | ✅ | 含 `test_app_version_regex_matches_real_config`（R-9 同款来源守卫） |
| **G-16** | 全部 | **无机械判据**（接缝侧由 G-2 拦） | —— | 🟡 **部分** | 文档登记侧无任何机器判据 ⇒ 靠流程 |
| **G-17** | B12 | `tests/test_guardrails.py:135/145/156` | 无 | ✅ | fail-open 逃生阀：默认 fail-closed、破例须显式登记 |
| **G-18** | B13 | `tests/test_guardrails.py:179/234/273` | 无 | ✅ **但** | `users` 仍 **0 消费者**（G-24 RBAC 授权记录仍靠测试夹具播种）⇒ **不得外推到 SSO / License** |
| **G-19** | A6 | `test_guardrails_delivery.py:134/172` | 无 | ✅ | tag 与 `app_version` 联动有专测 |
| **G-20** | B1 | `tests/test_guardrails_db.py:58` | 无 | ✅ | |
| **G-21** | B3 | `tests/test_guardrails_db.py:101` + **🛡 `:139`** | 无 | ✅ | 反向守卫本次仍绿 |
| **G-22** | A2 | `test_guardrails_delivery.py:231/253/262` | 无 | ✅ | 真插件 `plugins/json-csv-export/plugin.yaml`；`entry_point` 可导入有专测 |
| **G-23** | **C1** | `tests/test_guardrails_compliance.py:85/133` | ✅ `xfail(strict=True)` ×2 | **[--] 挂起 + 恒绿失效** | `backend/app/services/license/` **不存在**（实测 `Test-Path` = False）⇒ 按 R-9，**转正无意义** |
| **G-24** | B9 | `tests/test_guardrails_compliance.py:155/218/262/296` + `tests/test_rbac.py`（14 条） | 无 | ✅ | **不断言具体权限值**（属实现决策）；默认主体为 admin ⇒ 拒绝分支由 `test_rbac.py` 覆盖 |
| **G-25** | D10 | `tests/test_eval_ci_gate.py`（11 条）+ `tests/test_eval_corpus_a8.py:306` | 2 条 `skipif(not _REAL_GRAPH)` | ✅ **CI 内** | 本地无图 ⇒ 这 2 条 skip（见 §2 差值） |
| **G-26** | B4 / B8 | `tests/test_guardrails_rls.py`（15 条 + 14 表参数化） | 无 | ✅ | 判据 3 用裸连接 ⇒ 绕开 conftest 的默认租户脚手架 |

**xcail 数核验**：全量跑出的 `3 xfailed` = G-12（1）+ G-23（2）⇒ **与 readiness 的 `[--] 2 条` 完全一致，
没有第四条隐藏的挂起护栏。

## 4. ADR-0003 §4.1 两类用例专项（用户点名必核，未漏）

### 4.1 T1 跨 org 越权 —— ✅ 四个对象齐全，实跑通过

| 对象 | 用例 | 实跑 |
|---|---|---|
| `audit_log` | `tests/test_guardrails.py:293` `test_g9_t1_cross_org_read_returns_empty` | ✅ pass |
| `documents` | `tests/test_guardrails_graph.py:512` `test_g9_t1_documents_list_excludes_other_org` | ✅ pass |
| `qa_logs` | `tests/test_guardrails_graph.py:425` `test_g9_t1_qa_logs_other_org_rows_invisible` | ✅ pass |
| `storage_key` | `tests/test_guardrails_graph.py:491` `test_g9_t1_storage_key_cross_org_read_rejected` | ✅ pass |
| 图谱侧 5 条（DR-B11） | `.../map:218/253/279/321/376` | ✅ pass（**须真 Neo4j**；本地无图 ⇒ skip） |

三条裁定都满足：

1. **在 PostgreSQL 16.x 上跑** —— ✅ `test_g9_t1_cross_org_read_returns_empty:310` 与 T2 首行均有
   `_require_postgres()`（非 PG ⇒ 直接 fail，不是 skip）；本次实跑库版本 **16.15**、业务角色 `app_rls`（受限）。
   `documents` / `qa_logs` / `storage_key` 三条虽未各自调用 `_require_postgres()`，但
   `conftest.py:41` 已把 `DATABASE_URL` 固定到 PG 测试库（走 `setdefault`，不可用 `.env` 的开发库覆盖），
   且其 SQL 含 `set_config(...)` 等 PG 专有语法 ⇒ **在 SQLite 上不可能静默通过**。
2. **纳入 CI 必过** —— ✅ 三者**无任何 marker**，随 `ci.yml:227` 的 `pytest -q -rs` 跑；
   图谱侧由 `ci.yml:83` 的 `neo4j:5.26-community` service + `_real_graph_env()` 在 CI 上
   **`pytest.fail`（而非 skip）**兜住（`test_guardrails_graph.py:136-141`）。
3. **禁止 `local_only`** —— ✅ 全仓 `local_only` 登记集合仅 3 条
   （`tests/test_local_only_boundary.py:35-41`：import_to_neo4j / page_index / temporal_track_s），
   **T1 / T2 一条都不在里面**。

### 4.2 T2 并发串租户 —— ✅ 覆盖连接池复用，实跑通过

`tests/test_guardrails.py:328`：`ThreadPoolExecutor(max_workers=8)` × **24 次请求**交替两个 org
⇒ 连接必然被归还并跨租户复用（`SET LOCAL` 误写成会话级 `SET` 只有这条测得出来）。
判据为「**必须**看到本 org 的标记行 + **绝不能**看到对方的标记行」（P3-A 修正口径：
早先断言"B 的 items 为空"在正确实现下**恒不成立**——那 24 个请求本身就是 B 自己的）。
实跑：**pass**。

## 5. 弱化形态与 `check_startup_readiness.py` 的结构盲区

### 5.1 全仓弱化标记盘点（拉全，非抽样）

| 形态 | 命中 | 去向 |
|---|---|---|
| `xfail(strict=True)` | 3（G-12 ×1、G-23 ×2） | readiness 判 `[--]` ✅ 识别正确 |
| `xfail(条件, strict=False)` | 1（G-11 主用例） | readiness 判 `[OK]` ✅（条件为假时不上 xfail），性质见 §5.3 |
| `skipif(not _REAL_GRAPH)` | 2（G-25 真图） | ❌ **readiness 判 `[OK]`，不识别** |
| fixture 内 `pytest.skip` | 5（G-9 图谱侧，走 `real_driver` / `graph_service`） | ❌ **readiness 判 `[OK]`，不识别** |
| `local_only` | 3 | 有 `test_local_only_boundary.py` 独立登记 + CI 单列一步打印原因 ⇒ **不在 readiness 职责内，可接受** |

### 5.2 盲区 1（**核心**）：`skipif` / fixture skip 不计档

> **症状**：本地没起 Neo4j 时，`pytest` 结果从 `930 passed` 变成 `923 passed`，
> 少的 7 条**全绿通过、无人察觉**；而 `check_startup_readiness.py` 两次输出**一模一样**（都是 `[OK]`）。

这违反 §0.1 那句"判定一律以机器输出为准"——因为机器输出本身在这一格上失真了。
**处置：不在本批修**（`proposal.md` §3-6：改脚本会改 CI 报告口径，且要连带自测 ⇒ 独立批次 **P7-B**）。

### 5.3 G-11 的条件 xfail —— 有旁立守卫，**不构成缺口**（仅留说明）

`test_seam_signatures_match_frozen_snapshot` 带 `xfail(not SNAPSHOT.exists(), strict=False)`：
快照一旦丢失，主用例会**静默转 XFAIL（绿）**而不是判红——是典型的 R-9 形态。
但它有旁立方 `test_frozen_snapshot_is_committed`（`:45`，断言 `SNAPSHOT.exists()`）⇒ 快照丢失时
**第二条会红**，整条护栏不会静默失效 ⇒ 判定为**有兜底**。
小瑕疵（只登记不修）：该用例名写着 `is_committed`，实际只断言 `exists()`，**未校验 git 是否入库**。

## 6. 补齐优先级（**据此调整阶段 ②–⑤ 顺序**）

| 优先级 | 项 | 为什么 | 转正动作（**唯一方式**） |
|---|---|---|---|
| **P0** | **G-12 第 2 个真实变体**（DR-A1 / A3） | GA 五项缺口的**最后一项**；成本最低（一份 yaml + 几条 compose）。⚠️ 命名有**已登记的地雷**：`_customer_tokens()` 按文件名做**子串**匹配，而基座契约里 `default` 出现 10 次 / `demo` 3 次 ⇒ 照 §300 字面命名会让 G-14 **结构性假红**（2026-10-04 P2.5 实测，见 `changes/P2.5/proposal.md` §7） | 落第 2 个真实部署形态 ⇒ 测试**真通过**后摘 `@pytest.mark.xfail`（`:100`） |
| **P1** | **P7-B：readiness 脚本补 `skipif` / fixture-skip 档位** | §5.2 那 7 条是目前唯一会让"机器结论"说谎的地方；其余都在拦 | 改脚本 + 给脚本自身加自测（含反向验证） |
| **P2** | **G-23 / DR-C1 License 子系统** | 唯一 `(--]` 且**恒绿失效**：先把 `app/services/license/` 真的建起来，转正才有意义（R-9） | 落真子系统（≥6 项资产 + 行为侧 403）后摘 2 处 xfail |
| **P3** | **G-16 文档登记侧的机械判据** | 目前纯人工，且"新增文档必须登记"这条从没人被拦过 | 与 PRD 附录 C.0 联动后再定 |

### 6.1 对阶段 ②–⑤ 的排期结论：**不调整顺序，理由如下**

原计划顺序：② A1 向量基线 → ③ L2 端到端 → ④ Q8 拒答误伤 → ⑤ TBD-7 阈值。
按 P6-B 用过的判据（"**宣称了但欠着**"优先于"还没做"），④ 的 `refusal_false_refusal` 当前
**FAIL（1 条 Q8）**本来**应该**排到最前面。但有一条更硬的技术依赖压住它：

> **A1（dense top-k 基线 + 双侧判分）会改变检索路径本身**，而 Q8 的误伤正是沿检索路径产生的。
> 先修 Q8、再上 A1 ⇒ 等于在一个即将变动的管线上对着旧结果调参，**很可能白调一轮**。

⇒ 维持 ② → ③ → ④ → ⑤，并把这条理由留在案：**若 ② / ③ 落地后 Q8 的误伤条数发生变化，
须在 ④ 的日志里写明「变化前/后各是多少」，不得只报修好之后的那一次。**

另注（不影响顺序，影响可行性）：②–⑤ 依赖的"真机链路"阻塞**本批已解除**——
本地 PG 16.15 + 受限角色 + 真 Neo4j 现已可用（见 §2），`agent/query` 恒 501 的根因
（PG `kg_versions` 无 ready 版本）具备了实跑复现条件。

## 7. 需求基线回写清单（本次订正，均已落到文档）

| # | 位置 | 原口径 | 订正后 |
|---|---|---|---|
| 1 | §2.2 **G-10** 状态列 | `🟡 骨架已就位（xfail 挂起）` | `✅ 已生效`（2026-10-04 P3-A 转正，本次 2026-10-05 实跑复核通过） |
| 2 | §3.1 **B6** 行 | "仍缺 `documents` / `qa_logs` / `storage_key`（P3 补齐）" | 已补齐并新增 2026-10-05 实测行（四个对象齐全） |
| 3 | §3.1 **B11** 行 | "待建；**CI 无 Neo4j**" | `ci.yml` 已起 `neo4j:5.26-community` ⇒ CI 真验；补"本地无图 ⇒ 5 条 skip"的限定语 |
| 4 | §2.2 **G-23** | 只写"骨架已就位" | 增补"**恒绿失效 ⇒ 转正无意义（R-9）**，先要有真 License 子系统" |
| 5 | §2.2 **G-11** | — | 增补条件 xfail 性质 + "旁立方兜底，不构成缺口"+ 名实不符的小登记 |
| 6 | §2.2 **G-25** | — | 增补"两条真图判据本地 skip ⇒ 本地 923 / 有图 930" |
| 7 | §5 清单 | pytest 基数 **707 passed**（P1-C 时代） | 刷新为 **930 passed / 3 skipped / 3 xfailed**（有图）与 **923 / 10 / 3**（无图） |
| 8 | §8 审阅记录 | — | 新增「2026-10-05 全量对账」段 |

## 8. 收尾三问（自答）

1. **有没有"顺便做的"？属于哪条 DR / G？**
   没有。本批唯一的产品侧改动为 **0**；文档侧 8 处改动全部是 §7 清单内的对口订正，
   没有一条是"顺手补的"。期间发现的两个候选小 bug（`test_frozen_snapshot_is_committed`
   名实不符、readiness 的两个盲区）**都只登记、未动代码**。
2. **有没有为躲坑而绕路的实现？**
   没有实现，故无从绕路。但环境侧**没有绕**：`alembic` 的 `permission denied` 与
   `DuplicateTable` 两个坑都按根因（schema 授权 / 执行顺序）解决，没有采用
   `alembic stamp head` 之类的掩盖手法——后者会让 G-26 的迁移判据变成空跑。
3. **结论是真跑出来的还是读代码得出的？**
   **全部实跑**：PG 16.15 + 受限角色 + 真 Neo4j 上跑了两遍全量 pytest；
   readiness / seams / ruff / openapi 四个门禁各自真跑。唯一例外是 **G-5（前端 lint/tsc）
   本批未实测**，已在 §3.1 显式标注，不对它下结论。

## 9. 阶段小结

| 项 | 数 |
|---|---|
| 完成子任务 | T1–T8 全 8 组 ✅ |
| 降级登记 | 0 |
| 升级用户 | 0 |
| 发现文档漂移 | 8 处（已全部回写） |
| 发现机器盲区 | 2 处（`skipif` / fixture-skip 不计档；G-11 名实不符）⇒ 留 P7-B |
| 实测数字 | 930 passed / 3 skipped / 3 xfailed（有图）；923 / 10 / 3（无图）；ruff 绿；224 文件已格式化；seams OK 10；契约零漂移 |
