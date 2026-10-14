# 发版就绪度审计（release readiness audit）

| 项 | 内容 |
|---|---|
| **日期** | 2026-10-13 |
| **HEAD** | `9f16d3ec`（P6-X2 §5.1 期望值表定稿 + 演练②推迟裁决） |
| **`app_version`** | `1.6.0`（`backend/app/core/config.py:131`；tag 待 v2.0.0） |
| **目标** | `v2.0.0` = PRD MVP 1.0 完成点，可对外推广销售 |
| **方法** | **结论一律来自机器读数**：`check_startup_readiness.py` 实测、批次集成日志、`git status`、tests 源码。不采信文档表格中的 ✅/🟡（文档会过期，本审计已发现 5 处过期口径，见 §5） |
| **关联** | [`docs/delivery-plan.md`](./delivery-plan.md) §9.2（队列）｜[`docs/acceptance-traceability-matrix.md`](./acceptance-traceability-matrix.md)（判据）｜[`docs/delivery-requirements-and-guardrails.md`](./delivery-requirements-and-guardrails.md)（DR/G） |

---

## 1. 结论摘要

> **工程侧完成约 85~90%；剩余不是工程量，而是「少量几件事」。**
> 其中最大阻塞 = **86 道人工判分（1~2 人天）**，它卡死了 C1 与多跳两条准入线的全部数字。
> 剩余总投入估算 **15~25 人天**（含一个必须由**第二自然人**到场的半天）。
> 真正的风险不是工期，而是判分结果可能触发 **F1 / F2 熔断**（推翻"图谱路线"这一产品定位）。

**三条建议**：① 今天就判那 86 题（最便宜、决策价值最高、且能最早证伪产品定位）；② 先修 B 类生产硬阻断，再补 A 类流程项（按暴露风险排，不按队列编号排）；③ 冻结新增能力（新 G 护栏 / rubric 再迭代 / 新 spec 口径 / 文档整顿），治理的边际收益已低于核平既有数字。

---

## 2. 现状快照

### 2.1 已到位（有机器证据）

| 维度 | 读数 | 证据 |
|---|---|---|
| 护栏 | 🟢 **15 条 G 已生效**；🟠 部分生效 **0**；🟡 挂起 **0**；开工地雷 7 项全清 | `backend/scripts/check_startup_readiness.py` 2026-10-13 实测 |
| 条件跳过的 G | 🔵 **2 条**（G-9 五条 / G-25 两条）**依赖 `GRAPH_REAL_NEO4J_*`，CI 由 job env 注入 ⇒ CI 上真跑**，本地 skip | `backend/tests/test_guardrails_graph.py:51-82`、`test_eval_ci_gate.py:38-46` |
| 测试 | ~1298 passed / 5 skipped（有图口径）；114 个 `test_*.py`；`backend/app` 133 个 .py | `changes/P6-X2/integration-log.md:196` |
| 租户隔离 | RLS + 应用层常设防线 + 图谱侧；T1/T2 由 CI 在 PG 上跑 | G-26（15 条）/ G-9 / G-10 |
| 交付形态 | 交付 compose 全 `image:` 无 `build:`；离线 tar 473.53 MB（全包 ≈919MB）；`deploy/variants/` 2 个；`plugins/` 1 个真插件 | G-19（9 条）、`deploy/README.md:95-127` |
| License | Ed25519 验签 + 机器指纹 + 四维度判定 + 离线签发工具 + 公钥内置（无 env 覆盖） | `app/services/license/provider.py:181-213`、`policy.py:5-14` |
| 备份 / 恢复 / 安装验收 | `backup.py` / `restore.py` / `install_acceptance.py`（§10 十项全脚本化） | P6-W 已交付 |
| 恢复演练 | 已留证 **1 份** `docs/drills/restore-drill-20261013.md` | P6-X2（2026-10-13） |
| CI | 4 job（backend/frontend/contract/ci-summary）；backend 带 postgres:16 + neo4j:5.26 service 并起受限角色跑 | `.github/workflows/ci.yml:42,61-101,153-156` |

### 2.2 未到位

