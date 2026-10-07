# 新会话开场提示词 · P5-D（D1 第一批：私域出向管控 `PRIVATE_DEPLOY` + 内网双轨可切换）

> 🔒 **执行模式：无人值守**（技能 `unattended-sprint-execution`，用户已预授权）—— **不索过程性确认**，
> 只在 §10 列的四类升级边界停下找我。详见 §1。
>
> 📦 **本文件自包含**：前一个会话（P5-C）已收口（`main` = `14cde49d`，CI run `37616440691` 四 job 全绿）、
> 不会再回来。开工所需的**全部**坐标、命令、基线、陷阱都在本文里。唯一需要你额外读的是 §0.5 列的
> **五份仓库内文件**（都在库里，`git pull` 后可读）。
>
> ✅ **范围已由用户确认（2026-10-07）**：按 §2.1 的三条机械理由把 **D1 排在 M6 第二批之前**，
> 采纳 §2.4 的三刀切法。本文件可直接作为新会话第一条消息。
>
> 复制本文件**全文**到新会话作为第一条消息。

---

## 0. 本批一句话

**把 M5 §3 验收 4 / §4.6 的「私域出向管控」从零做成真的**：落
`PRIVATE_DEPLOY_ENABLED` + `ALLOWED_EGRESS_HOSTS` 两个配置、一个**构造期**出向守卫、
一个 503 `PRIVATE_DEPLOY_BLOCKED` 错误码 + 一条 `private_deploy.violation` 审计行，
并让**内网双轨**（本地 vLLM / Ollama = 只换 `base_url`）**不被自己的守卫误杀**。

**不做**的三件事（详见 §4）：`alert` 表与限流告警联动（M5 §3 验收 5 标 **P2**）、
M6 剩余三件（merge/split/rename、成本仪表盘、校正 GUI）、M5 其它验收条的"顺手补"。

---

## 0.5 开工前必读（五份文件）

| 顺序 | 文件 | 为什么必须读 |
|---|---|---|
| 1 | **`changes/P5-C/integration-log.md`** | 上一批实录。**重点 §7（四条偏离 X-2a/b/c + B-1 已裁决保留）**、§8.3 CI、§11 指针 |
| 2 | **`changes/P5-B/env-restore-checklist.md`** | ⚠️ **先按它的 §0 判断本地环境缺什么**，别到一半才发现 403 / 没有库。含可复制命令 |
| 3 | **`specs/m5-permission-audit.md`** | **v1.0 已定稿**（M5 MVP 已交付）。重点 §3 **验收 4（`:49`）**、**§4.6 配置表（`:152-157`）**、§4.4 `audit_log` 表结构（`:121-135`） |
| 4 | **`backend/app/services/providers/llm.py`（54 行）** | LLM 的**唯一**构造点（也是 `settings.llm_provider` 的唯一消费点）⇒ 守卫的首选落点；模块头已写明「内网双轨不新增档位」 |
| 5 | **`backend/app/core/errors.py`** | 新增一个错误码要动**四处**字典（见 §6 坐标表），漏一处 `export_openapi.py` 直接 KeyError |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

**替代真源映射**（沿用 P5-A/B/C 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（文件**已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-D/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | 照做。本批**预期必改契约**（新增 `ErrorCode` 会被注入 `ErrorCode.enum`），**这不是升级**，按 §5 **D2** 走完同步五步即可 |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

**角色隔离**：

| 段 | 角色 | 允许改的范围 |
|---|---|---|
| 配置 + 守卫 + 错误码 + 后端测试 | **后端开发 B** | **只允许** `backend/` + 跑脚本 |
| 契约与前端生成物**再生** | 仍是 B（**不写前端业务代码**） | 只允许 `contracts/openapi.yaml`（导出产物）与 `frontend/src/types/api.d.ts`（`npm run gen:api` 产物），见 §5 D2 |

**分支**：沿用 P4 / P2-C / P5-B / P5-C 的实际做法 —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是 P5-D / 为什么是这一刀

### 2.1 三条机械理由

