# 下一批开场提示词（写给 P6-D1b —— 由 P6-W 之后路由而来）

> **用法**：新会话里把本文**全文**粘贴给 AI（或直接让它读本文件路径）。
> **用途**：给 AI 一个精确到文件和行号的起点，避免"先聊半小时找回上下文"。
> **路由记录**：2026-10-10 用户裁决 —— 在 P6-X / P6-D1b 之间**选择先做 P6-D1b**，
> 理由是它的缺失是 P6-X 每一次尝试只能停在 SKIP 的同一个根（见 §1.2）。

---

## 0. 你要读的四份文件

```
1. changes/P6-W/integration-log.md                   ← 上一批实测证据与残留风险
2. docs/deployment-spec.md §6.4（三条判据）/ §12（缺口表 D-1b 行）
3. docs/delivery-plan.md §9.2 / §9.3                 ← 排期与「只能由人做」的边界
4. deploy/docker-compose.yml（全文 214 行，逐服务看完，别只读 grep）
```

---

## 1. 确认起点（**这是重点，先答"是/不是"**）

**起点 = P6-D1b：把 D-1b（离线镜像包 / 私有 registry）从 ⏳ 落成，
从而解开 §6.4① 的「交付物无 `build:`」前置。**

### 1.1 执行模式：**AI 可主导**（**不是** §9.3 的纯人工批次）

对照 `delivery-plan.md:288-292` §9.3 —— 三条只能由人做的是 ①判分 ②**演练** ③两条裁决。
**P6-D1b 不在这三条里**（它产出的是交付物，不是演练留证）⇒ AI 可以主导，正常跑 CI。

> 但**别越界**：本批**不做** P6-X 的恢复演练（`docs/drills/` 一个字都不许替人写），
> 也不得替人在 §10 上勾任何一个 √。

### 1.2 为什么是它（机械理由，不是排期感觉）

1. **P6-X 卡在它上面**：`scripts/install_acceptance.py` 第 9 项今天现场查出
   「compose 仍带 `build:`（backend, db-init, frontend）+ CI / deploy / scripts 下
   无 `docker save` / push registry」⇒ 只要 D-1b 不落地，**P6-X 每次尝试都只能停在 SKIP**。
2. **它是 DR-A7（离线包）与 DR-C2（补丁流程）的门闩**：`test_guardrails_delivery.py:134`
   原文「DR-A6 是 DR-A7 与 DR-C2 的**前置**」。DR-A6 已达成（固定 tag），
   但现在**没人能把 tag 送出去**。
3. **成本窗口开着**：本仓库 **PUBLIC**（`gh repo view`：`"isPrivate": false`）⇒
   GHCR 上**公开包免费无限存储** ⇒ registry 通道可以做到 **¥0**。

### 1.3 今天已做的机械查实（**别再查第二遍，直接用；动手前请复核行号**）

| # | 查了什么 | 读数 |
|---|---|---|
| **M1** | 现有 compose 的构建形态 | **3 个服务带 `build:`**：`db-init:97`、`backend:120`、`frontend:178`；三者**均已声明固定 `image:`**（`graphrag-agent/backend:1.6.0` ×2、`graphrag-agent/frontend:1.6.0`）；`neo4j:5.26-community` / `postgres:16-alpine` 无 build |
| **M2** | CI 有没有镜像作业 | **没有**。`.github/workflows/` 只有 `ci.yml` + `.gitkeep`；jobs = `backend / frontend / contract / ci-summary`，全部只做 lint / test，**无 build / push / save** |
| **M3** | 镜像体积（决定离线包能否进 artifact） | `graphrag-agent/backend:1.6.0` **782MB**；前端 `graphrag-agent-frontend:latest` **1.14GB** ⇒ 打包后 **`docker save` 约 1.9GB** |
| **M4** | **F-P6D1b-1（新发现）** | 本机**根本没有 `graphrag-agent/frontend:1.6.0`** —— 只有 `graphrag-agent-frontend:latest`（**连字符**，与 compose 要的**斜杠命名**不是同一个名字，且 tag 是 `latest`）；另有游离的 `graphrag-agent-backend:latest`（705MB）⇒ **前端镜像从未按 compose 声明的名 / tag 构建过一次**。清理与否由你裁决，**本批不许依赖它们** |
| **M5** | 构建上下文约束 | 仓库根 `.dockerignore` **存在**；backend 的 `context: ..`（**仓库根**）+ `dockerfile: backend/Dockerfile`（`deploy/docker-compose.yml:38-39`，为 COPY 根目录 `plugins/`，见 ADR-0007 §3.1）；frontend `context: ../frontend` |
| **M6** | `deploy/variants/` | 只有 `baseline.yaml` / `internal-demo.yaml`；grep `build:|image:|services:|extends|include` **零命中** ⇒ 是**参数片段**而非 compose，本批**不碰**（结论来自 grep，动手前请复核） |

