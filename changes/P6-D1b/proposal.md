# P6-D1b：离线镜像包（`docker save`）+ 交付 compose —— 解开 §6.4① 的前置

> **队列**：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §9.2 序 **6**
> **裁决来源**：**Y1 = 方案 A / Y8 = 离线包 / Y9 = 只打自研**（2026-10-10 用户拍板，
> 见 [`changes/P6-W/new-session-prompt.md`](../P6-W/new-session-prompt.md) §5 决策表）
> **判据源**：[`docs/deployment-spec.md`](../../docs/deployment-spec.md) §4（离线安装）/ §6.4①② / §11（D-1b 行）
> **上一批交接**：[`changes/P6-W/new-session-prompt.md`](../P6-W/new-session-prompt.md)
> **边界**：本文 §1（Non-goals **11** 条）

---

## 0. 本批到底做什么（**先把范围钉死**）

| 件 | 内容 | 落点 |
|---|---|---|
| **①** | **交付 compose**（Y1 = 方案 A） | 新增 `deploy/docker-compose.delivery.yml`：**全服务无 `build:`**，自研 tag == `app_version`（1.6.0），第三方 tag 固定非 `latest`；开发用的 `deploy/docker-compose.yml` **一个字不改**（`build:` 留住 ⇒ G-19 第二条仍有对象） |
| **②** | **离线包脚本**（Y8 = 离线包唯一主通道） | 新增 `backend/scripts/build_delivery_images.py`：`--dry-run` / `--save`（默认**只打自研**，Y9）/ `--include-third-party` / `--verify`，产出 `delivery-manifest.json` |
| **③** | **第 9 项查证口径** | `install_acceptance.py::inspect_d1b` 的 compose 指向**交付文件**，并**扩**扫描目录到 `backend/scripts/`（否则它永远看不见本批产物） |
| **④** | **护栏** | 新增 G-19 族三条（交付 compose 合规）+ 反向用例；脚本侧判据用例 |

**本批的"完成"只有一种定义**：**真的产出了 tar**（贴 `ls -l` + manifest）。只有 `--dry-run` 的打印一律不算。

---

## 1. Non-goals（**11 条** —— 改任何一条之前先按本文 §5 升级）

1. **不做 P6-X 的恢复演练**：`docs/drills/` 一个字不写，**不代签任何 √**。
   本批对第 9 项的义务只有一条：把 SKIP 的**理由**从"D-1b 未落地"改成"演练未做"。
2. **不做真正的发版**：不打 `v*` tag、不 bump `app_version`（仍 1.6.0）、不改 `.env.example`。
3. **不把镜像或其二进制产物提交进 git**：tar（≈456 MB，全包 ≈919 MB）、`delivery-manifest.json`、
   `dist/` 一律 gitignore；**不传 Actions artifact**。
4. **不在 PR 触发的 CI 里跑 docker build**（Y3）：**本批不新增任何 CI 作业**，不碰
   `.github/workflows/`。交付 compose 的合规由 **pytest 护栏**在 CI 里跑（不需要 docker daemon）。
5. **不碰任何远端 registry**（Y4 + Y8）：不建 GHCR / 不开付费档 / 不配 Secrets /
   不写 `docker login` / `docker push` / `GITHUB_TOKEN` 写权限。见到任何一条即越界，回滚不要商量。
   同时**不写"还剩多少配额"**（M7 已证明本机查不到：403 / 404）。
6. **不改既有服务的运行时配置**：不碰 RLS 角色串、`DATABASE_URL` / `DATABASE_URL_OWNER`、
   健康检查、`restart:` 策略、端口绑定。
7. **不改 frontend / backend 的应用代码**（只加 compose / 脚本 / 护栏测试 / 文档），
   `export_openapi.py --check` 零 diff。
8. **不动 P6-W 三条命令的既有行为**：`backup.py` / `restore.py` 一个字不改；
   `install_acceptance.py` **只许改** `DEFAULT_COMPOSE` 的指向与 `inspect_d1b` 的扫描目录（**扩**，不缩）。
9. **不改 G-19 两条既有用例的识别口径**（Y1 明确：不许动 `build:` 识别）；
   新增的交付 compose 护栏另写，**自研识别改用镜像名前缀** `graphrag-agent/`。
10. **不虚构"已推送" / 不虚构产物**：没真跑出来的 tar 就明写「未产出」，不许用 `--dry-run`
    的打印冒充；**不删** `--include-third-party` 这条后路（Y9 的断网现场要用）。
11. **不顺手解决 M4 的游离镜像**（`graphrag-agent-frontend:latest` / `graphrag-agent-backend:latest`
    命名与 tag 都不是 compose 要的那个）：**只登记**，清理属另一条审批。
    **也不动 `deploy/variants/`**（M6：是参数片段不是 compose）、**不动仓库根的 `delivery-kit/`**（商务素材包，非本批）。

> ⚠️ 若实现中发现必须触碰某条 Non-goal ⇒ **先缩范围再报告**
> （哪份文档哪一行 / 改什么 / 为什么绕不过 / 试过的替代方案）。

---

## 2. 决策表

