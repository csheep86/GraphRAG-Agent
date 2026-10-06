# P6-P1 · 任务清单（清偿三项遗留：R28 / R29 / Sprint10.5）

> 边界见 `proposal.md` —— ⚠️ **草案**。Non-goals **12 条**（编号列表，S1 实测读到 **12** 条）。
> **定位**：清偿遗留，不是新功能。R28 = **零代码**；R29 = 极小脚本；Sprint10.5 = **只登记不动目录**。
> 执行留痕：[`integration-log.md`](./integration-log.md)。

- [x] **T0 Triage（只读）**：三项遗留逐条查证，结论见 `proposal.md` §1
      - R28：本地 `app_rls`/`app_owner` **已存在**（`rolbypassrls = f`）、`graphrag_test` 库已存在、
        本地 pytest **本就是受限口径**（`g26_1/3/4` 单独跑 **6 passed**）⇒ **推翻** P6-O「需中和 `.env`」的推断；
        容器 `postgres:16-alpine` + `neo4j:5.26-community`（与 compose 同 tag）在跑；
        真因 = **本地 Neo4j 口令既不是 CI 那份也不是 `.env` 那份**（`.env` 那份是过期值）+ **图内无 `affiliation-demo-v2` 语料**
      - R29：其**既定处置** = P6-P0 §3.2 的 users 主体锚点 ⇒ 「收 R29」= 执行它
      - Sprint10.5：`delivery-plan.md:198` 既定 = **P5 承接并改指编号** ⇒ **不归档**，且带无门禁兜的债务 `G3`
- [x] **T1 R28 闭环（零代码，纯环境）**
      - [x] T1.1 导入受控语料（`--purge` 只删同 `kg_version` 节点，`ingest_affiliation_sources.py:1172`）
            ⇒ 主体 120 / 发票 500 / 凭证 100 / 共享与合同 548 / 关系 1428；回读 Entity 1268 / Relation 1428；6851 ms
      - [x] T1.2 注入 `GRAPH_REAL_NEO4J_URI/USER/PASSWORD`（**本地真实口令，全程不打印**）
      - [x] T1.3 跑全量 ⇒ **999 passed / 3 skipped / 2 xfailed / 0 failed**（collected 1002 = CI 同量；
            本地比 CI 多 2 条 passed = 本地独占资产；**原 8 条旧红全绿**）
      - [x] T1.4 ⚠️ 未半途而废：语料先于 env 注入，避免 G-25 3 + sentinel 1 + G-9 1 从 skip 转 fail
- [x] **T2 R29 闭环（users 主体锚点）**
      - [x] T2.1 **扩展** `backend/scripts/seed_dev_rbac.py`（不新增文件，继承 dev 闸门），主键 = `DEFAULT_ACTOR_ID`
      - [x] T2.2 双视角度量：`users` **0→1 行**；`user_roles` 孤儿**全局 2→0**、`documents.uploaded_by` **36→3**
            ⚠️ **严格视图仍有 1 条跨租户引用** + 残留 3 / 2 ⇒ 新立 **R30**，**不粉饰**
      - [x] T2.3 消费登记：**不需要** —— 闸门扫描根是 `app/`（脚本在 `scripts/`）；`pytest -k g18` **3 passed** 保持绿
      - [x] T2.4 `password_hash` = **stdlib PBKDF2-SHA256**（零新增依赖）、**不打印 / 不落日志 / 不进契约**
      - [x] T2.5 `--check` 三重奏验缺口判定非恒绿：缺 → **rc=1**；补 → rc=0；再验 → **rc=0**（幂等）
- [x] **T3 登记**
      - [x] T3.1 `dev-doc-status.md` §8：R28 → **已闭环**（保留原文 + 追加更正）；R29 → **锚点已补**（注明仍 0 读者）
      - [x] T3.2 新增 **R30**（引用口径残留：跨租户引用 / 随机 UUID / audit_log），归 **P2-C**
      - [x] T3.3 登记 Sprint10.5「不归档 / 归 P5-D4 承接 / 未了债务 `G3` 受控题集须重跑（无门禁兜）」
      - [x] T3.4 登记**发现但不修**：`ci.yml:280` 失败摘要里 `POSTGRES_DB=graphrag` 应为 `graphrag_test`
- [x] **T4** 回切点：S1 **12 条**、S2 OK + 门禁全绿（契约 zero diff ／ 无图口径 **991 passed** 不减 ／
      `ruff check` + `ruff format --check`（237 文件）／ `check_seams` **ERROR 0 / WARN 0 / OK 10**）
- [x] **T5** 摊 diff + 提交（Conventional Commits）+ CI 实证回登