---

## 2. 头号地雷：**别直接删 `build:`**（动手前第一件事）

`backend/tests/test_guardrails_delivery.py:186-201`，`test_g19_own_image_tags_track_app_version`
靠 **`if "build" not in service: continue`** 来识别"哪些是**自研**镜像"（第三方 neo4j / postgres
不参与 tag == app_version 校验），且末尾有这一条：

```python
    assert checked, (
        f"{COMPOSE.name} 里没有任何带 build: 的服务 ⇒ 本判据失去对象。"
        "自研镜像必须同时声明 build: 与 image:（DR-A6）"
    )
```

⇒ **把 `deploy/docker-compose.yml` 里的 `build:` 全删掉，G-19 第二条会立刻 FAIL**
（`checked == 0`）。**这不是护栏错了，是它的识别口径长在 `build:` 上。**

**两条走法，务必先选，选定后写进 proposal：**

| 方案 | 做法 | 代价 |
|---|---|---|
| **A（建议）** | 保留现有 `deploy/docker-compose.yml` 作**开发用**（保留 `build:` + `image:`，继续被 G-19 守）；**新增交付 compose**（如 `deploy/docker-compose.delivery.yml`：全服务**无 `build:`**、自研 tag = `app_version`、第三方 tag 固定）⇒ 把 `install_acceptance.py::inspect_d1b` 的 `compose_file` 指向**交付文件**；再**新增一条护栏**守"交付 compose 无 `build:`" | 多一份 compose 要维护；但**零护栏改动**、本地仍可 `docker compose up` 从源码构建 |
| **B** | 直接改主 compose 去掉 `build:`，同时**改 G-19 第二条**："自研"识别从 `build:` 换成**镜像名前缀**（image 以 `graphrag-agent/` 开头） | 要动既有护栏（须写清变更理由并补**反向用例**）；且本地从此不能 `compose up` 从源码构建，**开发体验变差** |

**反面例子（不许这么做）**：为了让第 9 项翻绿，就去放宽 `check_startup_readiness.py`
或给 G-19 套 `xfail` —— 那是把"护栏没响"伪装成"护栏通过"（R-9「恒绿即失效」）。

---

## 3. 边界纪律

> **先写边界文件再动手**：`changes/P6-D1b/proposal.md`，**Non-goals ≥ 8 条**。
> `changes/P6-W/proposal.md` 那 9 条只对 P6-W 有效，**不许沿用**。

建议至少覆盖：

1. **不做 P6-X 的恢复演练**（不写 `docs/drills/`、不代签任何 √）；
2. **不做真正的发版**（不打 `v*` tag、不 bump `app_version`）；
3. **不把镜像或其二进制产物提交进 git**（1.9GB；`dist/` / `*.tar` 一律 gitignore）；
4. **不在 PR 触发的 CI 里跑 docker build**（只在打 tag 时跑 ⇒ CI 分钟数为 0 增量）；
5. **不改既有服务的运行时配置**（不碰 RLS 角色串、`DATABASE_URL`、健康检查……）；
6. **不改 frontend / backend 的应用代码**（只加 CI / compose / 脚本 / 护栏测试）；
7. **不动 P6-W 三条命令的既有行为**（`backup` / `restore` 不许碰；`install_acceptance` 只许**扩**第 9 项的查证口径）；
8. **不虚构"已推送到 registry"**（没真 push 成功，就明写「未推送」，不许省略）；
9. **不顺手解决 M4 的游离镜像**（登记即可，清理属另一条审批）。

---

## 4. 已查证坐标表

