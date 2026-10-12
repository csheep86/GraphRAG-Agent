# P6-V5 集成日志（**实测证据**）

> 配 [`./proposal.md`](./proposal.md) / [`./tasks.md`](./tasks.md)。
> ⏱️ 本次会话范围（2026-10-12 第二次会话）：**D1 = 稍后再定** ⇒
> 只做零 LLM 费用动作（V0 清脏数据 + 拉基线）。**未起任何真实抽取 / 入库**。
> 起点 HEAD `1c32d7e`（= `49d8c63` + 两条「P6-V5 提示词」docs 提交）。

---

## 0. 开工自检（`check_startup_readiness.py`）

```
已生效 🟢 15 条 ｜ 条件跳过 🔵 2 条 ｜ 部分生效 🟠 0 ｜ 挂起 🟡 0
反向守卫 🛡 G-21 test_g21_production_sqlite_guard_still_present（必须恒绿）
💣 开工地雷 0 项（PG / compose / .env.example / plugins / variants / License / users 全部就位）
--self-test：用例 7 条（正向 4 + 反向 3）全部通过
```

⚠️ 🔵 那 2 条里有 **G-9 的 T1 跨租户 5 条用例**因 `real_driver` fixture
连不上 Neo4j 而 skip —— 本机 Neo4j 容器在跑（见 §1），但 fixture 走的是另一套配置，
⇒ **本地跑不通不等于判据达标**（与 ADR-0003 §4.1 的「必须跑在 PG / 纳 CI」同口径对待）。

---

## 1. V0：脏行定位（**本会话核心，全部为实测**）

### 1.1 先被澄清的坐标：脏行在两个不同的库里

| 库 | 连接串 | `cost_metrics`（默认租户） |
|---|---|---|
| **开发库** `graphrag` | `backend/.env` 的 `DATABASE_URL` | **0 行**（实测 `n_live_tup=0`，全表 instrument/count = 0） |
| **测试库** `graphrag_test` | `tests/conftest.py:28` `app_rls:***@localhost:5432/graphrag_test` | **1 行脏数据** |

⇒ 上一份提示词（P6-V6 §6 坑 4）只说「本机 `cost_metrics`」，**没说是哪个库**；
实测脏行在**测试库**。这条口径差决定了「`--live` 会不会吃到它」，故单列。

脏行原文（owner 角色 + `set_config('app.current_org')` 绑定后实读）：

```json
{"stage":"extraction","org_id":"00000000-0000-4000-8000-000000000001",
 "metric_date":"2026-10-12","token_usage_total":0,"doc_count":0,
 "counted_doc_ids":[],"single_doc_cost":0.0,"incremental_cost":null,
 "full_rebuild_cost":4.0,"cost_ratio":0.0,
 "created_at":"2026-10-12 03:47:29.283691+00:00"}
```

### 1.2 写入方：**只有一个文件**，且被实测闭合
```
$ uv run pytest tests/test_kg_build_executor.py -q      # 5 passed
   之后读全表：full_rebuild_cost 4.0 → 8.0，updated_at → 04:38:58+00
   ⇒ 单跑这一个文件注入 4.0，**写入方就是它**
```

机械推理（已被上面的实测闭合）：

- `_record_graph_cost()`（`cost_metrics.py:255`）建行时把
  `token_* / doc_count / counted_doc_ids / single_doc_cost` 全部写 0、只填 `field`
  ⇒ 与脏行的 0/null 形态**逐列吻合**；
- 唯一调用链 = `registry.py:837 if fresh_build:` → `record_full_rebuild_cost(...)`；
- 本文件 `_ENTITIES` / `_RELATIONS` 各 1 条 ⇒ 每次成功全新构建写入 `1+1=2`，
  文件里有 **2 条**用例走到该分支（`test_kg_build_happy_path`、
  `test_kg_build_records_retry_count`）⇒ `2×2 = 4.0`，与实测完全一致。

