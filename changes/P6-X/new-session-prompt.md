# 下一批开场提示词（v1 · 2026-10-12）—— **P6-X2：修 F-P6X-1 缺口 + 按 §9.2 序 7 完整口径重做演练（混合批次）**

> **本文件位置**：`changes/P6-X/new-session-prompt.md`（**当前批次目录下、写给下一批**）
> **上一份提示词**：[`../P6-W/new-session-prompt.md`](../P6-W/new-session-prompt.md)（已执行完）
> **上一批日志**：[`integration-log.md`](./integration-log.md)（§6 阻塞根因、§9 门禁、§12 缺陷登记）
> 📦 **旧交接件已归档**：本路径原有一份 **2026-10-11 写给 P6-X** 的交接件（已执行完），
> 现按 **R-5（守史实，不覆盖）** 归档为 [`new-session-prompt.20261011-p6x.md`](./new-session-prompt.20261011-p6x.md)
> （blob `547612e`，与 HEAD 逐字节一致）。**它 §0.5 / §3 的必读坐标与「期望值表」要求已并入本文 §4.1 / §5.1**。

---

## 0. 一句话定位

**先修「建图路径不同步图库 `:KgVersion` 镜像」这个缺口（F-P6X-1，AI 做），让 §6.2 第 2 条变得可达；
再由「人」按 `docs/delivery-plan.md` §9.2 序 7 的完整口径（独立环境 + 固定 tag 镜像 + **恢复演练 + 升级演练含回滚**）重做演练，
把第 9 项 SKIP→PASS。**

⚠️ **两场演练的判据都不止"跑起来"**：恢复演练要求**恢复后跑通 §10 的 1~6 项**；
升级演练要求**回滚后重跑 1~6 项**证明回到可用态（旧交接件 §3，坐标见本文 §4.1）。

本批是**混合批次**：修代码 AI 可以做主体；**演练那一段仍旧是「人做主体」**，红线与 P6-X 完全同款。

---

## 1. 起点确认 + 执行模式

### 1.1 起点

**起点 = 本 MD 所在的那一笔提交**（刻意**不钉** hash —— 上一份提示词把 HEAD 写死后，自身落成那一笔就触发了它的停机条件）。开学第一件事：

```bash
git log -1 --format="%H %s"            # 应含 changes/P6-X/new-session-prompt.md
gh run list --limit 1 --json databaseId,conclusion,headSha
gh run view <id> --json jobs --jq '.jobs[] | [.name,.conclusion] | @tsv'   # 4 项 success
```

### 1.2 执行模式：**混合批次**（**先看这一节**）

| 段落 | 谁做主体 | 依据 |
|---|---|---|
| **① 修 F-P6X-1**（建图 / 增量完成路径同步图库镜像 + 测试 + CI） | **AI 做主体**，修法**由人裁决** | 属代码缺陷修复，非 §9.3 三条 |
| **② 演练**（恢复 + 升级 + 回滚，留证 `docs/drills/`） | **人做主体**（§9.3 第 2 条） | 执行者 ≠ 见证者，AI 不得单独收口 |

⇒ **AI 在段落 ② 只允许做四件事**（与 P6-X 同款，不许退化）：**搬运**（整理步骤）/ **校验**（跑 `--verify`、门禁、贴输出）/ **跑命令**（人授权后代敲）/ **回登**（写进 `changes/P6-X2/integration-log.md`）。

**明确不许**（红线，不是建议）：

- **不许代写** `docs/drills/restore-drill-*.md` 与升级演练留证的正文（一个字都不许替人写）；
- **不许代填 / 代判**任何演练结论（"恢复成功""一致性通过""回滚成功"只能由执行者 + 见证者写）；
- **不许代收口** —— 第 9 项即使转 PASS，DR-E2 的状态回登也须由**人**确认后再由 AI 代笔；
- **不许把 SKIP / FAIL 说成 PASS**，也不许为了让第 9 项翻绿去改判据或改环境（Non-goal 1 / 9）。

