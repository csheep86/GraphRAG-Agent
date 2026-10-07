# P5-D · 集成日志（D1 第一批：私域出向管控 `PRIVATE_DEPLOY` + 内网双轨可切换）

> **日期**：2026-10-07　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-C/integration-log.md`](../P5-C/integration-log.md)
> **边界**：[`proposal.md`](./proposal.md)（11 条 Non-goals）｜**花销**：**¥0**
> **状态**：**已收口** —— 六笔提交在 `main`，CI **run `37627112419` 四 job 全绿**
> （pytest **1066 passed / 5 skipped / 0 failed**）

---

## 0. 一句话结论

**M5 §3 验收 4 从零命中变成了真的**：`PRIVATE_DEPLOY_ENABLED` + `ALLOWED_EGRESS_HOSTS`
两个配置落地（各自都有真实消费者），构造期出向守卫在 **LLM / MinerU / 评测 embedding**
三个出向面的**客户端构造之前**判定，违规 ⇒ 503 `PRIVATE_DEPLOY_BLOCKED` +
一行 `audit_log(action='private_deploy.violation', status='failure')`。

同时**内网双轨没有被自己的守卫误杀**：内网 / 回环地址（含本地 embedding 的
`127.0.0.1:8009`）**天然放行**——这是「只换 `base_url` 就切本地 vLLM / Ollama」
这句话能成立的前提，也是本批唯一一条"放行"性质的判据。

**一条必须先看的实现决策**（登记 X-3）：构造期的 LLM 路径**拿不到租户上下文**，
审计行归属回落 `settings.default_org_id` 并在 `detail.scope` 标 `'system'`；
任务侧（MinerU）**有** org ⇒ 传 `org_id=` ⇒ `scope='tenant'`。两侧都有测试用例钉住。

---

## 1. 开工自检（**结论来自脚本**）

| 项 | 读数 | 与 §8 基线 |
|---|---|---|
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0**，地雷 0 项，反向守卫在 `[SG]` 区 | ✅ 一致 |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12**（63 → **65** 个字段全部有消费者） | ✅ 一致 |
| `export_openapi.py --check` | 零漂移（26 路径） | ✅ 一致 |
| `pytest`（本地口径，补 `GRAPH_REAL_NEO4J_*`） | **1019 passed / 4 skipped / 2 failed** | ✅ 与基线逐位一致 |
| 起点 CI | run `37617561699`（P5-D 提示词落地）success | ✅ 起点绿 |

2 条 fail = 已登记环境债 `affiliation-demo-v2` 语料不在本地，与本批无关。

---

## 2. T1 · 配置落地（spec §4.6）

| 落点 | 内容 |
|---|---|
| `app/core/config.py` | `private_deploy_enabled: bool = False`、`allowed_egress_hosts: Annotated[list[str], NoDecode]` + 两个 validator |
| `backend/.env.example` | 新段，含「内网天然放行 / 端口须匹配 / 本批不支持通配」三条语义说明 |

### 2.1 实踩：`ALLOWED_EGRESS_HOSTS=` 空值会让**服务启动失败**

```
SettingsError: error parsing value for field "allowed_egress_hosts" from source "EnvSettingsSource"
  ↳ json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

而「白名单缺省」是这个字段**最常见的合法取值**——不该让一个缺省形态把整套服务带停。
处置：用 `Annotated[..., NoDecode]` 接管解析（pydantic-settings **2.15.0** 已支持），
`mode="before"` 的 validator 容忍四种写法：空串 / `[]` / 逗号分隔 / JSON 数组。
after-validator 再做 strip + 小写 + **丢空项**（清单被解析成 `['']` 会让
"空白名单"变成"放行一切"，即本批陷阱表点名的那条）。

实测四种写法：`""` ⇒ `[]`、`" , ,"` ⇒ `[]`、`" A.COM , b.internal:8000 "` ⇒
`['a.com', 'b.internal:8000']`、`'["x.example.com"]'` ⇒ `['x.example.com']`。

---

## 3. T2 · 错误码 `PRIVATE_DEPLOY_BLOCKED`（503）

按 D5 **四处**齐加（`ERROR_HTTP_STATUS` 是 projeto 头一个 503）：
ErrorCode 枚举 / 503 映射 / `DEFAULT_MESSAGES` / `ERROR_CODE_DESCRIPTIONS` /
`ERROR_CODE_SOURCES`。

与 501 的边界写进了描述：**501 = 连不上（被动）**，**503 = 主动禁止出网**。

---

## 4. T3 · 构造期守卫（新文件 `app/core/egress.py`）