| # | 决策 | 定案 |
|---|---|---|
| **Y1** ✅ | A / B 二选一 | **A**：保留开发 compose（含 `build:`）不动，**新增** `deploy/docker-compose.delivery.yml` |
| **Y2** ✅ | 交付通道 | **离线包 = 唯一主通道**，registry 本批不做 |
| **Y3** ✅ | 新增 CI 镜像作业 | **不新增**；校验落 pytest |
| **Y4** ✅ | 镜像命名 / 可见性 | 不适用 registry；本地 tag 沿用 `graphrag-agent/{backend,frontend}:<app_version>` |
| **Y5** ✅ | 前端 build-arg | 必须与开发 compose 的 `build.args` **逐项相同**（`NEXT_PUBLIC_USE_MOCK=false` 等）⇒ 漏了就是 R18 红线 |
| **Y6** ✅ | `db-init` | 与 `backend` **同一份镜像**，交付 compose 里保留同一 `image:` + 同样的 `command:` |
| **Y7** ✅ | 第 9 项 | 只改 SKIP 的**理由**，**不许**翻 PASS |
| **Y8** ✅ | registry 选型 / 配额 | 离线包分支 ⇒ 风险在源头消除 |
| **Y9** ✅ | 打不打第三方镜像 | **只打自研**（≈456 MB）；`--include-third-party` 留后路（≈919 MB） |
| **D1** 🆕 | 交付 compose 的项目名 | `name: ${COMPOSE_PROJECT_NAME:-graphrag-agent}` —— 留一个环境变量口子，
  是为了 §6.4②「**独立 compose 项目**」在同一台宿主机上也能成立（P6-X 的演练很可能就在开发机上做）；
  不设时与开发态同名，行为不变 |
| **D2** 🆕 | tar / manifest 落哪 | 默认 `backend/reports/delivery/`（已被 `backend/reports/` gitignore 覆盖），
  并再补 `*.tar` / `delivery-manifest.json` 两条显式规则（**不靠"记得不加"**） |
| **D3** 🆕 | `inspect_d1b` 扫描目录 | **扩**到 `backend/scripts/`（它现在只扫 `.github/` + `deploy/` + 根 `scripts/`，
  而根下根本没有 `scripts/` ⇒ 本批脚本放 `backend/scripts/` 会**永远看不见**） |

---

## 3. 验收判据（每条都要能贴机器输出）

1. **交付 compose**：① yaml 解析后**全服务无 `build:`**；② 自研 tag == `app_version`；
   ③ 第三方 tag 固定且非 `latest`；④ 用 yaml 解析逐服务断言（**不许 grep 数 `build:` 字样**）；
   ⑤ 开发 compose **保持原样**。
2. **脚本三条分支各自可 `--dry-run`**：`--save`（默认只打自研）/ `--include-third-party`（四个全打）/
   `--verify`；`--dry-run` 打印**完整命令**且**真的不调用 docker**。
3. **⑦b 机械比对**：tar 里的 tag 与交付 compose 的 `image:` **逐字节相同**（保存清单由 compose 反推，
   单一来源 ⇒ 不可能漂移），并有反向用例。
4. **`delivery-manifest.json`**：镜像名 / tag / size / image id + tar 的 SHA-256 / size + `app_version`；
   `--verify` 重算 SHA-256 比对（改一个字节必须 FAIL）。
5. **真跑过一次**并产出真实 tar：贴 `ls -l` + manifest 内容；`docker load` 后能在**另一套**独立项目里
   `compose config` 解析通过（至少做到 `docker compose -f ... config` + `docker load` 到临时项目验证）。
6. **第 9 项读数变了**：SKIP 的原因不再是"D-1b 未落地"；但**仍必须是 SKIP**。
7. **CI 里不许出现** `docker login` / `docker push` / 任何 registry 步骤（Y8）。
8. `pytest` **不降**（CI 口径基线 **1234 passed**）；G-19 两条原用例**仍然绿**；
   新增护栏有**反向用例**（把 `build:` 加回去 / 把 tag 改 `latest` ⇒ 必须 FAIL）。
9. 五项门禁读数不变：`check_startup_readiness.py`（`[OK] 17 / [~~] 0 / [--] 0`）、
   `check_seams.py`（ERROR 0 / WARN 0 / OK 12）、`export_openapi.py --check` 零 diff、
   `extract_seam_signatures.py --check` 一致、ruff check + format 全过。
10. 回登：`changes/P6-D1b/integration-log.md` + `docs/deployment-spec.md` §11 的 **D-1b 行**
    （+ §0 D-1 行 / §4 到货路径）+ `docs/acceptance-traceability-matrix.md` 的 **H14 行**。
11. **不许**因为"交付 compose 里没 `build:`"或"脚本能 dry-run"就宣称 D-1b 完成 —— 见 §0 最后一行。

---

## 4. 遗留 / 依赖登记

| # | 项 | 状态 |
|---|---|---|
| **M4** | 本机**没有** `graphrag-agent/frontend:1.6.0`（只有 `graphrag-agent-frontend:latest`，命名与 tag 都不对）⇒ 前端**必须先按 compose 的名 / tag 构建一次** | 本批构建时解决（不清理游离镜像） |
| **M7** | GHCR 配额本机查不到（403 / 404） | **本批不需要**（Y8 离线包） |
| **F-P6W-3** | `.env.example` 的 `PRIVATE_DEPLOY_ENABLED=false` | 本批不处置（非本批对象） |
| **P6-X** | 恢复演练（双人 + 留证） | 顺延；本批只把它的**前置**补上 |
| **TBD-7 / P6-T** | 各自有批次 | 本批不动 |
