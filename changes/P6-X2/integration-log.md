# P6-X2 集成日志（段落 ①：修 F-P6X-1 + F-P6X-5）

> **起点**：`2357b12`（P6-X2 立批骨架：Non-goals 9 条 + 前置核验 + §5.1 期望值表）
> **人裁决**：Y1′ = **纳入 F-P6X-5**（O-1：一次闭合镜像 org 维度，不留尾巴）；
> Y1″（真 LLM）按"开"预备 —— **段落 ① 不消耗 LLM**，演练前须再授权一次。
> **Y4（执行者 / 见证者）= 沿用 P6-X 已定：执行 `wIlliam` / 见证 `tianen`**
> （`changes/P6-X/proposal.md:16-17`、决策 X1 `:43`、`changes/P6-X/integration-log.md:3`）。
> ⚠️ **2026-10-13 更正**：本日志首版写「Y4 为空」是我**照搬提示词 §Y4 的原文**、
> 没继承 P6-X 已登记的人名所致 —— **不是人没给**。
> ⇒ 段落 ② 缺的已不是人名，而是**演练当天两人当场在场**（§9.3 第 2 条红线，AI 代不了）。

---

## 1. 做了什么（代码）

| # | 改动 | 文件 | 对应 |
|---|---|---|---|
| 1 | supersede **只收窄同 org** | `app/services/graphs.py` `_CYPHER_SUPERSEDE_OTHER_VERSIONS` | F-P6X-5 |
| 2 | 兜底查询**必须带 org** | 同上 `_QUERY_ACTIVE_KG_VERSION` + `fetch_active_kg_version` 传参 | F-P6X-5 |
| 3 | 新增 `sync_kg_version_mirror`（**旁路**语义） | `app/services/kg/mirror.py`（新） | F-P6X-1 |
| 4 | 建图完成路径同步镜像 | `app/tasks/registry.py`（`mark_ready` 之后） | F-P6X-1 |
| 5 | 增量完成路径同步镜像 | `app/services/kg/incremental.py`（`mark_ready` 之后） | F-P6X-1 |
| 6 | `get_active` 排序加次级键 | `app/services/kg/versioning.py` | **F-P6X-6**（见 §5） |
| 7 | 迁移脚本（**交付不执行**） | `scripts/migrate_kg_version_org.py`（新） | F-P6X-5 的历史 NULL 节点 |

### 1.1 关键设计决策（**写在这里，若与你的判断不符请叫停**）

| 决策 | 选择 | 理由 |
|---|---|---|
| supersede 的范围 | **同 org** | 旧实现 `MATCH (v:KgVersion) WHERE v.version <> $version` 不分租户 ⇒ A 租户激活会把 B 租户一并取代 |
| `org_id` 为 NULL 的历史节点 | **一律不动**（不 supersede、不写 org） | 无法证明归属：写死成当前 org = 污染；supersede 掉 = 越权。交由迁移脚本按 PG 反查补齐 |
| 兜底查询缺 org 时 | **匹配不到 ⇒ 抛 `NoActiveKgVersionError`** | fail-closed：宁可报"无 active 版本"，也不静默拿一个来源不明的版本 |
| 镜像同步失败 | **旁路（记 warning，不抛）** | 与 `cost_metrics` 同款范式：图已写完，判 failed 是造假；可观测性由 §6.2 的 `ghost_version` 兜底（**真正的 fail-closed 关卡在 §6.2**） |
| 同步代码放哪 | 抽 `kg/mirror.py` 一处，两处调用 | F-P6X-1 的成因就是"两处各写一遍、结果一处都没写" |

---

## 2. 撞上的既有设计：**P5F-4**（已核实消解，不是绕过去）

`incremental.py` 头注释（:20-23）写着：**不做**镜像全局激活，因为"新版本只承载受影响子图，
置 active 会让读侧只看到被校正的那一小撮"。而实测 PG 的 active **恰恰是增量版本**
`20261012T064951Z-inc-569555ad` ⇒ 不同步就闭合不了 §6.2。

