# P6-X2：修 F-P6X-1 缺口 + 按 §9.2 序 7 完整口径重做演练（混合批次）

> **本文件性质**：**AI 搭的骨架 + 机械依据**，按提示词 §5.1「期望值表必须先定，不许演练当天临时定」的要求起草。
> ⚠️ **每一项的最终判分（PASS / 登记过的 SKIP / FAIL）由人定稿**；AI 只负责把「依据」查实到 `文件:行`。
> **Non-goals 不是我新编的** —— 逐条继承自 [`../P6-X/new-session-prompt.md`](../P6-X/new-session-prompt.md) §3 的 9 条。
> 上一批查证结论：[`../P6-X/integration-log.md`](../P6-X/integration-log.md) §13（三查已证、零代码改动）。

---

## 0. 为什么先建这个文件

提示词 §5.1：**「这张表不先定好，演练当天会被读成『失败』，接着就会有人想把判据改松。」**
而 §13 的查证把「三种修法都要连带测试面」证出来了 ⇒ **Y1 未拍板期间，先把不依赖裁决的演练前置做掉**。

---

## 1. Non-goals（**9 条** —— 继承自 P6-X2 提示词 §3，改任何一条之前先按提示词 §10 升级）

1. **不许改 `check_9` / §10 的表换绿**（F-P6X-2 只登记）：判据「只读留证存在与否」是它的固有弱点，**本批不改**。
2. **不修 F-P6X-3**（§6.2 探针对准源环境、不认 `--target-db`），**只登记**：属另一批次（要连带改探针的注入方式）。
3. **AI 不得代做演练 / 代写留证正文 / 代判结论**：§9.3 第 2 条；**执行者 ≠ 见证者**；`docs/drills/` 正文一个字都不许 AI 代写。
4. **不起任何真 LLM 调用**（可持续到 D1 另行批准为止）：本批动作必须 ¥0 ⇒ 第 4 / 5 项是**登记过的 SKIP**。
5. **不做交付动作** —— release notes / tag / 对外验收一律不碰（**R-10**）；留证须标「内部演练，非客户现场验收」。
6. **不许碰生产 / 目标环境的真实数据**：演练落到**独立环境**（由**固定 tag 镜像**起，不许源码起）。
7. **不动 `cost_metrics` /「图元素个数」同量纲裁决**：那是 P6-V3 / P6-V4 的地盘（C3-a / C3-b）。
8. **不顺手清 `delivery-kit/` `.specstory/` `.vscode/` 等遗留未跟踪项**：前两批已列 Non-goal，**只登记不动**。
9. **不许为了让第 9 项翻绿而改环境 / 改判据**：含「先激活一下让 §6.2 通过」这种（P6-X §7 路径 B / C 已否决）。

> ⚠️ 若执行中发现必须触碰某条 Non-goal ⇒ **停下报告**，不自行处置。

> 回切点（每个子任务收尾）：`cd backend && uv run python scripts/check_session_drift.py`
> **S1 报「没有 Non-goals」⇒ 先停下来补边界。**

---

## 2. 演练前置核验（**2026-10-12 实跑，机械读数**）

| 项 | 判据 | 实测 | 结论 |
|---|---|---|---|
| **固定 tag 镜像仍在** | `delivery-plan.md` §9.4.1 登记 `sha256:2fcd0ed1389e`（backend）/ `sha256:6e0c62a6a2f6`（frontend） | `graphrag-agent/backend:1.6.0` ID `2fcd0ed1389e`、digest `sha256:2fcd0ed1389e7575…`；`frontend:1.6.0` ID `6e0c62a6a2f6`、digest `sha256:6e0c62a6a2f68e0b…` | ✅ **与登记一致**（前缀逐字节） |
| **交付 compose 无 `build:`** | `deploy/docker-compose.delivery.yml` | `^\s*build:` **0 处**；`:86 / :113` = `image: graphrag-agent/backend:1.6.0`、`:177` = `frontend:1.6.0`（第三方 `:36` neo4j / `:60` postgres 由现场自拉） | ✅ 符合 §6.4① |
| **四个服务都有 healthcheck** | 第 1 项要「全 healthy」 | `:48` neo4j（cypher-shell）/ `:67` postgres（pg_isready）/ `:157` backend（`/api/v1/health`）/ `:183` frontend（node fetch） | ✅ 第 1 项**可达**（不是结构性不可达） |
| **离线包仍在** | `backend/reports/delivery/graphrag-agent-offline-1.6.0.tar` | **496,532,480 字节**（2026-10-11 19:00），与 §9.4.1 登记一致 | ✅ 在；⚠️ **未入库（gitignore）** ⇒ 演练前再确认一次 |