| 准入线 | 当前 | 阻塞原因 |
|---|---|---|
| **C1 图谱增益 ≥10%** | ✅ **0.142857**（graph 1.0000 / baseline 0.8750） | **已出数**（2026-10-13，判分 86/86 完成）。⚠️ 读数**绑定环境坐标** `git=101773e7` + 池指纹 `e36322bb2d86865f`；当前 HEAD 环境**不可复现**（P6-T-D4）⇒ 见 A8 / P7-K |
| **多跳答对率 ≥0.80** | ✅ **0.833333**（5/6，错 M-05） | 同上。⚠️ 该判据直接读 `gold-multihop-v1.json` 已存的 `correct` 出数（P6-T-D5）⇒ 环境漂移时**照样报 PASS**，已登记待堵 |
| **C2-a 召回 ≥0.80** | ✅ 1.0000（20/20），下界 0.8609 | ⚠️ 判据层 = **L1 算法层**，L2 端到端未做 ⇒ **不得对外宣称端到端达标** |
| **C2-b 误报 ≤0.15** | ✅ 0.0000（0/20），上界 0.1391 | 同上；余量仅 0.011，改动涉及疑点算法/语料**必须重跑** |
| **C2-c 引用覆盖 =1.00** | 🟡 排除拒答 1.00 / 含拒答 0.9 | 拒答误伤已由 P6-R（`temperature=0`）转 PASS |
| **C3-a 单位成本** | 7574.0000 token/doc `PASS(provisional)` | **TBD-7 阈值未由人裁决** ⇒ 不构成达标证据 |
| **C3-b 增量成本比** | 0.2727 `PASS` | 同上 |
| **升级 / 回滚演练** | **0 份留证** | 缺升级目标版本（须先 bump 到 1.7.0）；且**必须双人** |

---

## 3. A 类：卡死上线 gate 的任务

| # | 任务 | 现状 | 成本 | 谁来 |
|---|---|---|---|---|
| **A1** | **人工判分 86 题**（C1 双侧 80 + 多跳 6） | ✅ **86/86 完成**（2026-10-13，`wIlliam`） | ~~1~2 人天~~ 实际 ≈ 0.5 人天 | **只能人**（A3 纪律：脚本代判 = 假达标） |
| ~~A2~~ | ~~多跳答案导出通道~~ | ❌ **本次审计更正：不需要做** | 0 | — 判分视图已存在 `backend/data/eval/judging/multihop-view-20261009T083610Z.md`，且多跳走 `gold-multihop-v1.json` 的 `correct` 回落读，**不与 C1 题号串台**；原 P6-S 提出的待裁决项自动消解 |
| **A3** | **TBD-7 裁决**：`EVAL_SINGLE_DOC_TOKEN_CEILING`（现 32000 provisional） | 实测 7574；`--calibrate` 建议 9100 但 n=1 未采纳 | 0.1 人天（只需拍板） | **只能用户** |
| **A4** | **P6-Y：L2 端到端** | 未开工 | 2~4 人天 | AI |
| **A5** | **升级演练 + 回滚留证** | 0 份；死锁：需目标版本而现行版本是 1.6.0 | 1~2 人天 **+ 第二人半天** | **双人**（执行者 ≠ 见证者，AI 不得单独收口） |
| **A6** | **P8-Release 终审**：矩阵 §3.1/§3.4/§4/§5.1 逐行对账 + gate 三件套 + `v2.0.0` notes + tag | `docs/dev-doc-status.md:162` P3-1 仍 ⏳ | 2~3 人天 | 架构师 + 用户终审 |
| **A7** | **P6-X2 三项遗留缺陷** | 已裁决"合并进下一批" | 1~2 人天 | AI |
| **A8** | **评测可复现性**（P6-T-D4 / D5） | **本轮新发现、未开工** | 1~2 人天 | AI（涉及数据变更时需用户裁决） |

> **A8 明细**（当日实测，详见 `changes/P7-K/proposal.md`）：
> - **P6-T-D4**：请求显式带 `kg_version=attendance-demo-v1`，后端仍解析成 `20261012T064951Z-inc-569555ad` ⇒ 检索 0 证据 ⇒ 6/6 全拒答 ⇒ **C1 / 多跳在当前环境无法重跑复现**。
> - **P6-T-D5**：`runner.py:500` 让多跳判据直接读 gold 已存 `correct` 出数 ⇒ 环境漂移时照旧报 PASS（当日 canary：6/6 拒答仍报 `0.8333 PASS`）⇒ **这是个会掩盖问题的设计**。
> - **后果**：C1 目前是**一次性快照**，不加坐标引用即为失真；P8-Release 终审也无从复核。

