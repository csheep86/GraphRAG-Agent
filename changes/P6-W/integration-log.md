# P6-W 集成日志：DR-E2 最小备份 / 恢复 + DR-E4 安装验收十项脚本化（2026-10-10）

> **队列**：`docs/delivery-plan.md` §9.2 序 **6**
> **裁决来源**：**W1 = 方案 I**（2026-10-10 用户拍板，`changes/P6-V3/integration-log.md` §7）
> **边界**：[`proposal.md`](./proposal.md) §1（Non-goals **9** 条）
> **判据源**：`docs/deployment-spec.md` §6.1 / §6.2 / §6.4 / §10

---

## 1. 本批做了什么

| # | 交付物 | 作用 |
|---|---|---|
| 1 | `backend/app/services/backup.py` | 备份清单 / §6.2 一致性的**唯一换算口**（两条命令共用，不许两处各写一份 ⇒ 漂移） |
| 2 | `backend/scripts/backup.py` | §6.1 六类对象采集 + `backup-manifest.json`；`--verify` 重算 SHA-256（第 8 项判据） |
| 3 | `backend/scripts/restore.py` | 恢复（Storage / License 用 stdlib；PG / Neo4j 调外部命令）+ **§6.2 一致性校验，错位 ⇒ 退出码 2** |
| 4 | `backend/scripts/install_acceptance.py` | §10 十项逐条 `PASS / SKIP / FAIL` + 原因，`--out` JSON |
| 5 | `backend/tests/test_backup_restore.py`（23 条）<br>`backend/tests/test_install_acceptance.py`（22 条） | 判据用例 |

---

## 2. 两条实测发现（**不是引用文档，是本机跑出来的**）

| # | 发现 | 实测命令与输出 |
|---|---|---|
| **F-P6W-1** | **G-26 的 `ENABLE` + `FORCE` RLS ⇒ `pg_dump` 必须由 BYPASSRLS 角色执行** | `docker exec -e PGPASSWORD=app_rls graphrag-pg pg_dump ... -Fc` ⇒ **EXIT=1**（`query would be affected by row-level security policy`）；`app_owner` ⇒ **EXIT=1**（同上，且提示 `ALTER TABLE ... NO FORCE ROW LEVEL SECURITY` —— 那等于临时拆隔离，不可取）；`graphrag`（超级用户）⇒ **EXIT=0**，190444 字节 |
| **F-P6W-2** | **Neo4j dump 必须在停服窗口内做** | 容器在线：`` neo4j-admin database dump neo4j --to-stdout`` ⇒ **EXIT=1**，`To perform a dump... please stop the database... Error: The database is in use`；停掉图容器后用 `docker run --rm --volumes-from <图容器> --entrypoint neo4j-admin <镜像> database dump` ⇒ **EXIT=0**，3435770 字节 |

⇒ 两条都已写成 `docs/deployment-spec.md` §6.1 的**实现约束**（**没有动 §10 的表格一行**，
Non-goal 4）。

**顺带的发现（不在本批处置范围，登记待裁决）**：

| # | 发现 | 现状 |
|---|---|---|
| **F-P6W-3** | `.env.example` 里 `PRIVATE_DEPLOY_ENABLED=false` | 把模板当目标 `.env` 跑第 10 项会红。**模板**如此是否合适属你们的事，本批**不擅自改** —— 只把第 10 项写成"须显式给 `--env-file`，不读脚本进程的 settings" |
| **F-P6W-4** | `scripts/inspect_d1b` 原本全仓 grep `docker save` **必然假阳性** | 命中全是 `docs/` 里**描述 D-1b 这条未做完的计划**（`deploy/README.md:4` / `docs/deployment-spec.md:377` 等 8 处）；已改为只查 `.github/workflows` + `deploy/` + `scripts/`，并有反向用例钉死 |

---

## 3. 决策落地（对照 proposal §2）

