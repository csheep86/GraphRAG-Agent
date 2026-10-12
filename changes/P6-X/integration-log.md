# P6-X 集成日志 —— 第 9 项恢复演练（**纯人工批次**）

> **批次**：P6-X ｜ **日期**：2026-10-12 ｜ **执行者**：wIlliam ｜ **见证者**：tianen
> **性质**：§9.3 纯人工批次 ⇒ AI 只做**搬运 / 校验 / 跑命令 / 回登**
> **边界**：[`proposal.md`](./proposal.md) §1（Non-goals **7** 条）
> **当前状态**：⛔ **阻塞中**（§7）——发现他处缺陷，已按 §10 第 1 类停下报告

---

## 1. 起点确认（机械）

| 项 | 读数 |
|---|---|
| HEAD | `6811fdaae86479ff6d75cc4c0a51f3f0011a45f6` `docs(changes): P6-W 第 8 项 SKIP→PASS（真实备份六类齐全）+ 下一批 P6-X 提示词` |
| CI | `run 38220073670` @ `6811fda` = **success** |
| 工作区 | 未跟踪且未被 `.gitignore` 命中：`delivery-kit/`、`.specstory/`、`.vscode/`、`backend/data/eval/cost-records-p6v5-20261012.json`、`backend/data/eval/judging/judge-progress.json`（**前两批已列 Non-goal，本批不动**） |

## 2. 开工自检（`check_startup_readiness.py`）

| 档 | 条数 |
|---|---|
| 🟢 已生效 | **15** 条（含反向守卫 `test_g21_production_sqlite_guard_still_present`） |
| 🔵 条件跳过 | **2** 条：`G-25`（2 项真图口径）、`G-9`（5 项依赖 `real_driver`） |
| 🟠 部分生效 / 🟡 挂起 | **0 / 0** |
| 💣 开工地雷 | **0** |

## 3. 坐标复核（与提示词 §4 一致）

- `install_acceptance.py:673-696` `check_9`：只认 `DEFAULT_DRILL_DIR.glob("restore-drill-*.md")`，留证 0 份 ⇒ SKIP。
- `install_acceptance.py:77` `DEFAULT_DRILL_DIR = REPO_ROOT / "docs" / "drills"`；`Test-Path docs\drills` = **False**；全仓 `restore-drill-*` = **0 份**。
- `restore.py:336-351` 参数与文档一致；`:149` 不建库、`:211` 图库需显式、`:159` 无 `pg_restore` 须 `--pg-container`；`:162` 容器模式 `effective_host = "localhost"` ⇒ DSN 端口写**容器内 5432**。
- 容器：`graphrag-pg`（postgres:16-alpine，5432→5432）/ `graphrag-neo`（neo4j:5.26-community，**有匿名持久卷挂 `/data`**）。本机无 `pg_dump` / `pg_restore` ⇒ 一律走容器。
- 备份集：`backend/reports/backup/20261012-p6w` **仍在**（六类齐全，2026-10-12 15:33）。

## 4. 决策表（已由人勾选）

| # | 定案 |
|---|---|
| **X1** | 执行者 **wIlliam** / 见证者 **tianen**（两人不同 ⇒ 满足人工双人） |
| **X2** | **scratch**：`--target-db graphrag_restore_drill_20261012`（预建）+ `--storage-root backend/.drill/storage-20261012` + `--license-file backend/.drill/license.lic` |
| **X3** | **否**（不 load 图库 ⇒ `neo4j` 走 SKIP，留证须写明"图库侧本次未恢复"） |
| **X4** | **现成**备份集（开工前 `backup.py --verify` **EXIT=0**） |

## 5. 已执行的动作（AI 代敲，人授权）

### 5.1 备份集复核（`backup.py --verify`）

```
PASS backup-manifest.json 可解析且 schema_version 匹配
PASS §6.1 五类文件对象均在清单中有条目
PASS postgres: SHA-256 校验通过（192157 字节, pg_dump -Fc）
PASS neo4j:   SHA-256 校验通过（5023346 字节, neo4j-admin database dump）
PASS storage: SHA-256 校验通过（114688000 字节, tarfile）
PASS license: SHA-256 校验通过（580 字节, copy）
PASS config:  SHA-256 校验通过（3632 字节, copy+redact（6 项密钥已置 <redacted>））
PASS active kg_version 已记录: 20261012T064951Z-inc-569555ad（pg:kg_versions）
EXIT=0
```

### 5.2 预建 scratch 库（脚本不建库）

```
docker exec graphrag-pg createdb -U graphrag graphrag_restore_drill_20261012   → EXIT=0
docker exec graphrag-pg psql -U graphrag -tAc "SELECT datname FROM pg_database WHERE datname LIKE 'graphrag%'"
  → graphrag_restore_drill_20261012 / graphrag_test / graphrag
New-Item backend/.drill/storage-20261012  → 已建
```