**A7 明细**（`changes/P6-X2/integration-log.md:151-161`）：
- **F-P6X-7**：`restore.py::restore_neo4j` 只在容器 running 时 exec，而 `neo4j-admin load` 须停服 + `--from-path` 传宿主路径 ⇒ **图库恢复在当前架构下不可能成功**（备份侧已解，恢复侧未解）
- **F-P6X-8**：`install_acceptance.py` 无认证入口 ⇒ 目标环境第 6 项必 401 FAIL、第 7 项 SKIP；**是工具缺口，不是数据不足**（演练栈 `audit_log` 862 条 ≥7）
- **`ghost_version`**：PG active 版本 `20261012T064951Z-inc-569555ad` 在图库无镜像节点 ⇒ 恢复后 §6.2 必然 FAIL（历史镜像缺迁移脚本）

---

## 4. B 类：生产硬阻断（AI 可改，且应在演示给客户之前修完）

| # | 问题 | 证据 | 影响 | 批次 |
|---|---|---|---|---|
| **B1** | **dev 身份兜底未删除**：`Bearer dev.<org_id>.<actor_id>` + `X-Org-Id` 请求头仍生效；文件头自称「Sprint 1 临时实现」 | `backend/app/core/auth.py:1,8,10-15`、`app/core/config.py:400-406` | **可伪造任意租户身份**，直接绕开 P2-C 的 JWT 登录。**必须先核实生产配置下是否真被关闭** | **P7-C** |
| **B2** | **前端 Mock 静默回落**：`USE_MOCK=false` 时，**不在 `CONTRACT_COVERED_PATTERNS` 的端点仍返回 Mock** | `frontend/src/api/client.ts:75-78`；未登记端点 = `/cost/dashboard`、`/auth/login`、`/ontology/{active,confirm,cold-start}`、`/graph/versions/{v}/activate` | 客户看到假数据且**不报错** | **P7-D** |
| **B3** | **契约说谎（X-5）**：cost/ontology 路径 summary/description 仍写"占位骨架，恒返回 501"，实际已真实现 | `app/core/openapi.py:83-84,99`、`app/api/v1/routes/cost.py:55,62,76,83` | 客户按契约集成会写错；违反自身「契约同步铁律」 | **P7-D** |
| **B4** | **前端 Base URL build 期硬编码**：默认 `http://127.0.0.1:8000`，`NEXT_PUBLIC_*` 构建期内联；交付 compose CORS 写死 `127.0.0.1:3000` | `frontend/Dockerfile:20`、`deploy/docker-compose.delivery.yml:126` | 客户换域名/IP **必须重建镜像**，运行时改 env 无效 | **P7-E** |
| **B5** | **License 私钥仍在本机** `%USERPROFILE%\.graphrag-license\private.pem` | `changes/P6-Z/proposal.md:196,241-251` | P6-Z 已实证「换公钥 + 自签」四步可绕过机器绑定 ⇒ 私钥泄露 = License 体系失效 | **P7-J**（纯人工） |
| **B6** | **根 README 无部署章节**；release notes 停在 v1.6.0 | `README.md:7-24`、`docs/release-notes/` | 客户侧唯一安装文档是 `deploy/README.md` | **P7-E** |

---

## 5. C 类：遗留未收的登记项（有编号、有人登记、尚无人还）

