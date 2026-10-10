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
3. ~~成本窗口开着：仓库 PUBLIC ⇒ GHCR 公开包免费 ⇒ registry 通道 ¥0~~
   **❌ 本条已作废（Y4 + Y8 裁决）**：走 registry 的前提是"能被 pull"，而用户要的是
   **不能被外人拉** + **不愿为额度操心** ⇒ D-1b 走**离线包**，不是 registry。
   保留此行只为记账，避免下次有人照着它又绕回去。

### 1.3 今天已做的机械查实（**别再查第二遍，直接用；动手前请复核行号**）

| # | 查了什么 | 读数 |
|---|---|---|
| **M1** | 现有 compose 的构建形态 | **3 个服务带 `build:`**：`db-init:97`、`backend:120`、`frontend:178`；三者**均已声明固定 `image:`**（`graphrag-agent/backend:1.6.0` ×2、`graphrag-agent/frontend:1.6.0`）；`neo4j:5.26-community` / `postgres:16-alpine` 无 build |
| **M2** | CI 有没有镜像作业 | **没有**。`.github/workflows/` 只有 `ci.yml` + `.gitkeep`；jobs = `backend / frontend / contract / ci-summary`，全部只做 lint / test，**无 build / push / save** |
| **M3** | 镜像**真实**占多少（见下：结论已**更正过一次**，别用 `docker images` 的读数） | **实测 `docker save` 产物**：`graphrag-agent/backend:1.6.0` = **163,941,376 B ≈ 156 MB**；前端 `graphrag-agent-frontend:latest` = **314,055,168 B ≈ 300 MB** ⇒ **两个合计 ≈ 456 MB**。再 gzip 压几乎压不动（`backend 155.3 MB` / `frontend 298.9 MB`，因为层内已是压缩包） |
| **M4** | **F-P6D1b-1（新发现）** | 本机**根本没有 `graphrag-agent/frontend:1.6.0`** —— 只有 `graphrag-agent-frontend:latest`（**连字符**，与 compose 要的**斜杠命名**不是同一个名字，且 tag 是 `latest`）；另有游离的 `graphrag-agent-backend:latest`（705MB）⇒ **前端镜像从未按 compose 声明的名 / tag 构建过一次**。清理与否由你裁决，**本批不许依赖它们** |
| **M5** | 构建上下文约束 | 仓库根 `.dockerignore` **存在**；backend 的 `context: ..`（**仓库根**）+ `dockerfile: backend/Dockerfile`（`deploy/docker-compose.yml:38-39`，为 COPY 根目录 `plugins/`，见 ADR-0007 §3.1）；frontend `context: ../frontend` |
| **M6** | `deploy/variants/` | 只有 `baseline.yaml` / `internal-demo.yaml`；grep `build:|image:|services:|extends|include` **零命中** ⇒ 是**参数片段**而非 compose，本批**不碰**（结论来自 grep，动手前请复核） |
| **M7** | GHCR 配额能否查实 | ⚠️ **查不到，别猜**：① `gh api user --jq .plan.name` 返回**空**；② `gh api "user/packages?package_type=container"` ⇒ **403 `You need at least read:packages scope`**（本机 token 没这 scope）；③ `gh api user/settings/billing/packages` ⇒ **404**。⇒ 配额只能由**人**在 GitHub 后台确认，**AI 不得写"还剩多少"** |

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
3. **不把镜像或其二进制产物提交进 git**（**≈ 456 MB**，全包时 919 MB）；`dist/` / `*.tar` / `delivery-manifest.json` 一律 gitignore；
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
| **Y1** ✅ **已裁决** | **A / B 二选一**（§2） | **走 A**：保留现有 compose 作开发用，**新增交付 compose**（无 `build:`），`inspect_d1b` 指向交付文件。**不许动 G-19 的识别口径** |
| **Y2** ✅ **已裁决 + 一处更正** | 交付通道：**registry / 离线包 / 两者** | **离线包 = 唯一主通道，registry 本批不做**（Y8）。① 我曾把 `docker images` 的展开大小当成镜像体积估成 **1.9GB** —— **那个数错了**（§11 已立规矩），真值是 `docker save` 的层产物；② 离线交付天然满足"防被拉"，且不占 GitHub 额度；③ 用户明确**不升级付费档、不想为额度操心、本机可放文件** |
| **Y3** ✅ **已裁决** | 要不要新增 CI 镜像作业 | **本批不新增**。理由是 Y8=离线包后，CI 里既没有 push 目标、也没必要每次构建（挂 PR 会烧 CI 分钟）。**校验靠 pytest**：交付 compose 的合规由**护栏用例**在 CI 里跑（不用 docker daemon）。若将来要自动化出包，再单开一批做 `workflow_dispatch` |
| **Y4** ✅ **已裁决** | 镜像命名 + **可见性** | **不适用 registry** —— Y8=离线包后没有远端 registry。本地 tag 沿用 compose 既有口径：`graphrag-agent/{backend,frontend}:<app_version>`（tag == `app_version`，不许 `latest`，沿用 D-N）。**用户明令：不允许外人拉到镜像** ⇒ 离线这条路天然满足，**但不许回头再补一个公开 registry** |
| **Y5** | 前端镜像怎么处理 | 现有 `frontend/Dockerfile` + `build.args`（`NEXT_PUBLIC_USE_MOCK=false` 等）；构建时**必须带同样的 ARG**（漏了就是 R18 红线：容器化前端静默走 Mock） |
| **Y6** | `db-init` 要不要单独推 | 它与 `backend` 共用**同一份镜像**（锚点 `&backend-build` + `image: graphrag-agent/backend:1.6.0`），只是 `command:` 不同 ⇒ **不需要第二个镜像**，交付 compose 里保留同一 image + 同样的 `command` |
| **Y7** | 第 9 项何时翻绿 | **只有 P6-X 能翻**（要出现 `docs/drills/restore-drill-*.md`）。本批把它 SKIP 的**原因从"D-1b 缺失"改成"演练未做"**即为成功，**不许直接翻成 PASS** |
| **Y8** ✅ **已裁决** | **私有 registry 用哪一家 + 配额够不够** | **选 ③ 的离线包分支 —— 用户原话：「离线包比较合适，我不希望升级，也不想为额度操心，本地电脑可以放文件」**。⇒ **本批完全不碰任何远端 registry**（不建 GHCR、不开付费档、不配 Secrets、不写 `docker login` / `docker push` 步骤）。**风险已在源头消除**：配额、可见性、被拉走三个问题，一个都不存在 |
| **Y9** ✅ **已裁决** | **离线包打不打第三方镜像**（neo4j / postgres） | **只打自研（≈ 456 MB）**。用户理由：**客户现场内网是可联网的（不联网大模型没法用）**；真遇到拿不到的现场，前期部署**人工用 U 盘拷上服务器**即可，"方法很多，不一定要从网上下载"。第三方两个 tag 由客户场自行 `pull`（tags 已固定：`neo4j:5.26-community` / `postgres:16-alpine`） |

