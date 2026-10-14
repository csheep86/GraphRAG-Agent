# P7-O 集成日志 · P7-H 的两个硬前置修复

> **日期**：2026-10-14 ｜ **提案**：[`proposal.md`](./proposal.md)
> **一句话**：把上次恢复演练里那两处会让 P7-H 白做的缺口先修掉。

---

## 1. ① 恢复落点错位 ⇒ 不给落点就 SKIP

**根因**：`apply_restore` 在调用方没给 `--storage-root` / `--license-file` 时，退回
`settings.storage_root` / `settings.license_file_path` —— 而**恢复脚本通常跑在宿主上**，
于是文件被写回本机而不是目标环境。这个错不报错、文件也确实落了盘，所以很难发现。

**改法**：不给就 `SKIP`（与 `--target-db` 不猜、`.env` 不自动回写同一套纪律），
并把"为什么"写进返回串；argparse 的 help 同步去掉"默认 settings"的说法。

### 真跑对照（同一套备份集，只差给不给落点）

| 场景 | storage | license |
|---|---|---|
| **A. 不给落点** | `SKIP 未给 --storage-root：…默认落到 settings.storage_root 等于把文件写回本机而不是目标环境` | `SKIP 未给 --license-file：…会覆盖**本机**的 License` |
| **B. 显式给落点** | `已解开 390 个成员 → <指定目录>`（落点存在 = True，文件数 = **390**） | `已恢复到 <指定路径>`（**580 字节**） |

⇒ A 组一个字节都没写；B 组精确落到指定处。

> 附带确认：`restore.py` 的主流程对**不完整**的备份集是 `[FAIL] 清单校验未通过 ⇒ 拒绝恢复`
> （本次备份集缺 postgres / neo4j / config）⇒ fail-closed 行为正确，没有绕过。
> 上面对照是直接调 `apply_restore` 做的（绕开主流程的清单校验，只为验证落点那一段）。

---

## 2. ② 幽灵版本 ⇒ 以 PG 真源为准补镜像

### 先核到底（**差点按错误前提动手**）

| 查证 | 读数 |
|---|---|
| PG 真源 `kg_versions` | **只有 5 条**，最新 = `20261012T064951Z-inc-569555ad`（`ready`） |
| 图库 `:KgVersion` | **248 个**，时间跨度 10-12 14:08 ～ 10-13 03:13，其中 1 个 `active` |
| 图库最新 active | `20261013T031301Z-inc-1cf86269` —— **PG 里根本没有这条记录** |

第一眼很容易读成"PG 落后图库 ⇒ 增量路径只写图库不写 PG ⇒ 新缺陷"。**核到底后是反的**：

- `incremental.py:304` 有 `versioning.mark_ready(...)` ⇒ 增量路径**是写 PG 的**；
- 那 248 个镜像全部产生于 **10-12 14:08 之后**（镜像接线生效后），命名与增量同款
  （`…-inc-xxxxxx`），而 PG 里一条都没有 ⇒ 它们是**测试 / 评测跑批**写进 dev 图库的产物
  （PG 侧随测试事务或临时库回滚消失）⇒ **脏数据，不是产品缺陷**；
- PG 的 active 停在 **10-12 06:49**，**早于**镜像接线 ⇒ 它在图库从来没有镜像
  ⇒ 这才是真的幽灵，与 P7-G 裁决 A 的结论**完全一致**（幽灵只来自接线前的历史版本）。

### 处置：以 PG 真源为准补一次镜像

调用**已存在**的 `sync_kg_version_mirror`（P6-X2 实装），**没有新建入口** ——
这正是 P7-G 裁决 A 里写的"补偿办法"。

| 项 | 读数 |
|---|---|
| 补镜像前 `fetch_kg_version_status(active)` | `None`（幽灵） |
| `sync_kg_version_mirror(...)` | **True** |
| 补镜像后 `fetch_kg_version_status(active)` | **`active`** |
| `evaluate_version_consistency` | **`code = pg_graph_consistent`、`ok = True`** |

⇒ §6.2 由 `ghost_version` **FAIL（退出码 2，不许启动）** 转为 **`pg_graph_consistent` OK**。

### 副作用（**如实登记，不是"顺手清理"**）

`sync` 会把**同 org** 的其余 active 置 `superseded` ⇒ 那条测试脏数据的 active 被降级了：

| active 节点 | org | 处置 |
|---|---|---|
| `20261012T064951Z-inc-569555ad` | `…0001` | 本次补上（= PG 真源，正确） |
| `attendance-demo-v1` / `affiliation-demo-v2` / `p6v5-truth-20261012` | **`NULL`** | **不动** —— `kg.mirror` 模块纪律明写：`org_id` 为 `NULL` 的历史节点"无法证明归属 ⇒ 一律不动" |

⇒ 现在 active 共 4 个（1 个真源 + 3 个 NULL 历史节点，后者按既有纪律保留）。

---

## 3. 门禁

| 项 | 读数 |
|---|---|
| 全量 pytest | **1272 passed / 46 skipped / 0 failed**（未降） |
| 受影响用例 | `test_backup_restore.py + test_kg_version_mirror_sync.py + test_install_acceptance.py` = **49 passed / 3 skipped** |
| ruff | `All checks passed!` ／ `299 files already formatted` |
| 契约零漂移 | `[OK]` |
| 接缝纪律 | `[OK]` |

---

## 4. 遗留（**1 条，留给后续批次**）

| 编号 | 内容 |
|---|---|
| **F-P7O-1** | dev 图库里有 **248 个测试 / 评测跑批留下的 `:KgVersion` 镜像**（PG 里没有对应记录）。它们当前是 `superseded`，不影响 §6.2；但说明**跑批会往开发图库写版本镜像** ⇒ 建议后续立一批：要么让评测跑批指向独立图库，要么给跑批加一个"不写版本镜像"的开关。本次按 Non-goal 1 **没有清理**它们 |

---

## 5. CI 读数（**R-10：以 CI 为最终裁决**）

| 项 | 读数 |
|---|---|
| CI run | **待回填**（推送后填入） |
| 四个 job | 待回填 |
| CI 后端 pytest | 待回填（基线 `1311 passed / 7 skipped / 0 failed`；本批无新增用例 ⇒ 期望持平） |