### 4.1 三个出向面的接线

| 出向面 | 接线点 | 构造期？ | org 归属 |
|---|---|---|---|
| LLM | `app/services/providers/llm.py::build_chat_model` | ✅ 在 `from langchain_openai import ChatOpenAI` **之前** | 无上下文 ⇒ 回落默认租户（`scope='system'`） |
| MinerU | `app/tasks/registry.py::_do_parse` | ✅ 在 `MineruClient(...)` 之前 | **有** `document.org_id` ⇒ `scope='tenant'` |
| 评测 embedding | `app/evaluation/baseline.py::build_default_embedder` | ✅ 在 `OpenAICompatibleEmbedder(...)` 之前 | 无上下文 ⇒ system |

**抽取（`langextract`）不单接**：它经接缝 3 的 `build_chat_model()` 构造客户端
（`langextract.py:388`）⇒ 已被第一处覆盖，单接一处会形成"两个地方拦同一件事"。
`external_data/cli.py` **不是**出向面（手工导入本地文件写 `external_refs`，零出网）⇒ 未接，登记。

### 4.2 两条语义决策（spec 只给了字段名，语义在此定义并登记）

| # | 决策 | 内容 | 依据 |
|---|---|---|---|
| **D9** | 内网 = 天然放行 | 只看 IPv4/IPv6 **字面量**（回环 / RFC1918 / ULA / link-local / 保留）+ `localhost`；**不做 DNS 解析** | spec §3 验收 4 的定语是「**外部网络**出向调用」；且 DNS 解析要联网，会把"零联网"判据自己破坏掉 |
| **D8** | 白名单精确匹配 | `host` 或 `host:port`；**写了端口就必须端口匹配**（不静默忽略）；URL 未写端口时按 scheme 推断（https⇒443）；**不支持**通配 / 子域 | 第 2 类升级的处置顺序：① 不在任一 Non-goal 里 ② 不外推 ⇒ 通配留给后续批次（§11 第 7 条） |

端口为什么要推断而不直接判失败：`https://host` + 白名单 `host:443` 若判不匹配，
用户写的那条白名单就形同虚设——那是"告诉你能限制、实际没限"的另一种形态。

### 4.3 X-3 · 审计行 `org_id` 的回落（偏离）

守卫跑在**构造期**，而 `build_chat_model()` 的三条调用链（`AgentService` / 本体建议 /
抽取）没有一条能把 org 传到这个深度。硬要传 ⇒ 得改 `build_chat_model` +
`LangextractClient.__init__` / `from_settings` + task registry 全链路签名——
那是本批摊太大的典型形态，故登记而非实现。

**为什么回落 `default_org_id` 不是"猜"**：ADR-0003 的 lean 默认方案 A 是
「一套 compose = 一个租户」⇒ 该值就是本部署租户。

**标注诚实性**：`detail.scope` 区分 `'system'` / `'tenant'`，两种各有一条用例钉住；
将来多租户部署时必须给每条出向路径补 org 传递。
**撤回**：调用点传入 `org_id=` 即覆盖，不需要改守卫。

---

## 5. T4 · 测试（46 条，¥0 全过程零出向）

新文件 `tests/test_private_deploy_egress.py`，六组：

1. URL 解析（含 `localhost:11434/v1` 这种不带 scheme 的 Ollama 写法）；
2. 内网识别的正 / 反两向（含 `8.8.8.8` / `1.1.1.1` —— 公网 IP 字面量**不是**内网）；
3. 判定：内网放行 / 公网阻断 / 开关关闭时一切照旧 / 解析不出 host ⇒ **阻断（fail-closed）**；
4. 白名单语义：精确 host / 端口不符即阻断 / scheme 默认端口 / **通配不支持** /
   清单归一化（`['']` 陷阱）/ 配置**读到的值**；
5. **构造期零出向**：把 `langchain_openai.ChatOpenAI` 打桩成"调用即 AssertionError"，
   断言 `calls == []`；并 monkeypatch `socket.create_connection` / `getaddrinfo`
   ⇒ 守卫若退化成"发出去再判"，这条会**先**炸；
6. 审计：默认路径写库（`scope='system'`）/ 传 session + org 的路径（`scope='tenant'`）/
   **库不可达时仍要阻断**（审计失败不得把主行为顶掉，更不许变 500）；
7. 端到端：`POST /ontology/cold-start` ⇒ **HTTP 503 + `PRIVATE_DEPLOY_BLOCKED`** + trace_id。

**测试计数对账**：本地 1019 → **1065**（+46）；CI 1020 → **1066**（+46）✅ 无其它增减。

