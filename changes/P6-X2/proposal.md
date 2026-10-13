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

| 项 | 判据 | 独立环境**预期**（AI 提案） | **演练 ① 实测 + 定稿**（**wIlliam 2026-10-13 拍板**） | 机械依据 | 演练前必须做的动作 |
|---|---|---|---|---|---|
| **1** 全 healthy + `/health` 200 | `docker compose ps` 全 healthy **且** HTTP 200 | **PASS** | **PASS** ✅（四服务 healthy、`/health` 200、新卷 `graphrag-drill_*`） | SKIP 只在：无 docker / 缺 compose 文件（`:311-318`）或 compose 命令本身失败（`:268-278`，原文：「验不到」≠「观测到不健康」）/ 缺 base-url（`:332-333`）；compose 四服务均有 healthcheck（§2） | 独立环境 `up -d` 等到全 healthy；给 `--compose-file` + `--base-url` |
| **2** License 生效 | `GET /license/status` = `active` + 四维度 | **PASS**（**前提是重新签发**） | **PASS** ✅（容器内取指纹重签 ⇒ `active`，四维度齐全；⚠️ **宿主指纹会 MISMATCH** ⇒ 指纹须在容器内取） | FAIL：`status != "active"`（`:351-352`）；SKIP 只在缺 base-url（`:339-347`）。⚠️ **P6-Z 已定：换机 ⇒ License 失效，须重新签发**（`tools/license/issue_license.py`，**不进镜像**） | **先签发 license 再验收**；不签 ⇒ 必 FAIL |
| **3** License 拒绝可达 | 移除 license → 403 `LICENSE_MISSING` | **PASS** | **PASS** ✅（G-23 复用 `1 passed`；⚠️ 委派 pytest 跑在**本机**测试库，非演练栈） | 委派 pytest：`tests/test_guardrails_compliance.py -k g23_missing_license_blocks_requests`（`:375-377`）；SKIP 只在 `--skip-pytest`（`:209-212`）；空跑（`ran == 0`）= **FAIL**（`:229-235`） | 不加 `--skip-pytest`；该用例要 PG `graphrag_test`（conftest.py:184）⇒ 演练机 PG 须在跑（本机基线 1251/43 已跑过 ⇒ 已就绪） |
| **4** 上传→解析→建图 | 样例文档 `pending → completed` + active `kg_version` 可读 | **SKIP（登记过）** | **SKIP（登记过）** ✅ 与预期一致（未给 `--pipeline-sample`） | 不给 `--pipeline-sample` ⇒ SKIP（`:387-395`，原文「本批默认**不**碰真解析器 / LLM」） | **当天不许补跑**；SKIP 是预期内，**不是回归**（Non-goal 4） |
| **5** 问答可溯源 | 引用 ≥1 且可回查原文 | **SKIP（登记过）** | **SKIP（登记过）** ✅ 与预期一致（未给 `--ask-question`；真 LLM 未授权 Y1″） | 不给 `--ask-question` ⇒ SKIP（`:458-465`，「真 LLM 不进 CI」）。⚠️ **给了**却零引用且未 `refused` ⇒ **FAIL**（`:480-482`） | 同上，**不给这个参数** |
| **6** 审计留痕 | `audit_log` 新增 **≥7 条**且 `trace_id` 可聚合 | **PASS（可 ¥0 达标）** ⚠️ **陷阱项** | ⚠️ **FAIL**（**与预期不符**）—— 判据读数为 0，但**数据够**：演练栈 `audit_log` = **862 条** ≥ 7 ⇒ **不是数据不足，是工具读不到**（F-P6X-8：脚本无认证入口 ⇒ 401）。**定稿：照实记 FAIL**，原「预期 PASS」保留作对照；口径冲突（登记「未授权⇒SKIP」vs 实现「401⇒FAIL」）**交下批裁决**，本批不改判据 | SKIP **只在**缺 base-url（`:490-491`）⇒ 演练**会**给 base-url ⇒ **不再 SKIP**，`len(items) < 7` 直接 **FAIL**（`:496-497`）。<br>可达路径：`AuditMiddleware` 对 `/api/v1/*` 且**非 health** 的请求**全量写**（`middleware.py:139-147`），且 `finally` 里写 ⇒ **403 / 失败也留痕**（`:133-135`）；`audit.list` 自举（audit.py:81） | **先连打 ≥7 次只读 `/api/v1/*`**（如 `GET /api/v1/documents?page_size=1`、`GET /api/v1/audit?page_size=1`）⇒ 不起 LLM、¥0 |
| **7** 跨 org 被拦截 | 列表空 / 直取 403 | **SKIP（整项）** | **SKIP（整项）** ✅ 与预期一致（g9 `4 passed` / g26 `30 passed`；目标环境子项因 401 ⇒ 一票 SKIP 拖整项） | 三子项：g9（`:510-516`）/ g26（`:517-523`）委派 pytest；目标环境子项缺 `--org-b` 或 **401/403 ⇒ SKIP**（`:540-554`，原文：「被 RBAC 挡在门外 ≠ 隔离生效」）<br>⇒ 一票 SKIP ⇒ **整项 SKIP**，即便两个 pytest 子项 PASS | 给 `--org-a` / `--org-b`；授权没备好也**只是 SKIP 不是 FAIL**。g9 真图用例本地未设开关会 skip，但 `test_g9_0_ci_really_has_neo4j_service` 是静态查 `ci.yml` ⇒ **会真跑** ⇒ 不会撞「空跑 FAIL」 |
| **8** 备份成功 | `backup-manifest.json` 完整 + SHA-256 通过 | **PASS** | **PASS** ✅（五类齐全、SHA-256 全过：PG 192157B／图库 6028528B／storage 114688000B／license 580B／config 3632B） | 纯本地哈希（`:52` / `:594-597`），**离线最稳的一项**；⚠️ **给了 `--backup-dir` 但目录不存在 = FAIL，不是 SKIP**（`:591-592`） | **演练当天先跑一次 `scripts/backup.py`**（P6-W 那套未入库、可能已被清，提示词 §4 已登记） |
| **9** 恢复演练 | `docs/drills/restore-drill-*.md` 存在 | **PASS（本批目标）** | **PASS** ✅（留证 `restore-drill-20261013.md` 落库后复跑转 PASS；落库前那轮是 SKIP ⇒ **SKIP 不是通过**） | 只认留证**真实存在**（`:681`）；有测试钉死（test_install_acceptance.py:173-188） | **先有留证（人写），再回登文档**；留证须标「内部演练，非客户现场验收」+ 执行者 / 见证者 |
| **10** 生产配置 | `PRIVATE_DEPLOY_ENABLED=true` **且** 无密钥进日志 | **PASS** | **PASS** ✅（`PRIVATE_DEPLOY_ENABLED=true`、5 个密钥值在 1 份日志里均未出现） | SKIP：缺 `--env-file`（`:728-736`）／缺 `--log-file`（`:738-747`）／env 里无可比密钥（`:754-758`）。⚠️ **日志文件不存在也计入 leaked ⇒ FAIL**（`:763-764`） | 两个参数都要给，**且路径真实存在** |