**核实结论**：该顾虑已被**版本继承读**（P5-H）消解 —— 机械证据
`tests/test_version_chain_readers.py::test_overview_reads_the_whole_graph_after_a_rename`
（真图 + 真 PG）钉死：**5 个节点改名 1 个（走增量 ⇒ 新版本物理上只承载受影响子图）之后，
读侧仍然拿得到全部 5 个**；该用例 docstring 明写它是 P5-G「物理上不承载全图」断言的反面。

⇒ 按 **R-5** 在该注释下**追加** P6-X2 说明（原文保留），未删改史实。

---

## 3. 机械验证（**全部实跑**）

| 判据 | 命令 / 用例 | 读数 |
|---|---|---|
| **跨租户 supersede 真的生效** | 真图 `test_activating_org_a_does_not_supersede_org_b` | ✅ A 的新版本 `active`、A 的旧版本 `superseded`、**B 的保持 `active`** |
| **NULL 节点不被认领** | 真图 `test_null_org_node_is_never_claimed` | ✅ 仍 `active`，且 `org_id` 仍为 `NULL`（没被"顺手"写成当前 org） |
| 同步真的发生（建图侧） | `test_kg_build_syncs_graph_mirror_after_ready` | ✅ 1 次调用，version/org 正确 |
| 同步真的发生（增量侧） | `test_incremental_rebuild_syncs_graph_mirror` | ✅ 1 次调用，version = `result.new_version` |
| 旁路语义 | `test_sync_is_bypass_when_graph_down` | ✅ 图库抛 `GraphUnavailableError` ⇒ **不抛**、返回 `False` |
| 迁移脚本干跑 | `scripts/migrate_kg_version_org.py --org-id <默认 org>` | PG 4 个可归属 / 图库 3 个 NULL / **可补 2 个** / 认不出 1 个（`affiliation-demo-v2` 属另一个 org，没传它的 org-id）/ `[DRY-RUN]` **未写入** |

---

## 4. 打红并修好的既有护栏（**不是绕过**）

| # | 现象 | 处置 |
|---|---|---|
| 1 | 新脚本触发 `test_runnable_scripts_force_utf8_stdio`（Windows GBK 会崩） | 给脚本补 stdio UTF-8 兜底（照门禁给的修法） |
| 2 | 兜底加 org 后，`test_backup_restore.py` 的探针用例从 pass **退化成 skip** | 见 §4.1 |

### 4.1 那条探针用例：**退化成 skip 就是护栏变弱**

`test_real_neo4j_probe_distinguishes_existing_and_missing_version` 原本靠图库里**既有**的
active 节点（`fetch_active_kg_version()` **无参** ⇒ 兜底按字典序取最大）来验"存在那一半"。
自 P6-X2 起兜底必须带 org，而历史节点 `org_id` 全 `NULL` ⇒ 取不到 ⇒ 走 `pytest.skip`。

**改写（不删原意）**：本用例**自己造一个带 `org_id` 的 active 节点**（`finally` 清理），
两个方向都真验，并顺带把"兜底按 org 生效"钉在真图上。

**顺手修掉一个恒绿失效**：旧写法把**断言**也包在 `except Exception` 里 ⇒ 断言失败会被
当成"连不上"转成 skip（纪律 **R-9**）。现在连通性**单独探测**，断言在外面 ⇒ 断言失败就真红。

---

## 5. 真图口径暴露出的**既有缺陷** F-P6X-6（原定"只登记"，本批改为修）

真图全量**连续两次稳定红**：`test_get_active_returns_latest_ready_for_same_org`
⇒ `assert 'v-old' == 'v-new'`。

**根因**：`get_active` 只按 `ready_at DESC` 排序，而两次 `mark_ready` 会落在**同一微秒**
⇒ 两条并列 ⇒ 返回哪个全看运气。**§6.2 的一致性判定要靠 active 唯一定位，不能靠运气。**

**修法**：`ORDER BY ready_at DESC, created_at DESC, id DESC` —— `created_at` 已与 `org_id`
组成复合索引 `ix_kg_versions_org_id_created_at` ⇒ **零新增索引**；`id` 是最后的确定性兜底。
同时更正模块头/方法 docstring 的措辞（是「**最新** ready」，不是「唯一 ready」——
同 org 允许多个 ready 共存，实测 5 行全 ready）。