| 编号 | 内容 | 出处 |
|---|---|---|
| **R22** | `question` 只参与**候选内重排**，不参与检索 ⇒ M3 §3 未闭环 | `docs/acceptance-traceability-matrix.md:52` |
| **R27** | 注入层 93%，挂起，触发条件在 P6-N | `changes/P6-S/new-session-prompt.md:248` |
| **R30** | 1 条跨租户授权引用 + 3 条随机 UUID `uploaded_by` + 2 条 `audit_log.actor_id`（演示库脏数据） | `changes/P6-P1/integration-log.md:112` |
| **X-3 / X-6 / X-7** | spec 口径偏离（成本 stage 列、`cost_ratio` 分母等） | 各属 P5-D / P6-V2 / P6-V3 |
| **F-P6W-3** | `.env.example` 的 `PRIVATE_DEPLOY_ENABLED` 仍 `false` | `changes/P6-W/integration-log.md:228` |
| **S9.13-2** | `human_review` 队列无读端点 | `changes/P6-S/new-session-prompt.md:249` |
| **H4 步骤 6** | 前端 `client.ts::request()` **只读不发** `X-Trace-Id` ⇒ 浏览器自然操作审计不聚合 | `docs/dev-doc-status.md:46` |
| **M5** | `alert` 表未建（有意 P2）；脱敏不覆盖日志 `message` 正文 | `docs/acceptance-traceability-matrix.md:175-176` |
| **M2** | `Citation.char_offset` 端到端未打通 | 同上 `:51` |
| **P6-R 遗留** | 钉 `temperature=0` 后**未真重入图**验证 gold 命中；"发布清单记录采样默认值"未落流程 | `changes/P6-R/integration-log.md:230,239` |
| **提示词** | `entity_relation_extract_v1.md` 无代码消费者（两套抽取模板其一悬空） | `docs/dev-doc-status.md:196` |

### 5.1 本次审计新查出的 5 处过期口径（**不改会让下一批照着错的排**）

| 位置 | 过期内容 | 应改为 |
|---|---|---|
| `docs/delivery-plan.md:268` | 队列第 13 项 **P6-V4 标「⏳未开工」** | V4/V5 已落地并出真值（7574 / 0.2727），队列状态须更新，**不得重做** |
| `docs/dev-doc-status.md:19-21` | §0 总览仍为 P1 完成 4/11、P2 0/3、P3 0/1 | 逐项复核后刷新（含 §2 P1-7 / P1-8 / P1-11 已实际落地） |
| `docs/acceptance-traceability-matrix.md:55`（M6 行） | 仍写「`/ontology/active`、`confirm`、`cold-start` 仍占位」 | ⚠️ **疑似过期**：`tests/test_ontology_placeholder_endpoints.py:47-56` 的 `PLACEHOLDERS` 列表已空 ⇒ **须机械复核后再改，不得凭本节下结论** |
| `changes/P6-W/integration-log.md:337` | 「全仓 `restore-drill-*.md` = 0 份」 | 已被 P6-X2 留证推翻（`docs/drills/restore-drill-20261013.md` 存在） |
| 缺陷编号冲突 | `F-P6X-1` / `F-P6X-3` 在 P6-Y2 与 P6-X2 里**各有一个含义** | 二选一重新编号（守 R-5：史实保留、活引用改指） |
| `changes/P7-C/proposal.md:35`（2026-10-13 新增，第 6 处） | 出口判据 3 写「`test_login_flow.py` **7 条**一条不降」 | 实测 **5 passed** ⇒ 判据照旧成立（不降），但条数口径过期；已登记 `F-P7C-4`，proposal 未改（史实保留） |

---

## 6. D 类：投入结构观察（事实陈述，供判断，不建议本期处置）

| 现象 | 读数 |
|---|---|
| **过程资产已超过产品资产** | `changes/` = 302 个 .md + 80 个 .py / 416 文件；`backend/app` 仅 133 个 .py |
| **评测子系统做得比产品重** | `app/evaluation/runner.py` 66KB + `baseline.py` 494 行 + ≥8 个评测脚本 + rubric 已迭代至 v2、判分表已到第 4 轮；P6-S 实测旧判分表图侧**仅 9/40 答案逐位一致** ⇒ 前几轮 80 道人工部分作废 |
| **商业化基建在零客户期已做到满配** | License Ed25519 + 离线签发工具 + 指纹 + 四维度 + variant 矩阵 + 插件机制 + 919MB 离线包——均为必需，但强度已到"可批量交付" |
| **交付物混进研发仓库** | `delivery-kit/`（docx/xlsx 对外资料包）已由 `637228f1` 入库 |
| **根级 5 个 MVP/PoC 目录仍在** | `temporal_poc/` `mineru_mvp/` `langextract_mvp/` `bridge_web_demo/` `langchain_mvp/` |

> **不建议删除任何一个**（见根 `CODEBUDDY.md`「不可删除清单」）。处置建议：交付打的是**镜像**，这些目录不进交付包即可，无需动源码树。

---

## 7. 执行队列（依赖顺序）

