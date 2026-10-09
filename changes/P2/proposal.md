# Proposal: P2 —— 账号与权限底座

> 依据：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §3（P2）/ §8.2（执行队列）
>
> **定位**：事前计划；事后实测证据记同目录 `integration-log.md`，两者不可互相替代。
>
> **需求**：**DR-B13**（`users` 表，**第一步**，RK-1 已裁决不随 M5）/ **DR-B9**（RBAC 三粒度）/ **DR-D9**（SSO / AD，提前）。
>
> **起跑状态**（2026-10-01 `check_startup_readiness.py` 实测）：已生效 **8** 条、部分生效 **2** 条、开工地雷 **4** 项，其中 **「users 表已建（DR-B13，P2 第一步）」= ❌**；G-18 / G-24 均为 xfail 挂起（CI 绿但未生效）。
>
> **冻结的在途批次**：`changes/P6-U/`（移交 P5 / D4，本阶段不接）。
>
> **批次命名**：沿用 P1 的「P + 序号」；本阶段三个批次为 **P2-A / P2-B / P2-C**。

---

## 1. 开工前可行性核查（2026-10-01）

**先查再排**。本节的结论已经决定了下面的批次表。

### 1.1 逐项结果

| 核查项 | 结果 | 证据 |
|---|---|---|
| `users` 表有没有 **spec** | ✅ **有**，口径明确 | `specs/m5-permission-audit.md` §4.1：7 列（`id` / `username` / `password_hash` / `org_id` / `status` / `created_at` / `updated_at`）；`username` **unique**、`org_id` idx、`password_hash` 标**敏感** |
| ADR-0003 对 `users` 的要求 | 必须带 `org_id`（§3.1 表第 8 行「✅ 已有」）+ **复合索引以 `org_id` 打头**（§3.1 第 1 条） | `docs/adr/ADR-0003-tenant-isolation-rls.md` |
| G-18 判据强不强 | ❌ **太弱**：只判 `"users" in Base.metadata.tables` | `backend/tests/test_guardrails.py:141` |
| G-18 当前状态 | `xfail(strict=True)` ⇒ 建表后 **XPASS 必红**，必须当场摘标记 | 同上；`check_startup_readiness.py` 报 🟠 部分生效 |
| G-24（RBAC）是否被建表连带转正 | **待实测**：其 missing 列表含 `users`（`re.search(r"class\s+User\b")`），划掉该项后 RBAC 主体仍缺 ⇒ 预期仍 XFAIL，**但以实测为准** | `backend/tests/test_guardrails_compliance.py:138-156` |
| 主键惯例 | **`Uuid` + `default=uuid.uuid4`**；`audit_log` 曾由 ADR-0003 §3.1 差异表 **A9** 把 spec 的 `BIGSERIAL` 改为 Uuid —— 本批的类型收敛与 A9 同源 | `models.py` 全表一致 |
| Alembic head | `b3e5a1c70d42`（s9.13 `entity_merge_candidates`） | `migrations/versions/` 版本链 |
| 加表必须写迁移 | ✅ 由 `tests/test_migrations_baseline.py` 机械钉死（迁移结果 vs ORM 元数据：表集 + 列集） | 该文件第 68-82 行 |
| 接缝 1 当前语义 | `LocalAuthProvider` **不查库**：解析 `Bearer dev.<org>.<actor>` / dev 头 ⇒ `Identity` | `app/services/auth/local.py:18-32` |
| ⚠️ 陈旧口径冲突 | `local.py:5` 写「users 表按 **T10 裁决不建**」——与较新的 **DR-B13**（2026-10-01）直接冲突 | 见 §6 决策点 3 |
| `documents.uploaded_by` | `Uuid`、`nullable=False`、`index=True`，**无 FK**；演示库已有真实数据 | `models.py:84` |
| **`users` 表当前的消费者** | **0 个**（无登录 / 无 RBAC / 无 License） | 全 backend 搜不到 `User` 引用 |

### 1.2 三条改写批次表的结论