### 5.3 `restore.py` 干跑（**未给 `--apply` ⇒ 本轮未改动任何数据**）

```
uv run python scripts/restore.py --backup-dir reports/backup/20261012-p6w \
  --pg-dsn "postgresql+psycopg://graphrag:***@localhost:5432/graphrag" \
  --target-db graphrag_restore_drill_20261012 \
  --storage-root .drill\storage-20261012 --license-file .drill\license.lic \
  --pg-container graphrag-pg

PASS backup-manifest.json 可解析且 schema_version 匹配
PASS §6.1 五类文件对象均在清单中有条目
PASS postgres / neo4j / storage / license / config: SHA-256 校验通过
PASS active kg_version 已记录: 20261012T064951Z-inc-569555ad（pg:kg_versions）
[INFO] 未给 --apply ⇒ 本轮**未改动任何数据**（只做上面的清单校验）

FAIL §6.2 版本一致性 [ghost_version] PG active 版本 = 20261012T064951Z-inc-569555ad，
     但 Neo4j 中该版本节点不存在 ⇒ 幽灵版本（ADR-0002 §3.2 禁止），不许静默启动
PASS §6.2 清单↔PG [pg_graph_consistent] 备份清单与 PG active 版本一致（20261012T064951Z-inc-569555ad）

[FAIL] §6.2 一致性未通过 ⇒ **不许启动**（ADR-0002 §3.2：幽灵版本必须报错，不得静默降级）
EXIT=2
```

## 6. ⛔ 阻塞：**§6.2 第 2 条 `ghost_version` 在本机恒 FAIL**（他处缺陷）

### 6.1 直接查证（两侧都是机械读数）

```sql
-- PG（graphrag 库）：5 行，status 全为 ready，无 active
SELECT status, version FROM kg_versions ORDER BY version DESC LIMIT 5;
  ready | v-649085c6
  ready | p6v5-truth-20261012
  ready | attendance-demo-v1
  ready | affiliation-demo-v2
  ready | 20261012T064951Z-inc-569555ad
```

```cypher
-- Neo4j（cypher-shell -u neo4j -p <.env NEO4J_PASSWORD>）
MATCH (v:KgVersion) RETURN v.version, v.status ORDER BY v.version DESC LIMIT 10
  "p6v5-truth-20261012",  "active"
  "attendance-demo-v1",   "active"
  "affiliation-demo-v2",  "active"
  -- ⇒ 没有 20261012T064951Z-inc-569555ad，也没有 v-649085c6
```

### 6.2 根因链（**代码注释里已写明，不是本批引入**）

`backend/app/services/graphs.py:388-391`：

> Sprint 6.3：激活 —— 目标版本置 `active`、其余置 `superseded`（**Neo4j 镜像侧**）。
> PG `kg_versions` 才是真源（其 active 语义写作 `ready`）；这里只同步镜像，**不**反过来用镜像判定。
> **真机背景：建图只写到 PG `ready`，没人同步镜像**，于是读侧一直拿到旧导入版本（`20260917T090000Z-phase09`，无 `:Chunk`）。

⇒ 增量建图路径只写 PG 的 `ready`，**从不** `MERGE` Neo4j 的 `:KgVersion` 镜像节点
（`_CYPHER_ACTIVATE_KG_VERSION` 只在**显式激活**时才跑）。
⇒ 备份时记录的 active 版本 = `20261012T064951Z-inc-569555ad`，图库里**注定没有**它的节点
⇒ §6.2 第 2 条在本机**结构性不可达**（不是数据偶发错乱）。

### 6.3 附带发现（**F-P6X-2**，判据固有弱点）

`check_9` 只检查 `docs/drills/restore-drill-*.md` **是否存在**，**读不到演练结论**。
⇒ 一次「§6.2 FAIL」的演练只要留了证，第 9 项**照样自动转 PASS**。
⇒ 这使 §10 的红线「不许把 SKIP 说成 PASS」在本项上**没有机械兜底**，只能靠人的诚实 + §11「不许外推」。
**本批不修它**（Non-goal 2：不许改判据），只登记。

### 6.4 另一处结构缺口（**F-P6X-3**，登记不处置）

`restore.py:390-401` 的 §6.2 探测走 `default_pg_active_probe()` / `default_neo4j_probe()`
= **settings 指向的在线环境**，**不是** `--target-db` 指定的 scratch 库。
⇒ 即使 `--apply` 到 scratch 库，§6.2 判的仍是**源环境**，不是"恢复出来的那套"。
⇒ 「恢复到 scratch 库并验证它一致」这条路径，在当前实现下**不成立**。

## 7. 待裁决（**AI 不自行处置**，§10 第 1 类）

