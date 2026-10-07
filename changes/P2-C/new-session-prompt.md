# 新会话开场提示词 · P2-C 登录 / SSO

> 复制本文件全文到新会话作为第一条消息。本批**不**从零探索——坐标表已查证，直接开工。
> 上一批：P4（License 商业化底座），已归档至 `changes/archive/2026-10-07-P4/`，三轮 CI 全绿。

---

## 0. 确认起点：为什么是 P2-C（三条机械理由）

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

## 1. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

三条硬规则：① 结论来自脚本输出，不来自文档表格；② `[--]`/`[~~]` 转正的唯一方式是让测试**真的通过**再删
`@pytest.mark.xfail`（只补断言留着 xfail **不算**转正，纪律 R-9）；③ 反向守卫
`test_g21_production_sqlite_guard_still_present` **必须始终通过**。

顺带确认：`pytest` 基线（见 §6）、`uv run python scripts/export_openapi.py --check` zero diff、
`uv run python scripts/check_seams.py` ERROR 0。

---

## 2. 边界纪律 · **12 条 Non-goals**（改一条都要先回来登记理由）

1. **不新增 `AuthProvider` 第二实现，除非先扩写 ADR-0004 §2.1 登记行**——接缝 1 实现集合 **恒为 1**
   （`docs/adr/0004-integration-seams.md:29/111`，`check_seams.py:142-145` `max_impls=1`）；
   `LdapAuthProvider` 属越界。先改 ADR、再改门禁，漏一侧 **CI 必红**（双向锁）。
2. **不改 `AuthProvider.authenticate()` 签名**——G-11 签名冻结（`app/services/auth/base.py:17/21`）。
3. **不改 `LocalAuthProvider` 语义**（`changes/P2/proposal.md:83` 明示归 P2-C 之前的批次，本批若改须先说明）。
4. **不伪造席位**：`activated_at` **只能**由真实首次成功登录回填。P4-D5 裁决明令
   「**不回填 `activated_at` 造假席位**」（`changes/archive/2026-10-07-P4/proposal.md:55`）。
   目录同步只落 `activated_at IS NULL`（不占席位）。
5. **不做用户 CRUD / 授权管理界面（UI）**——`changes/P2/proposal.md:85`。
6. **不改 RBAC 矩阵取值**——P2-B 已定，G-24 判据就是「矩阵存在 + 入口存在」，**不断言具体权限值**。
7. **不动 ADR-0006**（License 已完成、席位口径已定、三轮 CI 全绿）。
8. **`activated_at` 不进契约**（ADR-0006:123：MVP 内只有 License 一处消费者）。
9. **不做密码策略 / MFA / 找回密码 / 会话管理UI**。
10. **不处理 R30 跨租户引用与孤儿 actor 之外的历史挂账**（那两笔本批要收，别顺手扩）。
11. **不做前端页面**（除非契约漂移触发 `npm run gen:api`——那是机械生成物，不是设计）。
12. **不顺手改 `app/api/deps.py`**（`changes/P2/proposal.md:83` 点名）。

---

## 3. 已查证坐标表（**不要重做 recon**）

