# 下一批开场提示词（写给 P6-W 之后的那一批）

> **用法**：新会话里把本文**全文**粘贴给 AI（或直接让它读本文件路径）。
> **用途**：给 AI 一个精确到文件和行号的起点，避免"先聊半小时找回上下文"。

---

## 0. 你要读的三份文件

```
1. changes/P6-W/proposal.md 的 §1 Non-goals（9 条）   ← 边界
2. changes/P6-W/integration-log.md                   ← 上一批实测证据与残留风险
3. docs/delivery-plan.md §9.2（队列 §9.2 序 6 / 7）   ← 排期
```

---

## 1. 确认起点（**这是重点，先答"是/不是"**）

**起点 = `delivery-plan.md` §9.2 序 **7** 的 P6-X（演练留证）**，或由你裁决改走
**P6-D1b（先落离线镜像包 / 私有 registry）**。

### 1.1 执行模式：**人做主体**（**不是 AI 批**，见 `delivery-plan.md` §9.3 第 2 条）

> §9.3 原文：「**演练**：独立环境（固定 tag 镜像）+ **执行者 ≠ 见证者**，留证要标注"内部演练"」
> ——这一条和「判分」「两条裁决」并列明列 **AI 不得代做**。

| 动作 | 谁做 | 备注 |
|---|---|---|
| 准备**独立环境**（独立 compose 项目 / 卷 / 端口 / `.env`）、起停容器、拉或载镜像 | **人** | 见 §6.4②：`docs/deployment-spec.md:196-197` |
| 执行恢复 / 升级 / 回滚的**命令本身** | **人（执行者）** | AI 可以**在旁**把命令输出搬进 md |
| 逐条判 §10 十项、**签字**、写下"通过 / 不通过"的结论段 | **人（见证者）** | 执行者 ≠ 见证者 ⇒ `deployment-spec.md:198-199` |
| 搬运输出、跑现成的 `--check` 类命令、**机械**校验（哈希 / pytest 委托 / 脚本三态读数）、回登文档 | **AI**（本会话） | 只做这四类，**一条都不许多做** |

**AI 硬禁止清单**（写死，不因"反正差不多"而放宽）：

1. ❌ **不得代写演练结论**（"通过 / 不通过"、起因分析、RTO/RPO 读数结论都算）；
2. ❌ **不得代签 §10 的任何一个 √**，也不得把 `install_acceptance.py` 的 SKIP 事后改写成 PASS；
3. ❌ **不得自己给自己当见证人** —— 执行者（哪怕是 AI 跑的命令）与见证者必须是**两个不同的人**；
4. ❌ **不得代填 `correct` 值**（A3 纪律）；
5. ❌ **不得为了"推进下去"而放宽 §6.4 的三条独立环境判据** —— 放宽一次，整份留证作废；
6. ✅ **允许**做的只有：搬运输出、跑**既有**命令与脚本、机械比对、回登 `integration-log.md` 与文档状态表。

### 1.2 工量查实（**¥0，2026-10-10 已做，别照搬文档里的乐观口径**）

写提示词之前先把活量摸了一轮，**六条机械结论**：

| # | 查了什么 | 结论（**全是今天的机器读数**） |
|---|---|---|
| **M1** | 有没有**可复用**的演练模板 | ❌ **没有**。`docs/drills/` 目录**不存在**；`git log --all --diff-filter=A -- "*drill*"` **零命中**（历史上从未提交过任何 drill 文档）⇒ 第一份 `restore-drill-<日期>.md` 要**从零写**，不能"复制上一版改改"（这是「旧判分表能否复用」的同款结论：**不能**） |
| **M2** | 现在十项读到什么 | 不带任何参数跑 `install_acceptance.py --skip-pytest`：**`PASS 0 / SKIP 10 / FAIL 0`** ⇒ 十项**一项都没在验**（不是"过了十项里的零项"，是**全没跑到**） |
| **M3** | 版本号 / 迁移坐标齐不齐 | ✅ **源码坐标齐**：13 个 git tag（`v1.0.0`…`v1.6.0`）+ `backend/migrations/versions/` 下 **14 个迁移脚本**（基线 `00f44b912817` … `a1f7c2b93d04`）。⚠️ **但别外推**：这些都是**源码侧**坐标；§6.4①要的是 **`image: <固定 tag>` 镜像**，而 D-1b 未落地 ⇒ **可交付的镜像 tag 一个都没有** |
| **M4** | DR-E3 升级演练现在能不能做"原地升级" | ❌ **不能**。`deployment-spec.md:230` 迁移纪律写明「**D-2 未补齐前，升级只允许"全新部署 + 数据导入"，严禁原地升级**」，而 D-2 的"逐版本可幂等迁移纪律 + PG 实测"仍在 P6 ⇒ **升级演练只剩窄口径**（或先补 D-2，那是**另一条审批链**） |
| **M5** | P6-X 内部还有没有顺序 | ✅ 有。`deployment-spec.md:235` 第 1 步「**备份（§6）+ 校验可恢复 ← 不备份不升级**」⇒ **先 restore-drill，再 upgrade-drill（含回滚）**，不能并行开两份 |
| **M6** | 恢复后要"跑通 §10 冒烟"，那也要跑全十项吗 | 按 §6.4 第 3 条**只要求六件事**：服务起 → health 200 → License 状态正常 → 抽样 1 条文档可查 → 抽样 1 次问答有引用 → **跨租户隔离仍生效**。其中「跨租户隔离」= §10 第 7 项 ⇒ **必须先在目标环境给 org B 主体授权**（`scripts/seed_dev_rbac.py` 刻意只播默认 org），否则这一步会读到 SKIP 而不是 PASS |