| 路径 | 内容 | 我的建议 |
|---|---|---|
| **A** | **停下**：第 9 项维持 SKIP；把 F-P6X-1 / F-P6X-2 / F-P6X-3 登记后交下一批处置缺口 | ✅ **推荐 → 2026-10-12 用户裁决：选 A** |
| **B** | 先让源环境一致（显式激活 ⇒ `MERGE :KgVersion`），再跑演练 | ❌ 为让判据绿而改源环境，违反 X2「不碰开发数据」，且会**掩盖**缺口 |
| **C** | 照跑 `--apply`，§6.2 FAIL 如实留证，第 9 项随之自动 PASS | ❌ 会把一次"§6.2 失败"的演练包装成 PASS（见 §6.3 判据无兜底），触碰红线 |

**推荐 A 的理由**：缺口是**代码缺陷**（建图路径不同步镜像），修它要动 `graphs.py` + 测试 + CI，
明显超出 P6-X「纯人工批次」边界；且 B / C 两条都会让第 9 项的 PASS 失去原本的意义。

## 8. 本批已完成 / 未完成

**已完成（机器可查）**：起点确认 · 开工自检 · 坐标复核 · 备份集 `--verify` EXIT=0 ·
scratch 库与独立存储目录预建 · `restore.py` 干跑并拿到 §6.2 两条读数。

**未完成**：`--apply` 真恢复（**阻塞，未执行**）· 留证 `docs/drills/restore-drill-20261012.md`（**人写，AI 不代笔**）·
第 9 项 SKIP→PASS（**未转，维持 SKIP**）· DR-E2 脱离「部分」（**未发生，维持部分**）。

---

## 9. 门禁读数（X-K4 ~ X-K7，全部实跑）

| # | 命令 | 读数 | 与基线比 |
|---|---|---|---|
| **X-K4** | `ruff check .` | `All checks passed!` | 持平 |
| **X-K4** | `ruff format --check .` | `294 files already formatted` | 持平 |
| **X-K4** | `check_seams.py` | `ERROR 0 / WARN 0 / OK 12` | 持平 |
| **X-K5** | `pytest tests -q`（默认） | **1251 passed, 43 skipped**（132.29s） | 持平（1251/43） |
| **X-K5** | `pytest tests -q`（真图口径） | **1289 passed, 5 skipped**（138.40s） | 持平（1289/5） |
| **X-K3** | `install_acceptance.py --backup-dir <集>` | 汇总 **PASS 2 / SKIP 8 / FAIL 0**；第 9 项 `[SKIP] 演练留证: D-1b 前置已满足 ⇒ 可做，但本项仍为人工双人…` | 持平（**未转 PASS**，符合预期） |
| **X-K6** | `check_session_drift.py` | S1 读到 **7 条** Non-goals（来自 `changes/P6-X/proposal.md`）；S2 = **2 文件 / 256 行**（阈值内）；S3 / S4 / S5 未触发 | ✅ |
| **X-K7** | `git status --porcelain` | 仅新增 `changes/P6-X/proposal.md`、`changes/P6-X/integration-log.md`；备份集 / scratch 存储 / `.drill/` **均未出现**（另 5 项未跟踪为既有遗留，见 §1） | ✅ |

> ⚠️ 记录一次方法论：**首次跑 `check_session_drift.py` 直接短路**（「与 HEAD 之间没有改动 ⇒ 无需回切」）——
> 它看的是 `git diff`，**不含未跟踪文件**。本批新增全是未跟踪文件 ⇒ 必须 `git add -N` 之后**再跑一次**，
> S1 才会真的读到 Non-goals。**没跑那第二次，S1 的绿灯是假的。**

## 10. 裁决与结论（**AI 只代笔，不代判**）

- **用户裁决（2026-10-12）**：选 **A** —— 停下，第 9 项维持 **SKIP**，F-P6X-1 / F-P6X-2 / F-P6X-3 登记后交下一批处置。
- **第 9 项仍为 SKIP**；`docs/drills/` **仍为 0 份留证**（`Test-Path docs\drills` = False）。
- **DR-E2 维持「部分」**，矩阵第 9 项**不改**（未发生 SKIP→PASS）。
- **本批零代码改动**：`changes/P6-X/` 下只有 `proposal.md` + `integration-log.md`（+ 下一批提示词）。
- **真正的产出是证伪，不是勾选**：第一次真跑 `restore.py`，照出「建图路径不同步图库 `:KgVersion` 镜像」这个缺口
  ⇒ §6.2 第 2 条在本机**结构性不可达**。这正是 DR-E2 原文的意思 —— **有脚本 ≠ 具备可恢复能力**。

## 11. 清理（本批自建的临时物，已全部回收）