| 项 | 坐标 | 要点 |
|---|---|---|
| P2-C 子任务 | `changes/P2/tasks.md:204-216` | ① 扩 ADR §2.1 再改 `get_auth_provider()`；② `issuer`/`subject` 进 `users` + 迁移；③ `users.status` 接 RBAC；④ 真实授权链路；⑤ 出口判据 |
| 边界原文 | `changes/P2/proposal.md:83/:85` | 不接 SSO/LDAP/OIDC、不改 `LocalAuthProvider`、不做用户 CRUD |
| 排期 | `docs/delivery-plan.md:77/:179/:183/:194` | DR-D9（SSO/AD）**提前进 MVP**；执行序 P2-B→P2.5→P3→**P2-C**→P4；出口＝「接缝 1 第二实现 + 真机登录可用，**mock 不算完成**」 |
| 接缝 1 | `docs/adr/0004-integration-seams.md:29/:111/:129` | `AuthProvider`，覆盖 AD/LDAP/CAS/OIDC，required_from 1.1.0 |
| auth 代码 | `app/services/auth/base.py:17`（抽象）· `local.py:21`（唯一实现）· `local.py:41` `get_auth_provider()` 硬返回 | |
| 身份解析 | `app/core/auth.py:35` `parse_bearer_token` · `:75` `identity_from_dev_headers` · `middleware.py:216-239` `_resolve_identity`（bearer + `X-Org-Id`/`X-Actor-Id`）· `middleware.py:423-428` License 复用同一入口 | |
| users 表 | `models.py:779` · 列 `:809-832` · `activated_at` `:820` · `disabled_at` `:824` · `__seat_predicate__` `:835` | |
| 席位唯一消费者 | `app/services/license/policy.py:57-74` | 注释已写「登录属 P2-C ⇒ 当前恒 0」 |
| 消费者登记 | `backend/tests/test_guardrails.py:252` `USERS_CONSUMER_MODULES` | 新增消费者必须登记，否则红 |
| 契约面 | `contracts/openapi.yaml` **无** `/login` `/logout` `/token`；仅 `:2969-2973` bearerAuth 描述里提到「Sprint 3 起由 M5 `POST /auth/login` 签发 JWT」（**只有文字，路径不存在**） | |
| 契约黄金清单 | `tests/test_openapi_contract.py:15` `CORE_PATHS` · `:95` 断言相等 ⇒ **新增端点必须登记** | |
| 租户排除口径 | 同上 `:65` `TENANT_PROTECTED_PATHS`；`:165`/`:186` 要求受保护路径声明租户头 + 401/403 | 登录端点应仿 `/license/status` 走「不承载业务对象」排除，并写明理由与失效条件 |
| DR / G 状态 | DR-B13 `delivery-requirements-and-guardrails.md:101` ✅（表建完、功能无）；**G-18** `tests/test_guardrails.py:186/255/294` **无 xfail**；**DR-D9**（SSO/AD）`:122` ⏳ 未做且**无对应 G 护栏**；DR-C1/G-23、DR-B9/G-24 均无 xfail | 全仓 `backend/tests` 现存 xfail **仅 1 处**：`test_seam_signature_snapshot.py:26`（条件性、`strict=False`，非登录相关）⇒ **无 xfail 阻塞** |
| fixtures | `tests/conftest.py:296` `rbac_default_actor_is_admin` · `:388` `dev_headers` · `:397` `cross_tenant_headers` | |
| 历史病例 | `changes/P2/integration-log.md:118-119/:128-131/:285-287/:423-426` | 「G-18 转正 ≠ 账号体系落地」；disabled 账号仍有权限 |

---

## 4. 决策表（**新会话开工前先填，填不出来就升级用户，不要边写边定**）

| # | 决策点 | 已知约束 | 待定 |
|---|---|---|---|
| D1 | 本批是否真的新增 `AuthProvider` 第二实现？ | `max_impls=1`，加实现须先扩写 ADR §2.1 | 只做「真实登录」是否足以闭环 `activated_at`？ |
| D2 | 登录端点是否进 `contracts/openapi.yaml`？ | 进 ⇒ 必须登记 `CORE_PATHS` + 定 `TENANT_PROTECTED_PATHS` 排除口径 + 前端 `gen:api` | 是否先做成非契约端点？ |
| D3 | `activated_at` 回填时机 | ADR-0006:121 已定「首次成功登录」 | 失败重试 / 目录同步激活是否也算？ |
| D4 | `users.status = disabled` 是否立即失效既有会话？ | `changes/P2/integration-log.md:285` 挂账：disabled 账号仍有权限 | 本批收 or 继续挂？ |
| D5 | SSO（DR-D9）本批做不做？ | **无 G 护栏编号** ⇒ 做完无人盯 | 不做则须明写「不宣称完成」 |

