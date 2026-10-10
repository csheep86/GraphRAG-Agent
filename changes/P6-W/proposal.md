# P6-W：DR-E2 最小范围（backup / restore）+ DR-E4 安装验收十项脚本化

> **队列**：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §9.2 序 **6**
> **裁决来源**：**W1 = 方案 I**（2026-10-10 用户拍板，见
> [`changes/P6-V3/integration-log.md`](../P6-V3/integration-log.md) §7）
> **判据源**：[`docs/deployment-spec.md`](../../docs/deployment-spec.md) §6.1 / §6.2 / §6.4 / §10
> **上一批交接**：[`changes/P6-V3/new-session-prompt.md`](../P6-V3/new-session-prompt.md)
> **边界**：本文 §1（Non-goals **9** 条）

---

## 0. 本批到底做什么（**先把 W1 的范围钉死**）

| 半批 | 内容 | 落点 |
|---|---|---|
| **W-a** | DR-E2 **最小**备份 / 恢复能力 | `backup` 命令产出 §6.1 六类对象 + `backup-manifest.json`（各文件 SHA-256 / 大小 / 时刻 / active `kg_version`）；`restore` 命令 = 恢复 + §6.2 版本一致性校验（错位**报错**，非静默启动） |
| **W-b** | DR-E4 §10 十项脚本化的第 **1~7、10** 项 | `install_acceptance.py`，逐项一行 `PASS / SKIP / FAIL + 原因`；第 2 / 3 / 7 项**复用**既有 G，**不重抄断言** |
| 第 8 项 | 落在 W-a 的产出上（它验的就是 `backup-manifest.json`） | 由 `install_acceptance.py --backup-dir <真实备份集>` 验 manifest + SHA-256 |
| 第 9 项 | **顺延 P6-X**，本批**不勾选、不写"已完成"** | 由脚本**机械查** D-1b 前置是否成立（compose 是否仍带 `build:`、全仓是否有 `docker save` / registry）⇒ 现状给出 **SKIP + 原因** |

---

## 1. Non-goals（**9 条** —— 改任何一条之前先按本文 §5 升级）

1. **不做远端 / 对象存储备份**：只落本地目录。**不许**为了自洽把自己扩成 S3 / MinIO 客户端
   （那是新量程，属缝合 2 的另一种实现，需先扩写 ADR-0004 登记行）。
2. **不做加密 / 压缩算法自选 / 增量备份策略 / 备份保留轮转**：最小范围只有"一次全量 + 清单"。
   调度（cron / systemd timer）与 RPO / RTO 承诺**一概不动**（§6.3 仍 TBD-D3）。
3. **不做第 9 项（恢复演练）**：属 P6-X，且当前因 **D-1b** 未落地而**不具备可执行前提**
   （`deploy/docker-compose.yml` 的 backend / frontend / db-init **仍带 `build:`**，且全仓
   **0 命中** `docker save` / `docker load` / 私有 registry ⇒ 独立环境拿不到该 tag 镜像）。
   本批对它只有两个义务：**保持登记不丢**、**不许顺手去做**（那是 P1 的欠账，等 P8-Release 对账）。
4. **不许为了"十项全绿"改判据本身**：要脚本化的是 §10 的**表**，不是反过来把表里不合理的地方
   顺手改掉。⇒ `docs/deployment-spec.md` §10 的表格**一行不改**；本批对该文档的唯一改动是
   §6.1 补一条**实现约束注记**（pg_dump 必须以 BYPASSRLS 角色执行 —— §4 F-P6W-1 实测），
   那不是判据，是"照 §6.1 原文去写会当场失败"的事实。
5. **不重抄第 2 / 3 / 7 项的断言**：这三项已有 **G-23 / G-9 / G-26** 在 CI，脚本**委托 pytest 跑既有用例**
   并断言"真的跑了 N 条且绿"，不再抄一份等价断言（重复实现迟早漂移）。
6. **不改 `frontend/`**、**不改契约**：`export_openapi.py --check` 零 diff 为判据
   （含描述文本 ⇒ X-5 仍不在本批）。
7. **不夹带** X-5 契约描述文本、`cost/dashboard` 的 stage 切片、P5H-6 跨版本边 —— 各自有批次。
8. **不动 P6-V3 的成果**：两侧写入方唯一性、`_graph_elements` 单一换算口、`stage` 两档取值。
   **不许虚构备份 / 恢复 / 演练结果**：没跑就是没跑，SKIP 要写出"在哪台机器上/补什么才能跑"。
9. **AI 不得代填任何 `correct` 值**（A3）——永久红线；本批也不代回签 P6-X 的演练结果。