### 5.1 Y9 的依据（`docker save` 实测，不是估的）

| 镜像 | save 产物（真实） | 是否入包 |
|---|---|---|
| `graphrag-agent/backend:1.6.0` | **156 MB** | ✅ 自研（见 M4：本机没有 `graphrag-agent/frontend:1.6.0`，**前端必须先按 compose 的名 / tag 构建一次**） |
| `graphrag-agent/frontend:<app_version>` | **300 MB** | ✅ 自研 |
| `neo4j:5.26-community` | 351.5 MB | ❌ **不入包** —— 客户联网自拉 |
| `postgres:16-alpine` | 111.3 MB | ❌ **不入包** —— 客户联网自拉 |
| **选定：只打自研** | **≈ 456 MB** | 第三方两个 tag 在交付 compose 里**仍然固定**（非 `latest`） |

> **但脚本必须留后路**：`--save` **默认只打自研**，同时提供 **`--include-third-party`** 开关
> （一次包进四个 ⇒ ≈ 919 MB），给将来**完全离线**的客户现场用。
> **不许把这条后路砍掉** —— 今天能联网不代表每个现场都能；砍了下次要改代码、要重开批次。

> **客户侧如何到货**（写进交付 README，两条路都要写）：
> ① 联网现场：拷 tar → `docker load -i <包>.tar` → compose 自动拉第三方 → `up -d`；
> ② 断网现场：**U 盘拷**更能接受（用户原话）⇒ 先用 `--include-third-party` 出一个全包再拷。

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