| # | 决策 | 落地位置 | 落地结果 |
|---|---|---|---|
| **W1** ✅ | 第 8 / 9 项怎么办 | 见本日志 §1 | 第 8 项随 W-a 落地；第 9 项顺延 P6-X |
| **W2** | 机器可跑的定义 | `--verify` / `--apply` / `--skip-pytest` / `--base-url` 等显式档位 | 依赖目标环境的项一律 **SKIP + 原因**，不静默通过 |
| **W3** | 第 4 / 5 项要不要 live LLM | 默认 **SKIP**（缺 `--pipeline-sample` / `--ask-question`） | 给出了勾选项，但**不默认跑**（真 LLM 不进 CI，沿用 D6） |
| **W4** | 十项落哪 | `install_acceptance.py`；备份/恢复**另立两条命令** | 三份文件各自 `main(argv) -> int` |
| **W5** | 判据重复怎么办 | `pytest_subcheck()` 委托 pytest 跑既有 G-23 / G-9 / G-26 | 断言"**真的跑了 N 条且绿**"，`ran == 0` 判 **FAIL**（空跑不算通过） |
| **W6** 🆕 | pg_dump 用什么角色 | F-P6W-1 ⇒ `--pg-dsn` / env `BACKUP_PG_DSN`，**默认不是**应用账号 | 没给连接串时 `postgres` 落 `skipped` + 提示 BYPASSRLS |
| **W7** 🆕 | `.env` 恢复要不要自动覆盖 | `config_hint()`：**不回写**，只提示脱敏副本位置 | 避免盖掉客户现场新配的密钥 |
| **W8** 🆕 | 图容器停了怎么 dump | `_neo4j_dump_command()`：容器在跑用 `docker exec`；已停用一次性 `--volumes-from` | 停 stop-after-dump 后原容器照常启动，不用 `docker cp` 中转 |

---

## 4. 判据与机器输出

### 4.1 五项门禁（同 P6-V3）

```
uv run ruff check .            => All checks passed!
uv run ruff format --check .   => 285 files already formatted
uv run python scripts/check_seams.py                    => ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check         => [OK] 零 diff
uv run python scripts/extract_seam_signatures.py --check=> [OK] 与快照一致
uv run python scripts/check_startup_readiness.py        => [OK] 生效 17 / [~~] 0 / [--] 0
```

### 4.2 pytest

| 时刻 | 结果 |
|---|---|
| **改前（本批基线，有图口径三变量已设）** | **1191 passed / 5 skipped** |
| **改后（本机口径，未设 `CI=1`）** | **1235 passed / 6 skipped**（`+44 / +1`，无 FAILED） |
| **改后（CI 口径：设 `CI=1` + 三变量）** | **1236 passed / 5 skipped**（`+45 / +0`，无 FAILED） |

> **两个读数的差别只用一条**：`test_real_neo4j_probe_...` 在那台机器上有没有真图口令。
>
> **第一次推 CI 它红了**（run 38025313919，1 failed）——**原因是本批自己的问题，已修**：
> `conftest.py:57-58` 刻意把 `NEO4J_URI` / `NEO4J_PASSWORD` 中和成不可达端口，
> 所以 `GraphService` 在 pytest 里**默认连不到真图**；本批原写法直接调
> `default_neo4j_probe()` ⇒ CI 上抛 `NEO4J_PASSWORD 未配置`。
> 修法是照抄 `tests/test_guardrails_graph.py::graph_service` 的夹具
> （monkeypatch settings + `GraphService.reset()`），并把"存在那一半"改成
> **直接问图库它现在有哪些 `:KgVersion`**（不再从 PG 的 active 版本去猜 —— 两个库种子不同，
> 猜会让这条在 CI 上变掷骰子）。

> `+1 skipped` = `test_backup_restore.py::test_real_neo4j_probe_...`：本机 `.env` 未写
> `NEO4J_PASSWORD`（CI 作业有 `NEO4J_PASSWORD: ci-graph-pw-2026`）⇒ 走与
> `tests/test_guardrails_graph.py::\_real_graph_env` **同款口径**：本机 skip、**CI 缺失即 fail**。
>
> 全量跑时的 `PytestUnhandledThreadExceptionWarning (_readerthread)` **属既有告警**：
> 把本批两个新文件 `--ignore` 掉之后照样出现 ⇒ 非本批引入（两条新文件单独跑：44 passed / 1 skipped，无该告警）。