**新增护栏**：`test_get_active_is_stable_when_ready_at_ties`（把 `ready_at` 强行拉平后断言结果稳定）。
⚠️ 这条自己先红过一次：`created_at` **同样可能并列** ⇒ 已改为**显式拉开 `created_at`**，
只留 `ready_at` 并列（测试必须隔离变量，不能靠时序运气）。

---

## 6. 门禁读数（**两套口径都跑**）

| 口径 | 改前基线 | 改后 |
|---|---|---|
| pytest 默认 | 1251 passed / 43 skipped | **1257 passed / 46 skipped** |
| pytest 真图 | 1289 passed / 5 skipped | **1298 passed / 5 skipped** |
| `ruff check` / `format --check` | All checks passed / 294 files | All checks passed / **291 files** |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 | **ERROR 0 / WARN 0 / OK 12**（未新增 settings / 接缝） |
| `check_session_drift.py` | — | ✅ 未发现漂移（S1 读到本批 9 条 Non-goals） |

---

## 7. 边界（**没做的**）

- **迁移脚本未执行**：Non-goal 6 —— 不许碰生产 / 目标环境真实数据；本机只跑了干跑，**源环境一个字节未改**。
- ~~**段落 ②（演练）未开工**~~ → **2026-10-13 已开工 ①（恢复演练）**，读数见 §7.1。
- 未改 `check_9` / §10 判据（Non-goal 1）；未修 F-P6X-3（Non-goal 2）；未动 `cost_metrics`（Non-goal 7）。
- 未起任何真 LLM 调用（Non-goal 4）。
- ~~**第 9 项仍未 PASS**~~ → **已 PASS**：留证 `docs/drills/restore-drill-20261013.md`
  由 **wIlliam 写 / tianen 署名**（Non-goal 3：AI 不代写正文、不代判结论），**已落库** ⇒ 复跑转 PASS。

---

## 7.1 演练 ①（2026-10-13 恢复演练）实测读数

