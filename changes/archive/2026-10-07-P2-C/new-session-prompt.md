# 新会话开场提示词 · P2-C 登录 / SSO（**无人值守**）

> 复制本文件全文到新会话作为第一条消息。本批**不**从零探索——坐标表已查证、决策表已裁决，直接开工。
> 上一批：P4（License 商业化底座），已归档至 `changes/archive/2026-10-07-P4/`，三轮 CI 全绿。

---

## 1. 执行模式：无人值守（用户已授权）

**技能：`unattended-sprint-execution`** —— 计划已定稿 + 用户已预授权 ⇒ 不索过程性确认，
遇到"需要确认"的点一律**采纳文档中已写明的建议项**（降级预案 / 默认档 / 既定口径）并在
`integration-log.md` 登记事实，只在升级边界停下。

⚠️ **该技能的前提文件已全部归档**（这是本批开工前必须知道的第一件事，否则步骤 1 / 7 会踩空）：
`docs/sprint-calendar.md`、`docs/v1.1.0-demo-mvp-plan.md`、`docs/v2.0.0-ship-backward-plan.md`
均已在 `changes/archive/2026-10-01-obsolete-plans/`。⇒ **触发条件形式上不满足**，按下列映射用替代真源：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5 | **`changes/P2/tasks.md:204-216`**（P2-C 五项子任务）+ 本提示词 §5 决策表 |
| 2 SDD 事前 | `dev-doc-status.md` §9.1（**仍在，`:320`**） | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P2-C/`** |
| 3 契约先行 | `backend/CODEBUDDY.md` §3（**仍在，`:67`**） | 照做（契约先行 5 步） |
| 5 免请求提交 | — | **沿用**：任务验证通过即自行 Conventional Commits 提交 |
| 7 Sprint 收尾 | `dev-doc-status.md` §9.2（**仍在，`:329`**） | 照做；其中「更新 `sprint-calendar.md` §5 状态列」**一步无文件可更新** ⇒ **跳过并显式登记理由**（改在 `changes/P2-C/integration-log.md` 留痕），不得静默略过 |

**默认采纳建议项**：文档中存在降级预案 / 建议路径 / 默认档的决策点 ⇒ 直接按建议执行 + 登记，不停下问。

**升级边界**（技能 4 类 + 本批叠加）：
- 技能的 4 类里，**CP-2 PoC 不通 / F1~F5 触发 / 上线 gate 终审** 属 MVP 计划条款，**本批不适用**；
  本批主用「**文档未覆盖的决策**（无建议项可采纳、且不属于日常实现选择）」这一类。
- **叠加**本提示词 §10 的本批 4 类（新增依赖或改 ADR / 边界冲突 / CI 红且根因不明 / 跨端改前端）。
  叠加理由：技能本意是"仅此 4 类停下"，但本批存在**接缝双向锁**与**契约漂移**两处硬风险，升级线需更严。

**分支**：沿用 P4 的实际做法 —— **在 `main` 上直推**，不另开 `feature/sprint-<N>`；
若判断本批应改开分支 ⇒ 属"文档未覆盖的决策"，**升级用户**。

---

## 2. 确认起点：为什么是 P2-C（三条机械理由）

1. **它是 P4 唯一"建好了却量不出来"的口子**：席位按 `activated_at IS NOT NULL AND disabled_at IS NULL`
   计数（ADR-0006:115/121），而 `activated_at` 由**首次成功登录**回填，登录不做 ⇒ 全表 NULL ⇒
   `count_seats()` 恒 0（唯一消费者 `app/services/license/policy.py:57-74`）⇒ `max_seats` 判据**永远触发不了**。
   P4 已明确登记「不得宣称席位端到端生效」，这个债只能由 P2-C 还。
2. **增量最小**：`users` 表（`models.py:779`）、接缝 1（`AuthProvider`）、身份解析入口
   （`app/core/auth.py:35/75`、`middleware.py:216-239`）**都已就位**，缺的只是"首次登录"这一个回填点。
3. **P2 批次的三笔挂账都移交到这里**：R30 跨租户引用、孤儿 actor 挂账、disabled 账号仍有权限
   （`changes/P2/integration-log.md:285-287`/`:423-426`、`docs/dev-doc-status.md:107/313/314`）。
   `changes/P2/tasks.md:204-216` 已登记 P2-C 的五项子任务——本批就是把这份**既存清单**做完，不是新立题目。

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

三条硬规则：① 结论来自脚本输出，不来自文档表格；② `[--]`/`[~~]` 转正的唯一方式是让测试**真的通过**再删
`@pytest.mark.xfail`（只补断言留着 xfail **不算**转正，纪律 R-9）；③ 反向守卫
`test_g21_production_sqlite_guard_still_present` **必须始终通过**。

顺带确认：`pytest` 基线（见 §7）、`uv run python scripts/export_openapi.py --check` zero diff、
`uv run python scripts/check_seams.py` ERROR 0。

---

## 4. 边界纪律 · **12 条 Non-goals**（改一条都要先回来登记理由）

1. **不新增 `AuthProvider` 第二实现，除非先扩写 ADR-0004 §2.1 登记行**——接缝 1 实现集合 **恒为 1**
   （`docs/adr/0004-integration-seams.md:29/111`，`check_seams.py:142-145` `max_impls=1`）；
   `LdapAuthProvider` 属越界。先改 ADR、再改门禁，漏一侧 **CI 必红**（双向锁）。
2. **不改 `AuthProvider.authenticate()` 签名**——G-11 签名冻结（`app/services/auth/base.py:17/21`）。
3. **不改 `LocalAuthProvider` 语义**（`changes/P2/proposal.md:83`；本批若确需改，先登记理由）。
4. **不伪造席位**：`activated_at` **只能**由真实首次成功登录回填。P4-D5 裁决明令
   「**不回填 `activated_at` 造假席位**」（`changes/archive/2026-10-07-P4/proposal.md:55`）。
   目录同步只落 `activated_at IS NULL`（不占席位）。
5. **不做用户 CRUD / 授权管理界面（UI）**——`changes/P2/proposal.md:85`。
6. **不改 RBAC 矩阵取值**——P2-B 已定，G-24 判据是「矩阵存在 + 入口存在」，**不断言具体权限值**。
7. **不动 ADR-0006**（License 已完成、席位口径已定、三轮 CI 全绿）。
8. **`activated_at` 不进契约**（ADR-0006:123：MVP 内只有 License 一处消费者）。
9. **不做密码策略 / MFA / 找回密码 / 会话管理 UI**。
10. **不处理 R30 跨租户引用与孤儿 actor 之外的历史挂账**（那两笔本批要收，别顺手扩）。
11. **不做前端页面**（唯一例外：契约漂移触发的 `npm run gen:api` 生成物，那是机械产物不是设计）。
12. **不顺手改 `app/api/deps.py`**（`changes/P2/proposal.md:83` 点名）。

---

## 5. 决策表（**已裁决，按此执行；执行中若发现依据有误 ⇒ 停下升级，不要默默改道**）

| # | 决策点 | 裁决 | 依据（原文） | 代价 / 连带动作 |
|---|---|---|---|---|
| **D1** | 是否新增 `AuthProvider` 第二实现？ | **否** | ① `max_impls=1` 双向锁（ADR-0004:29/111、check_seams:142-145）；② SSO 需**自建 IdP**（Keycloak/Dex + Samba AD DC，`delivery-plan.md:183/194`），真机验证成本高；③ 本批目标是**量得出席位**，不是接 SSO | ⇒ `changes/P2/tasks.md` 子任务 ①（扩写 ADR §2.1 再改 `get_auth_provider`）**顺延**；⇒ P2 批次出口第 4 项「`check_seams.py` 登记接缝 1 第二实现」（`delivery-plan.md:77`④）**仍挂起，不得宣称达成** |
| **D2** | 登录端点是否进 `contracts/openapi.yaml`？ | **进**（`POST /auth/login`） | ① 真实登录是对外能力，前端联调需要类型；② 契约是**唯一真源**，不进契约 = 接口存在但前端拿不到类型（P4 第 1 轮 CI 就是栽在这，run 37480357477）；③ 契约 `securitySchemes` 已预告「Sprint 3 起由 M5 `POST /auth/login` 签发 JWT」（`contracts/openapi.yaml:2969-2973`，**只有文字、路径不存在**） | 三件事**同批**做，缺一必红：① 登记 `CORE_PATHS`（`test_openapi_contract.py:15`；paths **27 → 28**）且同步 operationId 计数断言；② 定 `TENANT_PROTECTED_PATHS`（`:65`）排除口径——仿 `/license/status` 走「不承载业务对象」，**写明理由与失效条件**；③ 前端 `npm run gen:api` 生成物同批提交 |
| **D3** | `activated_at` 回填时机？ | **仅"首次成功登录"**（失败不回填；目录同步 / 导入**不**回填） | ADR-0006:121 已定口径；`:115` 判定式；目录同步只落 NULL（不占席位） | 本批**不改** ADR-0006；回填点只能有一处，多一处就是"造假席位" |
| **D4** | `users.status = disabled` 是否立即失效？ | **收**（本批收，不再挂账） | `changes/P2/integration-log.md:285-287` 挂账原文；`changes/P2/tasks.md` 子任务 ③ 「接 `users.status` 到 RBAC」——不收则"真实授权链路"名不副实 | 判据要真跑：disabled 后**新请求被拒** + `disabled_at` 落值 ⇒ **不再计入席位** |
| **D5** | SSO（DR-D9）本批做不做？ | **不做** | ① **无对应 G 护栏编号**（`delivery-requirements-and-guardrails.md:122` 状态 ⏳）⇒ 做完无人盯；② 需自建 IdP（`delivery-plan.md:183`）；③ 不在本批动机内 | DR-D9 状态保持 ⏳，**不得宣称完成**；`delivery-plan.md:194`「真机登录可用（OIDC 用 Keycloak/Dex，AD 起 Samba AD DC）——**mock 跑通不得宣称完成**」**未达成** ⇒ P2 出口**只达成一半** |

> **D1 + D5 的合意**：本批做的是「**真实登录**」，不是「SSO」。这两件事在 `delivery-plan.md:194` 里被写在同一个出口判据中，
> 本批只完成前半，后半（第二实现 + 真机 SSO）**继续挂账**并在 `integration-log.md` 显式登记——不许用"登录可用"冒充"SSO 可用"。

---

## 6. 已查证坐标表（**不要重做 recon**）

| 项 | 坐标 | 要点 |
|---|---|---|
| P2-C 子任务 | `changes/P2/tasks.md:204-216` | ① 扩 ADR §2.1 再改 `get_auth_provider()`（**本批顺延，见 D1**）；② `issuer`/`subject` 进 `users` + 迁移；③ `users.status` 接 RBAC；④ 真实授权链路；⑤ 出口判据 |
| 边界原文 | `changes/P2/proposal.md:83/:85` | 不接 SSO/LDAP/OIDC、不改 `LocalAuthProvider`、不做用户 CRUD |
| 排期与出口 | `docs/delivery-plan.md:77`(④ 第二实现) / `:179`(执行序 P2-B→P2.5→P3→**P2-C**→P4) / `:183`(SSO 需自建 IdP) / `:194`(**mock 跑通不得宣称完成**) | |
| 接缝 1 | `docs/adr/0004-integration-seams.md:29/:111/:129` | `AuthProvider`，覆盖 AD/LDAP/CAS/OIDC，required_from 1.1.0，**实现集合恒为 1** |
| auth 代码 | `app/services/auth/base.py:17`（抽象）· `local.py:21`（唯一实现）· `local.py:41` `get_auth_provider()` 硬返回 | |
| 身份解析 | `app/core/auth.py:35` `parse_bearer_token` · `:75` `identity_from_dev_headers` · `middleware.py:216-239` `_resolve_identity`（bearer + `X-Org-Id`/`X-Actor-Id`）· `middleware.py:423-428` License 复用同一入口 | |
| users 表 | `models.py:779` · 列 `:809-832` · `activated_at` `:820` · `disabled_at` `:824` · `__seat_predicate__` `:835` | |
| 席位唯一消费者 | `app/services/license/policy.py:57-74` | 注释已写「登录属 P2-C ⇒ 当前恒 0」 |
| 消费者登记 | `backend/tests/test_guardrails.py:252` `USERS_CONSUMER_MODULES` | 新增消费者必须登记，否则红 |
| 契约面 | `contracts/openapi.yaml` **无** `/login` `/logout` `/token`；仅 `:2969-2973` bearerAuth 描述提到 `POST /auth/login`（**只有文字，路径不存在**） | 新增后 paths **27 → 28** |
| 契约黄金清单 | `tests/test_openapi_contract.py:15` `CORE_PATHS` · `:95` 断言相等 ⇒ **新增端点必须登记** | |
| 租户排除口径 | 同上 `:65` `TENANT_PROTECTED_PATHS`；`:165`/`:186` 要求受保护路径声明租户头 + 401/403 | |
| DR / G 状态 | DR-B13 `:101` ✅（表建完、功能无）；**G-18** `tests/test_guardrails.py:186/255/294` **无 xfail**；**DR-D9** `:122` ⏳ **无 G 护栏**；DR-C1/G-23、DR-B9/G-24 均无 xfail | 全仓 `backend/tests` 现存 xfail **仅 1 处**：`test_seam_signature_snapshot.py:26`（条件性、`strict=False`，非登录相关）⇒ **无 xfail 阻塞** |
| fixtures | `tests/conftest.py:296` `rbac_default_actor_is_admin` · `:388` `dev_headers` · `:397` `cross_tenant_headers` | |
| 历史病例 | `changes/P2/integration-log.md:118-119/:128-131/:285-287/:423-426` | 「G-18 转正 ≠ 账号体系落地」；disabled 账号仍有权限 |

---

## 7. 已完成项（不用重做）

- `users` 表 + `activated_at` / `disabled_at` + 席位谓词（P2 / P4 两批迁移已落）
- RBAC 三粒度矩阵与强制校验入口（P2-B，G-24 已转正）
- License 六项资产与 G-23 转正（P4，含 `count_seats()` 唯一消费者）
- 身份解析链路（bearer + dev 头）与 `get_auth_provider()` 单点出口
- dev-doc-status / integration-log / check_seams / check_startup_readiness 四套门禁

---

## 8. 基线（**本批结束不得低于此**）

| 项 | 读数 | 来源 |
|---|---|---|
| pytest | **994 passed / 11 skipped / 0 failed** | `changes/archive/2026-10-07-P4/integration-log.md:87` |
| 契约 | zero diff（paths 27） | 同上 `:90` |
| 接缝门禁 | ERROR 0 / OK 12 | 同上 `:91` |
| ruff | check + format 均干净 | 同上 |
| CI | 四 job 全绿（run 37562406596） | 同上 §5 |

---

## 9. 验收判据（**必须真跑出来，不是读代码得出**）

1. **端到端真断言**：一次真实登录成功后，该 `users.activated_at` **非 NULL**（查库，不查 mock）。
2. **席位可量**：`count_seats()` 在上述前提下返回 **≥1**（P4 时恒 0 —— 这是本批的**差分证据**）。
3. **D4 判据**：`users.status = disabled` 后新请求被拒，且 `disabled_at` 落值 ⇒ 不再计入席位。
4. 接缝门禁 ERROR 0（**本批不新增实现** ⇒ 若红了，说明有人越界加了第二个 Provider）。
5. 契约：`CORE_PATHS` 已登记（paths 28），`export_openapi.py --check` zero diff，前端 `gen:api` 无漂移。
6. 测试基线不回归（≥994 passed），`check_startup_readiness` 相关护栏状态不倒退。
7. **CI 四 job 全绿**（纪律 R-10：CI 才是终裁，本地绿不算）。

---

## 10. 提交推送与升级边界

**提交推送纪律**
- Conventional Commits（`feat` / `fix` / `docs` / `chore` / `refactor` / `test`）。
- **每个子任务收尾跑 `cd backend && uv run python scripts/check_session_drift.py`**（S1 读 Non-goals / S2 摊太大 / S3 配置同步 `.env.example` / S4 契约 / S5 孤独模块）。
  S1 报「没有 Non-goals」⇒ 停下来补边界；S5 命中必须回答属于哪条 DR/G，答不上就是顺手做的。
- 改 `contracts/` ⇒ 后端模型、契约、**前端 `npm run gen:api` 生成物**三处同改（P4 run 37480357477 的现场教材）。
- 本地检查 → 提交 → **推送后以 CI 为终裁** → 回登 run id 到 `integration-log.md`。

**升级用户的 4 类（叠加在无人值守技能之上，见 §1）**
1. **需要新增依赖或改 ADR**（尤其 ADR-0004 §2.1 接缝登记行——双向锁）。
2. **边界冲突**：本批 12 条 Non-goals 与实现路径互斥。
3. **CI 红且根因不明**（先看是不是摊太大，而不是先改测试让它绿）。
4. **需要跨端改前端**（角色隔离：改 `frontend/` 时只能动它，且只动生成物）。

---

## 11. 不许外推（**完成本批 ≠ 以下任何一条**）

- **登录可用 ≠ SSO 可用**：`delivery-plan.md:194` 明写「真机登录可用（OIDC 用 Keycloak/Dex，AD 起 Samba AD DC）
  —— **mock 跑通不得宣称完成**」。本批只做前半，后半继续挂账。
- **P2 批次出口只达成一半**：`delivery-plan.md:77`④「`check_seams.py` 登记接缝 1 第二实现」**未达成**（D1 顺延）。
- **DR-D9（SSO/AD）无对应 G 护栏编号** —— 无论做到哪一步，没有机械判据就**不得宣称完成**，只能登记状态。
- 登录做完 **≠** 账号体系完成：用户 CRUD、授权管理界面、MFA、会话管理都不在内。
- `activated_at` 能回填 **≠** 席位合规：`max_seats` 是否**真的拦得住**超限，需另做实测判据。
- 本批**不**触碰 ADR-0006，也不因席位而改动 License 的任何判据口径。