### 4.3 真机：一次**六类齐全**的备份（停图库窗口内）

```
uv run python scripts/backup.py --out-dir reports/backup/full2 \
  --pg-dsn "postgresql+psycopg://graphrag:***@localhost:5432/graphrag" --pg-container graphrag-pg \
  --neo4j-container graphrag-neo --env-file .env.example --license-file ../deploy/license/app.lic

PASS backup-manifest.json 可解析且 schema_version 匹配
PASS §6.1 五类文件对象均在清单中有条目
PASS postgres: SHA-256 校验通过（190444 字节, pg_dump -Fc）
PASS neo4j:   SHA-256 校验通过（3435770 字节, neo4j-admin database dump）
PASS storage: SHA-256 校验通过（10240 字节, tarfile）
PASS license: SHA-256 校验通过（580 字节, copy）
PASS config:  SHA-256 校验通过（23045 字节, copy+redact（12 项密钥已置 <redacted>））
PASS active kg_version 已记录: attendance-demo-v1（pg:kg_versions）
[OK] backup 完成
```

### 4.4 真机：恢复到 scratch 库 + §6.2 一致性**（全部通过）**

```
createdb graphrag_p6w_probe EXIT=0
uv run python scripts/restore.py --backup-dir reports/backup/full2 --apply \
  --pg-dsn "..." --pg-container graphrag-pg --target-db graphrag_p6w_probe \
  --storage-root reports/restore-probe/storage --license-file reports/restore-probe/app.lic

（清单 8 条 PASS 略）
DONE postgres: 已恢复到库 graphrag_p6w_probe
SKIP neo4j:   未给 --neo4j-container：图库 load 要求停服，副作用大于收益 ⇒ 不自动做
DONE storage: 已解开 2 个成员 → reports/restore-probe/storage（归档顶层 "w-test" 已被剥掉）
DONE license: 已恢复到 reports/restore-probe/app.lic
SKIP config:  不自动回写 .env（会盖掉现场新配的密钥）；脱敏副本在 .../env.redacted
PASS §6.2 版本一致性 [pg_graph_consistent] PG active 版本 = Neo4j 该版本节点存在（attendance-demo-v1）
PASS §6.2 清单↔PG [pg_graph_consistent] 备份清单与 PG active 版本一致（attendance-demo-v1）
[OK] restore 通过（§6.2 一致性已校验）
```

### 4.5 真机：**版本错位必须报错**（§6.2 第 2 条的反面）

把清单里记的 active 版本改成 `attendance-demo-vNINE`（文件一个字节没动 ⇒ 清单校验照过），再跑 **`--backup-dir` 不 `--apply`**：

```
PASS §6.2 版本一致性 [pg_graph_consistent] ...（attendance-demo-v1）
FAIL §6.2 清单↔PG [active_version_mismatch] 备份清单记的 active 版本 = attendance-demo-vNINE，
     恢复后 PG 的 active 版本 = attendance-demo-v1 ⇒ 版本错位
[FAIL] §6.2 一致性未通过 ⇒ **不许启动**（ADR-0002 §3.2）
EXIT=2
```

### 4.6 真机：安装验收十项（本机跑 `http://127.0.0.1:8000` + §4.3 的真实备份集）