> ⚠️ 若实现中发现必须触碰某条 Non-goal ⇒ **先缩范围再报告**
> （哪份文档哪一行 / 改什么 / 为什么绕不过 / 试过的替代方案）。

---

## 2. 决策表

| # | 决策 | 定案 / 建议 |
|---|---|---|
| **W1** ✅ | 第 8 / 9 项怎么办（DR-E2 零基础） | **已裁决 = 方案 I**（2026-10-10 用户）：本批补 DR-E2 最小范围（`backup` + `restore` 两条命令 + `backup-manifest.json` 契约，含 SHA-256）；第 8 项随之落地；**第 9 项顺延 P6-X**。**不动**调度 / 远端 / 加密 / 增量 / RPO-RTO |
| **W2** | "机器可跑"的定义 | 建议：**能进 CI 的进 CI**；依赖目标环境 / 真 LLM / 独立环境的给**明确 SKIP 档位 + 原因**，登记到 F-3 灰区 |
| **W3** | 第 4 / 5 项要不要 live LLM | 建议：**默认 mock 档**；真 LLM 沿用 D6 **不进 CI** ⇒ 本批这两项默认 **SKIP + 原因** |
| **W4** | 十项脚本落哪 | 建议新建 `backend/scripts/install_acceptance.py`，逐项 `PASS / SKIP / FAIL + 原因`；备份 / 恢复**另立两条命令，不塞进同一个脚本** |
| **W5** | 判据重复怎么办 | 建议**复用**既有 G，脚本只断言"这些构件跑过且绿" |
| **W6** 🆕 | pg_dump 用什么角色连库 | **必须 BYPASSRLS（超级用户）** —— F-P6W-1 实测：`app_rls` / `app_owner` 均 **EXIT=1**（`query would be affected by row-level security policy`），超级用户 **EXIT=0**。⇒ 备份 DSN 走 `--pg-dsn` / env `BACKUP_PG_DSN`，**默认不是**应用的受限账号；配套注记写进 §6.1 |
| **W7** 🆕 | `.env` 恢复要不要自动覆盖 | **不要**。恢复只产出**脱敏副本**并显式提示"密钥须现场重填"——自动回写会把客户的新密钥盖掉 |

---

## 3. 验收判据（每条都要能贴机器输出）

1. `backup` 产出 §6.1 六类对象 + `backup-manifest.json`（各文件 SHA-256 / 大小 / 时刻 /
   active `kg_version`）；`restore` 后校验 §6.2 两条，**尤其 PG active 版本 == Neo4j 中该版本节点存在**
   ——错位须**报错退出**（非 0），不许静默启动。两者都要有**机械判据**。
2. 十项**逐条**要么 PASS 有机器输出、要么 SKIP 有**明确登记的原因**（含它在哪个环境才能跑）。
3. 第 2 / 3 / 7 项**复用**既有 G-9 / G-26 / G-23，**不重抄**断言。
4. **第 8 项**的 PASS 必须建立在**真实 backup 产物**上；不许出现"只检查文件存在与否"的恒绿实现（**R-9**）。
5. **第 9 项**显式登记 **"顺延 P6-X；且当前因 D-1b 未落地不可执行"**，机器查得出来，不得写成"已完成"。
6. 脚本输出**可机读**（每条一行 + `--out` JSON）。
7. `pytest` **不降**（基线 **1191 passed / 5 skipped**）；五项门禁读数不变。
8. 回登：`changes/P6-W/integration-log.md` + `delivery-requirements-and-guardrails.md`
   （**DR-E2** ⏳ → **部分**、**DR-E4** ⏳ → **部分**）+ `docs/acceptance-traceability-matrix.md`。
9. **不许**因本批产出 backup / restore 脚本就宣称"具备可恢复能力"——那句话的证据只能来自
   **P6-X 的双人演练**；DR-E2 **最多标到"部分"**。

---

## 4. 遗留 / 依赖登记

| # | 项 | 状态 |
|---|---|---|
| **F-P6W-1** | G-26 的 `ENABLE` + `FORCE` RLS ⇒ **pg_dump 必须由 BYPASSRLS 角色执行** | 2026-10-10 实测（本文 §2 W6） |
| **D-1b** | 离线镜像包 / 私有 registry（P1 欠账），P6-X 与 §10 第 9 项的硬前置 | **只登记不处置**，等 P8-Release |
| **TBD-7** | `cost_ratio` 阈值未拍板 ⇒ C3-b 仍 BLOCKED | 本批不动 |
| **P6-T** | 86 题判分（已判 2 题） | 本批不动 |