---

## 6. 验收判据（**每条都贴了机器输出**）

| # | 判据 | 证据 |
|---|---|---|
| 1 | 配置落地且有消费者 | `grep PRIVATE_DEPLOY backend/` 不再零命中；`.env.example` 同步；`check_seams.py` **ERROR 0 / WARN 0 / OK 12，65 个字段全部有消费者**；`check_session_drift.py` S3 = "OK：新增 Settings 字段均在 `.env.example` 落位" |
| 2 | 开关开 + 空白名单 ⇒ 阻断 | 真机：`PRIVATE_DEPLOY_ENABLED=true` 下 `guard_egress('https://api.deepseek.com')` → `blocked http_status= 503 code= PRIVATE_DEPLOY_BLOCKED`；端到端 `POST /ontology/cold-start` ⇒ **503** + `body.code == 'PRIVATE_DEPLOY_BLOCKED'` + `detail.target == 'llm.base_url'`，且二者**都不发请求** |
| 3 | 白名单放行 + 内网双轨不误杀 | 真机：同一 session 下 `guard_egress('http://127.0.0.1:8009/v1', target='eval.embedding.base_url')` → `local embedding 8009 allowed`；用例侧另覆盖 `localhost` / `10.0.0.7:8443` / `192.168.5.10:11434`（Ollama 端口）/ `[fd00::1]:8080`，以及"把 `LLM_BASE_URL` 换成 `http://127.0.0.1:8000/v1` ⇒ 构造成功且 base_url 原样透传" |
| 4 | 审计行落库（**可举证**） | `docker exec graphrag-pg psql … \| private_deploy.violation \| failure \| c7d3c2cc-…-7f942394055d \| llm.base_url \| api.deepseek.com \| system`（另有 `unknown.example.org` 一行，来自第 2 轮的并非同一 trace）；`trace_id` 非空、`status='failure'` 逐列可读 |
| 5 | 构造期零出向 | `test_build_chat_model_blocked_before_client_construction`：构造器打桩 ⇒ `calls == []`；同时 patch 了 `socket.create_connection` / `getaddrinfo` ⇒ 真出网会在**这条**用例里先失败 |
| 6 | 契约再生 + 零漂移 | 生成物 diff = **openapi.yaml 3 行**（enum + descriptions + sources）+ **api.d.ts 1 行**（`ErrorCode` 联合类型）；**26 路径计数不变**；`export_openapi.py --check` 零漂移；CI「契约校验」job 的「后端契约校验」与「前端类型漂移校验（git diff --exit-code）」双绿 |
| 7 | 护栏不倒退 | `check_startup_readiness.py` = `[OK]` **17** / `[~~]` **0** / `[--]` **0** |
| 8 | pytest 不降 | 本地 **1065 passed / 4 skipped / 2 failed**（2 = 已登记环境债）｜**CI 1066 passed / 5 skipped / 0 failed**（实读 run `37627112419`） |
| 9 | M5 其它验收只核对不补 | 见 §7，逐条给了结论与证据 |
| 10 | CI 四 job 全绿 | ✅ **run `37627112419` / commit `43b3a5ae`**，`gh run watch --exit-status` = **EXIT=0** |

---

## 7. M5 §3 验收 1–7 的**核对结论**（Non-goal 7：只核对，不改代码）

| 验收 | 达成 | 证据 / 缺口 |
|---|---|---|
| 1 无权限 403 + `permission.denied` | ✅ | `rbac/service.py::record_permission_denied`（已在 `audit.py` 登记为第 ④ 个调用方）+ `tests/test_rbac.py` 的拒绝用例 |
| 2 全量审计 + 字段 + JSON 日志 | ✅ | `AuditMiddleware` 全量写 `/api/v1/*`（health 豁免）；`audit_log` 十列齐全；loguru JSON |
| 3 敏感字段脱敏 | ⚠️ **部分** | **缺口**：spec §4.5 的 `mask(field, category)` **脱敏器未实现**（代码三处明写"本批次不引入脱敏器，属 H5 / S11"）。现行替代防线是**不写原文**：`filename_hash` 不可逆哈希、`detail` 只写结构化字段、`tests/test_audit.py:103` 断言 `filename_hash` 不得出现在 detail 里。**这是"没有泄露面"，不是"已脱敏"**——两者不能混为一谈 |
| 4 私域出向 | ✅ | 本批做成（开工前 `grep -r PRIVATE_DEPLOY backend/` 零命中） |
| 5 限流 429 + `rate_limit.triggered` | ⚠️ **半达成** | 429 + 审计 ✅（`test_rate_limit.py`）；**`alert` 表缺**（spec 自标 **P2**，即本批 Non-goal 2，另见 §11 第 2 条） |
| 6 `trace_id` 全链路 + `X-Trace-Id` 回显 | ✅ | `TraceIdMiddleware` 注入 contextvar + 响应头；`test_error_contract.py` / `test_health.py` 覆盖回显 |
| 7 `GET /audit` 隔离 + `ts DESC` 分页 50 | ✅ | `list_audit_logs`：`AuditLog.org_id == identity.org_id` + `order_by(ts.desc())` + `PAGE_SIZE_DEFAULT = 50` |