| # | 项 | 状态 | 明细（**原文摘录**） |
|---|---|---|---|
| 1 | 全部容器健康 | **SKIP** | `/health 200: status=ok version=1.6.0`；`compose healthy: compose ps 未能执行（看不出来是否健康）: time=... .env file not found` |
| 2 | License 生效 | **PASS** | `status=active limits={'max_orgs': 100, 'max_seats': 100} modules=7` |
| 3 | License 拒绝可达 | **SKIP** | 本次用了 `--skip-pytest`；非跳过时委托 `test_guardrails_compliance.py -k g23_missing_license_blocks_requests` 并要求 `N passed` ≥ 1 |
| 4 | 上传 → 解析 → 建图 | **SKIP** | 缺 `--pipeline-sample`：**本批默认不碰真解析器 / LLM**（W3） |
| 5 | 问答可溯源 | **SKIP** | 缺 `--ask-question`：真 LLM 不进 CI（W3 / D6） |
| 6 | 审计留痕 | **PASS** | `100 条 / 100 个 trace 可聚合` |
| 7 | 租户隔离 | **SKIP** | 目标环境子项 = `org B 主体未获授权（HTTP 403 ... no_role_assignment）⇒ 这**证明不了隔离生效**，只是环境没备好`（`scripts/seed_dev_rbac.py` **刻意只播默认 org**）；G-9 / G-26 子项同 #3 |
| 8 | 备份成功 | **PASS** | 8 条明细全绿，含 `neo4j: SHA-256 校验通过（3435770 字节, neo4j-admin database dump）` |
| 9 | 恢复演练 | **SKIP** | **顺延 P6-X；且当前因 D-1b 未落地不可执行**：compose 仍带 `build:`（backend, db-init, frontend）；CI 工作流 / deploy / scripts 下未发现 docker save / load / push registry 的步骤或产物（docs/ 里的描述不算） |
| 10 | 生产配置 | **FAIL** | `PRIVATE_DEPLOY_ENABLED: = false，生产必须 true`（本次喂的是 `.env.example` ⇒ **F-P6W-3**）；另一子项 `无密钥进日志` SKIP（缺 `--log-file`） |

> **汇总: PASS 3 / SKIP 6 / FAIL 1** —— 这是**本机这一趟**的读数，不是"十项里过了三项"的结论：
> 把 `--base-url` / `--org-b` / `--log-file` / 真实目标 `.env` 补齐后，第 1 / 7 / 10 项会各自跑完自己的子项。

### 4.7 判据用例清单（**每一条都由 pytest 实际执行**）

`tests/test_backup_restore.py`（22 passed / 1 skipped）：

- `test_manifest_records_six_objects_and_active_version` —— 六类齐全 + active `kg_version`
- **`test_verify_detects_a_single_flipped_byte`** —— 改一个字节 ⇒ 必须红（**R-9 头号判据**）
- `test_verify_detects_a_deleted_backup_file` / `test_verify_on_a_directory_without_manifest` / `test_verify_rejects_incomplete_manifest_entry`
- `test_verify_treats_skipped_object_as_incomplete` —— 4 个 skipped ⇒ 4 条"备份集不完整"
- `test_storage_archive_roundtrip_is_byte_identical` —— 真打包 / 真解开 / 逐字节比对
- **`test_restore_storage_rejects_path_traversal`** —— `../` 成员 ⇒ `RestoreTarError`
- `test_restore_cli_refuses_to_touch_data_when_manifest_is_broken` —— 退出码 1 且目标目录没动
- `test_consistency_ok_when_version_node_exists` / **`test_consistency_fails_on_ghost_version`**
  / **`test_consistency_fails_when_graph_is_unreachable`** / `test_consistency_without_active_version_says_it_did_nothing`
  / `test_manifest_vs_pg_detects_version_drift` —— §6.2 五个分支逐一钉死
- `test_env_redaction_masks_secret_keys_only` —— 遮挡 `{DATABASE_URL, NEO4J_PASSWORD, MASK_SALT}`，**连接串只遮口令**（主机 / 库名留着）
- `test_run_backup_marks_missing_pg_dsn_as_skipped` / `test_backup_verify_subcommand_reports_nonzero_on_corruption`
- `test_real_neo4j_probe_distinguishes_existing_and_missing_version` —— 真图探针（**CI 缺失即 fail**）

`tests/test_install_acceptance.py`（22 passed）：