> ⚠️ **易混淆点（登记）**：本机另有 `graphrag-agent-backend:latest` / `graphrag-agent-frontend:latest`（12 天前，
> 名字是**连字符** `graphrag-agent-frontend`，不是 `graphrag-agent/frontend`）⇒ 拉镜像时**别拉错**。

---

## 3. §5.1 期望值表（**十项逐项；判分由人定稿**）

判据实现：`backend/scripts/install_acceptance.py`（`check_1`~`check_10`，`:245 / :337 / :366 / :383 / :454 / :488 / :507 / :576 / :673 / :710`）。
汇总规则（`:136-143`）：**FAIL 优先 → 其次 SKIP → 全 PASS 才 PASS** ⇒ **一项里有一个子项 SKIP，整项就是 SKIP**。
退出码只看 FAIL（`:898`）⇒ **SKIP 再多也是 0**，`render` 的汇总行明写「SKIP **不是**通过」。

| 项 | 判据 | 独立环境**预期**（AI 提案） | 机械依据 | 演练前必须做的动作 |
|---|---|---|---|---|
| **1** 全 healthy + `/health` 200 | `docker compose ps` 全 healthy **且** HTTP 200 | **PASS** | SKIP 只在：无 docker / 缺 compose 文件（`:311-318`）或 compose 命令本身失败（`:268-278`，原文：「验不到」≠「观测到不健康」）/ 缺 base-url（`:332-333`）；compose 四服务均有 healthcheck（§2） | 独立环境 `up -d` 等到全 healthy；给 `--compose-file` + `--base-url` |
| **2** License 生效 | `GET /license/status` = `active` + 四维度 | **PASS**（**前提是重新签发**） | FAIL：`status != "active"`（`:351-352`）；SKIP 只在缺 base-url（`:339-347`）。⚠️ **P6-Z 已定：换机 ⇒ License 失效，须重新签发**（`tools/license/issue_license.py`，**不进镜像**） | **先签发 license 再验收**；不签 ⇒ 必 FAIL |
| **3** License 拒绝可达 | 移除 license → 403 `LICENSE_MISSING` | **PASS** | 委派 pytest：`tests/test_guardrails_compliance.py -k g23_missing_license_blocks_requests`（`:375-377`）；SKIP 只在 `--skip-pytest`（`:209-212`）；空跑（`ran == 0`）= **FAIL**（`:229-235`） | 不加 `--skip-pytest`；该用例要 PG `graphrag_test`（conftest.py:184）⇒ 演练机 PG 须在跑（本机基线 1251/43 已跑过 ⇒ 已就绪） |
| **4** 上传→解析→建图 | 样例文档 `pending → completed` + active `kg_version` 可读 | **SKIP（登记过）** | 不给 `--pipeline-sample` ⇒ SKIP（`:387-395`，原文「本批默认**不**碰真解析器 / LLM」） | **当天不许补跑**；SKIP 是预期内，**不是回归**（Non-goal 4） |
| **5** 问答可溯源 | 引用 ≥1 且可回查原文 | **SKIP（登记过）** | 不给 `--ask-question` ⇒ SKIP（`:458-465`，「真 LLM 不进 CI」）。⚠️ **给了**却零引用且未 `refused` ⇒ **FAIL**（`:480-482`） | 同上，**不给这个参数** |
| **6** 审计留痕 | `audit_log` 新增 **≥7 条**且 `trace_id` 可聚合 | **PASS（可 ¥0 达标）** ⚠️ **陷阱项** | SKIP **只在**缺 base-url（`:490-491`）⇒ 演练**会**给 base-url ⇒ **不再 SKIP**，`len(items) < 7` 直接 **FAIL**（`:496-497`）。<br>可达路径：`AuditMiddleware` 对 `/api/v1/*` 且**非 health** 的请求**全量写**（`middleware.py:139-147`），且 `finally` 里写 ⇒ **403 / 失败也留痕**（`:133-135`）；`audit.list` 自举（audit.py:81） | **先连打 ≥7 次只读 `/api/v1/*`**（如 `GET /api/v1/documents?page_size=1`、`GET /api/v1/audit?page_size=1`）⇒ 不起 LLM、¥0 |
| **7** 跨 org 被拦截 | 列表空 / 直取 403 | **SKIP（整项）** | 三子项：g9（`:510-516`）/ g26（`:517-523`）委派 pytest；目标环境子项缺 `--org-b` 或 **401/403 ⇒ SKIP**（`:540-554`，原文：「被 RBAC 挡在门外 ≠ 隔离生效」）<br>⇒ 一票 SKIP ⇒ **整项 SKIP**，即便两个 pytest 子项 PASS | 给 `--org-a` / `--org-b`；授权没备好也**只是 SKIP 不是 FAIL**。g9 真图用例本地未设开关会 skip，但 `test_g9_0_ci_really_has_neo4j_service` 是静态查 `ci.yml` ⇒ **会真跑** ⇒ 不会撞「空跑 FAIL」 |
| **8** 备份成功 | `backup-manifest.json` 完整 + SHA-256 通过 | **PASS** | 纯本地哈希（`:52` / `:594-597`），**离线最稳的一项**；⚠️ **给了 `--backup-dir` 但目录不存在 = FAIL，不是 SKIP**（`:591-592`） | **演练当天先跑一次 `scripts/backup.py`**（P6-W 那套未入库、可能已被清，提示词 §4 已登记） |
| **9** 恢复演练 | `docs/drills/restore-drill-*.md` 存在 | **PASS（本批目标）** | 只认留证**真实存在**（`:681`）；有测试钉死（test_install_acceptance.py:173-188） | **先有留证（人写），再回登文档**；留证须标「内部演练，非客户现场验收」+ 执行者 / 见证者 |
| **10** 生产配置 | `PRIVATE_DEPLOY_ENABLED=true` **且** 无密钥进日志 | **PASS** | SKIP：缺 `--env-file`（`:728-736`）／缺 `--log-file`（`:738-747`）／env 里无可比密钥（`:754-758`）。⚠️ **日志文件不存在也计入 leaked ⇒ FAIL**（`:763-764`） | 两个参数都要给，**且路径真实存在** |