> 批次目录见 `changes/P7-C` ~ `changes/P7-K`、`changes/P8-Release`；每批 `proposal.md` 含 tempered Non-goals 与可贴机器输出的出口判据。
> **`P6-T`（A1 判分）已于 2026-10-13 完成 86/86**：`C1 = 0.142857`、`多跳 = 0.833333`，**F1 / F2 均未触发** —— 图谱路线站得住。

| 序 | 批次 | 覆盖项 | 依赖 | 出口判据要点 |
|---|---|---|---|---|
| **0** | **P6-T** ✅ 已完成 | A1 判分 86 题 | 无 | 两张独立判分表 + 多跳 `correct` 写回；读数 `C1=0.142857` / `多跳=0.833333`（绑定 `git=101773e7` + 池指纹 `e36322bb2d86865f`） |
| 1 | **P7-C** | B1 身份兜底 | 无 | 生产配置下 dev 兜底路径机械不可达 + 护栏用例钉住 + 既有登录用例不降 | **✅ 已交付（2026-10-13）**：`changes/P7-C/integration-log.md`。真相是**分叉**的——`X-Org-Id` 早关着、`Bearer dev.*` 全程开着（根因：交付 compose 从不注入 `APP_ENV` ⇒ `is_production=False`）；已收口到 `Settings.dev_identity_enabled` 一把开关，新增护栏 **G-27**（5 项，🟢 已生效，G 计数 15 → 16）。⚠️ **遗留 2 条**：F-P7C-1 交付栈仍以 `development` 运行（⇒ G-21 / 默认 JWT 密钥守卫在客户现场同样不生效）；F-P7C-2 dev 兜底**未删除**（只加开关）。🚩 **P6-T 后坐力 3 条红（F-P7C-5）需用户裁决**，见 P7-C 集成日志 §5 |
| 2 | **P7-D** | B2 + B3 | 无（可与 P7-C 串行） | 契约外端点不再静默回落 Mock；契约描述文本与实现一致；`gen:api` 无 diff | 🟢 **已交付（2026-10-13）**：`changes/P7-D/integration-log.md`。用户裁决①一致性检查落 `backend/tests`（不给 frontend 装测试框架）②8 条端点**全部纳管**、豁免清单为空 ⇒ 差集 **8 → 0**，孤儿 pattern 0；新增 `backend/tests/test_frontend_contract_coverage.py`（10 用例，CI **后端 job** 必跑），反向验证已证明能红（删一条 pattern ⇒ 测试点名该端点）。X-5 真源改 5 处：dev 兜底不再是「Sprint 3 必须移除」、ontology `active`/`confirm`/`cold-start` 改「**已实装 P5-C**」、cost tag 改「**已实装 P6-V**」、`cost.py` summary/description、X-Org-Id 与 501 描述。契约 paths 仍 **29** 未增删，契约里「必须移除」**26 → 0**。本地 pytest `1272 passed / 46 skipped / 0 failed`；双生成物幂等。🚩 **遗留 4 条**：F-P7D-1 注释层 4 处占位期口径（**不进契约**，按 §5.3 登记不改）；F-P7D-2 白名单里 `/agent/query` 写了两次（清理触 Non-goals 第 4 条）；F-P7D-3 `/auth/login` 与 `/cost/dashboard` **仍无 UI 消费方**（`app/` 下 14 个 `page.tsx` 里没有）⇒ 登记为已知 UI 缺口，本批只收机制不补页面；F-P7D-4 `deps.py` 另两处「Sprint 3」口径会落进契约，登记不改 |
| 3 | **P7-E** | B4 + B6 | 无 | 改 Base URL 不需重建镜像（有机械判据）；根 README 有可执行的部署章节 | 🟢 **已交付（2026-10-13）**：`changes/P7-E/integration-log.md`。**三层实现**：`frontend/entrypoint.sh`（每次启动把 env 写成 `public/env.js`）+ `layout.tsx` 的 `<Script strategy="beforeInteractive">` + `client.ts::runtimeApiBaseUrl()`（运行时 > 构建期 > 默认）。**真机对照**（同镜像 `docker run`，两个不同 env）：`/env.js` 分别返回 `127.0.0.1` 与 `192.168.10.77` ⇒ **未重建镜像**；**R18 未放松**：容器内 `grep NEXT_PUBLIC_USE_MOCK` ⇒ **零残留（退出码 1）**，该开关仍锁在构建期。CORS 由写死 JSON 改为 `${CORS_ALLOW_ORIGINS:-…}`，**默认值一字未放松**；两个变量已进 `.env.example`。根 README 新增「部署」章节（只指 `deploy/README.md` 一条路径）。**顺带 bump 1.7.0**（D9 裁决 b）：`config.py` + 4 处 compose/variants + release notes v1.7.0。🚩 **遗留 3 条**：F-P7E-1 bump 的隐藏真源是 `.env.example::APP_VERSION`（漏改 ⇒ 13 个测试红；本机 `.env` 不入库，不改会"本地红 CI 绿"）；F-P7E-2 **proposal 判据措辞有误**——`docker compose restart` **不会**应用新 env，能生效的是 `up -d`（recreate 容器，非镜像），已更正两份 README；F-P7E-3 `.env.development` 的 `APP_VERSION=1.1.0` 长期与默认值不一致，非本批造成、未动。⚠️ **验证限制**：3000 端口被在跑的演练栈占用 ⇒ 未用真实 delivery compose 端到端起栈；`install_acceptance.py` 只跑到 `--help`（无 dry-run 且会写数据），完整验收须在目标环境执行 |
| 4 | **P7-F** | A3 的落文档动作 | **用户先裁决阈值** | 仅回填、不改脚本擅自 take 值；Matrix C3 行同步 |
| 5 | **P7-G** | A7 三条遗留 | P7-C/D/E 已完成 | F-P6X-7 图库恢复真通；F-P6X-8 带认证；`ghost_version` 有迁移或显式豁免登记 | 🟢 **已交付（2026-10-13/14）**：`changes/P7-G/integration-log.md`。**① F-P6X-8**：`install_acceptance.py` 加 `--username/--password/--token`，凭据走 P7-N 已实装的 `POST /auth/login`（**不新造凭据流**）；有令牌时**只发 `Authorization`**、不叠 dev 头；登录失败退出码 2（不许"登录失败还照跑"）。**真机**（`APP_ENV=production` 后端）：无认证 **401** ／ dev 头 **401** ／ 真 token **200**；第 6 项 `FAIL 401` → **`PASS 100 条 trace`**，退出码 1 → 0。**② F-P6X-7**：`restore.py` 新增 `_neo4j_load_command`（与备份侧对称）：容器在跑 ⇒ 不发命令并说明；已停 ⇒ 一次性容器 `--volumes-from` + 挂载 dump 目录（`--from-path` 认的是**容器内**路径）。**端到端**（一次性容器，未动在跑的栈）：源库 2 节点 → dump **13673 字节** → 空目标库 → load → 起库数到 **2 节点**；拒绝分支拿**在跑的** drill 图库验过，未下任何命令。**③ ghost_version 按裁决 A 显式登记**：⚠️ 差点报错——两条测试注释写"恒判 ghost"，核到底发现 `sync_kg_version_mirror` 早在建图（`registry.py:840`）与增量（`incremental.py:314`）两处都接上且有测试钉着 ⇒ **幽灵只来自修复前的历史版本**；已把触发条件 / 后果（退出码 2 拒绝启动）/ 补偿办法写进 ghost message。🚩 **遗留 4 条**：F-P7G-1 第 7 项仍需第二个真实租户（与 F-P7N-2 同根）；F-P7G-2 备份侧 `NEO4J_DUMP_FILE` 硬编码 vs 可配库名（已加显式校验、根因未修）；**F-P7G-3：A 只是登记、不消除幽灵 ⇒ P7-H 之前须重跑建图/增量把 active 迁走，否则 §6.2 必 FAIL**；F-P7G-4 恢复要求容器已停（刻意不代劳停库）。本地 pytest `1272 passed / 46 skipped / 0 failed`；**CI run `38494943608`（②③）与 `38490476742`（①）四 job 全绿，后端 job `1311 passed / 7 skipped / 0 failed`**（本批无新增用例 ⇒ 与上批持平） |
| 6 | **P7-H** | A5 升级 + 回滚演练 | **先 bump 1.7.0**；P7-G（否则恢复后必 FAIL）；**第二见证者** | `docs/drills/upgrade-drill-*.md` 含回滚步骤与实证读数 |
| 7 | **P7-I** | A4 L2 端到端 | P6-T 出数后 | C2-a / C2-b 在端到端链路上的读数与 L1 层的差异登记清楚 |
| 8 | **P7-J** | B5 私钥处置 | 无 | 签发环境独立 + 本机私钥抹除，`git status` 无密钥入库痕迹 |
| **9** | **P7-K** | **A8 评测可复现性** | 无（越早越好） | 同一命令连跑两次答案**逐字一致**；池指纹不符 ⇒ `BLOCKED` + `value=null`；拒答/答案不匹配时**不再套用旧 `correct` 出数** | 🟡 **未开工，但修法已裁决（2026-10-13，wIlliam）**：选 **③ 独立评测环境（单独 org / 单独图库）**——最干净、彻底隔离增量版本干扰；① 动产品主链路（可能撞 P6-V5）与 ② 改演示库数据（牵动 86 题判分）**均不采用**。四项落地约束见 `changes/P7-K/proposal.md` §8 |
| **10** | **P7-L** | **P6-T 后坐力**：3 条既有断言过期（F-P7C-5） | 无（**当时唯一让 CI 后端 job 变红的东西**） | `pytest` 本地 0 failed；三条用例**原意图仍在**（L1 缺判分须吐原文 / L2 判分须非匿名 / L3 题行不得含 `correct`）；CI 四 job 全绿 | 🟢 **已收口（2026-10-13，CI 已确认）**：只改断言，3 文件 / +42 −3，产品代码与 P6-T 数据零改动。本地 `1262 passed / 46 skipped / 0 failed`（基线 1259+3 ⇒ 总数未降）；反向验证 8/8 证明新断言仍能被**打红**（含题行 `correct` / 匿名判分 / 半本判分）。L2 由「判分须存在」**加严**为「判分若存在则须署名」。详见 `changes/P7-L/integration-log.md`；CI run `38381092471` 后端 job `1301 passed / 7 skipped / 0 failed`，四 job 全绿。工具缺口见 F-P7L-1 |
| 11 | **P8-Release** | A6 终审 | 0~10 全完成 | 零缺口：`check_startup_readiness.py` 全 🟢；C1~C3 / 多跳 / 拒答全达标且不触发 F1~F5 |
| 12 | **P7-M** | **P7-D 遗留**：过期文案收尾（F-P7D-1 注释层 + F-P7D-4 落契约） | P7-D 完成后 | 7 条过期话改成实话且每条能指到 commit；未兑现承诺口径计数 = 0；双生成物幂等 | 🟢 **已交付（2026-10-13）**：`changes/P7-M/integration-log.md`。7 条全改（router.py M1-M3、schemas/cost.py M4、schemas/ontology.py M5、deps.py **落契约** M6-M7），契约 paths 仍 **29**；「Sprint 3 起由…提供/取代」类未兑现承诺 **2 → 0**，`X-Org-Id` 之外的 dev 兜底口径写清受 G-27 约束。本地 pytest `1272 passed / 46 skipped / 0 failed`（未降）；**CI run `38391401636` 四 job 全绿，后端 job `1311 passed / 7 skipped / 0 failed`**（本批无新增用例 ⇒ 计数与上批持平）。⚠️ **本批自我纠偏一处**：M7 第一版误写「认证态至今未提供 actor」，靠 `core/auth.py:103`（`actor_id=claims.user_id`）推翻 ⇒ 登记为教训。🚩 遗留 F-P7M-1：`AgentQueryResponse` 的历史沿革陈述（"Sprint 4 阶段 10.0 批次 A 扩展（Sprint 3 缺口 1 偿还）"）是**已发生事实**，保留不改 ⇒ 机械判据不可写成「见 Sprint 3 就红」 |
| 13 | **P7-N** | **前端登录链路**（P7-D 遗留 F-P7D-3 升级项） | P7-E 完成后优先 | 客户能用真账号登录；`Authorization: Bearer` 真发出；`users.activated_at` 有来源（席位计数） | 🟢 **已交付（2026-10-13）**：**性质不是"UI 缺口"而是交付阻塞**：后端 `POST /auth/login` 早已真实现（P2-C），而前端**无登录页 / 无 token 存储 / 无 `Authorization` 头**，P7-C 又把 dev token / dev header 收口为生产不可达（G-27）⇒ 生产环境里前端**没有任何身份入口**。**用户裁决**：token 走 `Authorization` 头 + `sessionStorage`（契约已把 JWT 携带方式写死为 Bearer；改 HttpOnly cookie 要动后端响应 + CSRF 防护，属改后端行为 ⇒ 越界）。`changes/P7-N/integration-log.md`。**五个新文件**：`api/session.ts`（存储 + `AUTH_REQUIRED`）、`api/auth.ts`（login / startSession / logout）、`components/auth/` 下 `use-session.ts` / `auth-gate.tsx` / `login-form.tsx`；`client.ts` 挂 `Authorization: Bearer` 且 401 一律清会话（**不做静默重试**）；`AuthGate` 套在 `AppShell` **外层**（未登录时不渲染侧栏）。**真机读数**：后端登录成功 `token_len=279`，`/api/v1/documents` 不带 token **401** ／ 带 token **200**（注意 `license/status` 是公开端点，不带 token 也 200 ⇒ 拿它验证会得到假结论）；同一份代码 production 形态 SSR **44410 → 10359** 字节且侧栏标记消失、development 形态 **47233** 字节侧栏仍在 ⇒ **生产拦住、dev 不受影响**。顺带：借改动 `client.ts` 清掉 **F-P7D-2**（重复 pattern），并把顶栏硬编码的「林默 · 管理员」+ 点了没反应的「退出登录」接上真会话（dev 形态显示「开发态」，不冒充具体的人）。本地 pytest `1272 passed / 46 skipped / 0 failed`；`test_frontend_contract_coverage.py` 仍 **10 passed**（本批删了一条重复 pattern，它第一次有机会红、没红）。🚩 **遗留 5 条**：F-P7N-1 **CSR 交互未被机械验证**（前端无测试框架是 P7-D 的裁决 ⇒ hydration 后的表单渲染、`Authorization` 是否真发出，**必须由浏览器确认**，已附四步手工清单）；F-P7N-2 首账号仍是**交付前提**（已裁决推迟到 P7-H 之前，方案占位 (a)，变量是客户是否接外部身份源）；F-P7N-3 顶栏「个人资料 / 偏好设置」仍占位且点击无反应；F-P7N-4 token 过期无 refresh 端点 ⇒ 直接回登录态；F-P7N-5 顶栏**不显示角色**（真角色由后端 `user_roles` 判定，前端无端点 ⇒ 不猜） |