**§10 第 9 项今天显示 SKIP 时说的理由**（`scripts/install_acceptance.py` 第 9 项**现查现算**，不是写死的文案）：

> **顺延 P6-X；且当前因 D-1b 未落地不可执行**：compose 仍带 `build:`（backend, db-init,
> frontend）⇒ tag 只能本机构建，独立环境拿不到；CI 工作流 / deploy / scripts 下未发现
> docker save / load / push registry 的步骤或产物（docs/ 里的描述不算——那是计划不是交付物）

**三条为什么是它**（机械理由，不是排期感觉）：

1. **P6-W 把能脚本化的都脚本化了，剩下来的卡在同一个前置上** —— `install_acceptance.py`
   十项里唯一不是"目标环境/真 LLM"缺口的就是第 9 项，而它的前置是 **D-1b**。
2. **D-1b 是"⏳ 只登记不处置，等 P8-Release 对账"的既定项**，2026-10-10 又机械查实一遍仍未落地
   （见 M2 / M3）⇒ P6-X 现在开工会在同一堵墙上撞第二次。
3. **P6-X 是双人环节**（执行者 ≠ 见证者）、且 §9.3 明列 **AI 不得代做** ⇒ 它不是"继续写代码"，
   它需要**两个不同的人**在环路里，所以是新会话的起点而不是本批的尾巴。

---

## 2. 开工自检（`cd backend`）

```bash
uv run python scripts/check_startup_readiness.py     # 护栏真实状态：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                 # ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check      # 零 diff
uv run python scripts/extract_seam_signatures.py --check
uv run python scripts/install_acceptance.py --skip-pytest   # 十项三态，作为"改前快照"留痕
```

| 读数不对时 | 该怎么做 |
|---|---|
| `[--]` / `[~~]` 不为 0 | **对应 DR 一律不得宣称完成**；转正的唯一方式是让测试真过再删 `xfail` |
| `check_seams` 报 WARN | 先看 docs/adr/0004 §2.1 登记行与实现集合是不是又漂移了 |
| OpenAPI 有 diff | 先跑 `uv run python scripts/export_openapi.py` 再查为什么手改过契约 |

---

## 3. 边界纪律

> **新批次必须先写边界文件（Non-goals ≥ 8 条）再动手**。`changes/P6-W/proposal.md` §1
> 那 9 条只对 P6-W 有效，**不许沿用**。

建议至少覆盖（按 P6-X / P6-D1b 各自重新写）：

1. 不做改变版本号以外的重构；
2. 不乱改 compose 里无关的服务；
3. **不许为了让第 9 项变绿而"先把 √ 勾上"** —— 它必须由 `docs/drills/restore-drill-*.md`
   的出现来翻绿（`install_acceptance.py::check_9` 就是这样判的）；
4. 不碰 `frontend/`、不改契约（X-5 描述文本仍悬置）；
5. 不夹带 X-5 / `cost/dashboard` stage 切片 / P5H-6；
6. 不动 P6-W 三条命令的既有行为（要改先升级）；
7. 不许虚构演练结果；
8. AI 不得代收口。

---

## 4. 已查证坐标表（**P6-W 交付时的真实行号/口径**）

