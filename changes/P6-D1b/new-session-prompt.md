# 下一批开场提示词（写给 **P6-X** —— 恢复演练，**纯人工批次**）

> **用法**：新会话里把本文**全文**粘贴给 AI（或直接让它读本文件路径）。
> **用途**：给一个精确到文件和行号的起点，避免"先聊半小时找回上下文"。
>
> ⚠️ **执行模式 = 人做主体**（`docs/delivery-plan.md` §9.3 明列的三条"只能由人做"里，
> **②演练**就在其中）。**AI 在 P6-X 只能做四件事：搬运文件 / 跑命令 / 校验机器输出 /
> 回登文档**；**不得**代做演练动作、**不得**代填判分或结论、**不得**代签任何 √。

---

## 0. 你要读的四份文件

```
1. changes/P6-D1b/integration-log.md       ← 上一批实测证据（离线包已产出 + 残留风险 §6）
2. docs/deployment-spec.md §6.4（独立环境三判据）/ §10（验收清单）/ §11（排期表）
3. docs/delivery-plan.md §9.3              ← 「只能由人做」的三条边界
4. deploy/docker-compose.delivery.yml（全文，逐服务看完）+ deploy/README.md「离线交付」一节
```

---

## 1. 确认起点（**先答"是/不是"**）

**起点 = P6-X：在独立环境做一次恢复演练，产出 `docs/drills/restore-drill-<日期>.md`，
让 §10 第 9 项从 SKIP 变 PASS。**

### 1.1 执行模式：**人做主体**（不是"AI 顺手做掉"）

| 角色 | 能做什么 | **不能**做什么 |
|---|---|---|
| **人（执行者）** | 按 §8 的步骤真跑：起独立环境 → 恢复 → 冒烟 → 写留证 | — |
| **人（见证者）** | 与执行者**不是同一人**，共同署名 | — |
| **AI** | 搬运（拷 compose / tar）、跑命令并贴输出、校验机器读数、回登文档 | **不得**替人跑出"结果"再写成已演练；**不得**代签；**不得**把 SKIP 写成 PASS；**不得**往 `docs/drills/` 里写一个字 |

### 1.2 为什么是它（**机械理由**，不是排期感觉）

1. **它是 §10 第 9 项唯一的翻绿条件**：`install_acceptance.py::check_9` 的判据就是
   `docs/drills/restore-drill-*.md` 存在（`backend/scripts/install_acceptance.py:658`）。
   今天该目录**不存在**（实测 `Test-Path docs/drills` = **False**）⇒ 第 9 项恒 SKIP。
2. **它的硬前置已经在上一批补上了**：P6-D1b 出了交付 compose（无 `build:`）+ 真实 tar
   （496,524,288 字节）+ `delivery-manifest.json`，且 `inspect_d1b(交付 compose)` 实测 `ok=True`
   ⇒ 第 9 项的 SKIP 理由已从"D-1b 未落地"变成"**演练留证未产生**"（实测读数见上一批日志 §4.7）。
   **前置已开，不做就是欠账。**
3. **§6.4 的原文是"不演练 = 没有备份"**：备份脚本（P6-W）与离线包（P6-D1b）都落了，
   但**没有任何一次**"拿交付物在独立环境恢复并跑通冒烟"的证据 ⇒ DR-E2 / DR-A7 / H14
   **都只能标「部分」**，谁都不能拿前面的产物宣称"可恢复 / 可交付"。

---

## 2. 头号约束：**独立环境**的三条判据（§6.4，**缺一条这次演练就不算**）

1. **从交付物部署** —— 用 `deploy/docker-compose.delivery.yml`（**无 `build:`**），
   **不许**用开发的 `docker-compose.yml`（它有 `build:`，从源码起证明不了客户能装上）；
2. **独立度** —— 独立 compose 项目 + **独立数据卷 / 端口 / `.env`**；
   复用开发机现有服务（`graphrag-neo` / `graphrag-pg`）**不算独立**；
