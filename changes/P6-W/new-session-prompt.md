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

**§10 第 9 项今天改成 SKIP 时说的理由是这句话**（`scripts/install_acceptance.py` 第 9 项现查现算）：

> **顺延 P6-X；且当前因 D-1b 未落地不可执行**：compose 仍带 `build:`（backend, db-init,
> frontend）⇒ tag 只能本机构建，独立环境拿不到；CI 工作流 / deploy / scripts 下未发现
> docker save / load / push registry 的步骤或产物（docs/ 里的描述不算——那是计划不是交付物）

**三条为什么是它**（机械理由，不是排期感觉）：

1. **P6-W 把能脚本化的都脚本化了，剩下来的卡在同一个前置上** —— `install_acceptance.py`
   十项里唯一不是"目标环境/真 LLM"缺口的就是第 9 项，而它的前置是 **D-1b**。
2. **D-1b 是"⏳ 只登记不处置，等 P8-Release 对账"的既定项**，2026-10-10 又查实一遍仍未落地 ⇒
   P6-X 现在开工会在同一堵墙上撞第二次。
3. **P6-X 是双人环节**（执行者 ≠ 见证者）、且明确写了 **AI 不能单独收口** ⇒ 它不是"继续写代码"，
   它需要**人**在环路里，所以是新的会话起点而不是本批的尾巴。

> ⚠️ **AI 不得代填 `correct` 值（A3）、不得代做或代收口 P6-X 的演练结果**。
> AI 在这批只做：搬运、机械校验、跑命令、回登。

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
| D-1b 的状态行 | `docs/deployment-spec.md` §12（缺口表）「**D-1b** 离线镜像包（`docker save`）/ 私有 registry ｜ **P1**（DR-A6） ｜ **⏳**」 —— 本批**没有**把它挪动，仍是 ⏳ |
| "独立环境"的定义 | `docs/deployment-spec.md` §6.4 引言（三个判据：无 `build:` / 独立卷端口 `.env` / 与其它环境不共享） |
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
| **DR-E4** | 🟡 **部分** | `install_acceptance.py` 十项三态机读；本机实测 **PASS 3 / SKIP 6 / FAIL 1** |
| 第 8 项 | ✅ 建立在真实产物上 | 见 `integration-log.md` §4.3 / §4.6 |
| 第 9 项 | **SKIP（顺延 P6-X）** | 由脚本机械查 D-1b 登记，不留白 |
| X-5 / P6-V3 / P5H-6 | 未动 | 各自有批次 |

---

## 7. 基线（验收判据的唯一 Motherboard）

| 项 | 数值 |
|---|---|
| pytest（有图口径三变量已设） | **1235 passed / 6 skipped**（P6-W 改前 **1191 / 5**；`+44 / +1`，无 FAILED） |
| 护栏 | `[OK] 17 / [~~] 0 / [--] 0` |
| 接缝 | `ERROR 0 / WARN 0 / OK 12` |
| OpenAPI | 零 diff |
| 有图口径 | **必须同时设 `GRAPH_REAL_NEO4J_{URI,USER,PASSWORD}`**，少设会静默 skip；本机 Neo4j 容器口令 = `ci-graph-pw-2026` |

---

## 8. 验收判据（**每条都要能贴机器输出**）

1. **先立边界再动手**：新批次必须先写边界文件（`changes/<新批次>/proposal.md`，Non-goals ≥ 8 条）。
2. **P6-D1b（若走这条）**：① `deploy/docker-compose.yml` 里 backend / frontend / db-init
   **不再有 `build:`**，只有 `image: <固定 tag>`（非 latest）；② `.github/workflows/` 或
   `scripts/` 里真的有产出离线包 / push registry 的步骤；③ 用
   `uv run python scripts/install_acceptance.py` 第 9 项复核 D-1b 那句 SKIP 原因**确实变了**。
3. **P6-X（若走这条）**：① `docs/drills/restore-drill-*.md` 真实存在并标注「内部演练，
   非客户现场验收」；② 第 9 项自动翻 PASS；③ **执行者 ≠ 见证者**，两人都签字。
4. 不论走哪条：`pytest` **不降**（≥ 1235 passed）、五项门禁读数不变。
5. 回登：`changes/<新批次>/integration-log.md` + `delivery-requirements-and-guardrails.md`
   （DR-E2 / DR-E4 是否往前挪一格）+ `docs/acceptance-traceability-matrix.md` H14 行。

---

## 9. 提交与推送纪律

- Conventional Commits；本批新文件全在 `backend/` 与 `changes/`。
- **临时产物别入库**：`backend/reports/` 已被 gitignore；演示用的 scratch 库记得 drop。
- 本机的 uvicorn 背景进程记得清掉。
- 推送后**以 CI 全绿为准**。

---

## 10. 升级用户的四类情况

1. **文档 / spec 与现实不符**，且要停下来先裁决才能继续（例：§10 某项判据在本环境不可能成立）；
2. 要改的东西与 **X-5 / P6-V3 成果 / ADR-0004 §2.1 既有接缝登记集合** 相交；
3. **要不要砍功能**（例如为过 CI 而放宽第 8 项或第 9 项的标准）；
4. 发现的待修项价值 > 本批任务，或原先画好的边界被现实推翻（2026-10-10 前车：P6-V3 一次选型带出了整条 Γ-落地）。

---

## 11. 不许外推

- ❌ 不许因脚本在跑就宣称"第 9 项已接近完成"；
- ❌ 不许因本机实测 PASS 3 就写「十项里过了三项」: SKIP 是没跑到、不是过了，换台机器读数还会变；
- ❌ 不许因已有 `restore` 就宣称"具备可恢复能力"，那句话只能来自 P6-X。