1. **交付 compose 存在且合规**（**Y1 已裁决走 A**）：① 全服务**无 `build:`**；② 自研 `image:` tag == `app_version`（1.6.0）；③ 第三方 tag 固定且**非 `latest`**；④ 用 yaml 解析后逐服务断言，**不许用 grep 数 `build:` 字样**（注释里全是这个词）；⑤ 开发用的 `deploy/docker-compose.yml` **保持原样**（`build:` 留住，G-19 才有的吃）。
2. **离线包侧（Y8=离线包 ⇒ 这是主线，`scripts/` 下有痕迹就满足 `inspect_d1b` 的第 ② 条）**：⑥ `scripts/build_delivery_images.py --dry-run`（或等价）打印出它将要执行的**完整命令**（含 `--build-arg NEXT_PUBLIC_USE_MOCK=false`）；⑦ `--save`（**默认只打自研**，Y9）× `--include-third-party`（四个全打）× `--verify`（对 tar / 镜像做 SHA-256 或 digest 校验）三条分支各自可 `--dry-run`；⑦b **tar 里的 tag 必须与交付 compose 的 `image:` 逐字节相同**（`graphrag-agent/backend:<app_version>` 等），差一个字符客户现场就会在 `pull` 那步卡死 —— 这条要**机械比对**，不许目测；⑧ 产出一份 **`delivery-manifest.json`**（镜像名 / tag / size / SHA-256 / image id）—— **风格对齐 P6-W 的 `backup-manifest.json`**（`backend/app/services/backup.py`）；缺了它，"这包是不是当时那份"无从机械核；⑨ **真跑过一次并产出真实 tar**（允许因为耗时长而留在你本机，**但必须贴出** `ls -l` + `delivery-manifest.json` 的内容）；⑩ **CI 里不许出现** `docker login` / `docker push` / 任何 registry 步骤（Y8）。
3. **CI 侧**：⑪ **本批不新增** CI 作业（Y3）—— 校验全部落在 pytest；⑫ 若将来要自动化出包，另开批次做 `workflow_dispatch`。
4. **第 9 项读数变了**（本批的闭环）：⑬ 跑 `install_acceptance.py` —— SKIP 的**原因不再是"D-1b 未落地"**（应变成"演练留证尚未产生"之类）；⑭ 但**仍必须是 SKIP** —— **翻成 PASS 说明有东西伪造了**。
5. **护栏**：⑮ `pytest` **不降**（CI 口径 ≥ 1234 passed）；⑯ G-19 两条**仍然绿**；⑰ 新增的交付 compose 护栏要有**反向用例**（把 `build:` 加回去 / 把 tag 改 `latest` ⇒ 必须 FAIL）。
6. **回登**：`changes/P6-D1b/integration-log.md` + `docs/deployment-spec.md` §12 的 D-1b 行（⏳ → 新状态，附真实产出物坐标）+ `docs/acceptance-traceability-matrix.md` 对应行。

---

## 9. 提交与推送纪律

- Conventional Commits；本批新增集中在 `deploy/`、`backend/scripts/`、`backend/tests/`
  （**Y3 ⇒ 不碰 `.github/workflows/`**）。
- **绝不入库**：镜像 tar、`delivery-manifest.json`、`.env`、`dist/`；临时 `backend/reports/` 已被 gitignore
  （**tar 要有 gitignore 规则，别只靠"记得不加"**）。
- **网络提示**：本机到 `github.com:443` 会间歇性 `Recv failure` ⇒ push 失败**先等 60~150 秒重试**，不要改 remote、不要 force。
- 推送后**以 CI 全绿为准**。