---

## 8. 门禁读数

| 项 | 读数 |
|---|---|
| `check_seams.py` | ERROR **0** / WARN **0** / OK **12**（Settings **65** 字段全部有消费者；本批新增的 2 个各自进账） |
| `export_openapi.py --check` | 零漂移（26 路径） |
| `check_startup_readiness.py` | `[OK]` **17** / `[~~]` **0** / `[--]` **0** |
| `ruff check` / `ruff format --check` | All checks passed / 253 files already formatted |
| `check_session_drift.py` | S1 读到 `changes/P5-D/proposal.md` 的 **11 条**；S2 = 9 文件 / 101 新增行（未超阈值）；S3 已落位；**S4 报契约改动 ⇒ 预期内（D2），不是越界**；S5 无孤独模块 |

### 8.3 ✅ CI：**run `37627112419`（commit `43b3a5ae`）四 job 全绿**

```
✓ 前端（lint + gen:api）      in 44s   ESLint ✓ / TypeScript 类型检查 ✓ / 重新生成前端类型 ✓
✓ 契约校验（前后端漂移门禁）  in 37s   export_openapi --check ✓ / 前端类型漂移 git diff --exit-code ✓
✓ 后端（ruff + pytest）       in 2m9s  Ruff 两件套 ✓ / check_seams ✓ / G-15 ✓ / Pytest 1066 passed, 5 skipped
✓ 流水线汇总                   in 3s
gh run watch 37627112419 --exit-status  => EXIT=0
```

> pytest 计数取自实读：`1066 passed, 5 skipped, 1 warning in 55.93s`（run `37627112419`）。
> 下一批请继续 `gh run view <id> --log | Select-String passed` **实读**，不要抄本表的数字。

**前端：本次 CI 里跑了 lint + tsc + gen:api 全绿**（本地仍未安装/运行前端工具链，
沿用 P5-C 的口径：**以 CI 为终裁**）。

---

## 9. 收尾三问（自答）

1. **有没有顺便做的？**
   没有发现第四条出向面之外的东西。三个接线点都对着 §4 判据；**没有**动 RLS / RBAC /
   租户隔离（本批一次都没 import `rls` / `policy`）；**没有**碰 P5-C 的三个 ontology
   端点（只在端到端用例里**调用**了 `cold-start`，一行实现未改）。
   唯一一处"多做"是 §2.1 的 `NoDecode` 接管——不做的话 `ALLOWED_EGRESS_HOSTS=`
   会让服务起不来，属同一条需求的必要部分，不是新增需求。
2. **有没有为躲坑而绕路的实现？**
   两处候选，都已登记：① **X-3（org 回落）** —— 绕过了"给全链路传 org"这条难路，
   代价是多租户场景归属不精确 → 已用 `detail.scope` 标注并在偏离表写明撤回方式；
   ② **D8 的端口推断** —— 为了让"白名单写了 443"不变成死规则，代价是引入了
   scheme→端口的一张小表；它不是"藏雷"，因为没有它才是误导。
3. **结论是真跑出来的还是读代码得出的？**
   **全部实跑**：两条真机 HTTP/命令行读数（§6 判据 2 / 3）、一条 **psql 真库查询结果**
   （判据 4）、pytest 两口径 + 三条门禁 + ruff 两件套 + `check_session_drift` 五条判据 +
   **CI 四 job 全绿（run `37627112419`，exit 0）**。没有一处是"读代码推断"。

---

## 10. 已沿用 / 新登记的决策

- **D2（契约再生）**：**如期发生** —— 新增 `ErrorCode` 会写进 `openapi.py:129-134` 的
  enum / descriptions / sources，而 `test_openapi_contract.py:149-152` 断言全等
  ⇒ 不导出必红。走完五步 + **单独一笔提交 `43b3a5ae`**（revert 即回到零契约改动）。
  **这不是第 3 类边界冲突**，不需要升级。
