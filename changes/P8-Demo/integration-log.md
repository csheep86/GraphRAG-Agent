# P8-Demo · 演示可用性收口 —— 集成日志

> **日期**：2026-10-29 ｜ **基线**：`e87846b`（P8-Release 路 B 裁决）｜ **范围**：见 `proposal.md` §3 的 10 条 Non-goals
> **结论**：演示栈从"起得来但用不了"救到 **彩排 PASS 10 / FAIL 0 / SKIP 0**（含真实 LLM）。
> ⚠️ **仍有 1 件必须人做的事**：4 个前端页是 CSR，脚本只能证"路由可达"，**文案渲染需你在浏览器点一次**（见 §6）。

---

## 1. 起始状态（真机读数，非推断）

| 项 | 读数 |
|---|---|
| 唯一在跑的栈 | `graphrag-drill`（delivery compose，镜像 **1.6.0**），四服务 healthy |
| `users` | **0 行** ⇒ 无任何账号 |
| 带 `X-Org-Id` 请求业务端点 | `401 UNAUTHORIZED`（`dev_fallback_enabled: false`） |
| `kg_versions` | 5 个全 ready，latest = `20261012T064951Z-inc-569555ad`（**5 实体 / 0 文档**） |
| `documents` | 7 篇（6 篇挂 `attendance-demo-v1`） |
| `affiliation_suspicions` | 0 行 |
| 容器内 LLM 凭据 | **无**（`printenv` 无 `LLM_*`） |

## 2. 做了什么（按序，每步都有读数）

| # | 动作 | 结果 |
|---|---|---|
| 1 | 用 **override** 把栈换到 1.7.0 镜像（1.7.0 镜像本机已存在，**未重建**） | `/health` = **1.7.0**；`documents` 仍 7；数据卷复用（项目名 `graphrag-drill` + 同名卷） |
| 2 | db-init 失败后修属主 | 见 §3.1 |
| 3 | 播种演示账号 | `users` 0 → **1**（`dev-00000000-0000-4000-8000-0000000000aa`，admin 授权） |
| 4 | 登录 | `POST /auth/login` → JWT（8h） |
| 5 | 切 active 图谱版本 | 见 §3.2；overview `doc=6 / entity=2625 / rel=3591 / version=attendance-demo-v1` |
| 6 | `demo_rehearsal.py` 支持 JWT | 加 `--password` / `--username`；无 token 时保持旧 dev 头行为 |
| 7 | 补齐 4 处容器缺口 | 见 §3.3~§3.6 |
| 8 | 完整彩排 | **PASS 10 / FAIL 0 / SKIP 0**（含真实 LLM 与前端 4 页） |

### 2.1 演示账号（**密钥不入库**）

- 用户名：`dev-00000000-0000-4000-8000-0000000000aa`
- 口令：**不写在本文件**（纪律：密钥禁入库）。存于 `backend/reports/delivery/.env.drill`（该目录已被 `.gitignore` 忽略）的播种记录附近；播种命令为
  `docker compose ... exec -T -e ALLOW_DEV_ORG_HEADER=true backend /app/.venv/bin/python scripts/seed_dev_rbac.py --password=<口令>`
  ⚠️ 那条 `-e` **只作用于本次一次性命令**，服务进程本身不开 dev 逃生口（G-27 口径未破）。

## 3. 踩到的坑与根因（**每一条都是实测，不是猜**）

### 3.1 db-init `exit 1`：`must be owner of table affiliation_suspicions`

`init_rls_roles.py` 的阶段 2 以 `app_owner` 身份 `ALTER TABLE … ENABLE RLS`，而现有表属主是超级用户 `graphrag`（阶段 3 才归主，顺序颠倒）。
**处置**：以超级用户把 19 张表属主归到 `app_owner`（脚本阶段 3 的既定动作，只是提前执行），再重跑 ⇒ `db-init Exited (0)`。

### 3.2 `POST /graph/versions/{v}/activate` **不能**切换 active

实测：激活返回 `graph_mirror_status=active`，但 `GET /graph/overview` 仍读 `inc-569555ad`。
根因：`KgVersioningService.get_active` 的语义是「**最新 ready**」（`versioning.py:206`，排序 `ready_at DESC…`）；`activate` 只同步 Neo4j 镜像 + 确保 ready。
**处置（走项目既定路径，不伪造时间戳）**：重跑 `ingest_attendance_csv.py --kg-version attendance-demo-v1 --purge-csv`（**确定性映射，零 LLM**，脚本 `:1144` 明写"重跑会刷新 `ready_at` ⇒ `get_active` 稳定选中本版本"）。
实测：16.2s，实体 2625 / 关系 3591，`[PG] attendance-demo-v1 -> ready`，演示用例 8/8 OK。

### 3.3 换镜像后 License 失效：`LICENSE_MISSING`

`license_file_path` 默认 `deploy/license/app.lic`（相对 cwd = `/app`），1.7.0 镜像内无此目录（1.6.0 行为不同）。
**处置**：override 挂载 `license-drill-20261013.lic` 到 `/app/deploy/license/app.lic:ro`。
⚠️ **同时必须保留 `/etc/machine-id` 挂载**——compose override 的 `volumes:` 是**整体替换**；丢了它，指纹退化成容器 MAC，License 每次 recreate 都失效。

### 3.4 合规扫描 3 条规则被**静默跳过**（最危险的一条）

