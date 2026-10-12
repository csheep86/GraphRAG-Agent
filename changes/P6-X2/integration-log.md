# P6-X2 集成日志（段落 ①：修 F-P6X-1 + F-P6X-5）

> **起点**：`2357b12`（P6-X2 立批骨架：Non-goals 9 条 + 前置核验 + §5.1 期望值表）
> **人裁决**：Y1′ = **纳入 F-P6X-5**（O-1：一次闭合镜像 org 维度，不留尾巴）；
> Y1″（真 LLM）按"开"预备 —— **段落 ① 不消耗 LLM**，演练前须再授权一次。
> **Y4（执行者 / 见证者）仍为空 ⇒ 段落 ② 未开工。**

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
- **段落 ②（演练）未开工**：Y4 为空。
- 未改 `check_9` / §10 判据（Non-goal 1）；未修 F-P6X-3（Non-goal 2）；未动 `cost_metrics`（Non-goal 7）。
- 未起任何真 LLM 调用（Non-goal 4）。

---

## 8. 下一批 / 下一步

段落 ② 开工前必须补齐：**Y4（执行者 / 见证者，两人当场在场）** + **§5.1 期望值表逐项判分定稿**
+ （若要第 4/5 项 PASS）**真 LLM 授权**。
留证 `docs/drills/restore-drill-<日期>.md` 由**人写**，AI 只搬运 / 校验 / 跑命令 / 回登。