---

## 10. 升级用户的四类情况

1. **文档 / spec 与现实不符**，且要停下来先裁决才能继续（例：§6.4① 的"独立环境"判据在本环境无法完全满足）；
2. 要改的东西与 **X-5 / P6-V3 成果 / ADR-0004 §2.1 接缝登记集合** 相交；
3. **要不要砍功能 / 放宽标准**（想把 `--include-third-party` 这条后路砍掉；或为省事把 `build:` 留在交付 compose 里）—— **一律先升级，AI 不得自己放宽**；
4. ✅ **已裁决（Y4 + Y8）**：**不用任何远端 registry**。

   演进记账（别删，下次要翻）：

   - Y4：用户先否了**公开 GHCR**（"防止仓库被人拉"）；
   - 我据此指出派生约束 Y8：**私有 GHCR 在 Free 计划下存储额度仅 500 MB**，
     而自研镜像合计 **456 MB** ⇒ **只够一个版本，推第二次必爆**；
     且本机 `gh` **查不到配额**（M7：`403 read:packages` / `404`），只能由人在后台核；
   - 用户终裁：**选离线包，不升级、不为额度操心、文件放本机**。

   ⇒ **本批不许出现** `docker login` / `docker push` / `GITHUB_TOKEN` 写权限 / registry Secrets
   —— 见到任何一条就是越界，**回滚不要商量**。
   ⚠️ ~~残留待答：Y9~~ → ✅ **已答（只打自研，第三方客户联网自拉 / 断网现场用 U 盘拷全包）**，
   **决策表现在已无未决项**。

> **连带提醒（本批不做，但要登记）**：用户确认客户现场**联网跑云端大模型** ⇒ `.env` 里会有真实
> API key。这让 §10 **第 10 项「无密钥进日志」**从"理论要求"变成"真会出事"，
> P6-X 那一批在目标环境务必用 `--log-file`（**目标环境的真实日志**）复核，别用本机 grep 冒充。

---

## 11. 不许外推

- 不许因为"加了文件 / 脚本"就宣称 D-1b 完成 —— **离线包必须真的产出来过一次**（贴 `ls -l` + manifest）；产不出来就明写「未产出」，不许用 `--dry-run` 的打印冒充。
- 不许因为"本机 build 过镜像"就宣称可用 —— M4 已经证明**前端从未按 compose 声明的名 / tag 构建过**。
- 不许把第 9 项改成 PASS —— 它归 **P6-X**（双人 + 留证），本批只能改 SKIP 的**理由**。
- 不许把 tar 传 Actions artifact、不许入库 —— **≈ 456 MB**（Y9：只打自研）是本地交付物，靠 U 盘 / 内网搬到客户现场。
- **不许再用 `docker images` 的读数当镜像体积** —— 那是展开大小（backend 782MB / frontend 1.14GB），
  registry 与实际传输的是 `docker save` 的层产物（**156MB / 300MB**）。本文件的初版就在这里栽过
  一次（估成 1.9GB），**已更正**；以后凡谈体积一律 `docker save` 实测。
- 不许因为"token 能推"就宣称合规 —— **Y8 已裁决不用 registry**，推这件事本身就不许发生。
- **不许写"还剩多少配额"** —— M7 已证明本机查不到（403 / 404）；**而且现在也不需要了**。
- 不许因为"交付 compose 里没 `build:`"就宣称 D-1b 完成 —— **离线包必须真的产出来过**（`docker load` 后能在**另一套**独立项目里 `compose config` 解析通过）。
- 不许因为"加了发布凭证"就顺手把 Secrets 写进工作流文件（一律 `${{ secrets.* }}` 引用）。

---

## 12. 下一批指针

做完 P6-D1b 后回到 **`P6-X`（演练留证）** —— 它是 §9.3 明列的**纯人工**批次
（执行者 ≠ 见证者，`docs/drills/restore-drill-<日期>.md` 须标「内部演练，非客户现场验收」）。
P6-X 的开场提示词在下发之前**必须重写为「人做主体」模式**。
