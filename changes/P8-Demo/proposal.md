# P8-Demo · 演示可用性收口（把"起得来"变成"演得下去"）

> **日期**：2026-10-29 ｜ **分支**：`main` ｜ **基线**：`e87846b`（2026-10-15，P8-Release 路 B 裁决）
> **一句话**：本机唯一在跑的栈是**演示数据齐全但用不了**的 `graphrag-drill`（镜像 1.6.0）；
> 本批把它救到**可完整演示**的状态，并用机械彩排取证。
> ⚠️ **本批是"演示线"，不是"交付终审线"** —— P8-Release 的 7 项前置与路 B 落地 4 项**不在本批**。

---

## 1. 为什么做（2026-10-29 真机读数，非文档推断）

| # | 事实 | 读数 / 证据 |
|---|---|---|
| 1 | **无账号 ⇒ 全站 401** | 演练库 `users` = **0 行**；带 `X-Org-Id` 请求业务端点 = `401 UNAUTHORIZED`（`dev_fallback_enabled: false`）；`POST /auth/login` 活着但返回 `invalid_credentials` |
| 2 | **默认 active 图谱是垃圾版本** | `kg_versions` 5 个全 `ready`，latest = `20261012T064951Z-inc-569555ad`（**5 实体 / 0 文档**）；6 篇文档挂在 `attendance-demo-v1`（2855 实体）⇒ 不激活则概览 `doc=0`、问答必拒答 |
| 3 | **疑点页必空** | `affiliation_suspicions` = **0 行** |
| 4 | **演示栈没有 LLM 凭据** | 容器内 `printenv` 无 `LLM_*` ⇒ 问答步骤无凭据 |
| 5 | **彩排脚本已失效** | `scripts/demo_rehearsal.py:119-125` 只发 `X-Org-Id` / `X-Actor-Id` / `X-Trace-Id`，**不发 JWT**；自 2026-09-28（Sprint9.6 `PASS 10/FAIL 0`）后未再跑过，其间经历 PG 切换 / RLS / 登录 / License 四次架构变更 |
| 6 | **镜像 1.6.0 有"Mock 静默回落"风险** | 1.7.0 的 P7-D（B2/B3）修的正是「`USE_MOCK=false` 时白名单外端点仍返回 Mock 且不报错」⇒ **演示必须用 1.7.0**。`graphrag-agent/{backend,frontend}:1.7.0` 镜像**已存在**，无需重建 |

## 2. 做什么

| 序 | 动作 | 出口判据 |
|---|---|---|
| 1 | 用 **override**（不改原 drill compose，那是演练留证）把栈换到 **1.7.0 镜像**并注入 LLM 凭据，复用同一批数据卷 | `docker compose ps` 四服务 healthy；`GET /health` = **1.7.0**；`documents` 仍 **7** |
| 2 | 播种演示账号（容器内 `seed_dev_rbac.py --password=…`；`app_rls` 受 RLS 约束 ⇒ 必要时用 owner 串） | `users` 0 → **1**；`POST /auth/login` 返回 token |
| 3 | 激活 `attendance-demo-v1` | `GET /graph/overview` 的 `doc_count` / `entity_count` **非 0** |
| 4 | 跑一次 detect 出疑点 | `affiliation_suspicions` 0 → **≥1** |
| 5 | `demo_rehearsal.py` 支持 JWT（`--username` / `--password`） | 旧路径（纯 dev 头）在关兜底的栈上必红，新路径取到 token |
| 6 | 完整彩排（含真实 LLM 一次） | `--domain attendance --with-llm --frontend-base http://127.0.0.1:3000` ⇒ **FAIL 0** |
| 7 | 打 tag `v1.7.0` | `git ls-remote --tags` 可核 |

## 3. 不做（Non-goals）

1. **不改产品代码**（唯一例外：`demo_rehearsal.py` 的鉴权适配，它是 `scripts/` 下的彩排工具）；
2. **不改契约**（⇒ 无 `gen:api` 漂移）；
3. **不重建镜像**（1.7.0 已存在）；
4. **不做 P8-Release 终审**：P7-I（L2 端到端）/ 审计 §5.1 剩 2 条 / 路 B 的语义判据口径 / 重判 P6-T 真值 —— **全部不在本批**；
5. **不灌新语料、不重建图谱**（沿用 `attendance-demo-v1`，灌数据要烧 MinerU + LLM 且不可逆）；
6. **不动 `docker-compose.drill-20261013.yml`**（P7-H / 恢复演练留证，改它 = 毁证据）；
7. **不补 `affiliation-demo-v2` 的文档与图谱**（演示走考勤域；关联方域只跑到"疑点非空"这一步）；
8. **不修 R22**（`question` 参与检索）—— 属检索设计变更；
9. **不动前端代码**；
10. **不做批次归档 / 文档大盘同步**（收尾另立）。

## 4. 验收

- [ ] `/health` = 1.7.0 且四服务 healthy，数据未丢（documents 7）
- [ ] 登录取到 JWT；带 JWT 的业务端点不再 401
- [ ] `/graph/overview` 统计非 0
- [ ] 疑点 ≥ 1 条
- [ ] 彩排 **FAIL 0**（含真实 LLM 与前端两页 200）
- [ ] `pytest` / `ruff` / 契约零漂移 无回归（改脚本后必跑）

## 5. 升级用户的四种情况

1. 换镜像后数据卷不复用 / 数据丢失 ⇒ **立刻停**（演示数据不可重建）；
2. 播种账号被 RLS 挡住且 owner 路径也不通 ⇒ 停，报告具体报错；
3. 激活 `attendance-demo-v1` 会同步 Neo4j 镜像、耗时或失败 ⇒ 停；
4. 需要烧 LLM 费用的动作（彩排 `--with-llm`）⇒ **先报费用量级再跑**。
