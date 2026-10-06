# P6-P1 · 集成日志（清偿三项遗留：**R28** 本地有图口径 / **R29** `users` 主体锚点 / **Sprint10.5** 处置）

> **日期**：2026-10-06 ｜ **边界文档**：`changes/P6-P1/proposal.md`（⚠️ 草案；Non-goals **12 条**编号列表，S1 实测读到 **12** 条）
> **定位**：**清偿遗留，不是新功能** —— R28 = **零代码**（纯环境）；R29 = 极小脚本（扩展既有 seed）；Sprint10.5 = **只登记、不动目录**
>
> **一句话**：三项遗留里 **R28 已闭环（本地有图口径实测 0 红）**、**R29 主体锚点已补（`users` 0→1 行、孤儿 2→0）**、
> **Sprint10.5 按文档既定处置不归档**；并把补锚点才暴露出来的引用口径残留新立为 **R30**（归 P2-C）。

---

## 1. T1 · R28 闭环（**零代码**，纯环境）

### 1.1 Triage 先推翻了 P6-O 的一条推断

| 证据（实测命令 → 读数） | 结论 |
|---|---|
| `docker exec graphrag-pg16 psql -U graphrag -c "select rolname, rolbypassrls from pg_roles where rolname in ('app_rls','app_owner','graphrag')"` ⇒ `app_rls` / `app_owner` 均在，且 **`rolbypassrls = f`** | 本地**已具备**受限角色 |
| 同上 `select datname from pg_database` ⇒ 含 **`graphrag_test`** | 测试库已就绪 |
| `uv run pytest tests/test_guardrails_rls.py -k "g26_4 or g26_3 or g26_1"` ⇒ **6 passed** | ⚠️ **本地 pytest 本就跑在受限角色口径** ⇒ **P6-O「需中和本地 `.env`」的推断被推翻**（原文按 R5 保留，只在 R28 行追加更正） |
| `docker ps` ⇒ `postgres:16-alpine` + **`neo4j:5.26-community`**（与 `deploy/docker-compose.yml` 同 tag） | 容器齐且版本一致 |
| `docker exec graphrag-neo4j cypher-shell -u neo4j -p ci-graph-pw-2026` ⇒ **认证失败**；`.env` 里的 `NEO4J_PASSWORD` 连 Neo4j 也 **`AuthError`** | ⚠️ **真因一：本地图库口令既不是 CI 那份，也不是 `.env` 那份**（`.env` 那份是**过期值**）；且与本地图（5607 节点）连得上的是 `docker inspect` 里容器自带那份 |

⇒ R28 的真实缺口被压缩到**两件自上一次就没人做过的事**：**口令不对** + **没导语料**。两者都不需要改代码。

### 1.2 闭环三步（幂等、可复现）

| 步 | 动作 | 实测 |
|---|---|---|
| ① | `docker inspect graphrag-neo4j` 取容器真实口令（**全程不打印口令**，脚本只回 `OK nodes=5607`） | 连通 |
| ② | `scripts/ingest_affiliation_sources.py --purge --corpus-dir ../demo/affiliation/generated --kg-version affiliation-demo-v2` | 主体 120 / 发票 500 / 凭证 100 / 共享与合同 548 / 关系 1428；回读 Entity 1268 / Relation 1428；PG 侧 `affiliation-demo-v2` → `ready`；耗时 **6851 ms** |
| ③ | 注入 `GRAPH_REAL_NEO4J_URI/USER/PASSWORD`（本地真实口令）+ 跑全量 | **999 passed / 3 skipped / 2 xfailed / 0 failed**（59.48s） |

**为什么 `--purge` 是安全的**：`ingest_affiliation_sources.py:1172` 的清理 Cypher 只删
`MATCH (n {kg_version: $kg_version})` ⇒ **只动 `affiliation-demo-v2`**，本地演示图（`attendance-demo-v1` 等）一根没碰。

**⚠️ 不能做一半**（proposal §2.1 已预警并被验证为必要）：只注入 env 而不导语料 ⇒ G-25 3 条 + sentinel 1 条 + G-9 1 条
会从 **skip 转 fail**（`test_guardrails_graph.py:136-141`、`test_evidence_window_sentinel.py:327-341` 的语义）。

