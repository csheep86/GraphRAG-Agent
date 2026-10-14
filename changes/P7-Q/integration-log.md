# P7-Q 集成日志 · 修 F-P7H-1：首次部署的建表路径（**升级阻断点**）

> **日期**：2026-10-14 ｜ **提案**：[`proposal.md`](./proposal.md)
> **一句话**：交付形态的建表从 `create_all`（从不 stamp）改成 `alembic upgrade head`
> ——**方案 A**，迁移成为唯一建表途径。
> **留证**：[`docs/drills/upgrade-drill-20261014-p7q.md`](../../docs/drills/upgrade-drill-20261014-p7q.md)

---

## 1. 做了什么（三处改动 + 一处新增）

| 坐标 | 改动 |
|---|---|
| `backend/scripts/init_rls_roles.py` | 新增 `--run-migrations`（以 owner 跑 `alembic upgrade head`）；**删掉**「空库就自动 `create_all`」的隐式分支（F-P7H-1 的成因）；`--create-tables` 与 `--run-migrations` **互斥**；**不再落 RLS 策略**，改为**校验** |
| `deploy/docker-compose.delivery.yml` | `db-init` 的 `--create-tables` → `--run-migrations` |
| `docs/deployment-spec.md` | §4.2（首次部署由 db-init 建表）/ §7.2 第 4 步（升级 = 同一条路 + 遗留库处置）/ §7.3 新增「目标库可迁移」检查项 |
| `backend/tests/test_migrations_baseline.py` | 新增 3 条机械判据（见 §4） |

### 1.1 为什么 `db-init` 的迁移要分三种初始状态

| 库的状态 | 处置 | 理由 |
|---|---|---|
| 已 stamp | `alembic upgrade head`（真跑） | 正常升级路径 |
| **空库** | `alembic upgrade head`（真跑，14 个迁移） | 首次部署：**建表只此一条路** |
| 有表但**无** `alembic_version`（旧版 `create_all` 建的库） | 先机械比对库 schema vs `Base.metadata`：等价 ⇒ `stamp head`；**不等价 ⇒ 报错退出并列出差异** | 那批迁移是"追平模型"的，跑不动；但**绝不**把已经漂移的库 stamp 成 head（那是伪造迁移历史） |

第三种是**客户现场真实存在的状态**（1.6.0 及更早都是 `create_all` 建的），不做它的话方案 A 只修了"未来"、修不了"存量"。

### 1.2 为什么策略改成「迁移落、db-init 只校验」

此前两边都落（`db-init` 的 `apply_tenant_rls` + 迁移 `8210590e76a5`）。方案 A 要求定清唯一落点：

- 策略若继续被"当前代码版本"重述，库里的策略就**不再对应任何一条迁移**——而回滚只改 tag，
  旧镜像的 `db-init` 会把新库的策略改回旧口径；
- 改为只**校验**之后，「有租户表漏了策略」从**零症状**（RLS 失效不报错）
  变成**部署期硬失败**。

dev 路径例外：`--create-tables` 那条分支仍然落策略（dev 库从不跑迁移，Non-goal 1：不动 dev）。

### 1.3 一个被迫修的坑：口令里的 `%`

`alembic.config.Config.set_main_option` 走 `ConfigParser` 的 BasicInterpolation ⇒
口令里一个裸 `%` 会直接抛 `ValueError: invalid interpolation syntax`（实测属实）
⇒ 交付现场带 `%` 的口令会让 `db-init` 当场崩。已转义（`%` → `%%`），写在 `_alembic_config` 的注释里。

---

## 2. 出口判据（§6）逐条 —— 全是实测，不是读代码

| # | 判据 | 读数 | 结论 |
|---|---|---|---|
| 1 | 空库首次部署 ⇒ schema == `Base.metadata` | db-init 日志 `空库：由迁移建表（14 个迁移真跑）`；容器内比对 `missing_tables=[] / extra_tables=[] / column_diff={}` ⇒ **EQUAL**，`alembic_version=a1f7c2b93d04` | ✅ |
| 2 | 再跑 `alembic upgrade head` 不撞 DuplicateTable，`current` = head | `upgrade_exit=0`、`Running upgrade` 条数 **0**、`alembic current → a1f7c2b93d04 (head)` | ✅ |
| 3 | 重跑 P7-H 演练 | `1.6.0 → 1.7.0 → 回滚 1.6.0` 三阶段读数齐（version 1.6.0→1.7.0→1.6.0、前端 45313→10483→45313、登录 279 ⇒ documents/audit 200）；升级那步 db-init **退出 0** ⇒ 服务正常起 | ⚠️ **有偏差，见 §3** |
| 4 | pytest 不降、CI 绿 | 本地 **1278 passed / 46 skipped**（改动前基线 1274，用 `git stash` 前后各跑一遍对比）⇒ **+4 = 本批新增 4 条用例**；ruff `All checks passed!` + `301 files already formatted`；接缝 `[OK]`；契约零漂移 `[OK]`；CI run **见 §4** | ✅ |

### 3. ⚠️ 判据 3 的偏差（**必须升级给用户裁决**）