### 1.3 为什么下一批是 P6-X2（三条机械理由）

1. **第 9 项仍 SKIP，且阻挡点已被机械证出**：`docs/drills/` **0 份留证**；而更关键的是 P6-X §6 已证出
   **§6.2 第 2 条在本机结构性不可达** —— 不是"人没做"，是"做了也过不了"。先修缺口，否则重做 10 次都一样。
2. **修复面已 ¥0 查实，工量可估（不是无底洞）**：
   - 写 PG `ready` 的落点 **2 处**：`registry.py:826`、`incremental.py:295`（定义 `versioning.py:129`）；
   - 同步图库镜像的调用点 **只有 1 处**：`graph.py:249` → `graphs.py:1474` `activate_kg_version` → `:1496` `_CYPHER_ACTIVATE_KG_VERSION`（`MERGE (v:KgVersion …)`）；
   - ⇒ 两处建图完成路径**都不调**镜像同步，缺口闭合面很窄。
3. **本批的演练方案与队列口径不符（F-P6X-4）**：§9.2 序 7 要的是「**独立环境**（由**固定 tag 镜像**起，不许源码起）+ 恢复演练 **+ 升级演练（含回滚）**」；
   P6-X 实际做的是「本机容器 + scratch 库」且**只覆盖恢复演练** ⇒ 即便缺口修完，照旧方案做出来的第 9 项**不满足队列口径**。
   固定 tag 镜像本机已有（`graphrag-agent/backend:1.6.0` / `frontend:1.6.0`，见 `delivery-plan.md` §9.4.1）。

---

## 2. 开工自检（**动手前必做，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

按最后一列行事：`[OK]` = 真在拦；`[~~]` = 管一半；`[--]` = 挂起（对应 DR **不得**宣称完成）。

> ⚠️ **方法论教训（P6-X §9 记下的坑，别再踩）**：`check_session_drift.py` 看的是 `git diff`，**不含未跟踪文件**。
> 本批新增文件在未跟踪状态时，第一次跑会直接短路成「与 HEAD 之间没有改动 ⇒ 无需回切」，**S1 的绿灯是假的**。
> ⇒ **跑之前先 `git add -N <新文件>`，再跑一次**，确认 S1 真的读到了本批的 Non-goals。

---

## 3. 边界纪律（**Non-goals 9 条，不许越过**）

| # | 边界 | 判据 / 说明 |
|---|---|---|
| 1 | **不许改 `check_9` / §10 的表换绿**（F-P6X-2 只登记） | 判据"只读留证存在与否"是它的固有弱点，**本批不改**，只登记 |
| 2 | **不修 F-P6X-3**（§6.2 探针对准源环境、不认 `--target-db`），**只登记** | 属另一批次（要连带改 `default_pg_active_probe` / `default_neo4j_probe` 的注入方式） |
| 3 | **AI 不得代做演练 / 代写留证正文 / 代判结论** | §1.2；§9.3 第 2 条 |
| 4 | **不起任何真 LLM 调用**（可持续到 D1 另行批准为止） | 本批动作必须 ¥0 |
| 5 | **不做交付动作** —— release notes / tag / 对外验收一律不碰 | 纪律 **R-10**；留证须标「内部演练，非客户现场验收」 |
| 6 | **不许碰生产 / 目标环境的真实数据** | 演练落到**独立环境**（由固定 tag 镜像起），不是本机开发容器 |
| 7 | **不动 `cost_metrics` /「图元素个数」同量纲裁决** | 那是 P6-V3 / P6-V4 的地盘（C3-a / C3-b） |
| 8 | **不顺手清 `delivery-kit/` `.specstory/` `.vscode/` 等遗留未跟踪项** | 前两批已列 Non-goal，**只登记不动** |
| 9 | **不许为了让第 9 项翻绿而改环境 / 改判据**（含"先激活一下让 §6.2 通过"这种） | P6-X §7 路径 B / C 已被明确否决 |