## 2. T2 · R29 主体锚点（扩展 `seed_dev_rbac.py`，**不新增文件**）

> **为什么不新开一个 `seed_dev_users.py`**：既有 `seed_dev_rbac.py` 已经有 dev 闸门（`ALLOW_DEV_ORG_HEADER`
> 未开即拒，`seed_dev_rbac.py:75-81`）、已经在同一会话里写这条 actor 的授权 ⇒ 在这里补「人」是顺向的一步；
> 新开一个文件反而会多出一个**没人编排顺序**的入口。

### 2.1 改了什么（`backend/scripts/seed_dev_rbac.py`，+97 行）

| 内容 | 说明 |
|---|---|
| `_hash_password()` | **stdlib PBKDF2-SHA256**（600k 迭代）——刻意**不引入 `passlib` / `argon2`**：当前**没有任何校验方**，为一列没人读的值加依赖 = 无消费者依赖（预留纪律第 6 条）；算法终选留归 **P2-C** |
| `_user_exists()` / `_ensure_dev_user()` | **以 `DEFAULT_ACTOR_ID` 为主键**幂等插一行 `users`（`username = dev-<actor_id>`，`status='active'`） |
| `main()` | ① 支持 `--password=<...>`（缺省取随机值且**不打印**——当前无校验方，打印只是制造一条需要保管的秘密）；② 播种顺序 = **先有被授权的人，再授权**；③ `--check` 现在同时判「锚点 + 授权」，**缺任一项返回非 0** |

**为什么主键刻意取 `DEFAULT_ACTOR_ID`**：既有 `user_roles.user_id` / `documents.uploaded_by` 里那个 actor_id
**恒为这个值**（`core/config.py:27`）⇒ 锚点对上后，**改业务代码这一步全省了**——改了反而会造出第一批需要回填的新数据。

### 2.2 实测（ `--check` 三重奏，缺 → 补 → 幂等）

| 步 | 命令 | 结果 |
|---|---|---|
| 补之前 | `uv run python scripts/seed_dev_rbac.py --check` | `dev 主体 users 锚点 = 缺失（待补）`，**rc=1**（⇒ 缺口判定**不是恒绿**） |
| 补 | `uv run python scripts/seed_dev_rbac.py` | `[OK] 已插入 users 锚点：username=dev-00000000-0000-4000-8000-0000000000aa / org=...0001`，rc=0 |
| 再验 | 同上 `--check` | `dev 主体 users 锚点 = 已存在`，**rc=0** |
| 幂等 | 再跑一次播种 | `[OK] 已存在，未重复插入（幂等）` |

### 2.3 ⚠️ 双视角度量（这是本批最需要留痕的一格）

> **为什么必须两种度量**：全局视图（只连 `id`）回答「这个 actor 存不存在」；
> **严格视图（`id` 与 `org_id` 都相等）**回答「这条引用有没有**跨租户**」。
> 只报全局视图，等于把 R29 从「孤儿」粉饰成「已闭环」——**而它并没有**。

| 列 | 补之前 | 补之后（**全局视图**） | 补之后（**严格视图**） |
|---|---|---|---|
| `users` | **0 行** | **1 行**（`...00aa` / org `...0001` / active） | 同左 |
| `user_roles.user_id` 孤儿 | **2 / 2** | **0** ✅ | **1** ⚠️（org `...0002` 的授权挂在 org `...0001` 的 user 上） |
| `documents.uploaded_by` 孤儿 | **36 / 36** | **3** ✅（33 行脱孤） | **4** ⚠️（另 1 行属跨租户口径；剩 3 行指向随机 UUID） |
| `audit_log.actor_id` 孤儿 | **2 / 2** | **2**（不变） | **2**（不变） |

⇒ **结论不许含糊**：补锚点**只解决了「人在不在」**，**没解决「引用自不自洽」**。三项残留已新立 **§8 R30**：
① 1 条**跨租户引用**（今天是 dev 脚手架共用一个 UUID，P2-C 真账号落地后形态就是**越权**）；
② 3 条 `documents.uploaded_by` 指向随机 UUID；③ 2 条 `audit_log.actor_id` 指向 `2efb11bb-…`
（`models.py:639` 明写「系统触发**不编造 UUID**」⇒ 本批**不补**）。三者**均归 P2-C**（届时 `actor_id` 唯一来源 = 认证态）。