### 1.3 根因

`tests/test_kg_build_executor.py::seed_document` 夹具的收尾只删了
**`KgVersion`（按 org）+ `Document`（按 id）**，漏了 **`CostMetric`** ——
而本模块的文档 / `TaskSpec` 用的是 `settings.default_org_id`
（`:90` / `:129`），写进的正是 C3 `--live` 读取口的**默认租户当日行**。

---

## 2. 修法（`backend/tests/test_kg_build_executor.py`，**只动这一个夹具**）

- 新增 `_cost_row_ids(org_id)`：取当前 `cost_metrics` 行 id 快照；
- `seed_document` **进入前**拍一次、**收尾时**再拍一次，按 **新增 id 精确删**：
  ```python
  stale_cost_ids = _cost_row_ids(org_id) - cost_row_ids_before
  ```
- **不按 org 全删**：同一会话里 `test_cost_metrics_extraction.py` 也写默认租户，
  全删会误伤（该文件模块 docstring 已写明这条纪律）。

```diff
+from app.db.models import CostMetric, Document, KgVersion
```

---

## 3. 出口判据 K0~K5（**全部跑出来的，不是读代码得出的**）

| # | 判据 | 结果 |
|---|---|---|
| **K0** | 脏行清空 + 定位到写入用例 + 隔离后不再产生 | ✅ 单跑该文件后 `AFTER_FIX_ROWS = 0`；**全量 pytest 后 `POST_FULL_PYTEST_ROWS = 0`** |
| **K1** | `check_startup_readiness.py --self-test` | ✅ 7 条全过，退出码 0 |
| **K2** | `ruff check .` + `ruff format --check .`（**全量**） | ✅ All checks passed / **294 files already formatted** |
| **K3** | `check_seams.py` | ✅ ERROR 0 / WARN 0 / **OK 12** |
| **K4** | `pytest tests -q` 全量 | ✅ **1251 passed, 43 skipped**（177.19s）——与基线**逐字相同，不降** |
| **K5** | 锚点五文件（`test_eval_acceptance_cli` / `test_eval_cost_criteria` / `test_cost_metrics` / `test_cost_metrics_graph` / `test_cost_metrics_extraction`） | ✅ **44 passed** |

回切点 `check_session_drift`：S1 读到 `changes/P6-V5/proposal.md` **7 条边界**；
S2 = **1 文件 / 新增 28 行**；S3~S5 未触发。

**K6 / K7（真值出数 + 矩阵回写）未做** —— 依赖 D1，本次会话不在范围内。

---

## 4. 会话级守卫（**反证：它不是恒绿** —— R-9）

上一版 §5.4 登记的「无回归守卫」缺口，按裁决结论补上了：
`tests/conftest.py::cost_metrics_residue_guard`（session 级 autouse 夹具，
整套用例跑完后断言**默认租户**的 `cost_metrics` **0 残留**）。

**它不是挂在 C3 下面的 pytest 用例**（← UNESCO → 因为残留**只在全部用例跑完之后**才可见，
单用例断言抓不到；session 夹具的收尾最后执行 ⇒ 位置正确）：

- 读库**必须自建 engine + 显式 `set_config('app.current_org', …)`** ——
  走到会话末尾时 `default_org_for_bare_sessions` 的 monkeypatch 已还原，
  用 `SessionLocal` 读会**恒返回 0 行** ⇒ 守卫当场退化成"恒绿失效"（纪律 **R-9**）；
- 表不存在（`to_regclass('cost_metrics') is NULL`）⇒ 静默 return：本次会话没建这张表，
  **没有可供残留的对象**，不是免责放行。

### 4.1 反证（播种脏行 ⇒ 必须红）