> 回切点（每个子任务收尾）：`cd backend && uv run python scripts/check_session_drift.py`
> **S1 报「没有 Non-goals」⇒ 先停下来补边界**。

---

## 4. 已查证坐标表（**2026-10-12 实读，开工必须先复核行号**）

| 事项 | 坐标 / 命令 | 机械结论 |
|---|---|---|
| 缺口写入点 | `app/tasks/registry.py:826` `versioning.mark_ready(`；`app/services/kg/incremental.py:295` 同 | **2 处**建图 / 增量完成路径 |
| 定义 | `app/services/kg/versioning.py:129` `def mark_ready` | 只写 PG |
| 镜像同步唯一入口 | `graph.py:249` → `app/services/graphs.py:1474` `activate_kg_version` → `:1496` `_CYPHER_ACTIVATE_KG_VERSION`（`:381` `_QUERY_KG_VERSION_STATUS` 用 `MATCH (v:KgVersion {version:$version})`） | **路由层显式激活才调**，建图路径不调 |
| 自陈缺口的注释 | `app/services/graphs.py:388-391` | 原文：**「建图只写到 PG `ready`，没人同步镜像」** |
| 两侧现状 | PG `kg_versions` **5 行全 `ready`**；图库 `:KgVersion` **3 个** | 缺 `20261012T064951Z-inc-569555ad` 与 `v-649085c6` |
| §6.2 判据实现 | `app/services/backup.py:370-418` `evaluate_version_consistency`；`restore.py:390-415` | 错位 ⇒ **EXIT=2**；`graph_unreachable` 也判**失败** |
| 判据第 9 项 | `backend/scripts/install_acceptance.py:673-696` `check_9`；`:77` `DEFAULT_DRILL_DIR = REPO_ROOT/"docs"/"drills"` | 只认留证**真实存在**；`docs/drills/` 现状 **0 份** |
| restore 参数 | `restore.py:336-351` | `--backup-dir` 必填 / `--apply` / `--pg-dsn` / `--target-db`（**须预建**）/ `--storage-root` / `--license-file` / `--neo4j-container`（显式给才 load，要求停服）/ `--pg-container` |
| 容器 | `docker ps` | `graphrag-pg`（postgres:16-alpine）/ `graphrag-neo`（neo4j:5.26-community，**有匿名持久卷挂 `/data`**） |
| 本机无 pg 客户端 | `where.exe pg_dump` ⇒ 未找到 | 一律走 `--pg-container graphrag-pg`（容器内 host=`localhost`、端口 **5432**） |
| 备份集 | `backend/reports/backup/20261012-p6w`（六类齐全，`--verify` EXIT=0） | ⚠️ **未入库（gitignore）**，下批演练前可能被清 ⇒ 需现跑一次新的 |

### 4.1 必读坐标（**旧交接件 §0.5 五份，开工前逐份复核是否过时**）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`docs/deployment-spec.md` §6.4（:211-226）+ §10 第 9 项（:418）** | **判据原文**：季度 ≥1 次、**独立环境恢复 + 跑通 §10 的 1~6 项**、留证文件名 `restore-drill-<日期>.md` |
| 2 | **`docs/deployment-spec.md:431`** | 「**恢复演练 0 次 ⇒ 不得据此宣称可恢复**」—— 这句话只有本批能改写 |
| 3 | `docs/delivery-plan.md` §9.4.1 | D-1b 解除的实测读数（tar 496,532,480 字节 / 镜像 `sha256:2fcd0ed1389e`、`sha256:6e0c62a6a2f6` / `--verify` 7 项） |
| 4 | `changes/P6-W/integration-log.md` §6 / §7 | **残留风险 7 条**决定演练会撞到什么 |
| 5 | `backend/scripts/install_acceptance.py:673-696` | 它怎么判断"演练有没有做" ⇒ 留证得落它认得的形式，否则第 9 项继续 SKIP |