| 项 | 位置 |
|---|---|
| 备份 / 恢复的唯一换算口 | `backend/app/services/backup.py`（清单结构、`verify_manifest()`、`evaluate_version_consistency()`、`redact_env_text()`、`split_pg_dsn()`） |
| 三条命令 | `backend/scripts/backup.py` / `restore.py` / `install_acceptance.py`（各自 `main(argv) -> int`） |
| 判据用例 | `backend/tests/test_backup_restore.py`（23 条）/ `backend/tests/test_install_acceptance.py`（22 条） |
| 第 9 项的机械查证 | `scripts/install_acceptance.py::inspect_d1b()` + `check_9()` |
| D-1b 的状态行 | `docs/deployment-spec.md` §12（缺口表）「**D-1b** 离线镜像包（`docker save`）/ 私有 registry ｜ **P1**（DR-A6） ｜ **⏳**」 —— P6-W **没有**把它挪动，仍是 ⏳ |
| "独立环境"的定义 | `docs/deployment-spec.md:192-203`（§6.4 引言三条判据）+ **留证命名**（`restore-drill-<日期>.md` / `install-acceptance-<日期>.md`，须标「内部演练，非客户现场验收」） |
| 恢复后要验的**六件事** | `docs/deployment-spec.md:207`（服务起 → health 200 → License 正常 → 抽样 1 条文档可查 → 抽样 1 次问答有引用 → 跨租户隔离仍生效） |
| **升级演练的顺序锁** | `docs/deployment-spec.md:235`（第 1 步「备份 + 校验可恢复 ← 不备份不升级」） |
| **原地升级禁令** | `docs/deployment-spec.md:230`（D-2 未补齐前**严禁原地升级**，只允许"全新部署 + 数据导入"） |
| AI 不得代做的原文 | `docs/delivery-plan.md:288-292`（§9.3 第 2 条「演练」） |
| 迁移脚本清单 | **`backend/migrations/versions/`**（注意不是 `alembic/versions`）：14 个脚本，基线 `00f44b912817` … `a1f7c2b93d04`（CostMetrics `stage` 列） |
| 版本 tag | `git tag`：13 个（`v1.0.0`…`v1.6.0` + `sprint-1-done`）—— **源码 tag，不是镜像 tag**（见 §1.2 M3） |
| §10 十项表 | `docs/deployment-spec.md` §10 |

---

## 5. 决策表

| # | 决策 | 建议 |
|---|---|---|
| **X1** | P6-X 与 P6-D1b 谁先 | **建议先 P6-D1b**：没有它，P6-X 的每一次尝试都只能停在 SKIP |
| **X2** | 第 9 项何时能翻绿 | `docs/drills/restore-drill-*.md` 真正出现时；脚本不再需要改动 |
| **X3** | 第 3 / 7 项在目标环境怎么验 | 已有 `--base-url` / `--org-a` / `--org-b` 勾选项；**org B 主体要先授权**（`scripts/seed_dev_rbac.py` 目前刻意只播默认 org） |
| **X4** | 第 4 / 5 项要不要真 LLM | 沿用 **W3 / D6**：默认 SKIP，不进 CI |
| **X5** | F-P6W-3（`.env.example` 的 `PRIVATE_DEPLOY_ENABLED=false`） | **待你们裁决**：本批只登记未改 |

---

## 6. 已完成项（P6-W）

| DR | 状态 | 说明 |
|---|---|---|
| **DR-E2** | 🟡 **部分** | `backup` / `restore` 两条命令 + `backup-manifest.json`（重算 SHA-256）+ §6.2 一致性（错位 ⇒ 退出码 2）。**恢复演练 0 次** |
| **DR-E4** | 🟡 **部分** | `install_acceptance.py` 十项三态机读；带真实参数那趟 **PASS 3 / SKIP 6 / FAIL 1**，**不带参数那趟 PASS 0 / SKIP 10 / FAIL 0**（后者才是"什么都没给"的诚实读数） |
| 第 8 项 | ✅ 建立在真实产物上 | 见 `integration-log.md` §4.3 / §4.6 |
| 第 9 项 | **SKIP（顺延 P6-X）** | 由脚本机械查 D-1b 登记，不留白 |
| X-5 / P6-V3 / P5H-6 | 未动 | 各自有批次 |

---

## 7. 基线（验收判据的唯一 Motherboard）

| 项 | 数值 |
|---|---|
| pytest（最终裁决 = **GitHub Actions**） | ✅ **1234 passed / 7 skipped**（本批 **45 条新用例全 passed，0 skip / 0 failed**） |
| pytest（本机同款命令） | CI 口径（`CI=1` + 三变量）：**1236 / 5**；普通口径：**1235 / 6**；改前基线 **1191 / 5** |
| 护栏 | `[OK] 17 / [~~] 0 / [--] 0` |
| 接缝 | `ERROR 0 / WARN 0 / OK 12` |
| OpenAPI | 零 diff |
| 有图口径 | **必须同时设 `GRAPH_REAL_NEO4J_{URI,USER,PASSWORD}`**，少设会静默 skip；本机 Neo4j 容器口令 = `ci-graph-pw-2026` |

---

## 8. 验收判据（**每条都要能贴机器输出**）

> **⚠️ P6-X 的判据由「人」判，AI 只负责把输出搬进 md 并机械复核签名是否齐全。**