### 汇总（**两行都留：事前预期 vs 事后实测**）

- **演练 ① 实测（2026-10-13，wIlliam 定稿）**：**PASS 6 / SKIP 3 / FAIL 1**
  （SKIP = 第 4、5 项「登记过」+ 第 7 项目标环境子项拖整项；FAIL = 第 6 项）。
- **演练前 AI 提案（保留作对照）**：**PASS 7 / SKIP 3 / FAIL 0**。
  ⚠️ **差异唯一来源 = 第 6 项**（预期 PASS → 实测 FAIL）：原因是**工具缺口 F-P6X-8**，
  **不是数据不足**（`audit_log` 862 条 ≥ 7 ⇒ 判据本身可达）⇒ **不许为对齐预期去改判据**。

⚠️ **与本机基线（PASS 1 / SKIP 9）不同口径，不许跨口径比**（提示词 §7 纪律）—— 本机那趟是**没给 base-url** 才 9 项 SKIP。

### 演练 ① 暴露的三条（**定稿备注；本批不改，下批一眼见坑**）

1. **F-P6X-7**：`restore.py` 图库恢复在「宿主编排 → 容器执行」形态下**不可行**
   （只走 `docker exec`，而 `neo4j-admin load` 要求停服；`--from-path` 传宿主路径、容器内不可达）；
   `backup.py` 已用 `--volumes-from` 解同款问题 ⇒ **两侧不对称**。演练中按备份侧思路**手工补完**
   图库（42 files / 268.3 MiB ⇒ 11668 节点、176 个 `:KgVersion`）。
2. **F-P6X-8**：`install_acceptance.py` **无认证入口** ⇒ 生产形态（`PRIVATE_DEPLOY_ENABLED=true`、
   `dev_fallback_enabled: False`）下第 6 项必 FAIL、第 7 项目标环境子项必 SKIP ⇒ **工具缺口，非演练失败**。
