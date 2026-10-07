# P5-D · D1 第一批：私域出向管控 `PRIVATE_DEPLOY` + 内网双轨可切换

> **日期**：2026-10-07　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-C/integration-log.md`](../P5-C/integration-log.md)（`main` = `14cde49d`，CI run `37616440691` 四 job 全绿）
> **边界**：本文件 §3（11 条 Non-goals）｜**花销**：预期 ¥0（守卫单测全程不联网、不调真 LLM）
> **任务拆解**：[`tasks.md`](./tasks.md)

---

## 1. 目标（一句话）

把 M5 §3 验收 4 / §4.6 的「私域出向管控」从零做成真的：落 `PRIVATE_DEPLOY_ENABLED` +
`ALLOWED_EGRESS_HOSTS` 两个配置、一个**构造期**出向守卫、一个 503 `PRIVATE_DEPLOY_BLOCKED`
错误码 + 一条 `private_deploy.violation` 审计行，并让**内网双轨**（本地 vLLM / Ollama =
只换 `base_url`）**不被自己的守卫误杀**。

三刀：

1. **配置落地**：两个字段名逐字照抄 spec §4.6，`.env.example` 同步，**各自**都要有真实消费点；
2. **构造期出向守卫**：解析出向目标的 host ⇒ 既非内网、又不在白名单 ⇒ **阻断**并写一行
   `audit_log(action='private_deploy.violation')`；
3. **同步测试 + 契约再生**：守卫单测全程不联网（¥0），契约 / 前端生成物走完同步五步。

## 2. 为什么是这一刀

- **排期队列指向它**：`docs/delivery-plan.md:198` 的 P5 顺序是 `D4 → D2 M6 → **D1** → D3/D5/D7/D8`；
  D4 已由 P5-B 收口、D2（M6）已由 P5-C 开出第一批 ⇒ 队列自然下一项是 D1。
- **它是零代码，不存在"实现了一半"的风险**：`grep -r PRIVATE_DEPLOY backend/` 开工前**零命中**。
- **它有已定稿的 spec，没有闸门要等**：`specs/m5-permission-audit.md` **v1.0（v1.0.0 已交付）**，
  §3 验收 4 与 §4.6 配置表是可直接照写的口径 ⇒ 不触发第 2 类升级（先升 spec 再动工）。

## 3. 明确不做（**11 条 Non-goals**，逐条对照）

1. **不新增 LLM provider 档位**：内网双轨 = **只换 `base_url`**，走 `openai_compatible`
   （ADR-0004 §3 第 2 条；`llm_provider` 仍是唯一切换开关）。
2. **不实现 `alert` 表 / 限流告警阈值联动**：M5 §3 验收 5 自己标了 **P2**。
3. **不改 `specs/m5-permission-audit.md`**：已 v1.0；要改 ⇒ 第 2 类升级。
4. **不动 RLS / RBAC / 租户隔离**：DR-B4 / DR-B9 各有门禁看着，本批只是**新增**一条阻断路径。
5. **不重建 / 迁移演示图谱**：图谱已在 P5-B 恢复。
6. **不新增第三方依赖**：守卫用标准库 `urllib.parse` + `ipaddress`。
7. **不顺手补 M5 其它验收条**：只做**核对 + 登记**，**不改代码**。
8. **不把守卫做成"发出去再判"**：必须**构造期**阻断——联网调用数为 0 才是真阻断。
9. **不改既有端点在私域关闭时的行为**：开关关闭 ⇒ 一切照旧。
10. **不为私域新增别名 / 第二开关**：两个配置名逐字照抄 spec §4.6。
11. **不碰 P5-C 刚落地的三个 ontology 端点与 `ontology_actions` 表**：偏离已裁决保留，不再"顺手订正"。

## 4. 采纳的决策（来自新会话开场提示词）

| # | 决策 | 处置 |
|---|---|---|
| D1 | 本批主题（D1 vs M6 第二批） | ✅ 按队列定 **D1 第一批**（M6 剩余三件各有未落地前置，凑一起即"摊太大"） |
| D2 | 契约会不会动 | ✅ **预期会动**（新增 ErrorCode 会被注入 `ErrorCode.enum`），按既有流程走完**同步五步**，**不算升级**；单独一笔提交便于整笔 revert |
| D3 | 守卫挂在哪一层 | **构造期**：`build_chat_model` / MinerU 客户端 / embedding 客户端构造处。**不**放中间件、**不**在请求发出后判 |
| D4 | 开关默认值 | `false`（与开发环境一致，CI 必须 false）；`.env.example` 标注「生产置 `true`」。**不**加"生产必须为 true"的护栏（属新增需求） |
| D5 | 新增错误码的四处同步 | `errors.py` 的 **ErrorCode 枚举 / 状态码映射 / 描述字典 / 来源字典** 四处**都要加**，漏一处 `export_openapi.py` 直接 `KeyError` |
| D6 | 审计怎么落 | 走既有 `record_audit_entry` 写 `audit_log`，`action='private_deploy.violation'`、`status='failure'`、带 `trace_id`。**不新增表** |
| D7 | 成本敞口 | 本批**预期 ¥0** |
| **D8** | 白名单条目 semantics：域名？端口？通配？ | spec 未写清 ⇒ 按第 2 类升级的处置顺序：① 不在任一 Non-goal 里；② **不外推到通配** ⇒ 本批只做**精确 host 匹配** + **可选 `host:port`（写了端口就端口必须匹配）**；子域通配留给后续批次并登记 |
| **D9** | 「内网」怎么判 | spec §3 验收 4 的定语是「**外部网络**出向调用」⇒ 内网 / 回环**天然不算外部**：纯 IPv4/IPv6 字面量判定（私有网段 / 回环 / link-local / ULA）+ `localhost`。**不做 DNS 解析**（解析要联网，违背"零联网"判据） |

## 5. 本批需要登记的**偏离**

| # | 偏离 | 为什么不这样不行 | 撤回方式 |
|---|---|---|---|
| **X-3** | 审计行的 `org_id` 在**无租户上下文**的构造点（如 `build_chat_model`）回落 `settings.default_org_id`，`detail` 标 `scope='system'` | 守卫跑在构造期，多数路径（无请求、无 TaskSpec）根本拿不到 org；而 ADR-0003 的 lean 默认方案 A 是「一套 compose = 一个租户」⇒ `default_org_id` 就是本部署租户。硬要传 org 就得改 `build_chat_model` / `LangextractClient` / `from_settings` / task registry 全链路签名——那是本批摊太大的典型形态 | 调用点传入 `org_id=` 即覆盖；将来多租户部署时必须给每条出向路径补 org 传递 |

## 6. 验收判据（每条都要能贴机器输出）

1. 两个配置落地且有消费者（grep 不再零命中、`.env.example` 同步、接缝 0/0、`check_session_drift.py` S3 不报）
2. 开关开 + 空白名单 ⇒ 阻断：HTTP **503** + `code=PRIVATE_DEPLOY_BLOCKED`（**不许真发请求**）
3. 白名单放行 + 内网双轨不误杀：本地 embedding（8009）**不被拦**
4. 审计行落库：`audit_log` 出现 `action='private_deploy.violation'`、`status='failure'`、带 `trace_id`（贴查询结果）
5. 守卫在构造期、零联网：单测 monkeypatch 断言被阻断时**没有任何**真实 HTTP 出向
6. 契约再生 + 零漂移：`export_openapi.py` → `npm run gen:api` → 提交两生成物 → `--check` 零 diff；26 路径不变
7. `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0
8. pytest 不降：CI 口径 **≥ 1020 passed / 5 skipped / 0 failed**
9. M5 其它验收**只核对、不补**：integration-log 给出 §3 验收 1–7 的核对结论（含证据），缺的登记进 §11
10. CI 四 job 全绿，`gh run watch --exit-status` 退出码 0，run id 回登 integration-log
