# 下一批开工提示词：P7-E（前端 Base URL 运行时可配 + 根 README 部署章节）

> 本文件是 **P7-D 批次目录下、写给下一批（P7-E）** 的开场提示词（2026-10-13 立）。
> 落地原因：对话上下文会丢，仓库不会。开工前**先读本文件**，再读 `changes/P7-E/proposal.md`。
> ⚠️ 本文件里的「已查证坐标」是**机械核实过的事实**，其中 **4 处与 proposal 的口径不一致**
> （见 §4 的 D2 / D3 / D4 / D9）——动工前先把那四条读完，别照 proposal 的乐观估计开工。

---

## 1. 确认起点：从 `P7-E` 开始

**执行模式**：AI 主体（改代码 + 跑命令 + 回登），**不需要**第二自然人。
但见 §5：**三项**必须先在任何代码改动之前处理——其中一项（D9 镜像 tag 耦合）属于 §10-① 的升级用户情形。

**为什么是它——三条机械理由**：

1. **它是执行队列的下一个未开工项，且卡着别人**：`docs/release-readiness-audit-2026-10-13.md` §7 的序 3，
   依赖列写「无（可与 P7-C 串行）」；而**序 5 的 P7-G 依赖是「P7-C/D/E 已完成」** ⇒ P7-E 不完成，P7-G 动不了。
2. **P7-D 已经把 CI 变成一个干净窗口**：CI run `38386715267` 四 job 全绿 ⇒ 任何红都能归因到本批。
3. **它是 B4 + B6 两条未决客户可见缺陷的唯一落点**：客户换域名要**重建镜像**（B4）、根 README **没有部署章节**（B6）。
   这两件事都在"能不能交付给客户"这条线上，不是打磨项。

---