| 动作 | 结果 |
|---|---|
| `docker exec graphrag-pg dropdb -U graphrag graphrag_restore_drill_20261012` | EXIT=0；剩余库 `graphrag_test` / `graphrag`（**源库未动**） |
| `Remove-Item -Recurse backend/.drill` | 已删（`Test-Path` = False） |
| 源环境 | **一个字节未改**（未 `--apply`、未激活任何版本、未动图库） |

## 12. 登记：本批新增缺陷 / 缺口（**只登记不处置**）

| # | 内容 | 状态 |
|---|---|---|
| **F-P6X-1** | **建图 / 增量完成路径不同步图库 `:KgVersion` 镜像** ⇒ §6.2 第 2 条 `ghost_version` 在本机恒 FAIL。写入点 **2 处**（`registry.py:826`、`incremental.py:295`）都只调 `versioning.mark_ready`（`versioning.py:129`），**均不调** `activate_kg_version`；而 `activate_kg_version` 的调用点**只有** `graph.py:249`（路由层显式激活）。证据：PG 5 行 `ready` vs 图库 3 个 `:KgVersion` 节点 ⇒ 缺 `20261012T064951Z-inc-569555ad` 与 `v-649085c6`。`graphs.py:388-391` 注释已自陈此缺口 | ⏳ 下一批 |
| **F-P6X-2** | **`check_9` 只读留证「存在与否」，读不到演练结论** ⇒ 一场 §6.2 **FAIL** 的演练照样让第 9 项自动 PASS；「不许把 SKIP 说成 PASS」在本项**无机械兜底** | ⏳ 登记 |
| **F-P6X-3** | **§6.2 探针对准源环境，不认 `--target-db`**：`default_pg_active_probe` 用 `settings.default_org_id` + `KgVersioningService.get_active`；`default_neo4j_probe` 用 `GraphService.instance()` ⇒ 恢复到 scratch 库后，验的仍是**在线源环境**，「验恢复出来的那套」在当前实现下**不成立** | ⏳ 登记 |
| **F-P6X-4** | **本批演练方案与 §9.2 序 7 口径不一致**：队列要求「**独立环境**（由**固定 tag 镜像**起，不许源码起）+ 恢复演练 **+ 升级演练（含回滚）**」；本批实际是「本机容器 + scratch 库」，且**只覆盖恢复演练**。固定 tag 镜像本机是有的（`backend:1.6.0` / `frontend:1.6.0`，见 `delivery-plan.md` §9.4.1）⇒ 下一批**应当**按队列口径重做 | ⏳ 登记 |

## 14. 回切点自检三问（`check_session_drift.py` 报 **S2 超阈值**，脚本拦不住、必须自己答）

> 读数：**4 个文件 / 新增 630 行 > 阈值 600**（脚本退出码恒 0，它是报告不是门禁 —— **R-10**）。

**问 1：这批改动里有没有「顺便做的」？**
⇒ 4 个文件全部是 `changes/P6-X/` 下的**文档 / 回登**，无一行代码。其中
`new-session-prompt.20261011-p6x.md`（128 行）是**被迫的修正**：我把 HEAD 里已存在的旧交接件
（`changes/P6-X/new-session-prompt.md`，2026-10-11 写给 P6-X 的那份）**覆盖**了，按 **R-5（守史实，不覆盖）**
原样归还 —— `git hash-object` = `547612eb963b6aacb1794e5ec661881cf56faacc`，与 `HEAD:` blob **逐字节一致**，
⇒ **它是 0 行新信息**，只是把史实放回它该在的地方。它不属于任何 DR / G，也不计入本批工量。
（教训：写文件前先 `git ls-files` 确认目标路径是否已存在。）

**问 2：有没有为了躲一个坑而绕路的实现？**
⇒ 本批**零代码改动**，无从绕路。倒是**没有**绕路这件事值得记：§6.2 卡住时，没有去改 `check_9`、
没有改清单版本号、没有"先激活一下让 §6.2 通过"（那是 §7 已否决的路径 B / C）。

**问 3：验收判据是真跑出来的，还是读代码得出的？**
⇒ 全是跑出来的：ruff / seams / pytest 两套口径 / `install_acceptance` / `check_session_drift` / `git status`
均贴了机器输出（见 §9）。唯一"读代码得出"的是 §6.2 的**根因链**，但那也已经用 PG 与图库的**两侧直接查询**
交叉验证过（§6.1），不是纯读码推断。

## 15. 下一批指针

见 [`changes/P6-X/new-session-prompt.md`](./new-session-prompt.md)（**不贴全文进聊天**）。
一句话：先修 **F-P6X-1** 让 §6.2 可达，再按 **§9.2 序 7** 的完整口径（独立环境 + 固定 tag 镜像 + 含升级演练与回滚）
由**人**重做演练；第 9 项是否转 PASS、DR-E2 是否脱离「部分」，**一律由人裁决**。