> **✅ 三件事已于 2026-10-12 由 AI 查证完毕（¥0、零代码改动）**
> ⇒ 完整读数见 [`integration-log.md` §13](./integration-log.md)。**摘要（别照旧口径外推）**：
>
> ① **active = 同 org 最新 `ready` 的那一行**（`versioning.py:203-212`，`ready_at DESC LIMIT 1`），**不是**「唯一 ready」
> ⇒ PG 5 行全 `ready` 属**设计内行为**，唯一性**不需要修**；实测 active = `20261012T064951Z-inc-569555ad`（图库**无**此节点）。
> ⚠️ 文档措辞「唯一 ready」与实现不符 ⇒ 已登记 **F-P6X-6**。
>
> ② 镜像 `MERGE` **幂等 ✅**；但**失败无回滚**（PG 已 commit ⇒ 同步失败就留下 ghost），且 `MERGE` 在**无数据时也会凭空造空壳节点**
> ⇒ 修法必须显式回答「**图库不可用时怎么办**」：上抛（图写完却判 failed）/ 旁路吞掉（静默留 ghost）/ 回滚 PG（**越界**）。
> ⚠️ 另有新发现：`_CYPHER_SUPERSEDE_OTHER_VERSIONS`（`graphs.py:402-408`）**不分 org**，会把其它租户节点一并 supersede；
> 图库 3 个 `:KgVersion` `org_id` 全 `NULL`、全 `active`；兜底查询按**字典序**取 active，与 PG「最新 ready」**不同口径** ⇒ 已登记 **F-P6X-5**。
>
> ③ `test_consistency_fails_on_ghost_version` **不会被推翻**（测的是纯函数 + 假探针，与「谁同步镜像」正交）
> ⇒ 它一红就等于修法越界，立刻停下。**但** A 会打红 `test_kg_versioning.py` 的 **5 处** `mark_ready`、
> B 会打红 `test_kg_build_executor.py`（两者默认口径都连不上 Neo4j）⇒ **任何修法都连带「测试面」工作，不是加一行调用**。

---

## 5. 决策表（**须由人勾选后才开工**）

| 编号 | 决策 | 选项 | 默认 |
|---|---|---|---|
| **Y1** | **F-P6X-1 怎么修** | A：`mark_ready` **内部**同步镜像（一处收口，但把图库写入塞进版本服务）<br>B：在 `registry.py:826` / `incremental.py:295` **两处显式调** `activate_kg_version`（调用点显式，但两处都要记得）<br>C：**只登记不修**（本批只做演练，缺口另立批） | **空 ⇒ 段落 ① 不开工**，须人拍板（**属接缝 / 行为变更，AI 不自选**） |
| **Y2** | 演练环境 | 独立环境（**固定 tag 镜像**起）/ 本机 scratch | **独立环境**（§9.2 序 7 原文：不许源码起） |
| **Y3** | 是否含**升级演练 + 回滚** | 含 / 只做恢复 | **含**（队列口径；只做恢复 ⇒ 不满足序 7，第 9 项**不得**据此回登） |
| **Y4** | 执行者 / 见证者（**须两人不同**） | 填人名（P6-X 为 **wIlliam / tianen**，须重新确认**当场在场**） | 空 ⇒ **段落 ② 不开工** |
| **Y5** | 是否顺手修 F-P6X-2 / F-P6X-3 | 修 / 不修 | **不修**（Non-goal 1 / 2） |
| **Y6**（新增） | 是否把**镜像 org 维度 / supersede 范围**纳入本批（F-P6X-5） | 纳入 / 只登记 | **只登记**（默认）⇒ 若选"纳入"，Y1 的 A / B **都不够**，须先扩选项（如 D：只 `MERGE` 不 supersede 的窄同步） |