## 2. 开工自检（**动手前先跑，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py   # 必须 🟢 16 条 / 🟠 0 / 🟡 0
git fetch -q && git log --oneline origin/HEAD..HEAD               # 必须空（无未推送提交）
git status --short                                                # 必须干净
cd backend && uv run python scripts/export_openapi.py --check     # 必须零 diff
cd frontend && npm run gen:api && git -C .. diff --exit-code -- frontend/src/types/api.d.ts
uv run pytest tests/test_frontend_contract_coverage.py -q         # 必须 10 passed（P7-D 新护栏）
```

⚠️ **别信 `check_session_drift.py` 的 S1**（F-P7L-1 同款病，本批会再犯一次）：它**按目录 mtime 猜当前批次**。
本文件一提交，`changes/P7-D/` 的 mtime 就最新 ⇒ S1 会报 **P7-D 的 5 条边界**，而正确的边界是 P7-E 的。
请以 `changes/P7-E/proposal.md` §3 为准手工对照。

然后**重跑 §4 里带命令的那几条**（D3 的 `cors_allow_origins`、D9 的 image tag）——
下面这张表是我在 `7170db0` 上实测的，换一行代码就得重新数，不许直接抄。

---

## 3. 边界纪律（**Non-goals 5 条**，原样照搬 `changes/P7-E/proposal.md` §3）

1. **不做反向代理 / HTTPS 证书 / 域名方案**（那是客户现场运维）。
2. **不放宽端口绑定纪律**（后端继续只绑回环）。
3. **不改 `docker-compose.delivery.yml` 的 `image:` 无 `build:` 纪律**（G-19 在盯，碰了必红）。
4. **不重写 `deploy/README.md`**（只做最小增量；它是客户侧唯一文档，重写风险高于收益）。
5. **不做多实例 / 集群编排**。

---

## 4. 已查证坐标表（2026-10-13 在 `7170db0` 上机械核实）

| # | 坐标 | 事实（**★ = 与 proposal 口径不一致**） |
|---|---|---|
| **D1** | `frontend/Dockerfile:17-23` | 三个 `NEXT_PUBLIC_*` 以 **ARG → ENV** 注入，**只在 build stage**；runtime stage（`:27-41`）**无 environment 段**、也没有 entrypoint ⇒ 运行时改 env 确实无效，B4 的病根成立。⇒ 改动时注意：`:5-7` 那段注释已经把「build 时内联」写成了纪律，改 Dockerfile 要连带改注释，
别留下自相矛盾的 Dockerfile |
| **D2** | ★ `frontend/package.json` `"next": "16.3.5"`，`src/app/` 存在（= **App Router**） | proposal §2.1 的三选一里，**`serverRuntimeConfig` 这条候选是死的**：它在 App Router 下不受支持 ⇒ **只剩两个候选**：① runtime stage 加 entrypoint 生成 `env.js` + 页面 `<Script>` 注入 `window.__ENV`；② 容器内反向代理代注入（要新增 nginx 依赖）。其余选项别浪费时间评估 |
| **D3** | ★ `backend/app/core/config.py:235` `cors_allow_origins`；`deploy/docker-compose.delivery.yml:126` | **CORS 机制早就可配**（`Settings.cors_allow_origins` 存在，compose 也是用 `CORS_ALLOW_ORIGINS` 注入的），**只是值被写死**成 `'["http://127.0.0.1:3000","http://localhost:3000"]'` ⇒ proposal §2.2 说「CORS 改为可配置」的**工量比字面小**：把字符串换成 `${FRONTEND_ORIGINS:-'[...原值...]'}` 即可，**默认值不许放松**（Non-goals 2 / proposal §2.2 后半句）。compose 里已有 `${APP_RLS_PASSWORD}`、`${NEO4J_PASSWORD}` 同款语法 ⇒ 语法可行 |
| **D4** | ★ `backend/app/core/config.py:131` `app_version = "1.6.0"`；`docs/release-notes/` 最新为 `v1.6.0.md` | audit §4 **B6 同时挂了「release notes 停在 v1.6.0」**，但**两者版本号是一致的** ⇒ 这里**当前不是缺口**，是 audit 用「停在」这个词造成的错觉。真正的缺口在 bump 之后才会出现（**P7-H 要先 bump 1.7.0**）⇒ 本批**只需做根 README 部署章节**这一件事，release notes 建议登记给 bump 之后的那批，**别在本批提前补 v1.7.0 notes**（那时连版本内容都还没定） |
| **D5** | `backend/scripts/install_acceptance.py` | 存在 ⇒ proposal §2.3 要求的「验收命令」有了可引用的真入口，README 里写它而不是编命令 |
| **D6** | `README.md` 一级/二级标题：`L1` 项目名、`L7` 项目状态与文档入口、`L24` 技术栈、`L36` 目录速查表、`L76` 开发约定、`L90` 开发环境（`L96` 后端 / `L99` 前端） | **确无部署章节** ✅ B6 的 README 部分成立。插入点建议：`L90 开发环境` 之后、或 `L36 目录速查表` 里加一行指向 `deploy/README.md`（最终自己在簿上选一处，别两处都写） |
| **D7** | 本机 Docker `Server.Version=29.7.2`，现有 `graphrag-drill-{frontend,backend,postgres,neo4j}-1`、`graphrag-neo` 在跑 | Docker 可用 ⇒ proposal §4.1 的机械判据（改 Base URL 后 **`docker compose restart` 生效**）**有可能真跑**。但它是**分钟级到十几分钟级**的真实镜像构建，不是 pytest 能替代的守卫 ⇒ 把它当成**一批真人执行的操作**，别指望 CI 替你验（CI 里没有 compose stack） |
| **D8** | ⚠️ `frontend/Dockerfile:5-7` 的 **R18 红线** | `NEXT_PUBLIC_USE_MOCK=false` **必须在 build 期注入**。本批做「运行时可配」时，**只允许 `API_BASE_URL` 走运行时** —— 若顺手把 `USE_MOCK` 也做成运行时可变 ⇒ 客户现场可自行打开假数据开关，直接违反 R18（Dockerfile 注释里那段「静默走 Mock」就是讲这个）。这是本批最容易踩的坑 |
| **D9** | ★ `deploy/docker-compose.delivery.yml:177` `image: graphrag-agent/frontend:1.6.0`；`app_version=1.6.0`；`backend/scripts/build_delivery_images.py` 写死 build-arg | audit 说 P7-E「依赖：无」，但这里有**一条隐藏耦合**：本批要改 **frontend 镜像内容**（Dockerfile + runtime 阶段），而 G-19 要求 **own image tag == `app_version`** ⇒ 同 tag（1.6.0）装不同内容 ⇒ 缓存命中旧镜像 / 不可复现。要破除就得 **bump 到 1.7.0**，而 **P7-H 的开工前提正是「先 bump 1.7.0」** ⇒ 本批可能提前动 P7-H 的开关。**这条没裁决前不许动 Dockerfile 的 tag** |

---

## 5. 决策表（**两项已由上面 §4 收窄，第三项要走 §10-①**）

| 决策 | 结论 |
|---|---|
| 边界 | Non-goals 5 条见 §3，**改一条都要先回来登记理由** |
| 运行时注入**怎么做** | 三选一已被 D2 机械砍到两选一 ⇒ **推荐 ① entrypoint 生成 `env.js` + `<Script>` 注入**（零新增运行时依赖，符合 §5 第 2 条"前端依赖应克制"）；选 ② nginx 要先拿下依赖批准 |
| **`USE_MOCK` 不许跟着走运行时** | 已由 **D8 / R18** 定死：**不许**。只有 Base URL 走运行时 |
| CORS 怎么改 | 已由 **D3** 收窄：把 compose 里那个写死的字符串换成带默认值的变量插值，**默认值不动** |
| **bump 1.7.0 与 P7-H 的耦合**（D9） | ✅ **已裁决（2026-10-13，wIlliam 采纳建议）→ 选 (b)**：顺带 **bump 1.7.0**，把 bump 连同 P7-E 一起做掉（P7-H 的前提本来就是 bump，提前做不算浪费）。执行时同时落到：`config.py:131 app_version`、交付 compose 的 own image tags、必要时的 release notes。（a）「同 tag 不同内容」不可接受：一旦有人从 registry 拉 1.6.0 就拿到旧内容，与 G-19「交付物可版本追溯」冲突 |
| B6 的 release notes 部分 | 建议按 **D4** 判为"当前非缺口"，登记给 bump 之后那批；**本批不补 v1.7.0 notes** |

---

## 6. 已完成项（不要重做）

- **P6-T**：86/86 判分，`C1=0.142857` / 多跳 `0.833333`，F1/F2 未触发。
- **P7-C**：dev 兜底收口 + 护栏 **G-27**（G 计数 15 → 16）。
- **P7-L**：P6-T 后坐力 3 条断言收口（`409dc36`），CI 已绿。
- **P7-D**（上一批，2026-10-13 完成，commit `0c2b0d9` + `7170db0`）：8 条契约端点纳管 ⇒ 差集 **8 → 0**；
  新增 `backend/tests/test_frontend_contract_coverage.py`（10 用例，**CI 后端 job** 跑）；X-5 五处契约文案真源改成实话。
  ⚠️ **本批若要动 `frontend/src/api/client.ts`（读 `window.__ENV` 大概率要动它），改完必跑那个测试文件**——
  它按正文抠 `CONTRACT_COVERED_PATTERNS` 数组，动了结构它会红。
- **P7-K**：修法 ③ 独立评测环境已裁决，未开工（本批不碰）。

---

## 7. 基线（**只能往好不能往坏**）

| 项 | 读数 |
|---|---|
| HEAD | **`7170db0`**（✅ 已推送；工作区干净） |
| CI | run **`38386715267`**：后端 ✅ / 前端 ✅ / 契约 ✅ / 汇总 ✅ |
| CI 后端 pytest | `1311 passed / 7 skipped / 0 failed` |
| 本地 `uv run pytest -q` | `1272 passed / 46 skipped / 0 failed`（本地 vs CI 差在 skip 数，见 P7-D 集成日志 §7） |
| `check_startup_readiness.py` | 🟢 **16 条** ｜🟠 0 ｜🟡 0 |
| `ruff check` / `ruff format --check` | All checks passed / 299 files formatted |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 |
| `export_openapi.py --check` | 零 diff ｜`api.d.ts` 幂等（暂存后再生成无 diff） |

---

## 8. 验收判据（**每条都要能贴机器输出**）

1. **Base URL 真能 runtime 生效**：贴出同一份 compose 上 `restart`（**不是 rebuild**）前后、
   前端实际请求的 API 地址变了的实际证据（容器日志 / 页面请求 URL / health 探针输出，任选但必须可读）。
2. **`USE_MOCK` 没有跟着变成运行时可改**：显式验证——容器运行时改 `NEXT_PUBLIC_USE_MOCK` ⇒ **行为不变**（D8）。
3. **门槛教育不退化**：`test_g19_*`、`test_g26_7_deploy_compose_uses_restricted_db_role`、
   `tests/test_frontend_contract_coverage.py` 全绿；`check_seams.py` ERROR 0。
4. **README 的每条命令都跑过**：贴关键节点输出。`deploy/README.md` 只做最小增量（Non-goals 4）。
5. **push 后 CI 四 job 全绿**（R-10）。

---

## 9. 提交推送纪律

- 一个批次一个 `proposal.md` + 一个 `integration-log.md`；**不得跨批次扩范围**。
- 本批跨 `frontend/`、`deploy/`、`docs/`、`README.md` ⇒ 按角色隔离逐处改；
  **若动了 Dockerfile 又要动 compose / app_version（D9 的情形 b），必须落在同一次提交**（否则中间那个 commit 必红）。
- 提交前本地三件套 + `pytest` + 前端 `lint` / `typecheck` / `gen:api`；**推送后以 CI 为最终裁决**（R-10）。
- 本批收尾：更新 `docs/release-readiness-audit-2026-10-13.md` §7 的 P7-E 行状态，
  **并顺带解锁提示**（P7-G 依赖 P7-C/D/E ⇒ 本批完成后 P7-G 才真正解锁）。

---

## 10. 升级用户的四种情况

1. ~~要做判定动作却没有授权~~ **D9 已裁决为 (b)**（见 §5），不用再升级。
   但仍需在动 `app_version` 之前确认一件事：**release notes v1.7.0 现在写还是等 P7-H**
   ——本文倾向"bump 时就补一版 notes"，内容至少覆盖本次 Base URL 运行时化。
2. **三方案都不可行 / 必须重建镜像** ⇒ 停下报告（proposal §5.1：商业影响里"现场改域名要重建"= 不可接受）。
3. **需要新增前端依赖或 nginx 组件** ⇒ 报告后等批准（前端依赖应克制）。
4. **CI 红且复核两遍仍红** ⇒ 带 job 名 + 失败行 + 归因。

---

## 11. 不许外推

- **"改了 Dockerfile" ≠ "客户能换域名了"**：D7 那条 restart 实验**必须真跑**；没贴前后读数就宣称完成，
  等于把"看起来改好了"当成"验过了"。
- **别顺手把 `USE_MOCK`、端口绑定、CORS 默认值一起放松**（D8 / Non-goals 2）：每一处放松都是在拆别人的护栏，
  而且症状都是"看起来能跑"。
- **写了 README ≠ 客户能装起来**：proposal §4.3 要求每条命令亲自跑过；跑不通的那条路径就不许写进去。
- **bump 版本是别批的开关**：不在用户裁决前动 `app_version` / image tag。

---

## 12. 下一批指针

**P7-E 完成后**：按审计 §7 队列，剩 `P7-F`（A3 阈值回填，**用户先裁决阈值**，序 4）、
`P7-G`（A7 三条遗留，依赖 **P7-C/D/E** ⇒ 本批完成后解锁）、`P7-H`（A5 升级 + 回滚演练，**先 bump 1.7.0 + 第二见证者**；
注意 D9：bump 若在本批提前发生，这里的开工条件要跟着改）、`P7-I`（A4 L2 端到端）、
`P7-J`（B5 私钥处置，**纯人工**）、`P7-K`（A8，修法 ③ 已裁决）、`P8-Release`（A6 终审，需 0~10 全完成）。

⚠️ 开工前**重跑** §2 的自检与 §4 里带命令的那几条——文档会过期，脚本不会。