**① 有 spec ⇒ 逐字照 spec §4.1，不发明字段。**
G-18 在基线文档里的描述是「断言 `users` 表已建且含 P2/P4 所需列（`org_id` / **外部身份字段** / **席位关联字段**）」。
但外部身份字段（`issuer` / `subject`）的消费者是 **SSO（DR-D9）**，席位关联字段的消费者是 **License（DR-C1）**：
现在加进去 = **没有消费者的预留** —— 正是 `CODEBUDDY.md`「预留必须有登记 / 无消费者的配置不得提交」要拦的形态。
⇒ **本批只建 spec §4.1 的 7 列**；那两组字段随各自消费批次（P2-C / P4）再来，届时自带迁移。

**② G-18 的判据必须同时加强，否则转正是假防御。**
只看「表存在」的话，日后有人删掉 `org_id` 或改名 `username`，G-18 依然绿 —— 它是三条线的**唯一**前置断言。
⇒ 摘 xfail 的同时把判据补到「表存在 **+ 列集合 = spec §4.1 的 7 列 + `org_id` 打头索引 + `username` 唯一」
（与 P1-C 给 G-8 补 16.x 断言同类动作，**须同步改基线文档 G-18 那行的描述**，不许只改代码）。

**③ `users` 当前 0 消费者 ⇒ 本批**只**交付「表 + 迁移 + 护栏转正」，不接线。**
这是解除 RK-1 **阻塞**，不是交付功能；**不得**因为批名是「账号与权限底座」就去造一个没人用的 CRUD / 登录端点。

---

## 2. Why

DR-B13 原文：`users` 表**当前不存在**，却是 **DR-D9（SSO）/ DR-B9（RBAC）/ DR-C1（License 席位）**三者的共同前置；
继续挂在原计划里「随 M5（P5）」⇒ **P2 的 SSO 与 P4 的 License 双双被阻塞**。RK-1 已裁决：**前置到 P2 第一步，不随 M5**。

经济账：它是 12 → 13 张表、一次迁移的成本，却同时给三条后续路线（身份 / 授权 / 计费）松开第一颗扣子；
排在 P2 队首同时也是 `delivery-plan.md` §2 第 1 条原则「签单优先」的直接要求。

---

## 3. What Changes

| 序 | 批次 | 动作 | 出口判据 |
|---|---|---|---|
| **1** | **P2-A**：DR-B13 `users` 表 | ① `models.py` 加 `User`（逐字照 spec §4.1 + ADR-0003 §3.1 索引） ② 新增 Alembic 迁移（`down_revision = b3e5a1c70d42`，down 对称） ③ **G-18 转正**并把判据补强 ④ 陈旧口径同步（`local.py` 的 T10 注释、基线文档 G-18 / DR-B13 状态） | G-18 进 🟢 **已生效**；地雷区「users 表已建」转 [OK]；**G-24 仍 XFAIL（实测确认）** |
| 2 | **P2-B**：DR-B9 RBAC 三粒度 | `roles`（全局字典表，**RLS 显式豁免**）/ `user_roles`（含 `doc_scope` / `scene_scope`）+ 路由层**强制校验入口** | G-24 转正；**只建角色表不算 RBAC**（端点不强制校验，权限只是库里的一列装饰） |
| 3 | **P2-C**：DR-D9 SSO / AD | 接缝 1 第二实现（LDAP / OIDC）+ **先扩写 ADR-0004 §2.1 登记行再改工厂** + 外部身份字段进 `users` | `check_seams.py` 接缝 1 集合一致；AD / OIDC 登录可用 |

**P2-A 先于 P2-B / P2-C**：后两者的主体都挂在 `users` 上；先做 B / C 会得到一个「没有主体的授权矩阵」。

**P2-A 不得顺手做的事**（详见 §4）：尤其**不要**改 `LocalAuthProvider` 的语义 —— 现有 dev token / dev header 是**全部测试**的身份来源，一改全线红。

---

## 4. Non-goals（**批次边界** —— 改到这些就是越界）