- `test_all_ten_items_report_a_status_and_a_reason` —— 十项逐条有状态 + 非空原因
- `test_render_and_json_are_machine_readable` / `test_combine_priority_*` / `test_combine_of_empty_is_skip_not_pass`
- **`test_item9_is_skipped_with_p6x_and_d1b_today`** / **`test_item9_would_flip_once_a_drill_is_filed`**
  —— 今天必须 SKIP 带证据；留证一出现必须认（不许永远停在 SKIP）
- `test_d1b_inspection_finds_build_in_deliverable_compose` / **`test_d1b_inspection_ignores_prose_in_docs`**
- **`test_item8_passes_on_a_real_backup_set`** / **`test_item8_fails_after_one_byte_is_changed`**
  / `test_item8_without_backup_dir_is_skipped_not_pass` / `test_item8_fails_when_backup_dir_does_not_exist`
- `test_target_env_items_skip_without_base_url[1,2,4,5,6]` / `test_item10_needs_an_env_file_and_a_real_log`

---

## 5. 本批踩到的坑（**留给下一批，别再踩**）

1. **Windows 上路径穿越判断不能拼字符串前缀**。`str(p).startswith(str(root) + "/")` 在本机会把
   **所有成员都判成越界**（分隔符是 `\`）⇒ 用 `Path.is_relative_to()`。
2. **Windows 上 subprocess 不能裸 `text=True`**。`docker compose ps` 的输出是 UTF-8、本机默认
   GBK ⇒ 异常发生在 **reader 线程**（不在主线程，看不见），表现为"第 1 项凭空消失"。
   一律写 `encoding="utf-8", errors="replace"`。
3. **`tar -extractall` 在 3.11 没有 `filter="data"` 兜底**（CVE-2007-4559）⇒ 必须自己逐成员校验，
   并且**要有反向用例**（本批 §4.7 的那条）。
4. **全仓 grep 当证据 = 假阳性发生器**：见 **F-P6W-4**（`docs/` 里描述计划的文字会冒充交付物）。
5. **脱敏只看 key 名会漏掉 `*_URL` 里内嵌的口令** ⇒ 补了第二种形态（只遮口令那一段）。

---

## 6. 残留风险（**不许被读成"DR-E2 / DR-E4 已完成"**）

1. **恢复演练仍是 0 次**。第 9 项由脚本**机械查** D-1b 得出 SKIP，原因写在输出里 ——
   **AI 不得单独把第 9 项收口**（属 P6-X 双人环节）。
2. **DR-E2 / DR-E4 一律只能标「部分」**。有脚本 ≠ 具备可恢复能力；那句话的证据只能来自 P6-X。
3. **Neo4j 对象的完整备份要求停图库**（F-P6W-2）⇒ 不停图库跑出来的备份集是**不完整的**
   （`neo4j` 落 skipped + 原因，`backup` 退出码 1）。别以为是脚本的 bug。
4. **`restore` 的 Neo4j 侧默认不做**（要求停服）⇒ 真正恢复要人工在窗口内 `--neo4j-container`。
5. **`.env` 恢复不自动回写**（W7）⇒ 恢复后必须人工重填密钥。
6. **第 4 / 5 项在本批没有真实链路证据**（SKIP 是登记过的，不是漏做）。
7. **F-P6W-3 未处置**：`.env.example` 的 `PRIVATE_DEPLOY_ENABLED` 仍为 `false`。

---

## 7. 下一批指针

→ [`new-session-prompt.md`](./new-session-prompt.md)

**三个候选**（未排程，**本节不构成任何承诺**）：

| 候选 | 说明 |
|---|---|
| **P6-X（双人）** | 第 9 项恢复演练；**硬前置 D-1b**（`install_acceptance.py` 第 9 项继续机械查） |
| **P6-D1b** | 先落离线镜像包 / 私有 registry —— 不落它，P6-X 与 §10 第 9 项年年只能 SKIP |
| **继续 P6-V3 之后的 C3 线** | `TBD-7 cost_ratio` 阈值仍 BLOCKED |