```
# 1) 播种一行（形态 = 本次抓到的脏行）
insert into cost_metrics (…stage='extraction'… full_rebuild_cost=4 …)
  ⇒ SEEDED_ROW = 6696d964-74a1-4123-bf95-b9cfa44e8bc7

# 2) 只跑一个小 SUBSET（tests/test_auth.py）
$ uv run pytest tests/test_auth.py -q
  8 passed, 1 warning, 1 error in 0.55s
  ERROR tests/test_auth.py::test_get_current_identity_prefers_bearer_over_dev_headers
        ↳ tests/conftest.py:564 AssertionError：cost_metrics（默认租户）有测试残留 ……
          [{"id":"6696d964-…","stage":"extraction","doc_count":0,
            "incremental_cost":null,"full_rebuild_cost":4.0}]
```
⇒ **会红，并把定位所需的全部信息摊出来**（残留行原文 + 治理路径）。

### 4.2 清掉后必须绿（不误报）

```
DELETE ⇒ DELETED = 1
$ uv run pytest tests -q
  1251 passed, 43 skipped, 16 warnings in 117.09s
```
⇒ 与修之前**逐字相同**（1251 / 43）；守卫没被算成用例，也没误报。

---

## 5. 追加：CI 抓到的**另外三处**同型污染（本机默认口径看不见）

首推之后 CI run `38209335460`（head `a44bb6a`）**后端 job failure**，失败的就是 §4
那条守卫 —— **它做的正是它被造出来的原因**：

```
ERROR at teardown of test_view_without_org_id_refuses_to_inherit
  AssertionError: cost_metrics（默认租户）有测试残留 ……
  残留行：[{"stage":"extraction","token_usage_total":0,"doc_count":0,
            "incremental_cost":60.0,"full_rebuild_cost":null}]
  1287 passed, 7 skipped, 1 error
```

**为什么本机全绿、CI 却红**：本机默认口径 `43 skipped`、CI `7 skipped` ——
本机**没设** `GRAPH_REAL_NEO4J_*` ⇒ 所有真图用例 skip ⇒ 那些文件里的写入分支**根本没跑**。
⇒ 判据"本机全量绿"**不足以代表 CI**（教训已并到 §6）。

**处置路径（不许削弱守卫的精神不能动摇）**：用本机 `.env` 的 Neo4j 凭据把真图开关打开
（`GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` / `_USER=neo4j` / `_PASSWORD`），
逐个文件复跑 + 二分定位，得到**三个**同源 writers：

| 文件 | 写入来源 | 本机复跑实测残留 |
|---|---|---|
| `tests/test_kg_incremental_rebuild.py` | `rebuild_incrementally` 成功分支 → `record_incremental_rebuild_cost` | `incremental_cost=15.0` |
| `tests/test_ontology_correction_actions.py` | `merge` / `split` / `rename` 成功分支（内含增量重算） | `incremental_cost=18.0` |
| `tests/test_version_chain_readers.py` | `rename` / `merge` 成功分支（内含增量重算） | `incremental_cost=27.0` |

**三处根因完全同型**：各自的 PG 夹具（`pg_fixture` / `pg_base`）只清理了
`KgVersion` / `OntologyAction` / `EntityMergeCandidate` / `Document`，**没有清理 `CostMetric`**，
而它们用的 org 都是 `settings.default_org_id`。
⇒ 修法照抄 §2：**进出各拍一次行 id 快照，按新增 id 精确删**（不许按 org 全删）。

**验证（三处修完后）**：

```
# CI 等效口径（开真图）全量：1289 passed, 5 skipped, 0 error ；残留行数 = 0
# 默认口径全量          ：1251 passed, 43 skipped, 0 error（与基线逐字相同）
ruff check . / format --check . ：All checks passed / 294 files already formatted
check_seams.py                  ：ERROR 0 / WARN 0 / OK 12
```

（修前的对照：同一套真图全量是 `1289 passed, 5 skipped, **1 error**`。）

---

## 6. 边界对照（7 条 Non-goals 逐条）