1. **排期队列指向它**：`docs/delivery-plan.md:198` 原文明写 P5 的顺序是
   `D4 → **D2 M6** → **D1** → D3/D5/D7/D8`。**D4 已由 P5-B 收口**（2026-10-07）、
   **D2 已由 P5-C 开出第一批**（三个端点真实现）⇒ 队列的自然下一项是 **D1**。
2. **D1 是零代码，不存在"实现了一半"的风险**：`grep -r PRIVATE_DEPLOY backend/` **零命中**
   —— `config.py` 无这两个字段、`errors.py` 无 `PRIVATE_DEPLOY_BLOCKED`、守卫零存在。
   对比 M6：那边还有 PoC / 占位骨架要先拆。
3. **它有已定稿的 spec，没有闸门要等**：`specs/m5-permission-audit.md` **v1.0**
   （头部写明「v1.0.0 已交付」），§3 验收 4 与 §4.6 配置表都是可直接照写的口径。
   ⇒ 不需要"先升 spec 再动工"（那是 §10 第 2 类升级的事，本批不触发）。

### 2.2 为什么**不是** M6 第二批

三件各有未落地的前置，**凑在一起就是本批最典型的"摊太大"**：

| M6 剩余 | 卡在哪 | 归属 |
|---|---|---|
| `merge` / `split` / `rename` | 契约要求**产新 `kg_version` + 增量重算**，而增量重算**本身不存在**（`specs/m6` §3.3 验收 6 压在这里） | 后续批次，且**先做增量重算** |
| `GET /cost/dashboard` | 需要 `token_usage` 聚合与 `cost_metrics` 表；同一个缺口卡着 MVP 准入 **C3-a / C3-b** | 后续批次（与 C3 一起做） |
| 前端校正 GUI | `frontend/src/app/` 下无 ontology 页面、无 API 封装 | 后端跑通后单开前端批次 |

### 2.3 为什么**不是**一口气做完 D1

D1 = 「M5 完整化 + 内网双轨」（`docs/delivery-requirements-and-guardrails.md:114`，DR-D1 ⏳ 未做）。
除本批这刀外还挂着：`alert` 表（限流超阈值告警，M5 §3 验收 5 明文标 **P2**）、
以及"M5 其它六条验收**到底哪几条还没达成**"这件事**本批只核对、不补**（§4 Non-goal 7）。

### 2.4 本批的三刀（建议范围）

1. **配置落地**：`PRIVATE_DEPLOY_ENABLED` + `ALLOWED_EGRESS_HOSTS`（spec §4.6 字段名**逐字照抄**），
   `.env.example` 同步；**必须有消费者**（`check_seams.py` 判据 2 + `check_session_drift.py` S3）。
2. **构造期出向守卫**：解析出向目标的 host ⇒ 不在白名单且开关打开 ⇒ **阻断**（抛 `AppError`），
   并写一行 `audit_log(action='private_deploy.violation')`。