1. **先立边界再动手**：新批次必须先写边界文件（`changes/<新批次>/proposal.md`，Non-goals ≥ 8 条）。
2. **P6-D1b（若走这条，AI 可主导）**：① `deploy/docker-compose.yml` 里 backend / frontend /
   db-init **不再有 `build:`**，只有 `image: <固定 tag>`（非 `latest`）；② `.github/workflows/`
   或 `scripts/` 里真的有产出离线包 / push registry 的步骤；③ 用
   `uv run python scripts/install_acceptance.py` 第 9 项复核 D-1b 那句 SKIP 原因**确实变了**
   （**脚本自己说的才算，不许 AI 口述"我觉得已经可以了"**）。
3. **P6-X（若走这条，人主导）** —— 四件套：
   ① **留证文件**：`docs/drills/restore-drill-<日期>.md`（＋ 若做升级演练再加 `upgrade-drill-<日期>.md`），
   正文**明确标注「内部演练，非客户现场验收」**（§6.4 原话）；
   ② **证据链**：贴**原始命令输出**（不是 AI 复述的摘要）——服务起 / `health 200` /
   License 状态 / 抽样 1 条文档可查 / 抽样 1 次问答有引用 / **跨租户隔离仍生效**（§6.4 六件事）；
   ③ **双人**：**执行者 ≠ 见证者**，两份具名签字都在文件里；缺任一即为**无效留证**；
   ④ **闭环**：第 9 项在下次跑 `install_acceptance.py` 时**自动翻 PASS**
   （脚本认 `docs/drills/restore-drill-*.md` 的出现）。
4. **升级演练的窄口径**（若同一批做）：受 §7.1 迁移纪律限制（**D-2 未补齐前严禁原地升级**，
   `deployment-spec.md:230`）⇒ 要么只做「全新部署 + 数据导入」，要么**先把 D-2 补到 Discipline
   层**再谈；**不许把"全新部署"的演练写成"升级演练"来充数**。
5. 不论走哪条：`pytest` **不降**（CI 口径 ≥ 1234 passed / 7 skipped）、五项门禁读数不变。
6. 回登：`changes/<新批次>/integration-log.md` + `delivery-requirements-and-guardrails.md`
   （DR-E2 / DR-E3 / DR-E4 是否往前挪一格）+ `docs/acceptance-traceability-matrix.md` H14 行。
   **DR-E2 只有在留证文件 + 双人签名齐全后才能从「部分」挪到「完成」；有脚本但零演练，永远不能挪。**

---

## 9. 提交与推送纪律

- Conventional Commits；本批新文件全在 `backend/` 与 `changes/`。
- **临时产物别入库**：`backend/reports/` 已被 gitignore；演示用的 scratch 库记得 drop。
- 本机的 uvicorn 背景进程记得清掉。
- 推送后**以 CI 全绿为准**。

---

## 10. 升级用户的四类情况

1. **文档 / spec 与现实不符**，且要停下来先裁决才能继续（例：§10 某项判据在该环境不可能成立）；
2. 要改的东西与 **X-5 / P6-V3 成果 / ADR-0004 §2.1 既有接缝登记集合** 相交；
3. **要不要砍功能 / 放宽标准**（例如为省事把 §6.4 的"独立环境"改成"本机开发环境"，
   或为让第 9 项翻绿而降低留证要求）—— **这类一律先升级，AI 不得自己放宽**；
4. 发现的待修项价值 > 本批任务，或原先画好的边界被现实推翻
   （2026-10-10 前车：P6-V3 一次「两侧量纲」的选型，带出了给 `cost_metrics` 加 `stage` 列
   这条偏离 X-6 的追加裁决）；
5. **（P6-X 专属）** 见证者临时缺席 / 独立环境起不来 / 镜像 tag 拿不到 —— 停下来**改期**，
   **不许降格为"AI 先跑一遍垫着"**。

---

## 11. 不许外推

- ❌ 不许因脚本在跑就宣称"第 9 项已接近完成"；
- ❌ 不许因本机实测 PASS 3 就写「十项里过了三项」: SKIP 是没跑到、不是过了，换台机器读数还会变
  （**不带参数那趟是 PASS 0 / SKIP 10**，那才是"什么都没给"的诚实读数）；
- ❌ 不许因已有 `restore` 就宣称"具备可恢复能力"，那句话只能来自 P6-X 的双人留证；
- ❌ 不许看到 **13 个 git tag** 就以为"升级演练前置齐了" —— 那是**源码 tag**，§6.4①要的是
  **镜像 tag**，而 D-1b 未落地 ⇒ 可交付的镜像 tag 数为 **0**；
- ❌ 不许把「全新部署 + 数据导入」写成"升级演练"充数 —— §7.1 明列那是**过渡期替代品**，
  且 D-2 补齐前**只允许**这么做，不是"升级"本身；
- ❌ 不许把 AI 复述的输出当作留证正文 —— 留证要贴**原始命令输出**。