### 2.4 消费登记：为什么**不需要**动 `USERS_CONSUMER_MODULES`

闸门 `test_guardrails.py:253-258` 的扫描根是 **`APP_ROOT` = `backend/app`**（`:49`），而本脚本在 `backend/scripts/`
⇒ 不会命中。实测 `pytest -k g18` **3 passed** 保持绿。
⚠️ 但这也说明：**补了行 ≠ 有读者** —— `app/` 下仍 **0 处 `select(User)`** ⇒ **不得宣称账号体系落地**（需求基线 `:228`）。

## 3. T3 · 登记

| 项 | 处置 |
|---|---|
| **R28** | `dev-doc-status.md` §8 由「开放」→ **✅ 已闭环**，保留 P6-O 原文 + 追加更正与复现三件事 |
| **R29** | 同上 → **主体锚点已补**，并明写「app/ 仍 0 读者、仍有残留（见 R30）」 |
| **R30**（**新增**） | 上述三项引用口径残留，归 **P2-C**；并给出**留给那批的判据建议**：把「严格视图孤儿 = 0」写成机械断言 |
| **Sprint10.5** | **不归档** —— 采纳 `delivery-plan.md:198` 既定处置（P5-D4 **承接并改指阶段编号**）；登记其**无门禁兜的未了债务**：演示库被不可逆改动 ⇒ `G3` 受控题集（`eval_controlled_qset.py`）**必须重跑** |
| **发现但不修** | `ci.yml:280` 失败摘要复现命令写 `POSTGRES_DB=graphrag`，与 job 实际（`ci.yml:68`）的 `graphrag_test` 不一致 ⇒ 照抄会**建错库**；按 Non-goal 11 **只登记** |

## 4. 验收判据逐条（proposal §6，5 条全机械）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| ① | 有图口径 0 failed，原 8 条旧红全绿 | **999 passed / 3 skipped / 2 xfailed / 0 failed**（rc=0）；collected **1002** 与 CI（997+5）**同量** ⇒ 差值 = **本地独占 2 条**（CI 缺 `bridge_web_demo/output.json` / MinerU 产物故 skip），本地实则**多跑通 2 条**。⚠️ 计划目标 997/5 是**下界**，实测 999/3，**0 failed 达成** | ✅ |
| ② | `users` ≥1 行；`user_roles` 孤儿 0；`\bUser\b` 命中 ⊆ 登记（双向） | `users` **1 行**；孤儿**全局 0**（严格视图 1 ⇒ 已登记为 R30，**未粉饰**）；`app/` 下 `\bUser\b` 仍只有定义处 `models.py:773`，登记集合仍为空 ⇒ **双向一致** | ✅ |
| ③ | 契约 zero diff / 无图口径 pytest 不减 / ruff / `check_seams` ERROR 0 | `export_openapi.py --check` **零 diff**；无图口径 `pytest` **991 passed / 11 skipped / 2 xfailed**（= 基线，**不减**）；`ruff check` **All checks passed**、`ruff format --check` **237 files**（首轮因 1 文件需格式化已 `ruff format` 后复验通过）；`check_seams` **ERROR 0 / WARN 0 / OK 10** | ✅ |
| ④ | drift S1 读到 **12 条** Non-goals | ✅（且批次 = `changes/P6-P1/`） | ✅ |
| ⑤ | 三项遗留状态更新且带证据 | R28 **已闭环** / R29 **锚点已补（残留见 R30）** / Sprint10.5 **不归档 + 债务登记**，每条带命令与行数 | ✅ |

## 5. 不许外推

- 本地有图口径 0 红 **≠** R28 曾存在的 8 条红被"修好" —— 它们是被**语料 + 口令**两件环境前提补齐后才通过的；
  **任何一台新机器不补这两件事仍会红**（属环境前提，不属代码债）。
- `users` 有 1 行 **≠** 账号体系落地 —— **仍 0 真实读者**，G-18 那条「红灯](26)绿灯只代表表存在」的边界照旧。
- R28 / R29 转「闭环」**≠** 引用口径自洽 —— 残留另立 **R30**。
