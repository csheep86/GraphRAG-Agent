# P6-D1b 集成日志：离线镜像包（`docker save`）+ 交付 compose（2026-10-10）

> **队列**：`docs/delivery-plan.md` §9.2 序 **6**
> **裁决来源**：**Y1 = 方案 A / Y8 = 离线包 / Y9 = 只打自研**（用户拍板，
> 见 [`changes/P6-W/new-session-prompt.md`](../P6-W/new-session-prompt.md) §5）
> **边界**：[`proposal.md`](./proposal.md) §1（Non-goals **11** 条）
> **判据源**：`docs/deployment-spec.md` §4（离线安装）/ §6.4①② / §11（D-1b 行）

---

## 1. 本批做了什么

| # | 交付物 | 作用 |
|---|---|---|
| 1 | `deploy/docker-compose.delivery.yml`（新增） | **交付用**编排：全服务**无 `build:`**、自研 tag == `app_version`、第三方 tag 固定非 `latest`；开发用的 `docker-compose.yml` **一个字没动** |
| 2 | `backend/scripts/build_delivery_images.py`（新增） | 离线包的**唯一换算口**：`--dry-run` / `--save`（默认只打自研）/ `--include-third-party` / `--verify` + `delivery-manifest.json` |
| 3 | `backend/tests/test_delivery_images.py`（新增，25 条） | 交付 compose 合规（G-19 族 7 条含反向用例）+ 脚本三分支 + `--verify` 判据 + Y8 红线 |
| 4 | `backend/scripts/install_acceptance.py`（**扩**） | 第 9 项查证指向**交付** compose；扫描目录**扩**到 `backend/scripts/` 且纳入 `*.py`（D3） |
| 5 | `backend/tests/test_install_acceptance.py`（改 2 条） | 第 9 项 SKIP 的**理由**断言从"D-1b 未落地"换成"D-1b 前置已满足"（仍 SKIP） |
| 6 | `.dockerignore`（修 1 行） | 去掉 `**/scripts/` —— 它会让 backend 镜像**构建失败**（F-P6D1b-1） |
| 7 | `.gitignore`（+2 条） | `*.tar` / `delivery-manifest.json` 显式忽略（不靠"记得不加"） |
| 8 | 回登 | `docs/deployment-spec.md` §0 / §4 / §11；`docs/acceptance-traceability-matrix.md` H14；`deploy/README.md` |

---

## 2. 实测发现（**不是引用文档，是本机跑出来的**）

| # | 发现 | 实测命令与输出 |
|---|---|---|
| **F-P6D1b-1** | **仓库根 `.dockerignore` 的 `**/scripts/` 会让 backend 镜像构建失败** | `docker build -f backend/Dockerfile -t graphrag-agent/backend:1.6.0 .` ⇒ **EXIT=1**：`#14 ERROR: failed to calculate checksum of ref ...: "/backend/scripts": not found`，且只伴随一条 **warning**（`CopyIgnoredFile: ... excluded by .dockerignore (line 39)`）。根因：`backend/Dockerfile:39` 有 `COPY backend/scripts ./scripts`（镜像里要跑 `init_rls_roles.py`）。⇒ 删掉那一行（**不是**放宽 `COPY`：少了它，`db-init` 建不了 RLS 而 backend **照常起来**、症状为零）。已加回归护栏 `test_dockerignore_does_not_exclude_the_scripts_the_dockerfile_copies` |
| **F-P6D1b-2** | **`docker save -o` 不会自己建目录** | 首次真跑：`failed to save image: invalid output path: GetFileAttributesEx ...\backend\reports\delivery: The system cannot find the file specified` ⇒ 脚本改为出包前 `mkdir(parents=True)` |
| **F-P6D1b-3** | **Windows 控制台 GBK + `sys.path` 两个坑** | ① 输出里的 `⇒` 直接抛 `UnicodeEncodeError: 'gbk' codec ...`（与 P6-W 同款）⇒ `sys.stdout.reconfigure(encoding="utf-8")`；② `python scripts/xxx.py` 时 `sys.path[0]` 是 `scripts/` ⇒ `No module named 'app'` ⇒ 与 `scripts/backup.py` 同款补 `BACKEND_ROOT` |
| **F-P6D1b-4** | **`inspect_d1b` 的第 ② 条在结构上**看不见**本批产物** | 它只扫 `.github/` + `deploy/` + 根 `scripts/`，而①仓库根**没有** `scripts/` 目录；② patterns 里**没有 `*.py`**。⇒ 出包脚本放 `backend/scripts/` 会**永远命中不到**，第 9 项会**恒红**却查不出原因。修法（D3）：前缀表加 `("backend","scripts")` + patterns 加 `*.py`；同时把正则**扩**到 argv 形态 `("docker", "save", ...)` —— 只认 `docker\s+save` 的话，Python 里以 argv 元组写的命令**永远**匹配不上（真·假阴性） |
| **F-P6D1b-5** | **M4 已在本批消解**：前端镜像从未按 compose 的名 / tag 构建过 | 构建前 `docker images` 只有 `graphrag-agent-frontend:latest`（连字符 + `latest`）；本批构建出 `graphrag-agent/frontend:1.6.0`（image id `sha256:74659a14…`）。游离镜像（`graphrag-agent-backend:latest` 等）**只登记未清理**（Non-goal 11） |
| **F-P6D1b-6** | 交接文件里的**章节号有一处对不上** | `new-session-prompt.md` §0 / §8 写「`deployment-spec.md` §12（缺口表 D-1b 行）」，但该文档**只有 §0~§11**；D-1b 行实际在 **§11 排期与未决事项**（`docs/deployment-spec.md:399`）。已按实际位置回登，**未**改交接文件（它是历史记录） |