**AI 提案的汇总预期**：**PASS 7 / SKIP 3 / FAIL 0**（SKIP = 第 4、5 项「登记过」+ 第 7 项目标环境子项拖整项）。
⚠️ **与本机基线（PASS 1 / SKIP 9）不同口径，不许跨口径比**（提示词 §7 纪律）—— 本机那趟是**没给 base-url** 才 9 项 SKIP。

### 3.1 演练前必做的 4 个动作（**不做就会变 FAIL，不是 SKIP**）

1. **重新签发 License**（第 2 项）—— 换机即失效（P6-Z 已定），`tools/license/issue_license.py`，不进镜像；
2. **现跑一次备份集**（第 8 项）—— 旧集未入库、可能已被清；给了不存在的目录 = FAIL；
3. **先打 ≥7 次只读 `/api/v1/*`**（第 6 项）—— ¥0、不起 LLM，把隐患 FAIL 转成 PASS；
4. **备好 `--env-file` + `--log-file` 且真实存在**（第 10 项）—— 日志文件不存在会被判 leaked。

### 3.2 两处口径风险（**登记，本批不改**）

- `--compose-file` 的 help 文案写「默认 `deploy/docker-compose.yml`」（`:840`），**实际默认 `deploy/docker-compose.delivery.yml`**（`:76` / `:872`）⇒ 第 1 / 9 项按**交付** compose 判定，别照 help 读。
- SKIP / FAIL 分界：**缺参数 / 缺工具 / 命令跑不起来 / 主体未授权 / 合法拒答** ⇒ SKIP；**拿到了观测值但不符合判据** ⇒ FAIL；**已给的目录 / 文件不存在算 FAIL**（`:591-592`、`:763-764`）。

---

## 4. 待定（**由人填，AI 不代判**）

| # | 事项 | 状态 |
|---|---|---|
| Y1 | F-P6X-1 修法（A / B / C / **或扩选项 D**） | ⏳ 未拍 ⇒ **段落 ① 未开工**（§13 已证 A / B 都会触发不分 org 的 supersede，F-P6X-5） |
| Y2 | 演练环境 = 独立环境（固定 tag 镜像起） | 默认，未反对即照此 |
| Y3 | 含升级演练 + 回滚 | 默认含 |
| Y4 | **执行者 / 见证者**（须两人不同、当场在场） | ⏳ 空 ⇒ **段落 ② 不开工** |
| Y5 | 不顺手修 F-P6X-2 / F-P6X-3 | 默认不修 |
| Y6 | 镜像 org 维度 / supersede 范围是否纳入本批 | 默认只登记 |
| — | **本表逐项判分定稿** | ⏳ **等人定稿**（AI 只出了依据与提案） |