> **Y1 补充（2026-10-12 查证，见 `integration-log.md` §13）**：A / B **都会**触发 `_CYPHER_SUPERSEDE_OTHER_VERSIONS`
> 的**不分 org** 的 supersede（F-P6X-5），且**都**要连带处置「图库不可用时怎么办」+「既有测试面」。
> ⇒ 若人认为「跨租户 supersede / 镜像 org 维度」属本批范围，**先扩 Y1 选项再拍板**；**AI 不自选**。

### 5.1 ⚠️ **期望值表必须先定，不许演练当天临时定**（旧交接件 §3 的硬要求）

开工第一件事：把「独立环境里 §10 十项的**预期读数**」写进本批 `proposal.md`，逐项写清
**预期 PASS / 登记过的 SKIP（附原因）/ 预期 FAIL**，演练当天**只对表，不临时解释**。

> 已知参照（**本机**那一趟，P6-W）：**PASS 3 / SKIP 6 / FAIL 1** —— 缺的是目标环境的 org B 授权、真 LLM 链路、双人。
> ⇒ 独立环境里同样的 SKIP 若在预期内，就是**登记过的 Skip**，**不是回归**。
>
> **这张表不先定好，演练当天会被读成"失败"，接着就会有人想把判据改松。**（这正是 Non-goal 1 / 9 要防的）

---

## 6. 已完成项（**别重做**）

- 起点 / 自检 / 坐标复核 / 备份集 `--verify` EXIT=0 —— P6-X §1~§5.1。
- scratch 库与 `.drill/` **已建后已回收**（`dropdb` EXIT=0、`Remove-Item`）⇒ 下批**不复用**这套本机方案（F-P6X-4）。
- `restore.py` 干跑已跑通并拿到 §6.2 两条读数（清单↔PG **PASS**、版本一致性 **ghost_version FAIL**、EXIT=2）—— **结论别重跑一遍才知道，直接引用**。
- 门禁全跑过：默认 **1251/43**、真图 **1289/5**、ruff **294 files**、seams **OK 12**。
- **第 9 项维持 SKIP**；`docs/drills/` **0 份**；DR-E2 维持「部分」。
- **AI 段到此为止**：缺口修复**方案**由人裁决，演练**只能人做**。

---

## 7. 基线（**同侧比，不许跨口径**）

| 口径 | 数字 | 备注 |
|---|---|---|
| CI（4 项 job） | 最近一次绿：`run 38220073670` @ `6811fda` | 全 success |
| 本机 pytest 默认口径 | **1251 passed / 43 skipped**（132.29s） | 真图用例**默认 skip** |
| 本机 pytest 真图口径 | **1289 passed / 5 skipped**（138.40s） | 须显式设 `GRAPH_REAL_NEO4J_{URI,USER,PASSWORD}`（取自 `.env` 的 `NEO4J_*`，**别硬编码**） |
| `install_acceptance.py` **无参** | **PASS 1 / SKIP 9 / FAIL 0** | |
| `install_acceptance.py --backup-dir <集>` | **PASS 2 / SKIP 8 / FAIL 0** | 第 8 项 PASS；**第 9 项 SKIP**（本批要它转 PASS） |
| ruff / seams | All checks passed / **294 files**；**ERROR 0 / WARN 0 / OK 12** | |
| 护栏自检 | 🟢 **15** 条 / 🔵 条件跳过 **2** 条（G-25 ×2、G-9 ×5）/ 🟠 **0** / 🟡 **0** | |

> ⚠️ **本机绿 ≠ CI 绿**（历史教训：本机默认口径会跳过真图用例）。

---

## 8. 验收判据（**必须实际跑出，不许读代码得出**）