---

## 3. 决策落地（对照 proposal §2）

| # | 决策 | 落地位置 | 落地结果 |
|---|---|---|---|
| **Y1** ✅ | A / B 二选一 | 新增 `deploy/docker-compose.delivery.yml`；开发 compose 不动 | ✅ 交付 compose `config` 解析通过、**无** `build:`；`test_g19_dev_compose_keeps_its_build` 钉住开发那份的 `build:` 不许被删 |
| **Y2/Y8** ✅ | 离线包 = 唯一主通道 | `build_delivery_images.py` | ✅ 无任何 `login` / `push` / registry；用例 `test_no_registry_operations_in_the_script` + `test_no_registry_steps_in_ci` 双向钉死 |
| **Y3** ✅ | 不新增 CI 作业 | — | ✅ `.github/workflows/` **一个字没动**；校验全在 pytest |
| **Y4** ✅ | tag 命名 | 交付 compose | ✅ `graphrag-agent/backend:1.6.0` / `graphrag-agent/frontend:1.6.0`；**不许 `latest`** 由 `delivery_compose_problems` 判 |
| **Y5** ✅ | 前端 build-arg | `FRONTEND_BUILD_ARGS` | ✅ `--dry-run` 打出 `--build-arg NEXT_PUBLIC_USE_MOCK=false` 等三个，与开发 compose 的 `build.args` 逐项相同 |
| **Y6** ✅ | `db-init` 不另出镜像 | 交付 compose | ✅ 与 `backend` 同一 `image:`、同样的 `command:` |
| **Y7** ✅ | 第 9 项只改理由 | `install_acceptance.py` | ✅ 实测「D-1b 前置已满足 … 顺延 P6-X」，**仍 SKIP** |
| **Y9** ✅ | 只打自研 | `--save` 默认 / `--include-third-party` 后路 | ✅ 默认 2 个镜像；`--include-third-party` 4 个（**未砍**） |
| **D1** 🆕 | 项目名留口子 | `name: ${COMPOSE_PROJECT_NAME:-graphrag-agent}` | ✅ 设 `COMPOSE_PROJECT_NAME=graphrag-drill` ⇒ `config` 解析出的项目名 / 卷名全部变 `graphrag-drill*`（§6.4② 的"独立 compose 项目"在同一台宿主机上成立） |
| **D2** 🆕 | 产物落 `backend/reports/delivery/` + 显式 gitignore | 脚本 + `.gitignore` | ✅ 真跑产物未被 git 跟踪（`git status` 无 tar / manifest） |
| **D3** 🆕 | 扩 `inspect_d1b` 扫描范围 | `SCANNED_DELIVERY_PREFIXES` + patterns + 正则 | ✅ `inspect_d1b(交付 compose)` 实测 `ok=True` |