- **D4（生产必须为 true 的护栏）**：登记为建议项，本批**不实现**。
- **D8 / D9**：新增的两条语义决策（内容见 §4.2）。它们都不出自 spec——spec 只给了字段名，没有这两条语义——但都落在「第 2 类升级处置顺序」里可自行决定的那一侧 ⇒ 未升级，仅登记。
  但都落在"第 2 类升级处置顺序"里可以自行决定的那一侧 ⇒ 未升级，仅登记。
- **本批没有触发任何一类升级**（前置成立、未动 spec/ADR、未撞 Non-goal、CI 一次绿）。

---

## 11. 下一批指针（**按优先级，按实际结果更新**）

0. **DR-D1 的出口判据已达成，但状态行还没改**：`docs/delivery-requirements-and-guardrails.md:114` 仍是 「未做」箭头 + ⏳，而该行出口判据原文是「PRIVATE_DEPLOY 路径可用」——本批的守卫 + 503 + 审计三项正是它的兑现。**本批有意不改那一行**：改需求基线属架构师范围的文档口径，须与验收追踪矩阵同批同步（非本批三刀）⇒ 登记在此，留待确认后单独一笔 docs 提交。

1. **M5 §3 验收 3 的缺口——脱敏器 `mask(field, category)`**：本批核对确认
   spec §4.5 的八类脱敏**未实现**（现行防线是"不写原文"）。它与"audit.detail 想写更多结构化字段"
   是同一个前置，建议与 S11 / H5 一起做，不单独开工。
2. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2 部分；本批 Non-goal 2 排除）。
3. **白名单通配 / 子域匹配**（D8 明确留在这里：`*.example.com` 本批不放行 `a.example.com`）。
4. **多租户出向审计归属**：部署形态脱离"一套 compose = 一个租户"时，
   必须给 `build_chat_model` / `build_default_embedder` 两条链路补 org 传递（X-3 的撤回条件）。
5. **出向面的清单化 registro**：本批只覆盖**已知**三处；新增出向点不设防 — 建议后续加一条
   "新增 httpx/SDK 客户端必须同批补 `guard_egress`"的机械检查（本批**未做**，不属三刀）。
6. **RBAC 债随端点走**（沿用 P5-C §11 第 1 条）：`merge` / `split` / `rename` /
   `/cost/dashboard` 谁实现谁同批补 `require_permission` + `PROTECTED_ENDPOINTS`。
7. **增量重算**仍是 merge/split/rename 的硬前置；`/cost/dashboard` 与 MVP 准入 C3-a/b 一起做。

---

## 12. 不许外推（**完成本批 ≠ 以下任何一条**）

- **守卫写了 ≠ 私域合规**：只拦**已知三处**出向面（LLM / MinerU / 评测 embedding）。
  今天新增的 httpx 客户端明天就会绕过它——本批**没有**做"新增出向即被拦"的机制。
- **开关默认关着 ≠ 没出向**：`PRIVATE_DEPLOY_ENABLED` 默认 `false` ⇒ 开发 / CI / 演示环境
  **完全不拦**；生产是否置 `true` 是部署侧动作，**无护栏强制**（D4 建议项，未实现）。
- **返回了 503 ≠ 请求没发出去**：判据 5（构造期阻断、`socket` 层面零出向）才是这条的保证。
- **内网放行 ≠ 内网安全**：放行只是"不算外网"，那条路径上的服务是否可信本批**不评估**。
- **白名单精确匹配 ≠ 白名单不会被滥用**：值是人填的，本批不做任何域名 / 归属校验。
- **内网双轨能切换 ≠ 内网模型可用**：本批只保证"换 `base_url` 不被自己的守卫误杀"，
  **没有**在本机真跑 vLLM / Ollama，**没有**任何一次真实推理。
- **审计落了 ≠ 归属正确**：默认路径的 `org_id` 是**回落值**（X-3），多租户下会张冠李戴。
- **M5 其它验收核对了 ≠ 达成**：§7 里标 ⚠️ 的两条（脱敏器、`alert` 表）一件都没做。
- **本地 1065 绿 ≠ CI 绿**：本地仍有 2 条 `affiliation-demo-v2` 的已知 fail；
  CI 1066 全绿是因为 CI 上有那套语料。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着「pytest 全绿 ≠ 护栏在拦」。
- ⚠️ **本批未动租户隔离路径**（预期不动，结果也确实未动）⇒ 未触及 ADR-0003 §4.1 的
  T1 / T2 两类测试；**下一批若碰到**，仍须带上它们并在 PostgreSQL 上执行、纳 CI 必过项、
  禁止标 `local_only` 绕过。