3. **执行人 ≠ 写部署脚本的人**，须**一人执行、一人见证**并共同署名。

### 2.1 本机实测的端口账（**做之前先看，别到 `up` 那一步才发现**）

| 端口 | 交付 compose 要用 | 本机现状 |
|---|---|---|
| `127.0.0.1:7474` | neo4j HTTP | 未见占用 |
| `127.0.0.1:7687` | neo4j bolt | ❌ **已被 `graphrag-neo`（开发容器）占用**（`0.0.0.0:7687` LISTENING） |
| `127.0.0.1:8000` / `3000` | backend / frontend | 空闲 |
| 5432 | **不映射**（内部） | 被 `graphrag-pg` 占用（不影响 compose） |

⇒ **同一台宿主机上起交付栈，必须先停掉开发用的 `graphrag-neo`**（或改用另一台机器）。
`deploy/README.md`「本机端口冲突」一节原有规矩：**不许靠改宿主端口绕开** —— 绕开等于没验证默认配置。
若确需在一台机器上并存，**只能**用 `COMPOSE_PROJECT_NAME=graphrag-drill` 隔离项目名与**卷名**
（已实测：`config` 解析出的卷名会变成 `graphrag-drill_*`），**端口仍然会撞** ⇒ 这条要**人**来裁，
AI 不得自行改交付 compose 的端口（改了它就不是交付物了）。

---

## 3. 边界纪律

> **先写边界文件再动手**：`changes/P6-X/proposal.md`，**Non-goals ≥ 8 条**。
> `changes/P6-D1b/proposal.md` 那 11 条只对 P6-D1b 有效，**不许沿用**。

建议至少覆盖：

1. **AI 不得代做演练 / 代签 / 代写 `docs/drills/` 正文**；
2. **不做客户现场验收**（留证必须标注「内部演练，非客户现场验收」）；
3. **不改交付 compose 一个字符**（尤其端口 / tag / `build:`）——改了就不是交付物；
4. **不重做出包 / 不改出包脚本**（已有真实 tar；只在 tar 丢失时才重出，且要重贴 `ls -l`）；
5. **不动 P6-W 的 `backup.py` / `restore.py` 行为**（只许按既有 CLI 跑）；
6. **不改 `install_acceptance.py` 的判据**（第 9 项翻绿只能靠留证**真的出现**）；
7. **不碰任何 registry / 不新增 CI 作业**；
8. **不顺手清 M4 的游离镜像**、不顺手处置 **F-P6W-3**（`.env.example` 的 `PRIVATE_DEPLOY_ENABLED`）；
9. **不许把"包能 load + compose 能解析"写成"演练通过"**（那是上一批已做到的，不是演练）。

---

## 4. 已查证坐标表（**别再查第二遍，直接用；动手前请复核行号**）

| 项 | 位置 |
|---|---|
| 交付 compose | `deploy/docker-compose.delivery.yml`（`name:` 支持 `COMPOSE_PROJECT_NAME` 覆盖） |
| 离线包（本机） | `backend/reports/delivery/graphrag-agent-offline-1.6.0.tar`（496,524,288 字节）+ `delivery-manifest.json` |
| 出包 / 校验命令 | `backend/scripts/build_delivery_images.py`（`--verify` 重算 SHA-256 + 核 image id + 比对 tag） |
| 备份 / 恢复命令 | `backend/scripts/backup.py` / `restore.py`；**完整备份集要求停图库**（F-P6W-2） |
| 第 9 项判据 | `backend/scripts/install_acceptance.py:658`（只认 `docs/drills/restore-drill-*.md`） |
| 既有备份集 | `backend/reports/backup/`（P6-W 产物，**逐条核是否六类齐全**再用） |
| 独立环境定义 | `docs/deployment-spec.md` §6.4（三条判据） |
| 上一批残留风险 | `changes/P6-D1b/integration-log.md` §6（**1 / 2 条就是这个批次要还的债**） |