| # | 边界 | 结论 |
|---|---|---|
| 1 | 不自动改阈值 | ✅ 未碰 `config.py:302` / `.env.example:328`，**未跑** `--calibrate` |
| 2 | 不动 C3-b 量纲 | ✅ 未碰 |
| 3 | 不做 `stage` 切片契约变更 / 仪表盘改造 | ✅ 未碰 `contracts/` |
| 4 | 不做交付动作 | ✅ 未碰 P6-X / release notes / tag |
| 5 | 不许伪造 `value` | ✅ C3-a / C3-b **仍登记为 `BLOCKED`**，没写 0 |
| 6 | 不许以降低判据换绿 | ✅ 修的是**测试隔离**，没有一条断言被放宽 |
| 7 | 不许起真 LLM | ✅ 全程无 LLM 调用（suite 内均为替身 / mock） |

---

## 7. 遗留与本次裁决结论

1. **C3 真值仍 `BLOCKED`** —— 本会话只把「读取源」洗干净 + 加了守卫，没取真值，等 **D1**。
2. **P6-V5 目录命名**（2026-10-12 裁决）：保留 `changes/P6-V5/` 作为**批次目录**。
   理由（不是喜好，是三条机械口径）：① 它承接的是 `P6-V4` §3 切片表里留下的 **V4-c**，
   编号在 V4 收尾时就已经定下；② P6-V6 是**计划外**插队（CI flaky 修复），不是 V5 的后继；
   ③ 提示词正文、上批次 §15 指针两处都写 P6-V5 ⇒ 改名只会新增第三处矛盾。
   ⇒ 提示词**仍留在它被写下的目录**（`changes/P6-V6/`，符合「提示词落在当前批次目录下」），
   仅在其顶部加一句指向本目录的重定向。
3. **`backend/data/eval/judging/judge-progress.json`：保留，不删。**
   它不是垃圾 —— 是 `scripts/judge_interactive.py`（P6-T 交互式判分，**:43** 的
   `DEFAULT_PROGRESS`）的**续判状态**：`{"G-01": true, "G-02": true}` = **人工已判 2/86 题**，
   写入时间 `2026-10-09 17:08`。脚本 `q` / `Ctrl-C` 就落盘它，下次 `--progress` 接着判 ⇒
   **删它 = 销毁人工判分进度**（且脚本会在 86 题判满前拒绝落判分表）。
   代价权衡：它只有 39 字节，留在工作区只会是 `git status` 的一行；被误 `git add -A` 也不丢。
   ⇒ **不加 `.gitignore`**（加了反而容易被当成"可随意重建的产物"）。
4. **无回归守卫** —— 已按裁决补上（见 §4），§4.1 / §4.2 双向验证；
   **并且它上线不到一轮就抓到了 CI 上另外三处污染**（见 §5）⇒ 值回票价。
5. **⚠️ 本机全量绿 ≠ CI 绿**（本条血泪，下一批开工先看这条）：
   本机没设 `GRAPH_REAL_NEO4J_*` ⇒ 真图用例**默认 skip**（本机 43 skipped / CI 7 skipped）
   ⇒ 那些文件里的写库分支**本机根本没跑**。
   ⇒ 之后凡是动到「真图 / 真 PG 写入」的改动，**收尾前必须**
     `GRAPH_REAL_NEO4J_URI=bolt://localhost:7687 GRAPH_REAL_NEO4J_USER=neo4j GRAPH_REAL_NEO4J_PASSWORD=<本机 .env>`
     再跑一次全量（≈2 分钟），不能只信默认口径的 1251/43。
6. **G-9 T1 在本机仍 skip**（`real_driver` 连不上 Neo4j）⇒ 跨租户判据在本地跑不出证据，
   CI 才是裁决者 —— 与 ADR-0003 §4.1「T1 / T2 必须在 PG 上跑、纳入 CI 必过项」属同一类处理。