---

## 4. 判据与机器输出

### 4.1 五项门禁

```
uv run ruff check .                             => All checks passed!
uv run ruff format --check .                    => 287 files already formatted
uv run python scripts/check_seams.py            => ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check => [OK] 零 diff
uv run python scripts/extract_seam_signatures.py --check => [OK] 与快照一致
uv run python scripts/check_startup_readiness.py=> [OK] 生效 17 / [~~] 0 / [--] 0
                                                   （G-19 项数 2 → 9，新增 7 条全 [OK]）
```

### 4.2 pytest

| 口径 | 结果 |
|---|---|
| **改前（P6-W 基线，CI 口径）** | **1236 passed / 5 skipped** |
| **改后（CI 口径：`CI=1` + 三变量）** | **1262 passed / 5 skipped**（+26 / +0，**0 failed**） |
| 改后（**未**设 `GRAPH_REAL_NEO4J_*` 的那趟） | 1224 passed / 43 skipped —— 差的 37 条是**真图用例静默 skip**（基线同因，非本批引入） |

### 4.3 三条分支各自 `--dry-run`

```
$ uv run python scripts/build_delivery_images.py --dry-run --save
app_version=1.6.0  交付 compose=docker-compose.delivery.yml
入包镜像（2）: graphrag-agent/backend:1.6.0, graphrag-agent/frontend:1.6.0
第三方不入包（Y9）⇒ 客户现场联网自拉；断网现场改用 --include-third-party
DRY  docker build -f backend/Dockerfile -t graphrag-agent/backend:1.6.0 .
DRY  docker build -f frontend/Dockerfile --build-arg NEXT_PUBLIC_USE_MOCK=false
     --build-arg NEXT_PUBLIC_APP_ENV=production
     --build-arg NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
     -t graphrag-agent/frontend:1.6.0 frontend
DRY  docker save -o '.../backend/reports/delivery/graphrag-agent-offline-1.6.0.tar'
     graphrag-agent/backend:1.6.0 graphrag-agent/frontend:1.6.0
[DRY] 以上为将要执行的命令；未调用 docker、未产出产物

$ ... --dry-run --save --include-third-party
入包镜像（4）: graphrag-agent/backend:1.6.0, graphrag-agent/frontend:1.6.0,
              neo4j:5.26-community, postgres:16-alpine

$ ... --dry-run --verify
FAIL ...\backend\reports\delivery 下无 delivery-manifest.json：这不是一个交付包
```

### 4.4 **真跑**：一次出包（判据 ⑨ —— 不是 dry-run）

```
$ uv run python scripts/build_delivery_images.py --save
（backend / frontend 两次 docker build 均 EXIT=0；前端首次按 compose 的名 / tag 构建）
RUN  docker save -o '.../graphrag-agent-offline-1.6.0.tar' graphrag-agent/backend:1.6.0 graphrag-agent/frontend:1.6.0
清单已落盘: ...\backend\reports\delivery\delivery-manifest.json
[OK] 离线包已产出

$ Get-ChildItem reports/delivery
Name                                Length LastWriteTime
----                                ------ -------------
delivery-manifest.json                1097 2026-10-10 下午 03:42:25
graphrag-agent-offline-1.6.0.tar 496524288 2026-10-10 下午 03:42:24
```