---

## 5. 决策表（**开工前逐条给建议，不决不动手**）

| # | 决策 | 状态 / 建议 |
|---|---|---|
| **X1** | 在哪台机器上做独立环境 | **未决 ⇒ 人裁**。同机必须先停 `graphrag-neo`（端口 7687 撞车，§2.1）；另一台机器更贴近客户现场，但要先把 tar 搬过去（496 MB） |
| **X2** | 用哪份备份集 | **未决 ⇒ 人裁**。要**六类齐全**的那一份（`neo4j` 不能在清单里是 `skipped` —— 那说明备份时没停图库，恢复出来也不完整） |
| **X3** | 谁来当见证者 | **人定**（执行者 ≠ 见证者，§6.4③） |
| **X4** | 冒烟到哪一步 | 至少跑满 §6.4 末尾的六条：服务起 → health 200 → License 正常 → 抽 1 条文档可查 → 抽 1 次问答有引用 → 跨租户隔离仍生效 |
| **X5** | 第 9 项由谁点 PASS | **脚本自己点**（留证一出现即 PASS）；**人不许手改脚本、也不许在文档里代勾** |
| **X6** | tar 丢了怎么办 | 重跑 `build_delivery_images.py --save`（同一 tag 可复现）；**重出的包要重贴 `ls -l` + manifest** |
| **X7** | 要不要连着做安装验收十项 | 建议**只做第 9 项**（本批范围）；十项全跑属另一条线 |

---

## 6. 上一批已完成项（P6-D1b）

| 项 | 状态 |
|---|---|
| **D-1b 离线包分支** | 🟡 **产物已出**：交付 compose + 出包脚本 + 真实 tar（496,524,288 字节）+ 清单校验通过；`docker load` 与独立项目 `config` 均已实测 |
| **registry 分支** | ⛔ **按裁决 Y8 不做**（本仓库不该出现 `docker login` / `push`） |
| DR-E2（备份 / 恢复） | 🟡 **部分**：脚本齐、**演练 0 次** |
| DR-E4（安装验收脚本化） | 🟡 **部分**：十项三态机读；本机 `PASS 1 / SKIP 9 / FAIL 0`（不带参那趟） |
| X-5 / P6-V3 / P5H-6 / TBD-7 / P6-T | 未动，各自有批次 |

---

## 7. 基线（验收判据的唯一基准）

| 项 | 数值 |
|---|---|
| pytest（**最终裁决 = GitHub Actions**，run 38036390121） | ✅ **1260 passed / 7 skipped**（P6-D1b 新增 **26 条全 passed**，0 skip / 0 failed） |
| pytest（本机 CI 口径：`CI=1` + 三变量） | **1262 / 5**（与 CI 差的 2 条是**真图探针**用例：本机有图库跑、CI 上 skip，既定口径） |
| 护栏 | `[OK] 17 / [~~] 0 / [--] 0`（**G-19 项数 2 → 9**） |
| 接缝 | `ERROR 0 / WARN 0 / OK 12` |
| OpenAPI | 零 diff |
| 有图口径 | **必须同时设 `GRAPH_REAL_NEO4J_{URI,USER,PASSWORD}`**（`bolt://localhost:7687` / `neo4j` / `ci-graph-pw-2026`），少设会静默 skip 37 条 |

**开工自检**（`cd backend`，四项必须全对才能动手）：

```bash
uv run python scripts/check_startup_readiness.py
uv run python scripts/check_seams.py
uv run python scripts/export_openapi.py --check
uv run python scripts/extract_seam_signatures.py --check
uv run ruff check . && uv run ruff format --check .
```

---

## 8. 验收判据（**每条都要能贴机器输出 / 真人署名**）

1. **留证存在**：`docs/drills/restore-drill-<日期>.md`，**显式标注**「内部演练，非客户现场验收」，
   含**执行者 + 见证者两人署名**（§6.4③）。