| # | 判据 | 命令 / 动作 | 通过标准 |
|---|---|---|---|
| **X2-K1** | 缺口真的闭合 | `registry.py:826` / `incremental.py:295` 之后，图库出现对应 `:KgVersion` 节点 | 新增用例**真的跑**；`test_consistency_fails_on_ghost_version` **不被推翻**（被推翻 ⇒ 修法越界，停下） |
| **X2-K2** | §6.2 第 2 条变得**可达** | 新备份集上跑 `restore.py`（不带 `--apply`） | `[PASS] §6.2 版本一致性 [pg_graph_consistent]` + `[OK] restore 通过`，**EXIT=0** |
| **X2-K3** | **反面验证**（必须红） | 改清单版本号 / 造一个幽灵版本 | **EXIT=2** 且输出含 `ghost_version`（不许静默） |
| **X2-K4a** | **恢复演练**（**人做**） | 独立环境（固定 tag 镜像起）恢复 **+ 跑通 §10 的 1~6 项** | 机器输出贴全；**任一环节失败就如实写失败**，不许挑好看的贴；与 §5.1 期望值表逐行对 |
| **X2-K4b** | **升级演练（含回滚）**（**人做**） | 升级 → 失败或不满意 → **回滚到升级前** ⇒ **重跑 1~6 项**证明回到可用态 | 回滚后的读数**必须**贴；只贴"回滚成功"四个字不算 |
| **X2-K5** | **留证出现**（**人写**） | `docs/drills/restore-drill-<日期>.md`（+ 升级演练留证） | 文件名匹配、位置是**仓库根** `docs/drills/`；标「内部演练，非客户现场验收」；写清**执行者 / 见证者**；**先有留证，再回登文档** |
| **X2-K6** | 第 9 项 **SKIP → PASS**（**自动**，不许手改） | `uv run python scripts/install_acceptance.py --backup-dir <集>` | 第 9 项 `[PASS] 演练留证: N 份留证: ...`；第 8 项保持 PASS |
| **X2-K7** | 静态 / 接缝 / 测试不倒退 | `ruff check .` + `ruff format --check .` + `check_seams.py` + `pytest`（两套口径） | All checks passed / 294 files；ERROR 0 / WARN 0 / OK 12；**1251/43 与 1289/5 都不降**（新增用例 ⇒ 应**上升**并更新基线） |
| **X2-K8** | 漂移 / 产物不入库 | `check_session_drift.py`（**先 `git add -N`**）+ `git status --porcelain` | S1 读到本批 Non-goals；S2 不超阈值；S3~S5 未触发；备份集 / 独立环境产物 / scratch 存储**一律不出现** |

---

## 9. 提交 / 推送纪律

0. **分支**：沿用 P4~P6-U —— **`main` 直推**，不另开分支。**留证优先于回登**：先有 `docs/drills/<...>.md`，再改 `deployment-spec` / `delivery-plan` / 矩阵。
1. **一笔提交只做一种角色**：后端修复（含测试）/ `docs/drills/` 留证（**人写**）/ changes 回登 / 文档登记 —— **分开**（脚本 / 判据类归**后端**，留证与文档回登归**架构师**，不得混在一个提交）。
2. Conventional Commits（`fix` / `docs` / `chore` / `test`）；commit body 必须带**实测输出**。
3. **推送后以 CI 为最终裁决**（4 项 job success）；`pre-commit` 未启用（**R-10**）。
4. **不许提交**：备份产物（`backend/reports/**`）、独立环境 / scratch 产物、`backend/storage/**`、`reports/eval/**`、`.drill/**`。
5. 网络：本机到 `github.com:443` 会间歇性 `Recv failure` ⇒ push 失败**先等 60~150 秒重试**，不改 remote、不 force。
   ⚠️ **2026-10-12 实测补充：光重试不够** —— 那次等了 **120s + 150s 共两次**都失败（第二次直接
   `Failed to connect to github.com:443 after 21133 ms`），而**同期** `gh api` 通、
   `Test-NetConnection github.com -Port 443` = `True` ⇒ 不是断网，是 **git-over-https 的 HTTP/2 通道**卡住。

   ```bash
   # 判因（两步，先别急着重试）：
   gh api /repos/csheep86/GraphRAG-Agent/commits/main --jq '.sha'   # 通 ⇒ 网络没断，只是 git 通道问题
   git log -1 --format="%h"                                          # 两者不同 ⇒ 提交确实没推上去

   # 解法（一次就通；-c 是单次调用覆盖，不改任何 git 配置）：
   git -c http.version=HTTP/1.1 push origin main
   ```

   ⇒ 顺序：**等一次 → 仍失败就用 `gh api` 判因 → 直接上 `HTTP/1.1`**，别在重试上耗掉 5 分钟。

   > ⚠️ **反例（2026-10-12 当晚实测，别外推成「HTTP/1.1 一定灵」）**：同一天晚些时候推 `2beb394` 时，
   > **HTTP/1.1 连试 3 次（等 0s / 90s / 150s）全部** `Failed to connect to github.com:443 after 21xxx ms`；
   > 而**同期** `gh api` 通、`Test-NetConnection github.com -Port 443` = `True`；
   > **改回默认通道（不加 `-c http.version`）一次就通**（`cb186b0..2beb394`）。
   > ⇒ 两条通道**都可能**卡，且**卡哪一条不固定**。`gh api` 判因只用于确认「网络没断」，
   > 解法是**两条都试**（先默认、再 `HTTP/1.1`），别在一条上耗掉 5 分钟。
   > （另测：SSH 通道 `git@github.com` 本机 = `Permission denied (publickey)` ⇒ **无 key**，HTTPS 是唯一通道。）