`delivery-manifest.json`（原文）：

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-10-10T07:42:24.632240+00:00",
  "app_version": "1.6.0",
  "compose_file": "deploy/docker-compose.delivery.yml",
  "third_party_included": false,
  "size_basis": "images[].size=docker inspect .Size（展开后）；传输体积=tar.size",
  "tar": {
    "name": "graphrag-agent-offline-1.6.0.tar",
    "path": "backend/reports/delivery/graphrag-agent-offline-1.6.0.tar",
    "sha256": "e8c6d7ee50967f8b45dcf7e3bb1353d29bd4268284e849674a8b5bcdd3da9217",
    "size": 496524288
  },
  "images": [
    { "ref": "graphrag-agent/backend:1.6.0", "tag": "1.6.0",
      "image_id": "sha256:f5cde93acd8fc43d13b30eec6be3431a6eaaf3ccdd2756bfb15492b324a87543",
      "size": 179152468, "own": true },
    { "ref": "graphrag-agent/frontend:1.6.0", "tag": "1.6.0",
      "image_id": "sha256:74659a14231bc457c2aef574d1f8e5bdfad32ab4c7f4d87af091f84852e46207",
      "size": 317332851, "own": true }
  ]
}
```

> ⚠️ **体积口径**：tar = **496,524,288 字节（≈ 474 MB）**（`docker save` 的层产物）。
> `images[].size` 是 **展开后**的大小（179 MB + 317 MB），**不是**传输体积 ——
> 交接文件里那个"1.9GB"就是把 `docker images` 的展开大小当传输体积估出来的（已更正）。

### 4.5 `--verify`（重算 + 机械比对 tag）

```
$ uv run python scripts/build_delivery_images.py --verify
PASS delivery-manifest.json 可解析且 schema_version 匹配
PASS app_version 一致（1.6.0）
PASS tar: SHA-256 校验通过（496524288 字节）
PASS tag 与交付 compose 逐字节一致（2 个镜像）
PASS 第三方不入包（Y9）：neo4j:5.26-community, postgres:16-alpine 由客户现场联网自拉
PASS graphrag-agent/backend:1.6.0: image id 一致（sha256:f5cde93acd8f）
PASS graphrag-agent/frontend:1.6.0: image id 一致（sha256:74659a14231b）
[OK] 校验通过
```

### 4.6 `docker load` 回灌 + **独立项目**解析（§6.4②）

```
$ docker load -i backend/reports/delivery/graphrag-agent-offline-1.6.0.tar
Loaded image: graphrag-agent/backend:1.6.0
Loaded image: graphrag-agent/frontend:1.6.0

$ $env:COMPOSE_PROJECT_NAME='graphrag-drill'
$ docker compose -f backend/reports/delivery/drill-check/docker-compose.delivery.yml config --quiet
config EXIT=0
$ ... config --format json | Select-String '"name"'
  "name": "graphrag-drill"
  "name": "graphrag-drill_default"
  "name": "graphrag-drill_neo4j_data"
  "name": "graphrag-drill_neo4j_logs"
```

> 只到"**包能被 load + 交付 compose 能被另一套独立项目解析**"为止；
> **没有**真的 `up` 起全套并跑冒烟 —— 那是 **P6-X**（双人 + 留证）。

### 4.7 第 9 项读数变了（判据 ⑬ / ⑭）

```
$ uv run python scripts/install_acceptance.py
 9 SKIP 恢复演练 | 未覆盖: 演练留证（D-1b 前置已满足 ⇒ 可做，但本项**仍为人工双人**
     （执行者 ≠ 见证者），AI 不得单独收口 ⇒ **顺延 P6-X**）⇒ 已过的子项不顶替没跑的子项