3. **§6.2 `ghost_version`**：PG active `20261012T064951Z-inc-569555ad` 在图库无镜像节点
   ⇒ 恢复后 §6.2 判 **FAIL**（退出码 2「不许启动」）⇒ 属 F-P6X-1 的**历史**部分，
   补它须写源环境 ⇒ **Non-goal 6 ⇒ 本批不执行**（本次裁 8.3-A：到此为止、另立批）。

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
| Y1 | F-P6X-1 修法（A / B / C / **或扩选项 D**） | ✅ **已拍（2026-10-12）= O-1「纳入 F-P6X-5，一次闭合」** ⇒ 段落 ① **已完成并推送**（`383b818`，CI 绿，见 `integration-log.md`） |
| Y2 | 演练环境 = 独立环境（固定 tag 镜像起） | 默认，未反对即照此 |
| Y3 | 含升级演练 + 回滚 | 默认含 |
| Y4 | **执行者 / 见证者**（须两人不同、当场在场） | ✅ **沿用 P6-X 已定：执行 `wIlliam` / 见证 `tianen`**（`changes/P6-X/proposal.md:16-17`、决策 X1 `:43`、`integration-log.md:3`）⇒ 段落 ② **不再卡人名**；⚠️ 仍须**演练当天两人当场在场**（§9.3 第 2 条红线，**AI 代不了**） |
| Y5 | 不顺手修 F-P6X-2 / F-P6X-3 | 默认不修 |
| Y6 | 镜像 org 维度 / supersede 范围是否纳入本批 | ✅ **纳入本批**（即 Y1′ / O-1），不再是「只登记」 |
| Y1″ | 是否开真 LLM（决定第 4 / 5 项是 PASS 还是登记过的 SKIP） | ⏳ **演练前须再授权一次**（段落 ① 未消耗 LLM） |
| **Y7** | **演练日期**（恢复 + 升级两场，须两个不同日期） | ✅ **已定（用户 2026-10-13 授权 AI 代填）**：**恢复 10-13（周二）／升级 10-14（周三）** ⇒ 详见 §5 |
| — | **本表逐项判分定稿** | ✅ **已定稿（2026-10-13，wIlliam 逐项拍板）**：演练 ① 实测 **PASS 6 / SKIP 3 / FAIL 1**；第 6 项按实测记 **FAIL**（F-P6X-8 工具缺口，非数据不足），原「预期 PASS」保留作对照；三条发现（F-P6X-7 / F-P6X-8 / §6.2）已作为备注钉在 §3 表末 |

---

## 5. 演练排期（**日期由用户授权 AI 代填；演练本身仍由人做**）

> 用户 2026-10-13：「不需要换人，就是 wIlliam / tianen；演练日期你按经验填两个不同的。」

| # | 演练 | 日期 | 留证文件（**人写**） | 为什么排在这里 |
|---|---|---|---|---|
| **①** | **恢复演练**：现跑备份集 → 独立环境（固定 tag 镜像）恢复 → 冒烟 → 十项验收 | **2026-10-13（周二）** | `docs/drills/restore-drill-20261013.md`<br>⚠️ 文件名**必须**匹配 `restore-drill-*.md`（`install_acceptance.py:681`） | 它**不依赖**升级 ⇒ 排最前；先把「独立环境 + **重新签发 License**（换机即失效，P6-Z）+ 现跑备份集」跑通 ⇒ **第 9 项当天即可转 PASS** |
| **②** | **升级演练（含回滚）**：1.6.0 → 升级 → 回滚 → 重跑 1~6 项 | **2026-10-14（周三）** | `docs/drills/upgrade-drill-20261014.md`<br>（不匹配第 9 项的 glob ⇒ 是**升级**留证，**不影响**第 9 项判定） | 起点必须是「① 已恢复到 1.6.0 的**健康**环境」⇒ **只能在 ① 之后**；回滚后还要重跑 1~6 项，单独占一天 |

**排序理由（经验，可改）**：

1. **② 依赖 ①、① 不依赖 ②** ⇒ 顺序不可倒（升级演练的"回滚"是回滚到 ① 恢复出来的基线）；
2. **第 2 项（License）必须在 ① 当天第一步处置** —— 换机即失效，`tools/license/issue_license.py` 不进镜像，不签 ⇒ 必 FAIL（`:351-352`）；
3. **第 6 项（audit_log ≥7 条）放在 ① 的冒烟里** —— 连打 ≥7 次只读 `/api/v1/*`，¥0、不起 LLM；
4. 两场**分开写两份留证** ⇒ 符合「**先有留证（人写），再回登文档**」。

**n=2（O-3，可选）**：若按「恢复 + 升级**各两轮**」，第二轮建议 **10-15（周四）/ 10-16（周五）**，
留证另起文件名（如 `restore-drill-20261015.md`）⇒ **两轮读数都贴**，n=1 不得当分布或上限（提示词 §11）。

**⚠️ AI 边界（Non-goal 3，红线）**：

- 上面两个日期是**登记**，不是"演练已做"；
- 留证正文由**执行者 wIlliam** 写、**见证者 tianen** 署名（两人**当场在场**，§9.3 第 2 条）；
- AI 只做**搬运 / 校验 / 跑命令 / 回登**，`docs/drills/` 正文一个字都不代写。

**现状（2026-10-13 收盘）**：演练 ① **已完成**，留证 `docs/drills/restore-drill-20261013.md`
**由 wIlliam 写 / tianen 署名并落库** ⇒ 第 9 项 **SKIP → PASS**，复跑读数 **PASS 6 / SKIP 3 / FAIL 1**
（`install_acceptance.py:680-687`）。§5.1 期望值表**已定稿**（见 §3）。

**演练 ②（升级，10-14）**：2026-10-13 查实 —— 本地**只有 `1.6.0` 镜像**，交付 tag 受
「自研 tag == `app_version`」约束（G-19）⇒ **没有真实升级目标版本**；
wIlliam 裁决 **不造同镜像别名充数** ⇒ **升级演练等真有新版本（下一批 1.7.0）再做**，
不写"验到升级"的假留证。