3. **同步测试 + 契约再生**（§5 D2）：守卫单测**全程不联网**（¥0），契约/前端生成物走完同步五步。

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0
uv run python scripts/export_openapi.py --check       # 期望：零 diff
uv run pytest -q                                      # 本地口径基线见 §8（须补 GRAPH_REAL_NEO4J_*）
Get-NetTCPConnection -LocalPort 8009 -State Listen    # 本地 embedding 服务（跑 C 类判据才需要）
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点是绿的（否则先别动代码）
```

**任何一条与 §8 基线不符，先治病，不要带着红底写代码** —— 否则你无法分辨 CI 红是自己改的还是本来就红的。
（P5-B 补 dev License、P5-C 起本地服务加 admin 授权，都是同一条纪律下的动作。）

---

## 4. 边界纪律 · Non-goals（**11 条，逐条对照**）

| # | Non-goal | 说明 |
|---|---|---|
| 1 | **不新增 LLM provider 档位** | 内网双轨 = **只换 `base_url`**，走 `openai_compatible`（ADR-0004 §3 第 2 条；`llm_provider` 仍是唯一切换开关） |
| 2 | **不实现 `alert` 表 / 限流告警阈值联动** | M5 §3 验收 5 自己标了 **P2** |
| 3 | **不改 `specs/m5-permission-audit.md`** | 已 v1.0；要改 ⇒ §10 第 2 类升级 |
| 4 | **不动 RLS / RBAC / 租户隔离** | DR-B4 / DR-B9 各有门禁看着，本批只是**新增**一条阻断路径 |
| 5 | **不重建 / 迁移演示图谱** | 图谱已在 P5-B 恢复；除非 §0.5 第 2 份文档 §0 指向重建 |
| 6 | **不新增第三方依赖** | 守卫用标准库 `urllib.parse` 解析 host 即可 |
| 7 | **不顺手补 M5 其它验收条** | 只做**核对 + 登记**（哪几条已达成、哪几条缺），**不改代码** |
| 8 | **不把守卫做成"发出去再判"** | 必须**构造期**阻断：联网调用数为 0 才是真阻断（见 §5 D3） |
| 9 | **不改既有端点在私域关闭时的行为** | 只新增阻断路径，开关关闭 ⇒ 一切照旧 |
| 10 | **不为私域新增别名 / 第二开关** | 两个配置名逐字照抄 spec §4.6，不自造同义字段 |
| 11 | **不碰 P5-C 刚落地的三个 ontology 端点与 `ontology_actions` 表** | 它们的偏离已裁决保留（P5-C §7），本批不要再"顺手订正" |

> **回切点**：每个子任务收尾跑 `uv run python scripts/check_session_drift.py`，
> S1 必须读到**本文件这 11 条**；S5 命中要答得出归属哪条需求。
> ⚠️ 本批 S4 一定会报"动了 contract / schema"——**那是预期内**（§5 D2），
> 不要因为 S4 报了就以为自己越界。

---

## 5. 决策表（**已裁 / 建议采纳项**，逐条有据）

| # | 决策 | 处置 | 依据 |
|---|---|---|---|
| **D1** | 本批主题（D1 vs M6 第二批） | ✅ **按 §2.1 定 D1 第一批**。若你要换成 M6 第二批，只需改本文件 §2.4 / §4 / §9 三处，不必重写全文 | `delivery-plan.md:198` 队列 + M6 剩余三件各有未落地前置 |
| **D2** | 契约会不会动 | ✅ **预期会动，按既有流程走完同步五步，不算升级**。新增 `ErrorCode` 会被 `app/core/openapi.py:129-134` 写进 `ErrorCode` 的 `enum` / `x-enum-descriptions` / `x-enum-sources`，而 `tests/test_openapi_contract.py:152` 断言 `enum == {code.value for code in ErrorCode}` ⇒ **不导出必红**。五步：`export_openapi.py`（不加 `--check`）→ `npm run gen:api` → 提交两个生成物 → CI 零漂移 | **P5-C 的 B-1 已开先例且被裁决保留**：生成物随实现再生是既有流程，不是越界 |
| **D3** | 守卫挂在哪一层 | **构造期**：`build_chat_model` 与 MinerU 客户端构造处。**不**放中间件、**不**在请求发出后判 | ① 可单测、不依赖真实网络；② 出向**一次都没发生**才算阻断；③ 与 `llm.py:36-40`「未知档位显式报错」同款纪律 |
| **D4** | 开关默认值 | `PRIVATE_DEPLOY_ENABLED` 默认 **`false`**（与开发环境一致；CI 必须 false，否则全红）；`.env.example` 标注「生产置 `true`」。**不**加"生产必须为 true"的护栏 ⇒ 登记为建议项，本批不实现 | spec §4.6 写明「`false`（开发）/ `true`（生产）」；护栏化属新增需求，不做顺手活 |
| **D5** | 新增错误码的四处同步 | `errors.py` 的 **ErrorCode 枚举 / 状态码映射 / 描述字典 / 来源字典** 四处**都要加**（坐标见 §6），漏一处 `export_openapi.py` 直接 `KeyError` | `openapi.py:129-134` 遍历全部 `ErrorCode` 取两个字典 |
| **D6** | 审计怎么落 | 走既有的 `record_audit_entry`（`app/services/audit.py:108`）写 `audit_log`，`action='private_deploy.violation'`、`status='failure'`、带 `trace_id`。**不新增表** | M5 §3 验收 4 只要求 `private_deploy.violation` 事件；§4.4 已有 `audit_log` 表 |
| **D7** | 成本敞口 | 本批**预期 ¥0**：守卫单测全程不联网、不调真 LLM。若确需真机 ⇒ 先说明再花 | 沿用 P5-C D6 |

**已知陷阱（省钱用）**：

| 陷阱 | 后果 / 处置 |
|---|---|
| `Settings.model_config` 是 **`extra="ignore"`**（`config.py:42`） | 环境变量名拼错会被**静默忽略**，表现为"开关永远读不到" ⇒ 用例要断言**读到的值**，不能只断言"设了" |
| `ALLOWED_EGRESS_HOSTS` 是 **LIST** | 空串要当**空表**处理，不能被解析成 `['']` 从而把空串 host 判成"白名单内" |
| 本地 embedding 服务（`scripts/local_embedding_server.py`，端口 8009） | 它是**内网**，守卫**不该拦**它；内网双轨判据就是验这个 |
| `check_seams.py` 会查"配置有消费者" | 两个新字段**各自**都要有真实消费点，不接受"写了配置但只在测试里读" |

---

## 6. 已查证坐标表（**不要再 recon 一遍**）

> 行号是当前 HEAD（`14cde49d`）的值，**仅供定位；以代码实读为准**（行号漂移不影响结论）。

| 坐标 | 位置 |
|---|---|
| 需求条目 | `docs/delivery-requirements-and-guardrails.md:114` **DR-D1**（⏳ 未做；出口判据「PRIVATE_DEPLOY 路径可用」） |
| 排期队列 | `docs/delivery-plan.md:198`（D4 → D2 M6 → **D1** → D3/D5/D7/D8） |
| Spec 判据 | `specs/m5-permission-audit.md:49`（验收 4：503 `PRIVATE_DEPLOY_BLOCKED` + 审计 `private_deploy.violation`）、`:152-157`（§4.6 配置表：`PRIVATE_DEPLOY_ENABLED` / `ALLOWED_EGRESS_HOSTS`）、`:121-135`（`audit_log` 表）、`:137-150`（脱敏规则，本批不改但要遵守） |
| 配置（**零命中**） | `backend/app/core/config.py:35` `Settings`、`:42` `extra="ignore"`、`:75-79` `llm_*`、`:84-86` `eval_embedding_*`；`grep -r PRIVATE_DEPLOY backend/` 当前无结果 |
| `.env.example` | `backend/.env.example` 对应段（`check_session_drift.py` S3 盯 config ↔ env 同步） |
| 错误码（动四处） | `backend/app/core/errors.py:18` `ErrorCode` 枚举、`:70-74` 状态码映射（**无 503**）、`:98-102` 描述字典、`:192-196` 来源字典、`:213-217` HTTP→码映射 |
| 契约出口 | `backend/app/core/openapi.py:129-134`（遍历 `ErrorCode` 注入 enum / 描述 / 来源） |
| 契约计数门禁 | `backend/tests/test_openapi_contract.py:41-49` 与 `:106-107`（现 **26 路径**）、`:149-152`（`enum` 与 `ErrorCode` **全等**断言） |
| **出向面**（守卫要覆盖的） | `backend/app/services/providers/llm.py:27` `build_chat_model`（LLM，首选）、`backend/app/services/parsing/mineru.py`（MinerU）、`backend/app/services/extraction/langextract.py`（抽取）、`backend/app/services/external_data/cli.py`（外部数据，先确认是否属出向面） |
| **不该被拦的** | `backend/scripts/local_embedding_server.py`（本地 embedding，8009）、任何 `localhost` / 内网 `base_url`（内网双轨） |
| 审计 | `backend/app/services/audit.py:52` `ACTION_BY_ROUTE_NAME`、`:108` `record_audit_entry`、`:211` `_assert_valid_status` |
| ADR 约束 | `docs/adr/0004-integration-seams.md` §2.1（**若新增实现类**须先扩登记行再改 `check_seams.py`） |
| 三条门禁 | `scripts/check_seams.py` / `check_session_drift.py` / `check_startup_readiness.py` |
| P5-C 先例 | `changes/P5-C/integration-log.md` §7.4（B-1 契约再生的处置模板）、§11（指针） |

---

## 7. 已完成项（P5-C，2026-10-07）

- ✅ **`ontology_actions` 审计表**建成（含迁移 + RLS，迁移 `3f7c1b90ad24`）。
- ✅ **`GET /ontology/active` / `POST /ontology/cold-start` / `POST /ontology/confirm`** 接线：
  真机 `GET /ontology/active` = `200 / version=1 / 13 实体 + 14 关系`；confirm 是唯一写 `status='active'` 的入口。
- ✅ 占位测试改写为真行为断言（未实现的 4 个仍钉死 501）+ 新增 10 条闭环用例。
- ✅ **四条偏离已裁决保留**：X-2a（`action_type` 增 `confirm`）、X-2b（`kg_version` NULL 仅豁免 `confirm`）、
  X-2c（`domain_description` 空串）、**B-1（契约与前端生成物再生）**。
- ✅ CI 四 job 全绿：run `37607081246`（代码）/ `37616440691`（收口）。

---

## 8. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1020 passed / 5 skipped / 0 failed**（run `37607081246` / commit `f7c0fa12`） |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*`） | **1019 passed / 4 skipped / 2 failed**（2 failed = `affiliation-demo-v2` 语料不在本地，**已知不修**） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0**；反向守卫 `test_g21_production_sqlite_guard_still_present` 恒通过 |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**26 路径**） |
| 前端 | P5-C **未**在本地跑 `typecheck` / `lint` / `build`；只在 CI 内绿（前端 job 含 lint + `gen:api`）⇒ 本批若改前端生成物，**以 CI 为终裁** |
| 最近一次绿 CI | **不要照抄写死的 run id**。开工时用 `gh run list --limit 1` 实读：P5-C 收口时点是 **run `37616440691` / commit `14cde49d`**，之后以实读为准 |

