# P6-O · 集成日志（**G-12 转正**：variant 矩阵构建由 `--` 转为常驻门禁）

> **日期**：2026-10-06 ｜ **边界文档**：`changes/P6-O/proposal.md`（Non-goals **10 条**已冻结，S1 实测读到 10 条）
> **目标**：G-12 由 `[--]` 挂起 → `[OK]` 已生效（开工自检实测：改前 `[OK] 73 / [~~] 0 / [--] 2`，另一条 `[--]` 是 G-23，不在本批）
> **拍板**：O-D1 命名 `internal-demo`（先过契约词频）／O-D2 **偏离**（见 §5：未写 `domain_profile`）／
> O-D3 **骨架阶段**（只判 yaml 可解析 + 顶层是映射）／O-D4 `base_ref` 机械核对 = **v1.6.0**
>
> **一句话**：第二个**真实部署形态**（需求基线 §300 点名的 demo 内部演示形态）落地 ⇒ 变体达 **2 个**
> ⇒ G-12 摘 `xfail` 转常驻门禁。**绿灯只代表矩阵机制可跑，不代表多客户交付已验证。**

---

## 1. T1 调查批（**只读，先查证再造** —— 顺序未反）

| # | 调查项 | 实测命令 | 机械读数 | 结论 |
|---|---|---|---|---|
| **T1.1** | `domain_profile` 有无**代码消费者** | 全仓 `rg domain_profile`；`rg "domain_profile\|domainProfile\|domain-profile" backend/` | 全仓 **6 处**，全部在 `docs/adr/ADR-0007` 与 `changes/P6-O/` 文档；**`backend/` 0 命中** | ❌ **零消费者** |
| **T1.2** | 两业务域是否**都真实入图** | `system_session()` 直查 `kg_versions` / `documents` / `affiliation_tasks` / `affiliation_suspicions` | `kg_versions` **1 条** = `attendance-demo-v1`（`ready`）；`documents` 6；`affiliation_tasks` **0**；`affiliation_suspicions` **0** | ❌ **实证前提不成立** |
| **T1.3** | 候选名契约词频（proposal §2 指定命令） | `(Select-String -Path contracts/openapi.yaml -Pattern "<名>" -AllMatches).Matches.Count` | `internal-demo` **0** ／ `baseline` **0** ／ `demo` **3** ／ `default` **60** | ✅ 可用（**顺带发现**：`baseline.yaml` 头注记 `default` 为 10 次，实测 **60 次**，已漂移 ⇒ 已在该头注订正，结论不变） |
| **T1.4** | `app_version`（决定 `base_ref`） | `get_settings().app_version` | **1.6.0** | ✅ `base_ref: v1.6.0` |

**T1 的两条硬结论（直接改写 O-D2，见 §5）**：

- `domain_profile` **无消费者** ⇒ 按 proposal §3 的 O-D2 前置，**不许写**；
- 且 T1.2 显示「两域都入图」这个**差异实证本身也不成立** ⇒ 即便有消费者，该维度本批也无实证支撑。

## 2. 落地了什么（3 个文件 / +1 新文件）

| 文件 | 改动 |
|---|---|
| `deploy/variants/internal-demo.yaml` | **新增**（第二个真实部署形态）：`customer: internal-demo` / `base_ref: v1.6.0` / `plugins: [json-csv-export 1.0.0]`；头注记明命名依据与**没写 `domain_profile`** 的两条理由 |
| `deploy/variants/baseline.yaml` | 头注 **两处同步**：①「只产 1 个变体 / G-12 仍挂起」已过时 ⇒ 改为 P6-O 已补第二个形态；② 词频订正 `default` 10 → **60** |
| `backend/tests/test_guardrails_delivery.py` | 摘 `test_g12_variant_matrix_builds` 的 `@pytest.mark.xfail(strict=True)`，补转正注记；`pytest` 因此无消费者 ⇒ 删该 import |

## 3. 转正流程（**先真通过，再摘标记** —— 不是只删标记）

| 步 | 命令 | 结果 |
|---|---|---|
| ① 未摘标记、已加第二个变体 | `pytest tests/test_guardrails_delivery.py -v` | `[XPASS(strict)]` ⇒ **FAILED**（机制强制，实测到过） |
| ② 摘标记后 | 同上 | **8 passed**（含 `test_g12_variant_matrix_builds PASSED`、`test_g14_base_contract_has_no_customer_specific_fields PASSED`） |
| ③ 护栏状态 | `scripts/check_startup_readiness.py` | G-12 由 `[--]` → **`[OK]`**；`[--]` 仅剩 G-23（不在本批） |
| ④ **反向验证** | 移走 `internal-demo.yaml` → 跑单条 → 还原 → 跑单条 | 移走 ⇒ **1 failed**（`variant 只有 1 个`）；还原 ⇒ **1 passed** |