汇总: PASS 1 / SKIP 9 / FAIL 0
```

理由从「**D-1b 未落地**」变成「**D-1b 前置已满足、演练未做**」，**仍是 SKIP** ✅。

### 4.8 判据用例清单（**每一条都由 pytest 实际执行**）

`tests/test_delivery_images.py`（25 条，全 passed）：

- **交付 compose（G-19 族 7 条）**：`test_g19_delivery_compose_has_no_build` /
  `test_g19_dev_compose_keeps_its_build`（**不许有人删开发那份的 `build:`**）/
  `test_g19_delivery_compose_rejects_a_reintroduced_build` /
  `test_g19_delivery_compose_rejects_latest_tag` / `..._rejects_missing_own_images`（防恒绿）/
  `..._rejects_unpinned_third_party` / `..._rejects_a_missing_file`
- **脚本三分支**：`test_dry_run_prints_the_frontend_build_args`（含 `NEXT_PUBLIC_USE_MOCK=false`）/
  **`test_dry_run_never_calls_docker`**（被调用即失败）/ `test_save_defaults_to_own_images_only` /
  `test_include_third_party_adds_all_four` / **`test_saved_refs_match_the_compose_byte_for_byte`**
  （`image: <ref>` 整行比对）/ `test_plan_refuses_a_non_compliant_compose`
- **`--verify`**：`test_verify_passes_on_an_intact_bundle` /
  **`test_verify_detects_a_single_flipped_byte`**（R-9 头号判据）/ `test_verify_detects_a_tag_mismatch` /
  `test_verify_dry_run_does_not_call_docker` / `test_verify_on_a_directory_without_manifest` /
  `test_verify_rejects_a_foreign_schema_version` / `test_verify_rejects_app_version_drift`
- **Y8 红线**：`test_no_registry_operations_in_the_script`（3 参数：push / login / tag）/
  `test_no_registry_steps_in_ci`；**F-P6D1b-1 回归**：`test_dockerignore_does_not_exclude_the_scripts_the_dockerfile_copies`

`tests/test_install_acceptance.py`（改 2 条）：`test_d1b_inspection_finds_build_in_dev_compose`
（改名 + 改语义）、**新增** `test_d1b_inspection_passes_on_the_delivery_compose`、
`test_item9_is_skipped_because_no_drill_is_filed_yet`（断言「D-1b 前置已满足」且**不含**「未落地」）。

---

## 5. 本批踩到的坑（**留给下一批，别再踩**）

1. **别直接删开发 compose 的 `build:`** —— G-19 第二条靠它识别自研，删了那条会 FAIL，
   而失败原因看起来像"护栏错了"（`test_guardrails_delivery.py:198` 的 `assert checked`）。
2. **`.dockerignore` 的通配会误伤 Dockerfile 要 COPY 的目录**，而且只报 warning（F-P6D1b-1）。
   改 context / 改 COPY 之前先真跑一次 `docker build`，别只看 `compose config`。
3. **`inspect_d1b` 这类"全仓找痕迹"的查证，要同时盯目录范围与后缀白名单** ——
   少一个 `*.py` 或少一个 `("backend","scripts")` 前缀，就会**恒红且查不出原因**（F-P6D1b-4）。
4. **`resolve().relative_to(REPO_ROOT)` 在跨盘符时会抛 `ValueError`**（Windows 上 `tmp_path`
   在 C:、仓库在 D:）⇒ 清单里记路径要能退回落盘原样。
5. **`docker save -o` 不建目录**、**GBK 打印 `⇒` 会抛异常**、**`python scripts/x.py` 的
   `sys.path[0]` 是 `scripts/`** —— 三个都是跑一遍才知道的（F-P6D1b-2 / F-P6D1b-3）。

---

## 6. 残留风险（**不许被读成"D-1b 已完成 / 可私有化交付"**）

1. **没有做过一次独立环境的完整 `up` + 冒烟**。本批只到"包已产出 + 可被 load + 交付 compose
   可解析"。**§6.4 的三条判据里，②（独立度）与 ③（执行者 ≠ 见证者）仍未兑现** ⇒ 归 **P6-X**。
2. **DR-A7（离线包）/ DR-C2（补丁流程）仍只能标「部分」**：出的是**包**，不是"打补丁"的能力；
   补丁流程还需要"客户现场换 tag 回滚"的演练证据。
3. **registry 分支按 Y8 不做** ⇒ 客户若要求"从 registry 拉"，本批**没有**这条通道（不该解释为"已完成"）。
4. **M4 的游离镜像未清理**（`graphrag-agent-backend:latest` 705MB / `graphrag-agent-frontend:latest`
   1.14GB）⇒ 占着本机磁盘，且与 compose 的命名**不是同一个**；清理属另一条审批。
5. **`.dockerignore` 的 `**/scripts/` 是**删掉**而不是改成白名单** ⇒ `backend/scripts`（1.2 MB）
   现在会进镜像（这是 Dockerfile 本来就想要的）；若将来 `backend/scripts` 里放了**不该 baked**
   的东西（大语料 / 本地产物），要回来逐条点名排除。
6. **F-P6W-3 仍未处置**（`.env.example` 的 `PRIVATE_DEPLOY_ENABLED=false`）⇒ 第 10 项仍会红。
7. **tar 只留在本机**（496 MB，U 盘 / 内网搬运）；**不入库、不传 artifact** ⇒
   换机器时这份产物要**重新出**（同一 tag 可复现，但 sha256 可能不同）。

---

## 7. 下一批指针

→ [`new-session-prompt.md`](./new-session-prompt.md)（**P6-X = 纯人工批次，已改写为「人做主体」模式**）