---

## 5. 已完成项（不用重做）

- `users` 表 + `activated_at` / `disabled_at` + 席位谓词（P2 / P4 两批迁移已落）
- RBAC 三粒度矩阵与强制校验入口（P2-B，G-24 已转正）
- License 六项资产与 G-23 转正（P4，含 `count_seats()` 唯一消费者）
- 身份解析链路（bearer + dev 头）与 `get_auth_provider()` 单点出口
- dev-doc-status / integration-log / check_seams / check_startup_readiness 四套门禁

---

## 6. 基线（**本批结束不得低于此**）

| 项 | 读数 | 来源 |
|---|---|---|
| pytest | **994 passed / 11 skipped / 0 failed** | `changes/archive/2026-10-07-P4/integration-log.md:87` |
| 契约 | zero diff | 同上 `:90` |
| 接缝门禁 | ERROR 0 / OK 12 | 同上 `:91` |
| ruff | check + format 均干净 | 同上 |
| CI | 四 job 全绿（run 37562406596） | 同上 §5 |

---

## 7. 验收判据（**必须真跑出来，不是读代码得出**）

1. **端到端真断言**：一次真实登录成功后，该 `users.activated_at` **非 NULL**（查库，不查 mock）。
2. **席位可量**：`count_seats()` 在上述前提下返回 **≥1**（P4 时恒 0，这是本批的差分证据）。
3. 接缝门禁 ERROR 0（若新增实现 ⇒ ADR §2.1 与 `check_seams.py` **两侧同改**）。
4. 契约：新增端点已登记 `CORE_PATHS`，`export_openapi.py --check` zero diff，前端 `gen:api` 无漂移。
5. 测试基线不回归（≥994 passed），`check_startup_readiness` 相关护栏状态不倒退。
6. **CI 四 job 全绿**（纪律 R-10：CI 才是终裁，本地绿不算）。

---

## 8. 提交推送纪律

- Conventional Commits（`feat` / `fix` / `docs` / `chore` / `refactor` / `test`）。
- **每个子任务收尾跑 `cd backend && uv run python scripts/check_session_drift.py`**（S1 读 Non-goals / S2 摊太大 / S3 配置同步 `.env.example` / S4 契约 / S5 孤独模块）。
  S1 报「没有 Non-goals」⇒ 停下来补边界；S5 命中必须回答属于哪条 DR/G，答不上就是顺手做的。
- 改 `contracts/` ⇒ 后端模型、契约、**前端 `npm run gen:api` 生成物**三处同改（P4 第 1 轮 CI 就是栽在这里，run 37480357477）。
- 优先级：本地检查 → 提交 → **推送后以 CI 为终裁** → 回登 run id 到 `integration-log.md`。

---

## 9. 升级用户的 4 类情况（**遇到就停，不要自行裁决**）

1. **需要新增依赖或改 ADR**（尤其 ADR-0004 §2.1 接缝登记行）。
2. **边界冲突**：本批 12 条 Non-goals 与实现路径互斥。
3. **CI 红且根因不明**（先看是不是摊太大，而不是先改测试让它绿）。
4. **需要跨端改前端**（角色隔离：改 `frontend/` 时只能动它，且只动生成物）。

---

## 10. 不许外推（**完成本批 ≠ 以下任何一条**）

- 登录做完 **≠** 账号体系完成：用户 CRUD、授权管理界面、MFA、会话管理都不在内。
- `activated_at` 能回填 **≠** 席位合规：`max_seats` 是否**真的拦得住**超限，需另做实测判据。
- 接缝 1 有第二实现 **≠** SSO 可用：`delivery-plan.md:194` 明写「**真机登录可用，mock 不算完成**」。
- **DR-D9（SSO/AD）无对应 G 护栏编号**——无论做到哪一步，没有机械判据就**不得宣称完成**，只能登记状态。
- 本批**不**触碰 ADR-0006，也不因席位而改动 License 的任何判据口径。