- **不做** RBAC（`roles` / `user_roles` / 权限校验）—— 归 P2-B；
- **不接** SSO / LDAP / OIDC、**不新增**接缝 1 实现、**不改** `LocalAuthProvider` 校验语义 —— 归 P2-C（含：**不改** `app/api/deps.py` 的身份解析路径）；
- **不加**任何 API：`contracts/openapi.yaml` **零 diff**（`export_openapi.py --check` 无漂移），**不动** `app/schemas/*`；
- **不做**用户服务 / CRUD / 密码策略 / 登录端点 —— 当前**没有消费者**，造它就是「顺手预留」；
- **不加** `documents.uploaded_by` → `users.id` 外键、**不做**数据回填（§6 决策点 2）；
- **不动** ADR 原文（守 **R5**）：`ADR-0003` §3.1 第 77 行「`users` 本批次未建」属历史陈述，状态与新登记一律落在 `docs/delivery-requirements-and-guardrails.md` §5 与本批 `integration-log.md`；
- **不做** RLS / `SET LOCAL`（DR-B4，**P3**）、**不动** License（DR-C1，**P4**）；
- **不改** `prompts/`（无关）；**不填**日期（原则 4）。

---

## 5. 出口判据（一句话）

`check_startup_readiness.py` 里 **G-18 进「🟢 已生效」区**、「users 表已建」由 ❌ 变 [OK]，
且 **G-24 仍是 XFAIL**（实测确认它没变成 XPASS ⇒ 不会逼我们提前处理 P2-B）。

---

## 6. 风险与待裁决点

| # | 项 | 处置 |
|---|---|---|
| **RK-1** | SSO 提前但 `users` 未建 ⇒ P2 被阻塞 | **本批就是它的处置**（既有裁决，不重新讨论） |
| **RK-2** | `username` 照 spec 取**全局 unique**，与多租户「同名不同 org」冲突 | 先照 spec（保 spec 权威）；若日后真出现跨租户同名账号，届时单开一批改成 `(org_id, username)` 复合唯一 + 迁移。**登记为本批遗留** |
| **RK-3** | `documents.uploaded_by` 与 `users` 无引用关系 | 见决策点 2：**本批不加 FK** |
| **RK-4** | 「表已建」被误读成「账号体系已完成」 | G-18 转正常驻门禁 **≠** 交付功能：`users` 仍 **0 消费者**，不得宣称完成；边界见 §4，`integration-log.md` 复述 |

### 决策点（按你 2026-10-01「其余按你建议来」的交代，均已按建议处置）

1. **字段范围：spec §4.1 的 7 列 vs 基线描述里的「外部身份 / 席位关联」列。**
   ⇒ 采纳 **逐字照 spec §4.1**（理由见 §1.2 ①），并同步改写基线文档 G-18 那行的判据描述，
   避免「代码跟基线各说一套」。
2. **`documents.uploaded_by` 是否加外键。**
   ⇒ 采纳 **本批不加**：演示库已有真实数据，加 FK 必须先清洗 / 回填，属**不可逆**数据操作；
   且它不影响 B 组隔离（隔离键是 `org_id`）。**登记为遗留**，待首次真实账号链路（P2-C）一并处理。
3. **`local.py` 里「users 表按 T10 裁决不建」这条陈旧注释怎么办。**
   ⇒ 采纳 **改口径不删历史**：把该句改为「T10 已被 DR-B13（2026-10-01）推翻 —— `users` 已于
   P2-A 建表；本实现**暂不查库**，接线归 P2-C」。**不动 T10 的原始记录**，只在冲突处写明它被推翻。
4. **类型与 spec 的 TEXT 不完全一致怎么办（spec 写 TEXT，我们写 `String(n)`）。**
   ⇒ 采纳 **照既有先例 A9**：类型按本仓惯例收敛（`String(n)` / `Uuid`），`status` 加
   `CheckConstraint` 限定两档；并把这条差异**登记**（守 R5：不篡改 ADR 原文，
   登记落在 `delivery-requirements-and-guardrails.md` §5 与本批 `integration-log.md`）。