---

## 10. 升级用户的 4 类情况（**AI 不许自行处置**）

1. **修复撞上既有判据**（如 `test_consistency_fails_on_ghost_version` 被自己的修复推翻）⇒ 停下报告，**不许改测试让它绿**。
2. **修法需要新增 `settings.*` 配置项 / 动接缝 / 改契约** ⇒ 停下报告（ADR-0004 §2.1 登记集合 + `check_seams.py` 会拦）。
3. **CI 红了且复核两遍仍红** ⇒ 先按 §7 **同侧比**看是不是本次引入，**不许先改测试**。
4. **出现任何需要钱的环节**（联网恢复验证 / LLM / MinerU / 独立环境的云资源）⇒ 停下，回决策表补批准。

> **外加两条本批专属**：
> ① 只要出现「AI 要不要替人把留证写了」的念头 ⇒ **答案恒为不**，直接停下；
> ② 只要出现「先激活一下 / 先同步一下让 §6.2 通过」的念头 ⇒ **停下**，那正是 P6-X §7 已否决的路径 B。

---

## 11. 不许外推（**写到 != 做到**）

- **缺口闭合 ≠ 可恢复能力**：修完 F-P6X-1 只说明 §6.2 **可达**；恢复能力仍只能由**演练**证明。
- **第 9 项 PASS ≠ 目标 / 离线环境能恢复**：`check_9` 只读留证存在（F-P6X-2），**它读不到演练结论** ⇒ 别把 PASS 读成"验证通过"。
- **只做恢复演练 ≠ 满足 §9.2 序 7**：队列要的是恢复 **+ 升级（含回滚）**，缺一块就如实写缺一块。
- **一次演练 ≠ 客户现场验收**：留证必须标「内部演练，非客户现场验收」。
- **备份集那趟 n=1**：`postgres 192157 B` / `neo4j 5023346 B` / `storage 114688000 B` 都是单次读数，**不得**当作分布或上限。
- **第 9 项转 PASS 后，DR-E2 是否脱离「部分」须由人裁决** —— AI 只代笔，不代判。

---

## 12. 下一批指针

第 9 项 PASS 且 DR-E2 状态**由人裁决回登**之后，按 `docs/delivery-plan.md` §9.2 队列往下走
（序 8 = **P6-Y 知识时效 L2 端到端**；序 9 P7-B 已交付；序 13 P6-V4 ⏳ 未开工）—— **不由本批指定**。

下一份提示词仍按惯例落成 MD：`changes/<当前批次>/new-session-prompt.md`，**不贴全文进聊天**；
若其中包含演练段落，§1.2 的「演练 = 人做主体」**照抄过去**，不许退化成 AI 主导。