2. **独立环境**：① 用的是 **交付** compose（无 `build:`）；② 项目名 / 数据卷 / `.env`
   与开发态**不共享**（贴 `docker compose ... config` 或 `docker ps` 输出为证）；
   ③ 端口账与 §2.1 的处理方式写进留证（**停容器**还是**换机器**）。
3. **恢复链路**：`restore.py` 跑完 + **§6.2 一致性通过**（贴输出；版本错位必须退出码 2 ⇒ 那次演练算失败，重做）。
4. **冒烟六条**（§6.4 末尾）逐条有结果；跑不动的要写清**缺什么才能跑**，不许留白。
5. **第 9 项翻绿**：`install_acceptance.py` 的第 9 项输出 **PASS** 并带留证文件名
   （**这是脚本算出来的，不是人写上去的**）。
6. **护栏 / 门禁不降**：pytest ≥ **1262 passed**；五项门禁读数不变；**不得**为翻绿改 `check_9` 的判据。
7. **回登（AI 可做）**：`changes/P6-X/integration-log.md` + `docs/deployment-spec.md` §11
   （D-1b 行 / 备份恢复行）+ `docs/acceptance-traceability-matrix.md` **H14 行**
   + `docs/drills/` 索引（若有）。

---

## 9. 提交与推送纪律

- Conventional Commits（`docs(drills)` / `chore(p6-x)` 等）。
- **绝不入库**：镜像 tar、`delivery-manifest.json`、`.env`；`docs/drills/` 的留证**要入库**。
- **网络提示**：本机到 `github.com:443` 会间歇性 `Recv failure` ⇒ push 失败**先等 60~150 秒重试**，
  不要改 remote、不要 force。
- 推送后**以 CI 全绿为准**。

---

## 10. 升级用户的四类情况

1. **文档 / spec 与现实不符**，且要停下来先裁决才能继续（例：§6.4② 的"独立端口"在本机只能通过
   停开发容器满足，而停容器会影响正在跑的其他验证）；
2. 要改的东西与 **X-5 / P6-V3 成果 / ADR-0004 §2.1 接缝登记集合** 相交；
3. **要不要砍功能 / 放宽标准**（想把冒烟六条砍成三条、想用开发 compose 顶替交付 compose、
   想让 AI 代写留证正文）—— **一律先升级，AI 不得自己放宽**；
4. **演练失败了怎么办**（恢复后一致性错位 / 服务起不来）——先把失败**原样**登记进
   `changes/P6-X/integration-log.md` 并升级，不许修脚本让它变绿。

---

## 11. 不许外推

- **不许**因为"留证文件建好了"就宣称演练通过 —— 通过与否只能来自 §8 的六条冒烟与 §6.2 一致性输出。
- **不许**用开发 compose（带 `build:`）起的栈冒充交付物演练 ⇒ 那证明不了客户能装上。
- **不许**复用开发机现有服务（`graphrag-neo` / `graphrag-pg`）当独立环境（§6.4② 明令不算）。
- **不许** AI 往 `docs/drills/` 写正文、代签署名、或在 §10 清单上代勾任何一个 √。
- **不许**把上一批的"包能 load + compose 能解析"当成演练证据 —— 那只到"能装上"之前的一步。
- **不许**用 `docker images` 的展开大小当传输体积（tar 才是）：实测 tar = **496,524,288 字节**。
- **不许**为了翻绿去改 `install_acceptance.py::check_9` 或给第 9 项套 `xfail`（**R-9 恒绿即失效**）。

---

## 12. 下一批指针

P6-X 收口后（第 9 项 PASS、H14 可往上抬一档），队列里剩下的是 **P5H-6 / P6-V3 的 C3 线
（`TBD-7 cost_ratio` 阈值仍 BLOCKED）** 与 **X-5（契约描述文本）** —— 各自有批次，
**本批不许顺手带**。