| 项 | 位置 |
|---|---|
| 现有 compose（开发） | `deploy/docker-compose.yml`（214 行；`build:` 见 97 / 120 / 178；`image:` 见 98 / 126 / 189） |
| G-19 两条护栏 | `backend/tests/test_guardrails_delivery.py:131` / `:169`（第二条靠 `build:` 识别自研） |
| D-1b 的机械查证 | `backend/scripts/install_acceptance.py:590` `inspect_d1b(*, compose_file, repo_root)`；调用口在第 9 项 `check_9`（`:645`） |
| 构建上下文约束 | backend 构建 context = **仓库根**（`.dockerignore` 在根，含 `.env` 排除）；frontend context = `../frontend` |
| app_version | `backend/app/core/config.py` 的 `app_version`（当前 **1.6.0**）⇒ compose tag 必须同步 |
| 运行时门禁脚本 | `scripts/check_startup_readiness.py`（护栏档位）、`scripts/check_seams.py`（接缝集合） |
| 上一批证据 | `changes/P6-W/integration-log.md` §2（F-P6W-1 / F-P6W-2 / F-P6W-3 / F-P6W-4） |

---

## 5. 决策表（**开工前逐条给建议，不决不动手**）

| # | 决策 | 建议 |
|---|---|---|
| **Y1** | **A / B 二选一**（§2） | **建议 A**：新增交付 compose，零护栏改动 |
| **Y2** | 交付通道：**registry / 离线包 / 两者** | **建议两者都留命令，但只让 registry 上 CI**：GHCR 公开包免费（见 §1.2 第 3 条：`isPrivate=false`）；离线包 `docker save` 约 **1.9GB**（M3）**不适合进 Actions artifact**（免费额度 500MB 存储）⇒ 落到本地脚本 `--save`，CI 里**只 push registry** |
| **Y3** | CI 触发条件 | **建议 `push: tags: ['v*']`**（只对发版跑）＋ 保留 `workflow_dispatch` 供手工；**不许**挂到 PR 上（会烧 CI 分钟） |
| **Y4** | 镜像命名 | 自研统一 `ghcr.io/<owner>/graphrag-agent/{backend,frontend}:<app_version>`；**tag 一律等于 `app_version`，不许出现 `latest`**（沿用 D-N） | 	
| **Y5** | 前端镜像怎么处理 | 现有 `frontend/Dockerfile` + `build.args`（`NEXT_PUBLIC_USE_MOCK=false` 等）；构建时**必须带同样的 ARG**（漏了就是 R18 红线：容器化前端静默走 Mock） |
| **Y6** | `db-init` 要不要单独推 | 它与 `backend` 共用**同一份镜像**（锚点 `&backend-build` + `image: graphrag-agent/backend:1.6.0`），只是 `command:` 不同 ⇒ **不需要第二个镜像**，交付 compose 里保留同一 image + 同样的 `command` |
| **Y7** | 第 9 项何时翻绿 | **只有 P6-X 能翻**（要出现 `docs/drills/restore-drill-*.md`）。本批把它 SKIP 的**原因从"D-1b 缺失"改成"演练未做"**即为成功，**不许直接翻成 PASS** |

---

## 6. 上一批已完成项（P6-W）

| 项 | 状态 |
|---|---|
| DR-E2（备份 / 恢复脚本） | 🟡 **部分**：`scripts/backup.py` / `restore.py` + `backup-manifest.json` + §6.2 一致性（错位 ⇒ 退出码 2）。**恢复演练 0 次** |
| DR-E4（安装验收脚本化） | 🟡 **部分**：`scripts/install_acceptance.py` 十项三态；带参那趟 PASS 3 / SKIP 6 / FAIL 1，不带参那趟 PASS 0 / SKIP 10 |
| D-1b | ⏳ **本批目标**（P6-W **没有**挪动它） |
| X-5 / P6-V3 / P5H-6 | 未动，各自有批次 |

---

## 7. 基线（验收判据的唯一基准）

| 项 | 数值 |
|---|---|
| pytest（最终裁决 = **GitHub Actions**） | ✅ **1234 passed / 7 skipped**（P6-W 新增 **45 条全 passed**，0 skip / 0 failed） |
| pytest（本机口径） | CI 口径（`CI=1` + 三变量）：**1236 / 5**；普通口径：**1235 / 6** |
| 护栏 | `[OK] 17 / [~~] 0 / [--] 0` |
| 接缝 | `ERROR 0 / WARN 0 / OK 12` |
| OpenAPI | 零 diff |
| 有图口径 | **必须同时设 `GRAPH_REAL_NEO4J_{URI,USER,PASSWORD}`**，少设会静默 skip；本机 Neo4j 口令 = `ci-graph-pw-2026` |

**开工自检**（`cd backend`，四项必须全对才能动手）：

