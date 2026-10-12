# 新会话开场提示词 · P6-V5（**C3 真值 + TBD-7 裁决包**）

> 👤 **用户先做两个勾选（开工前必读本段）**
>
> **D1｜要不要批 V4-c 真机实测**（会产生 LLM 费用）：
>   □ 批准 —— 跑一轮真实抽取 + 一次增量重算，拿到 C3-a / C3-b **真值**
>   □ 仍不批 —— C3 真值维持 `BLOCKED`，本批改为「**P6-W**」（DR-E2 备份 / 恢复，W1 已裁决）
>   **两个都没勾时按「仍不批」处理**：不许自行起 LLM 账单。
>
> **D2｜TBD-7 阈值由你拍板**（AI **不得代填**）：本批只负责把
> 「实测值 / 建议值 / 各选项后果」摊到你面前，**采纳哪一个是你一个人的决定**。

---

> 🔒 **执行模式：混合（不是纯无人值守）**
> - **AI 段**：跑命令、搬运数字、校验门禁、回登日志 —— 可无人值守；
> - **人段**：**TBD-7 采纳哪个阈值**、**是否批 V4-c** —— 这两件事 AI **不得代做**，
>   也不许"先写进 config 再请你复核"（那等于把裁决做成既成事实）。
> ⚠️ **外加一条**：**真 LLM 调用不经批准不许起**。
>
> 📌 **计划真源**：本批**尚无 proposal**（P6-V4 的 V4-c 切片留在这里）→
> 开工第一步是照 `specs/_template/` 立 `changes/P6-V5/proposal.md` + `tasks.md`，
> **先写边界（Non-goals）再动手**（`check_session_drift.py` S1 报「没有 Non-goals」就要停）。
> 上游真源：[`../P6-V4/proposal.md`](./proposal.md) §3 切片表 + §6 停机条件。
>
> 📦 **本文件自包含**：批次定位、上游状态、坐标、判据、坑都在本文里。
> ⏳ **写于 2026-10-11 晚**（P6-V4 收口时）。开工先复核 §3 坐标表是否仍成立。

---

## 1. 本批一句话

P6-V4 已经把 C3-a / C3-b **出数能力**补齐（三态 + 取样器），但**真值仍是 `BLOCKED`**
——因为**系统一次真实抽取都没跑过**（`cost_metrics` 里没有 `stage='extraction'` 样本行）。
本批要么**真跑一轮**把真值拿出来（D1 批准），要么**如实维持 `BLOCKED`** 转去做 P6-W。

---

## 2. 为什么是它（**三条机械理由**，不是排期感觉）

| # | 机器读数 | 说明 |
|---|---|---|
| 1 | `pytest` 全量 **1247 passed / 43 skipped**；`check_seams` **OK 12 / ERROR 0** | C3 的**读口**已通（注入样本实测：C3-a=20000.0 token/doc、C3-b=0.25 ratio）⇒ 挡住真值的**不是代码** |
| 2 | `cost_metrics` 在本机 / CI **均空** | 缺的是**一次真实运行**，不是一段实现 ⇒ 这是"跑一下"而不是"写一段" |
| 3 | C1~C3 / 多跳 / 拒答五条准入线里**只有 C3 没有真值** | 用户 2026-10-11 裁决：目标是「软件可上线」⇒ 最短路径上的最后一块拼图 |

---

## 3. 已查证坐标表（**2026-10-11 实读，开工先复核**）