彩排 A2 报 `unresolved=[weekly_hours_cap, monthly_standard_hours, core_hours_required]`、`skipped=[weekly_hours_exceeded, monthly_overtime_exceeded, core_window_absence]`
⇒ 演示时表现为"扫完了没事"，其实是**没算**。
根因：阈值正则只能从制度文档的 M1 产物 `full.md` 命中（`policy_values.py::load_policy_documents`）；图谱侧只存 `mention` + `canonical_name`（短提及里不可能有「每周工作 40 小时」）。而容器内 `/app/storage` **不存在**（0 个 `full.md`）。
**处置**：挂载本机 `backend/storage` ⇒ A2 转 PASS：**7 条规则值全部带出处**，findings **8**（high 2 / medium 6），样例「李静 月排班 216h − 月标准 174h = 加班 42h > 上限 36h」。

### 3.5 问答 HTTP 500：`PromptNotFoundError: Prompt 目录不存在: /prompts`

与 `demo/` 同源：镜像内 `REPO_ROOT` 解析为 `/`。
**处置**：挂载仓库 `prompts/` 到 `/prompts:ro`。

### 3.6 问答出答案但为空：`private_deploy.violation`

`.env.drill` 的 `PRIVATE_DEPLOY_ENABLED=true`（生产默认）⇒ 私域禁外发把 LLM 调用拦了。
**处置**：override 里显式 `PRIVATE_DEPLOY_ENABLED: "false"`。
⚠️ **取舍已登记**：想演示「私域禁外发」这条能力时改回 `true`，代价是问答不再出答案——**两者不能同时演**。

### 3.7 前端 4 页：不是页面坏了，是**判据测错了对象**

交付镜像跑 `next start`（生产构建），考勤四页是 **CSR** ⇒ SSR HTML 只有应用壳（实测 11 KB，`考勤|异常|合规|工时` **零命中**，title 是通用站名）⇒ 原"HTML 含文案"断言**必然假红**。
修正后判据 = **HTTP 200 + 应用壳**；又踩一处：`could not be found` 是 Next App Router **每个页面** RSC 载荷里都带的内置 notFound 元数据（`/attendance` 命中 2 次却是正常页）⇒ 404 只能靠**状态码**判（对照实测：不存在路由 → 404）。

## 4. 门禁

| 项 | 读数 |
|---|---|
| `pytest -q` | **1307 passed / 46 skipped**（本地新起 PG 容器 `graphrag-pg-local` 提供 5432） |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12** |
| `export_openapi.py --check` | **零 drift**（本批不改契约 ⇒ 无 `gen:api` 漂移） |
| `ruff check` / `ruff format --check` | 全过 |
| 彩排 | **PASS 10 / FAIL 0 / SKIP 0**（`--domain attendance --with-llm --frontend-base http://127.0.0.1:3000`） |

费用：真实 LLM 问答 **3 次**（1 次 500 前、1 次空答案、1 次成功），量级 **< ¥0.1**。

## 5. 演示前一键自检

```bash
cd backend
uv run python scripts/demo_rehearsal.py --domain attendance --password=<口令> \
  --with-llm --frontend-base http://127.0.0.1:3000
```
期望 `PASS 10 / FAIL 0 / SKIP 0`。只做 ¥0 预检就去掉 `--with-llm`（→ PASS 9 / SKIP 1）。

## 5.5 重启演示栈（2026-10-29 收工后 **已停**，数据在卷里）

数据卷**全部保留**：`graphrag-drill_pg_data` / `graphrag-drill_neo4j_data` / `graphrag-drill_neo4j_logs`。
重启必须用**带 override 的那条命令**（少了 override 会退回 1.6.0、丢 License、丢 storage ⇒ A2 静默跳过、问答 500）：

```powershell
cd D:\AIProject\GraphRAG-Agent\backend\reports\delivery
$env:COMPOSE_PROJECT_NAME='graphrag-drill'
docker compose -f docker-compose.drill-20261013.yml -f drill-license-override.yml `
               -f demo-170-override.yml --env-file .env.drill up -d
```

起来后自检：**完整**（烧一次 LLM）→

```powershell
cd D:\AIProject\GraphRAG-Agent\backend
uv run python scripts/demo_rehearsal.py --domain attendance --password=<口令> --with-llm --frontend-base http://127.0.0.1:3000
```
期望 `PASS 10 / FAIL 0 / SKIP 0`。**¥0 预检版**去掉 `--with-llm`（→ PASS 9 / SKIP 1）。

> ⚠️ 若 rebuilt/换了镜像出现 `must be owner of table …`（db-init exit 1），按 §3.1 先把 19 张表属主归到 `app_owner` 再 `up -d`。

## 6. 未做 / 遗留（不伪装）

1. **4 个前端页需人工在浏览器点验**——脚本只能证路由可达（CSR 无 SSR 文案）。**这一步 AI 不能代做**。
2. **关联方疑点页仍是空的**（`affiliation_suspicions` = 0，且 `affiliation-demo-v2` 挂 0 篇文档）。本批走考勤域，按 Non-goal 7 未补；若演示要演疑点清单，需另立批次跑 detect + 补该域数据。
3. **演示环境的 override 在 `backend/reports/delivery/`（被 `.gitignore` 忽略，不入库）** ⇒ 换机器 / 清理该目录后**无法复现**。本批按 Non-goal 未在 `deploy/` 新增编排（会牵动 G-19 / G-27 的扫描口径），故只在此登记风险。
4. ~~`v1.7.0` tag 待打~~ —— **2026-10-29 已打并推送**：CI run `40876350736` **success** 后 `git tag -a v1.7.0` → `git push origin v1.7.0`。此前 tag 停在 `v1.6.0` 而 `app_version` 已是 1.7.0，差的那一步补齐了。
5. **P8-Release 终审线未动**：P7-I（L2 端到端）、审计 §5.1 剩 2 条、路 B 的语义判据口径与重判 P6-T 真值——按 Non-goal 4 **全部不在本批**。