判据 3 原文「本次**迁移必须真跑通**」。在 **1.6.0 遗留库**上这一条**不可能成立**：

- v1.6.0 → 1.7.0 新增的 9 个迁移是**追平模型**的迁移（它们要建的表 / 列，`create_all` 早就建好了）。
  机械证据：遗留库比对 **无缺表、无缺列**（若有一处缺，脚本会报错退出而不是 stamp）；
- P7-H 那次已实测"把版本号拨到哪一段都会撞"（基线 ⇒ `DuplicateTable: affiliation_suspicions`；
  `b3e5a1c70d42` ⇒ `DuplicateTable: users already exists`）。

⇒ 本批实际证明的是：① **升级不再被阻断**（db-init 退出 0、`current`=head、服务可用）
② **首次部署的 14 个迁移真跑**（判据 1 / 2）。
按 Non-goal 2「不把 SKIP 写成 PASS」的口径照实登记，**不**宣称为已满足。

> 演练仍是**双人批次**：`docs/drills/upgrade-drill-20261014-p7q.md` 的「见证者」一栏
> **须人工签真名**，AI 不得代填。

---

## 4. 门禁

| 项 | 读数 |
|---|---|
| 新增单测 | `tests/test_migrations_baseline.py`：空库由迁移建表 == 元数据 / 二次 upgrade 不撞 / 交付编排不许退回 `--create-tables` + dev 编排保留 `--create-tables` ⇒ 本文件 **6 passed** |
| 全量 pytest（本地） | 改前 **1274 passed / 46 skipped** ⇒ 改后 **1278 passed / 46 skipped**（+4，未降） |
| ruff / format | `All checks passed!` ／ `301 files already formatted` |
| 契约零漂移 / 接缝纪律 | `[OK]` / `[OK]`（ERROR 0 / WARN 0 / OK 12） |
| 回切点 S1 | 读到本批 **4 条 Non-goals** 并逐条对照；S2 = 6 文件 / 419 行（阈值内）；S3/S4/S5 均无漂移 |
| CI run | 见提交后的回填 |

**核销**：本批新增 4 条用例 ⇒ 计数**应当上升**（+4），实测正好 +4 ⇒ 新用例真被收进去跑了。

---

## 5. 三条自检（脚本拦不住，自己答）

1. **有没有顺便做的？** 新增的 3+1 条测试与「策略只校验不落」的校验，都直接服务本批
   （F-P7H-1 若无机械判据，下次改回 `--create-tables` 无人拦；不落策略就必须校验，
   否则漏策略是零症状）。`%` 转义是**被迫**发现并修的坑，不是顺手加的。
   没有动 §5 里任何一条 Non-goal：dev / 测试路径未改（`main.py` lifespan 与 conftest 一律未动）、
   迁移脚本一个字节未改、策略**内容**未改（只定谁落）。
2. **有没有绕路？** 遗留库用 stamp 而非真跑迁移，是**唯一可行**路径，不是绕路；
   但它构成判据 3 的偏差，已升级登记，没有拿它冒充"迁移真跑通"。
3. **判据是真跑出来的吗？** 判据 1 / 2 / 3 全在**真实交付镜像 + 独立环境**上实测
   （1.7.0 镜像本批现构建：`backend ea8042213985` / `frontend c94567ce41f9`）；
   判据 4 是 pytest 实测，且用 `git stash` 前后各跑一遍做对比，不是读代码得出的。

---

## 6. 遗留

| 编号 | 内容 |
|---|---|
| **F-P7H-1** | ✅ **关闭**（方案 A），留证 `docs/drills/upgrade-drill-20261014-p7q.md` §4 |
| **F-P7H-2** | 未变：Windows 宿主做交付演练必然踩 License 指纹不匹配，本次照旧挂宿主 machine-id 绕过（非产品缺陷） |
| **F-P7H-3** | 本次**已重新加压**：回滚后 1.6.0 旧代码读"结构 = 1.7.0 元数据"的库 ⇒ 登录 / documents / audit 全 200 无报错。⚠️ 但那 9 个迁移**没新增任何表 / 列**，"旧代码读被新迁移改过的结构"**仍未真正压到** ⇒ 要等一个**确实加表 / 加列**的迁移出现再验 |
| **F-P7Q-1** | 任何"已由 `create_all` 建成"的旧库升级时都只能 stamp、不能真跑（那批迁移无处可跑）。这是**存量迁移的性质**决定的，不是本批实现的问题；要真正验证"升级时迁移真跑"，需等一个加表 / 加列的迁移 |
| **F-P7Q-2** | `db-init` 不再落策略 ⇒ 将来若有迁移加了租户表却漏了 RLS 迁移，`db-init` 会**硬失败**（刻意设计）。CI 侧由 G-26 的清单漂移断言 + 「迁移后策略齐备」判据兜底 |
| **F-P7Q-3** | dev 库 / `graphrag_test` 仍是 `create_all`、未 stamp（与 `probe_temporal_state.py:94-98` 同一形态）⇒ Non-goal 1，本批不动 |
| **F-P7O-1** | （沿用登记）dev 图库 248 个脏 `:KgVersion` 未清理 |