| 坐标 | 位置 | 用途 |
|---|---|---|
| 抽取侧记账 | `backend/app/tasks/registry.py:566` `record_extraction_usage(...)` | 唯一写入口；`extraction_engine='mock'` **不写**（不造 0） |
| 全量分母 | `backend/app/tasks/registry.py:837` `if fresh_build:` → `record_full_rebuild_cost(...)` | **重跑同一 kg_version 不计**（分母不会被垫大） |
| 增量分子 | `backend/app/services/kg/incremental.py:305` `record_incremental_rebuild_cost(...)` | 仅**成功**分支调用；失败走 `_fail` ⇒ 不记 |
| 读侧聚合 | `backend/app/services/cost_metrics.py::aggregate_stage()` | 判据唯一读口，**只认指定 stage** |
| 取样器 | `backend/scripts/export_cost_records.py` | 导出 `--calibrate` 能吃的 JSON |
| 校准 | `backend/scripts/eval_acceptance.py::\_calibrate()` | **只输出建议、绝不写 config**（RK-E7） |
| 真实入库入口 | `scripts/ingest_affiliation_sources.py --purge --corpus-dir ../demo/affiliation/generated --kg-version affiliation-demo-v2` | CI 同款（`.github/workflows/ci.yml:226`）；⚠️ 路径**必须带 `../`** |

---

## 4. 边界纪律（**Non-goals，立 proposal 时不得少于 6 条**）

1. **不自动改阈值** —— `--calibrate` 只输出建议，**绝不写 `config.py` / `.env`**。
   写入 `EVAL_SINGLE_DOC_TOKEN_CEILING` 只能由**人**做（且必须同步 `.env.example`）。
2. **不动 C3-b 的量纲裁决** —— 2026-10-10 拍板 A 组「图规模同量纲」（实体数 + 关系数）。
3. **不做 `stage` 切片契约变更 / 仪表盘改造**（P6-V3 §6.3 遗留，属契约变更）。
4. **不做交付动作** —— P6-X 演练 / release notes / 打 tag 一律不碰。
5. **不许伪造 `value`** —— 无数据 ⇒ `BLOCKED` + `value=null`，**不是 0**。
6. **不许以降低判据换绿**（R-10）—— 真值难看就如实登记，再交用户裁决。

---

## 5. 决策表（**碰到就照这里办，别临场发挥**）

| 情况 | 怎么办 |
|---|---|
| D1 批准 | 起后端 → 真实入库一次 → 触发一次**增量重算** → `--live` 读 C3 → 导出 → `--calibrate` → 出裁决包 |
| D1 不批 | C3-a / C3-b 如实维持 `BLOCKED`，**不要**为了让它绿而注入样本当真值（P6-V4 已做过一次注入探针，那是**证明读口会出数**，不是真值） |
| 实测值出来后 | **只给数据 + 各选项后果**，TBD-7 采纳由用户定 |
| 发现要改量纲才能出数 | 属 ② 裁决，**先缩范围再报告** |

---

## 6. P6-V4 留给本批的三个坑（**别再踩**）

1. **offline 绝不能读库**：本机测试库是**持久库**（P6-V2 起记过两次），
   offline 一旦读 `cost_metrics`，真图写入的成本行会让 offline 报告**产出判据数字**
   ⇒ `test_offline_yields_no_criterion_numbers` 当场红，报告也不再幂等。
   ⇒ 判据读库**只在 live 分支**。
2. **conftest 的 `autouse` 桩会顶掉 `get_active`**（`tests/conftest.py::pg_active_kg_version`
   恒返回 `v-test`）：要真读 PG 的 active 版本，必须显式请求 `real_pg_get_active` fixture 撤桩
   ——否则会以「基线版本不一致」的形态红掉，**看起来像增量失败，实为夹具问题**。
3. **`test_cost_metrics.py::test_dashboard_endpoint_returns_real_rows` 有顺序耦合**：
   真图用例会**真的写**成本列 ⇒ 它读到脏值。历史修法是**改它的隔离**（先清本 org 当日行），
   **不是**改判据让它绿。

---

## 7. 已完成项（P6-V4，**不要再重做**）

| 切片 | 状态 |
|---|---|
| V4-a 两个 evaluator 出数化（三态） | ✅ `d66bec0` |
| V4-b 取样器 `scripts/export_cost_records.py` + `--calibrate` 提示订正 | ✅ `d66bec0` |
| V4-c 真机实测 | ❌ **未做**（D1 未批准） |
| `tests/test_eval_cost_criteria.py`（J1~J5，11 条） | ✅ |

---

## 8. 基线（**CI / 本地两套口径都要记**）