## 4. 验收判据逐条（proposal §6，8 条全机械）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| ① | G-12 摘 `xfail` 后 PASS | **PASSED**（且摘前 `XPASS(strict)` 判红已实测） | ✅ |
| ② | G-14 不假红 | `test_g14_base_contract_has_no_customer_specific_fields` **PASSED** | ✅ |
| ③ | 护栏 `[--]` → `[OK]` | `check_startup_readiness.py`：**G-12 `[OK]`** | ✅ |
| ④ | 全量 `pytest ≥ 998`／0 回归 | 本地 **991 passed / 11 skipped / 2 xfailed / 0 failed**；改动前同口径对照 **990 / 11 / 3** ⇒ **+1 passed −1 xfailed（= G-12 转正），0 回归**。绝对值未达 998 的原因已机械定位：**11 条 skip 中 8 条 = 真图用例**（本地无 `GRAPH_REAL_NEO4J_*` ⇒ 整批 skip，CI 由 job env 注入）＋ 3 条 `TEMPORAL_TRACK_REAL_URI` 本地独占 ⇒ 991 = 999 − 8。**CI 终裁（判据 ④）**：run **`37433603894`** / job `112169957664` —— **997 passed / 5 skipped / 2 xfailed / 0 failed**
（= CI 基线 996 **+1** / xfailed 3→2，**差的那 1 条正是 G-12**，0 回归）⇒ ✅ **0 回归达成**。
⚠️ **字面阈值 998 未达，已量化归因（未放宽任何判据）**：本地 991 = 999 − **8 条真图用例 skip**
（本地无 `GRAPH_REAL_NEO4J_*`，CI 由 job env 注入）；CI 侧 997 = 基线 996 + 1。**判据本身未被改动**
（启用条件仍 `≥2`、未摘其它标记、未 skip 任何用例）⇒ 属"本地环境口径差"，非需求未达成。**✅ 2026-10-06 用户裁决：按 CI 口径结案**（不再追本地 998）
⇒ 本地环境的 8 条真图/RLS 债**另立 R28**（`docs/dev-doc-status.md` §8），本批不修、不越界。 |
| ⑤ | 契约零 diff | `export_openapi.py --check` ⇒ `[OK] 与模型一致` | ✅ |
| ⑥ | 门禁 ERROR 0 | `ruff check` **All checks passed** ／ `ruff format --check` **237 files** ／ `check_seams --base HEAD` **ERROR 0 / WARN 0 / OK 10** | ✅ |
| ⑦ | 反向验证 | 见 §3 ④（删 ⇒ 红／还原 ⇒ 绿）；`git status` 确认无临时残留 | ✅ |
| ⑧ | 状态登记 | 需求基线 §2.2（G-12 行）／§3（A 组映射）／§3.2（A1 / A3 行）+ `dev-doc-status.md` §0 追加段 ⇒ 🟡 → **✅ 已生效**，**均保留**「绿灯只代表机制可跑、不代表多客户交付已验证」注记 | ✅ |

## 5. 偏离登记：O-D2 未按建议项写 `domain_profile`（**有文档授权，非自作主张**）

proposal §3 的 O-D2 **前置条款**写死：「无消费者 ⇒ **不许写**这个字段，改用别的**有实证**的差异维度；
若确实需要先建消费者 ⇒ 那属于另一批，升级用户」。

本批实测命中前半段（T1.1 零消费者 + T1.2 实证不成立），**且找到了别的真实差异维度**
⇒ 按文档指令执行，**不升级用户**：

- **差异维度落在 `customer`（部署形态标识）** —— 它是 **G-14 真实消费**的字段
  （`_customer_tokens()` 读文件名 stem 与 `customer` 值），不是"没人读的差异"；
- 两个形态均由 **需求基线 §300 点名**（demo 内部演示 + default 基线），**非捏造客户**
  （实证资产：`backend/scripts/demo_rehearsal.py`、`docs/demo-seed-dataset.md`、`demo/`）；
- 未新建任何消费者 ⇒ 未越界到"另一批"。

## 6. 未达成 / 不许外推（照实登记）

1. **真实镜像构建仍未验证**：骨架阶段只判「yaml 可解析 + 顶层是映射」（ADR-0007 §3.2 的变体镜像构建
   依赖 deploy 侧流程）⇒ **不得**宣称"构建成功已验证"。
2. **绿灯 ≠ 多客户交付已验证**：G-12 只证明矩阵机制可跑。
3. **本地绝对值 991 < 998**：差值 8 条全部是本地无真图 env 的 skip，已在 §4 ④ 量化；
   若在 CI 上数字与基线（996）不符 ⇒ 以 **CI 结论**为准并回登本节。
4. **本地有图口径的既有环境债**（与本批无关，如实登记）：注入真 Neo4j 凭据后跑出
   `986 passed / 8 skipped / 2 xfailed / **8 failed**`（G-25 语料门槛 3 / G-9 图谱 1 / G-26 RLS 3 / sentinel 1）。
   **非本批引入**：`deploy/variants/` 的消费者只有 `test_guardrails_delivery.py` 与
   `check_startup_readiness.py`（`rg "deploy/variants\|VARIANT_DIR"` 全仓仅此两处），
   本批改动**触达不到**那些用例；且无图口径下改动前后对照为 **990 → 991（0 failed）**。

## 7. 提交与推送（**push 未成功，命令已交用户**）

| 项 | 状态 |
|---|---|
| 提交 | ✅ `8e80935` `feat(g12): 落第二个真实部署形态 internal-demo，G-12 转正常驻门禁`（**7 files / +144 / −28**） |
| 推送 | ✅ **第 19 次成功**（`7fea6484..2afb8555 main -> main`）——前 18 次全失败：`Recv failure: Connection was reset` / `Failed to connect to github.com:443 after 21s`（**非 DNS**，与历史病例同型：曾拒 9 次第 10 次成功）。**未**改用 `--force`、**未**换远程 |
| **CI 实证（判据 ④ 终裁）** | ✅ run **`37433603894`**（sha `2afb855`）**四 job 全绿**：后端 `112169957664` ／ 契约校验 `112169957837` ／ 前端 lint+`gen:api` `112169957847` ／ 流水线汇总 `112170698376`（`gh run watch --exit-status` = **0**）。后端 pytest **997 passed / 5 skipped / 2 xfailed / 0 failed**（基线 996 ⇒ **+1** = G-12 转正，0 回归）；**前端 `gen:api` 无 diff**（判据 ⑥ 末项由 CI 兜住）。 ⇒ 差值归因见 §4 ④ |