```bash
uv run python scripts/check_startup_readiness.py
uv run python scripts/check_seams.py
uv run python scripts/export_openapi.py --check
uv run python scripts/extract_seam_signatures.py --check
uv run ruff check . && uv run ruff format --check .
```

---

## 8. 验收判据（**每条都要能贴机器输出**）

1. **交付 compose 存在且合规**（若选 A）：① 全服务**无 `build:`**；② 自研 `image:` tag == `app_version`（1.6.0）；③ 第三方 tag 固定且**非 `latest`**；④ 用 yaml 解析后逐服务断言，**不许用 grep 数 `build:` 字样**（注释里全是这个词）。
2. **产出侧真的能跑**：⑤ `scripts/build_delivery_images.py --dry-run`（或等价）能打印出它将要执行的**完整命令**（含 `--build-arg NEXT_PUBLIC_USE_MOCK=false`）；⑥ `--push` / `--save` 两条分支各自可 `--dry-run`。
3. **CI 侧**：⑦ 新工作流仅在 `push: tags: ['v*']` / `workflow_dispatch` 触发（**用 yaml 断言 `on:` 段**，不许口述）；⑧ 有真实的 build + push registry 步骤。
4. **第 9 项读数变了**（本项目-specific 的闭环）：⑨ 跑 `install_acceptance.py` 第 9 项，SKIP 的**原因不再是"D-1b 未落地"**；⑩ 但**仍必须是 SKIP**（留证还没出现） —— **翻成 PASS 说明有东西伪造了**。
5. **护栏**：⑪ `pytest` **不降**（CI 口径 ≥ 1234 passed）；⑫ G-19 两条**仍然绿**；⑬ 新增的交付 compose 护栏要有**反向用例**（把 `build:` 加回去 / 把 tag 改 `latest` ⇒ 必须 FAIL）。
6. **回登**：`changes/P6-D1b/integration-log.md` + `docs/deployment-spec.md` §12 的 D-1b 行（⏳ → 新状态，附真实产出物坐标）+ `docs/acceptance-traceability-matrix.md` 对应行。

---

## 9. 提交与推送纪律

- Conventional Commits；本批新增集中在 `.github/workflows/`、`deploy/`、`backend/scripts/`、`backend/tests/`。
- **绝不入库**：镜像 tar、`.env`、`dist/`；临时 `backend/reports/` 已被 gitignore。
- **网络提示**：本机到 `github.com:443` 会间歇性 `Recv failure` ⇒ push 失败**先等 60~150 秒重试**，不要改 remote、不要 force。
- 推送后**以 CI 全绿为准**。

---

## 10. 升级用户的四类情况

1. **文档 / spec 与现实不符**，且要停下来先裁决才能继续（例：§6.4① 的"独立环境"判据在本环境无法完全满足）；
2. 要改的东西与 **X-5 / P6-V3 成果 / ADR-0004 §2.1 接缝登记集合** 相交；
3. **要不要砍功能 / 放宽标准**（选 Y2 时要不要索性放弃离线包只留 registry；或为省事把 `build:` 留在交付 compose 里）—— **一律先升级，AI 不得自己放宽**；
4. **发现了新伤口**：选 registry 通道前请确认 —— **本仓库是 PUBLIC**，推到 GHCR 的镜像默认**任何人可拉**（公开包）。若这件产品不该让人拉到完整镜像，**这条必须先问**，不要自作主张开 private 包（会撞存储额度）。

---

## 11. 不许外推

- 不许因为"加了一个 workflow 文件"就宣称 D-1b 完成 —— **没真的 push 成功一次镜像，就是没完成**；没 push 成就明写「未推送」。
- 不许因为"本机 build 过镜像"就宣称可用 —— M4 已经证明**前端从未按 compose 声明的名 / tag 构建过**。
- 不许把第 9 项改成 PASS —— 它归 **P6-X**（双人 + 留证），本批只能改 SKIP 的**理由**。
- 不许把 1.9GB 的 tar 传 Actions artifact —— 免费额度 500MB 存储，会 OOM 或烧额度。
- 不许因为"加了发布凭证"就顺手把 Secrets 写进工作流文件（一律 `${{ secrets.* }}` 引用）。

---

## 12. 下一批指针

做完 P6-D1b 后回到 **`P6-X`（演练留证）** —— 它是 §9.3 明列的**纯人工**批次
（执行者 ≠ 见证者，`docs/drills/restore-drill-<日期>.md` 须标「内部演练，非客户现场验收」）。
P6-X 的开场提示词在下发之前**必须重写为「人做主体」模式**。