```
pytest（本机，双容器 Up）: 1247 passed, 43 skipped, 0 failed
ruff check / format --check: All checks passed（6 个改动文件）
check_seams.py            : ERROR 0 / WARN 0 / OK 12
check_startup_readiness   : --self-test 7 条全过（⚠️ 本机 PowerShell 需
                            $env:PYTHONIOENCODING="utf-8"，否则打印 `⇒` 时 GBK 崩）
check_session_drift       : S1 6 条 / S2 4 文件 339 行 / S3~S5 未触发
```

---

## 9. 验收判据（**跑完才能收口**）

| # | 命令 / 判据 | 期望 |
|---|---|---|
| V1 | `ruff check` + `ruff format --check` | 绿 |
| V2 | `check_startup_readiness.py --self-test` | 7 条全过，退出码 0 |
| V3 | `pytest tests -q`（全量） | **不降**（1247 / 43） |
| V4 | `check_seams.py` | OK 12 / ERROR 0 / WARN 0 |
| V5 | `pytest tests/test_eval_acceptance_cli.py tests/test_eval_cost_criteria.py -q` | 既有断言**不得崩**（第 76-78 / 125-126 行锚 `"M2"` / `"TBD-7"` / `"增量重算"`） |
| V6 | **（仅 D1 批准时）** 真跑一轮后 C3-a / C3-b 出数 | `value` 非 null；若仍 `BLOCKED`，`blocked_by` 必须点名**当前**真实缺口 |
| V7 | **真值出来后立刻回改 `docs/acceptance-traceability-matrix.md` 的 C3-a / C3-b 两行**（架构师侧**单独提交**） | 那两行刚在 2026-10-11 被 P6-V4 订正过（措辞已准、真值仍写 `BLOCKED`）⇒ **拿到真值就回写**，否则会第四次过期。C3 线已经因为「机器变、文案没复核」过期过三次 |

---

## 10. 提交推送纪律

- **角色隔离**：AI 段默认只**后端开发 B**（只改 `backend/`）；
  改 `specs/` / `contracts/` / `docs/` / plan ⇒ 归**架构师**段（**单独提交**）。
- **分支**：沿用 P4~P6-V4 —— **`main` 直推**，不另开分支。
- **提交**：按**后端 / 架构师 / changes** 分段 Conventional Commits，跨侧**不得**混在一起。
- **推送**：⚠️ GitHub 推送通道不稳（晚间多次 `443`）。失败 ⇒ **重试一次**，
  仍失败就**把完整命令交给用户**，**不许**改 remote / 绕道。
- **回登纪律**（P5-B §5.3）：**不要为"多记一个 run id"而提交** —— 回登 ⇒ 新 commit ⇒ 新 run。

---

## 11. 升级用户的 4 类情况

1. **要不要起真 LLM**（会产生费用）⇒ 见开头 D1；
2. 要动**已裁决**的 rubric / 判据口径（量纲、阈值、C3 出数口径）⇒ **先缩范围再报告**；
3. 边界冲突（要碰 Non-goal，例如必须改契约才能出数）；
4. CI 红了且复核两遍仍红（**不许先改测试让它绿**）。

---

## 12. 不许外推

- **不许**把 P6-V4 的注入探针值（20000.0 / 0.25）当真值登记 —— 那是**注入样本的算术**；
- **不许**把 `--calibrate` 的建议值写进 config 后说"已校准"；
- **不许**因为分位数退化（P50 == P90，日聚合摊平所致）就宣称"已拿到分布上界"；
- **不许**为了让 P8「零缺口」通过而把判据改松。

---

## 13. 下一批指针

- D1 **批准** ⇒ 本批（P6-V5）跑完真值 + 裁决包 ⇒ 下一批回 **P6-W**（DR-E2 备份 / 恢复，
  W1 裁决 = 方案 I：`backup` / `restore` 两条命令 + `backup-manifest.json` 契约含 SHA-256）。
- D1 **不批** ⇒ 本批直接改名做 **P6-W**，C3 真值作为**遗留**带进 P8 对账。