**执行 `wIlliam` / 见证 `tianen**（两人当场在场）；AI 只跑命令 + 校验 + 回登。**
**内部演练，非客户现场验收**（R-10）。命令序列见 `drill-20261013-runbook.md`。

| 序 | 动作 | 实测读数 |
|---|---|---|
| 1 | 起独立环境（`COMPOSE_PROJECT_NAME=graphrag-drill`，compose **副本**改宿主端口 7688 / 7475） | 四服务 healthy；新卷 `graphrag-drill_*`（与源环境 `graphrag-agent_*` 分离）；`GET /health` = **200** |
| 3 | License | 先用**宿主**指纹签 ⇒ `LICENSE_FINGERPRINT_MISMATCH`；改在**容器内**取指纹（`4d0e04e0…`，machine-id `208c9ebe…`）重签 ⇒ `status: active`（max_orgs 5 / max_seats 50 / 7 modules / 2027-12-31） |
| 4 | 现跑备份集 | 五类齐全、SHA-256 全过：PG 192157B ／图库 6028528B ／storage 114688000B ／license 580B ／config 3632B（6 项密钥脱敏）⇒ `[OK] backup` |
| 5 | 恢复 `--apply` | PG ✅ 已恢复到 `graphrag` 库；图库 ❌ `neo4j-admin load` 失败（退出码 1）；storage ⚠️ 落到**宿主** `backend/storage`；license ⚠️ 落到**宿主** `deploy/license/app.lic` |
| 5b | 图库补恢复 | 停演练栈图库 + `docker run --volumes-from` 一次性容器 load ⇒ **42 files / 268.3MiB** ⇒ 11668 节点、176 个 `:KgVersion` |
| 7 | 十项验收（**留证落库后复跑**） | **PASS 6 / SKIP 3 / FAIL 1**（明细下） |

**十项明细（复跑后）**：1 PASS ／ 2 PASS ／ 3 PASS（G-23 复用 `1 passed`；委派 pytest 跑在**本机**测试库，非演练栈）／
4 SKIP（登记过）／ 5 SKIP（登记过）／ **6 FAIL** ／ 7 SKIP（g9 `4 passed`、g26 `30 passed`，目标环境子项因 401 SKIP）／
8 PASS ／ **9 PASS**（留证 `docs/drills/restore-drill-20261013.md` 已落库，判据认到 1 份）／ 10 PASS。
（落库前那轮 = PASS 5 / SKIP 4 / FAIL 1 ⇒ **只有第 9 项由 SKIP 转 PASS**，其余读数不变。
两份报告都留着：`acceptance-20261013.json`（前）与 `acceptance-20261013-final.json`（后）。）

### 三个真实发现（**登记，本批不改**）

1. **F-P6X-7（新）**：`restore.py::restore_neo4j`（`:203-232`）只在**容器 running** 时 `docker exec`，
   而 `neo4j-admin database load` **要求停服**；且 `--from-path` 传的是**宿主**路径、容器内不可达
   ⇒ 「宿主编排 → 容器执行」形态下图库恢复**不可能成功**。`backup.py` 已用「容器停 ⇒ `docker run --volumes-from`」
   解决同款问题（`:153-190`），**恢复侧没有** ⇒ 两侧不对称。
2. **F-P6X-8（新）**：`install_acceptance.py` **无认证入口**（`:836-864` 无 `--token`）⇒ 目标环境为
   生产形态（`PRIVATE_DEPLOY_ENABLED=true`、`dev_fallback_enabled: False`）时，第 6 项读 `audit_log`
   必 **401 ⇒ FAIL**、第 7 项目标环境子项同理 ⇒ SKIP。按 Non-goal 9 **不许改环境 / 改判据**迁就
   ⇒ 照实记 FAIL。（数据本身是够的：演练栈 `audit_log` = **862 条** ≥ 7，第 6 项判据可达，是工具读不到。）
3. **§6.2 `ghost_version` 复现**：PG active `20261012T064951Z-inc-569555ad` 在图库无镜像节点
   ⇒ 恢复后 §6.2 判 **FAIL**（退出码 2「不许启动」）。这是 F-P6X-1 的**历史**部分：本批修复只管
   **新**版本同步，历史节点须迁移脚本补 ⇒ Non-goal 6 ⇒ 本批不执行。

### ⚠️ 本次操作失误（守史实，不掩饰）

`restore.py` 的 storage / license 落点默认取 `settings`（**本机**路径）⇒ `storage` 被解开覆盖到
宿主 `backend/storage`、`license` 覆盖到宿主 `deploy/license/app.lic`（同源 580B / 10-11，无实质差异）；
**演练栈容器内的 License 未受影响**（588B，`status` 仍 active）。
⇒ 教训：容器化独立环境的恢复须在**目标环境内**跑 restore，或显式给 `--storage-root` / `--license-file`。

### 诚实标注（写进留证，不许略）

- 本次**同机**起独立栈 ⇒ **未覆盖**「换机 ⇒ License 失效、须重新签发」场景；
- 容器内 machine-id（`208c9ebe…`）**与宿主不同** ⇒ Windows 上 `/etc/machine-id` 挂载无效，
  指纹回落容器 MAC（compose `:138-144` 已警告）；
- 第 3 / 7 项的 pytest 委派跑在**本机**测试库，**不是**演练栈 ⇒ 属"复用既有用例"口径，不是目标环境实测。

### 补记：留证落库后 **CI 变红**（2026-10-13，两条都是我的提交引起的）

留证落库那笔（`8ba41ff`）CI **failure**，后端 job 两条：

1. **`test_install_acceptance.py:167`**（稳定红）：`assert 'PASS' == 'SKIP'` —— 第 9 项判据在仓库里
   **真的找到**了 `docs/drills/restore-drill-20261013.md` ⇒ 第 9 项**正确地**翻成 PASS，
   而这条护栏断言"第 9 项必须仍是 SKIP" ⇒ **护栏过期**（前提"演练还没做"已不成立），不是脚本错。
   **修法**：用 `monkeypatch` 把 `DEFAULT_DRILL_DIR` 指向空的临时目录 ⇒ **隔离仓库真实状态**，
   保住它的内核（若没翻 PASS，理由必须是"演练未做"，**不许**退回拿 "D-1b 未落地" 当借口）；
   "留证真出现就必须翻 PASS"由紧邻的反向守卫守。
   ⚠️ 教训：**护栏不该读仓库的真实可变状态** —— 仓库里多一份留证它就红一次。

2. **`test_backup_restore.py:644`**（**flaky**：CI 第一次红、原样重跑绿；本机单独跑绿、全量跑红）
   ⇒ 不是"偶发算了"，根因已定位（**F-P6X-9**）：用例 `session.run("CREATE …")` 的返回值
   **没有 `.consume()`** ⇒ Neo4j 的**自动提交事务可能尚未落盘**，而探针 `default_neo4j_probe`
   **另开一个 session** 去读 ⇒ 读不到刚造的节点 ⇒ `assert … is True` 变 False。
   时机不同就红/绿（单独跑时缓存/时序恰好对得上 ⇒ 绿）。
   **修法**：CREATE 与清理的 DELETE 都补 `.consume()`（**只改用例，不动产品代码**）。

**修后读数**（两套口径都跑）：默认 **1257 passed / 46 skipped**；真图 **1298 passed / 5 skipped**；
`ruff check` All checks passed / 291 files；`check_seams.py` ERROR 0 / WARN 0 / **OK 12**。
⚠️ 真图口径必须**显式清掉** `GRAPH_REAL_*` 才是默认口径读数（同一会话里变量还在会污染读数，本次已单独复跑）。

### 判分裁决（**wIlliam 2026-10-13**；AI 给选项与建议，**勾选与定稿归人**）

| 问 | 裁决 |
|---|---|
| 8.1 环境可复现？ | **B 部分达标** —— 数据复现了，但 §6.2 不许启动 + storage / license 落点错位 |
| 8.2 第 6 项 FAIL 归类 | **B 记 FAIL + 另立缺陷** —— 口径冲突（登记「未授权⇒SKIP」vs 实现「FAIL」）交下批裁决 |
| 8.3 §6.2 未过处置 | **A 到此为止，另立批** —— 历史镜像迁移会写源环境 ⇒ 不动（守 Non-goal 6） |
| 8.4 是否单独立批 | **A 合并进下一批** —— F-P6X-7 + F-P6X-8 + 历史镜像迁移 |

§7 过程观察与 §8.5 / §8.6 措辞：由 wIlliam 从 AI 提供的**候选措辞**中逐条选定
（候选只含机械读数；署名、观察、结论**均由执行者本人定**，AI 未代写一句正文）。

---

## 8. 下一批 / 下一步

> **2026-10-13 更新（用户裁决）**：① **不换人** —— 执行 `wIlliam` / 见证 `tianen`（沿用 P6-X，已确认）；
> ② **演练日期授权 AI 代填** ⇒ 已定为 **恢复 2026-10-13（周二）／升级（含回滚）2026-10-14（周三）**
> （排序理由与留证文件名见 `proposal.md` §5；n=2 的第二轮建议 10-15 / 10-16）。
> ⚠️ 日期是**登记**，不是"演练已做" —— 演练仍**人做主体**，AI 只搬运 / 校验 / 跑命令 / 回登。

段落 ② 开工前必须补齐：

1. ~~**演练日期 + 两人当场在场**~~ → **日期已定**（见上）；剩下的只有**当天两人当场在场**
   （执行 `wIlliam` / 见证 `tianen`，§9.3 第 2 条红线，**AI 代不了**）；
2. **§5.1 期望值表逐项判分定稿**（AI 只出了依据与提案）；
3. （若要第 4/5 项 PASS）**真 LLM 授权**（Y1″，演练前再给一次）。

留证 `docs/drills/restore-drill-<日期>.md` 由**人写**（须含执行者 / 见证者两人署名 +
「内部演练，非客户现场验收」），AI 只搬运 / 校验 / 跑命令 / 回登。