---

## 9. 验收判据（**每条都要能贴出机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **两个配置落地且有消费者** | `grep PRIVATE_DEPLOY backend/` 不再零命中；`.env.example` 同步；`check_seams.py` 仍 0/0；`check_session_drift.py` S3 不报 |
| 2 | **开关开 + 空白名单 ⇒ 阻断** | 构造 LLM 客户端抛 `AppError` ⇒ HTTP **503** + `code=PRIVATE_DEPLOY_BLOCKED`（真机或 TestClient 均可，但**不许真发请求**） |
| 3 | **白名单放行 + 内网双轨不误杀** | 把 `base_url` 换成白名单内 / 内网端点 ⇒ 构造成功；**本地 embedding（8009）不被拦** |
| 4 | **审计行落库** | `audit_log` 出现 `action='private_deploy.violation'`、`status='failure'`、带 `trace_id`；**可举证**（贴查询结果） |
| 5 | **守卫在构造期、零联网** | 单测用 monkeypatch 断言：被阻断时**没有任何**真实 HTTP 出向（本批 ¥0 的机械保证） |
| 6 | **契约再生 + 零漂移** | `export_openapi.py`（无 `--check`）→ `npm run gen:api` → 提交两生成物 → `--check` 零 diff；26 路径不变；`ErrorCode` enum 与代码全等 |
| 7 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0 |
| 8 | **pytest 不降** | CI 口径 **≥ 1020 passed / 5 skipped / 0 failed**（本批新增用例会使分子变大） |
| 9 | **M5 其它验收只核对、不补** | integration-log 里给出「§3 验收 1–7 各自达成情况」的**核对结论**（含证据），**不改代码**；缺的登记进 §11 指针 |
| 10 | **CI 四 job 全绿**，`gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |

---

## 10. 提交推送纪律 + 升级我的四类情况

**提交**：按 backend / 契约+前端生成物**分段** Conventional Commits（契约再生单独一笔，便于整笔 revert）；
跨侧改动**不得混在一个提交**。推送后 **以 CI 为终裁**（R-10），CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。
推送偶发网络失败（本仓库近期 `github.com:443` 间歇性不可达，曾重试 7 次才成功），**重试到位再报告**，
期间**不许**拿估算的 run id 把表格填满。

**只在以下四类停下找我**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §8 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完下面三步自检再报告**） | 真踩到的例子：`ALLOWED_EGRESS_HOSTS` 的语义（域名？含端口？通配？）spec 没写清楚、且无法用"最小代价 + 登记"绕开 |
| 3 | **边界冲突** | 实现过程中发现必须触碰 §4 的某条 Non-goal。**注意**：§5 D2 的契约再生**不属此类** |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 你自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？（如：想给内网再加一个 provider 档位 ⇒ Non-goal 1）
2. 能不能**整体推到下一批**（如：`ALLOWED_EGRESS_HOSTS` 的通配语义 ⇒ 本批只做**精确 host 匹配**，通配留给后续批次并在 integration-log 登记）？
3. 真不行了 —— **报告时带上**：哪份 spec 的哪一行、要加/改什么、为什么绕不过去、**你试过的替代方案**。
   不接受"spec 没写所以做不了"这种笼统结论。

**为什么这么定**：动 spec 的代价比推迟一个字段高一个量级（要连带契约同步五步 + 前端重导 + CI 零漂移校验），
而本仓库历史上多数"必须改 spec"最后都被证明是**范围没切干净**。

---

## 11. 不许外推（**完成本批 ≠ 以下任何一条**）

- **守卫写了 ≠ 私域合规**：只拦了**已知出向面**（LLM / MinerU / 抽取 / 外部数据）；新出现的出向点不拦。
- **开关关着 ≠ 没出向**：默认 `false` ⇒ 开发/CI 环境**完全不拦**，prod 是否置 `true` 是部署侧的事（已登记为建议项，无护栏）。
- **503 有了 ≠ 请求没发出去**：判据 5 才是这条的保证（构造期阻断、零联网），别用"返回了 503"反推"没出网"。
- **白名单放行 ≠ 出网安全**：白名单是**人填的**，本批不做域名校验之外的任何安全评估。
- **内网双轨能切换 ≠ 内网模型可用**：本批只保证"换 `base_url` 不被自己的守卫误杀"，**不验证**本地 vLLM/Ollama 真能跑通。
- **M5 其它验收核对了 ≠ 达成**：核对结论里"缺"的那些条，一件都没做。
- **本地 pytest 绿 ≠ CI 绿**：本地仍有 2 条 `affiliation-demo-v2` 的已知 fail。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己说过"pytest 全绿 ≠ 护栏在拦"。
- ⚠️ **若你在实现中动到了租户隔离相关路径**（本批**预期不动**）：须带上 **ADR-0003 §4.1** 已登记的两类测试 ——
  **T1 跨 org 越权**、**T2 并发串租户**，**在 PostgreSQL 上执行、纳入 CI 必过项、禁止标 `local_only` 绕过**。

---

## 12. 下一批指针（**本批收口时按实际结果更新，别照抄**）

1. M5 §3 验收条的缺口清单（由本批核对产出）。
2. `alert` 表与限流告警阈值联动（M5 §3 验收 5 的 P2 部分）。
3. 回到 M6：**增量重算**（merge/split/rename 的硬前置）。
4. `/cost/dashboard` + `cost_metrics` 表（与 MVP 准入 **C3-a / C3-b** 一起做）。
5. **RBAC 债随端点走**：`merge` / `split` / `rename` / `cost/dashboard` 谁实现谁同批补
   ① `require_permission` ② `PROTECTED_ENDPOINTS` 登记（含 D4 遗留的 `/cost/dashboard`）。
6. `applied` 枚举的契约同步五步，绑在做 **merge** 那一批之前。