---

## 8. 成本估算

| 档位 | 内容 | 人天 | 可对外口径 |
|---|---|---|---|
| **D0 最小可售（试点）** | B1~B6 + A1 判分 + A3 裁决 | **6~9 人天** | 可签**试点合同**（我方工程师现场实施 + `install_acceptance.py --out` 出十项报告）；C1 / 多跳**已出数**，但**必须带环境坐标引用**（`git=101773e7` + 池指纹 `e36322bb2d86865f`），且在 P7-K 修好可复现性前**不得写成"可复核的达标"** |
| **D1 GA（v2.0.0 零缺口）** | D0 + A4 + A5 + A6 + 口径清理 | **+8~15 人天** | 含必须双人到场的半天 |
| **D2 面向大型企业** | D1 + SSO/AD 真机（Keycloak + Samba AD DC） | **+10~20 人天** | 既定窗口 **v2.1.0**；风险 R8：SSO 不进 MVP ⇒ v2.0.0 对企业客户不可交付 |

**到可推广销售 ≈ 15~25 人天（D1）**，外加 LLM 费用约 ¥10~50 量级（重跑 C2-a/C2-b 与 L2）。

---

## 9. 熔断提示（判分前必须知道）

| 熔断 | 触发条件 | 后果 |
|---|---|---|
| **F1** | 图谱相对 RAG 增益 **< 10%** | **退回 RAG-first 产品形态，从路线图移除图谱依赖** |
| **F2** | 多跳答对率 **< 0.80** | **暂缓图谱化投入**，优先补抽取与实体消解质量 |
| **F3** | 引用覆盖率 < 100% | **直接 NO-GO**（不可降级） |
| **F4** | 单位成本无法收敛 | 降级为"仅解析 + 结构化抽取"轻量产品 |

> 出处：`docs/acceptance-traceability-matrix.md:220-224`。
> 这就是为什么 **A1（判分）必须排在最前**：一旦 F1 触发，A4/A5/A6 全白做；而它是最便宜的一项。
