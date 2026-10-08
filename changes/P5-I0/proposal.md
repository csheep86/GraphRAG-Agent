# P5-I0 · **版本号定长** + M6 文档状态对账（GUI 批次的前置清理）

> **日期**：2026-10-08　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-H/integration-log.md`](../P5-H/integration-log.md)（`main` = `f503e8a4`，CI run `37769050202` 四 job 全绿）
> **边界**：本文件 §3（**10 条** Non-goals，逐条对照）｜**花销**：预期 ¥0（只改字符串生成 + docs，不调 LLM）
> **任务拆解**：[`tasks.md`](./tasks.md)
> **为什么单独成批**：① 是 **GUI 批次的前置**（不是顺手做的债）—— 见 §2；②③ 是纯文档纠偏，
> **没有 ABI / 没有行为改动**，搭本批的车最便宜。**它们都不是 P5-I 的组成部分**（P5-I = GUI）。

---

## 1. 目标（一句话）

把增量版本号从「**在 base 上拼后缀**」改成「**定长生成**」，消掉一个 GUI 上线当天就会被撞到的
**500 `DataError`**；顺手把三处已经过期、且有一处**会误导**的 M6 文档状态修正过来。

```python
# 改前（每级累积 +11 字符 —— 第 4 级撑爆 String(64)）
candidate = f"{base}-inc-{uuid.uuid4().hex[:6]}"

# 改后（恒 29 字符，与级数无关）
candidate = f"{stamp}-inc-{uuid.uuid4().hex[:8]}"   # stamp = %Y%m%dT%H%M%SZ
```

三刀：

1. **版本号定长**（`app/services/kg/incremental.py::_next_version`）+ 一条「连续 N 级长度不增长」的用例。
2. **`backend/app/core/openapi.py` 的 `ontology` tag 描述**：删掉两处已过期、且其中一处会把
   GAP-F2 讲反的陈述（详见 §2.2），**走完整契约同步**（重导出 `contracts/openapi.yaml` + `npm run gen:api`）。
3. **`specs/m6-ontology-incremental.md:261` 的端点状态行** + `docs/acceptance-traceability-matrix.md` M6 行
   + **DR-B6 / DR-B7 与 G-9 / G-10 的口径对账**（纯 docs，搭车）。

## 2. 为什么是这一刀

### 2.1 ① 是功能缺陷的前置，不是技术债洁癖（**证据全部实读**）

| 环节 | 事实 | 位置 |
|---|---|---|
| 列宽 | `version = String(64)` | `backend/app/db/models.py:286` |
| 生成规则 | `f"{base}-inc-{uuid4hex6}"` —— **每级 +11 字符**，且 base 自身也是拼出来的 | `backend/app/services/kg/incremental.py:522` |
| 基线格式 | `YYYYMMDDTHHMMSSZ-<8hex>` = **25 字符** | `backend/scripts/import_to_neo4j.py:583-585` |
| **同一个限制面其实是 3 列** | `ontology_actions.kg_version` / `result_kg_version` **也是 `String(64)`**（写 parent link 必落） | `backend/app/db/models.py:1069` / `:1071` |

算：1 级 36 ✓ ／ 2 级 47 ✓ ／ 3 级 58 ✓ ／ **4 级 69 ✗**。
⇒ **连续第 4 次校正必然抛 PG `DataError`**，形态是 **500**，走不到任何既有业务错误码
（不是 404 / 409 / 501）⇒ 前端只能显示「未知错误」。

**这不是推算**：P5-H 写多级版本链用例时**实测撞到**，当时被迫用「最短后缀 `-i1`」绕过，
workaround 与理由至今留在 `backend/tests/test_version_read_view.py:235-237`。

**为什么必须排在 GUI 之前**：GUI 的本质就是把「连续校正」开放给人手。人手连点 4 次 rename
是常规操作 ⇒ **上线当天就能炸**。

### 2.2 ② 是文档在讲一个已经不真的话（**其中一句还讲反了安全口径**）

`backend/app/core/openapi.py:74-77`（**不是** `openapi.yaml` —— 后者是导出产物，手改会被
`export_openapi.py --check` 判漂移）现在写着：

- 「⚠️ **当前全部为占位骨架，恒返回 501**」⇒ **已假**：merge / split / rename 自 P5-G 起返回 200；
- 「**只有 `POST /ontology/confirm` 会写生效状态**，其余端点不改本体」⇒ **会误导**：现在
  merge / split / rename **确实改本体**（人工触发，不违反 GAP-F2），这句话会让人读成
  「它们还不能改」—— 而这恰恰是 GUI 批次要用到的一句话。

③ 的 `specs/m6-ontology-incremental.md:261` 是同一句的镜像（「7 个端点均为 501 占位骨架」）。

### 2.3 为什么不把它们塞进 P5-I（GUI）

- ① 会改 `incremental.py` ⇒ 与 P5-I 的 Non-goal 1（**不动后端三动作写侧**）相邻，
  混进去就会变成"GUI 批次里顺手改了写侧"，而这正是 §9 不许外推想防的那一类；
- ②③ 是**纯文档**，塞进 GUI 批次会让该批次的 `check_session_drift` S2 变大、一次摊太开；
- 三者各自 **¥0 / 无迁移 / 无新依赖**，半天可以收干净。

## 3. 明确不做（**10 条 Non-goals**，逐条对照）

1. **不做 GUI / 前端业务代码**：② 唯一的前端产物是 `npm run gen:api` 的**生成物**
   （且预期零变更）；不写一个 `.tsx`、不改一份 UI 逻辑。
2. **不改写侧语义**：`rebuild_incrementally` 的流程、`_rewrite_subgraph`、P5F-3
   （「增量重写节点数 = 校正节点数」）**全部维持**。本批改的**只是版本号字符串怎么生成**。
3. **不动 `correction.py` 的三个 transform**。
4. **不写数据库迁移**：不扩 `String(64)` ⇒ **不触碰 G-6 迁移等价性**（方案见 §4 D2）。
5. **不给 `kg_versions` 加 `parent_version` 列**：P5-H §11 指针 4 的另一半，本批不裁。
6. **不改 `ontology_actions` 的任何语义 / 字段**：版本链的**真源**仍是它（ADR-0008）。
7. **不动 `KgVersioningService.get_active` / `resolve_read_versions` / 三条读路径**：P5-H 的行为零变化。
8. **不动 `cost` tag**（它那句「占位骨架」**仍然为真**）与**成本仪表盘**（批次 D）。
9. **不新增配置项 / 不新增错误码 / 不新增第三方依赖**。
10. **不做 P5-H §11 里剩下的任何一条**：P5H-6 多跳跨版本、P5H-4 概览统计值口径、
    剩余读路径切换、`alert` 表、DR-B6/DR-B7 之外的对账 —— **本批只做 §1 点名的三刀**。

## 4. 决策

| # | 决策 | 处置 |
|---|---|---|
| **D1** | 主题 | ✅ 定 **版本号定长 + M6 文档状态对账** |
| **D2** ⚠️**必答** | 版本号怎么办 | **取 A（定长，不写迁移）**：`<%Y%m%dT%H%M%SZ>-inc-<8hex>` = **29 字符**。<br>**B（扩列到 255）不选**：要写 Alembic 迁移 + 触碰 **G-6 迁移等价性**，与该护栏的举证成本不匹配<br>**为什么 A 是安全的（已核）**：全仓 grep 确认**没有任何业务代码**从版本号字符串
   反解父子链；真正依赖它的只有两处测试辅助（清理 / 读取），本批改为不依赖格式
   （见 §5 **P5I0-2**）。**且这与 ADR-0008 一致**：父子链的真源是 `ontology_actions`，
   版本号字符串从来不是消费者 |
| **D3** | 定长后怎么保证唯一 | 时间戳 + 8hex，**且**保留既有的「重名则重试 8 次」的 `_next_version` 唯一性检查（原来就有，不改） |
| **D4** | 是否保留 `base` 形参 | **删**：改后 `_next_version()` 不再需要 base。调用方只有 `incremental.py:243` 一处（仍是同一 commit 内的机械改动） |
| **D5** | 契约会不会动 | **会动一格**：只动 **tag description**（不是 schema / 不是字段）⇒ 仍走同步五步（改 `openapi.py` → `export_openapi.py` → 后端 → `npm run gen:api`）。**路径数不变（**开工实测 **28** 条） |
| **D6** | 文档状态怎么改 | **改成事实**，并把"实现到哪一批"写进去（哪批做的、还剩哪几个端点占位）；**不改启用条件 / 不降标准** |
| **D7** | DR 对账范围 | **只**做 **DR-B6 / DR-B7 ↔ G-9 / G-10** 的口径对账（纯 docs，不碰护栏代码、不改判据强度）；其余需求类对账**不展开** |
| **D8** | 审计 / 成本 | 本批不新增审计点；**¥0** |

## 5. 本批需要登记的**决策补充**

| # | 冲突点 | 本批取法 | 登记理由 |
|---|---|---|---|
| **P5I0-1** | **版本号不再自带父子信息**：看一列 version 值看不出它是从哪个版本校正来的 | 接受；在 `_next_version` docstring 与 ADR-0008 各留一句说明指向 `ontology_actions` | 父子链的**唯一真源**是 `ontology_actions.kg_version / result_kg_version` 两列（ADR-0008 §3），版本号字符串从来不是消费者；运营侧溯源查该表即可，`incremental.py` 的完成日志本来就打了 `base_version` 与 `new_version` 两个字段 |
| **P5I0-2** | **两处测试依赖 `<base>-inc-%` 前缀**：<br>・`test_kg_incremental_rebuild.py:617`（断言"失败时一行都不落"）<br>・同文件 `:315`（fixture 清理） | **不再依赖字符串格式**：前者改为「调用前后快照对比」（语义更强：直接数没多出行）；后者改为按 `trace_id` 精确清理 | 前缀依赖本身就是"产品格式泄漏进测试"；改完的断言**更强**（不靠命名约定推断"这是本用例产出的"），且将来再改格式不会静默失效 |
| **P5I0-3** | `test_version_read_view.py:235-237` 的 workaround 注释 | 更新注释：这条列宽限制已被本批解除（保留真实后缀即可，不再需要 `-i1` 短写） | 把"曾经不得不绕"的原因留档 ⇒ 将来有人再遇到同形态问题有参照 |

## 6. 验收判据（**每条都要能贴机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **版本号定长，与级数无关** | 真 PG：连续 **8 次** `_next_version()` ⇒ 每次长度恒为 **29**，且全部 ≤ 64 |
| 2 | **看门狗：旧写法确实会撑爆** | 同一用例里用旧口径算出「第 4 级 = 69 字符」并断言 **> 64** ⇒ 把"为什么必须定长"钉成可执行事实（注释 + assert），防止有人改回去 |
| 3 | **写侧判据没被打掉** | `test_kg_incremental_rebuild.py` **9 条全绿**；P5F-3（增量重写节点数 = 校正节点数）断言**未改** |
| 4 | **P5-H 的读侧判据没被打掉** | `test_version_read_view.py` 13 条 + `test_version_chain_readers.py` 6 条**全绿且断言未改**；`test_ontology_correction_actions.py` 12 条仍绿 |
| 5 | **版本链不受影响** | P5-H 的链仍然能解析（`ontology_actions` 是真源，与版本号无关）—— 由判据 4 直接覆盖 |
| 6 | **`ontology` tag 描述已是事实** | `export_openapi.py --check` 零 diff（先导出后校验）；描述里**不再**出现「全部为占位骨架」与「只有 confirm 会写生效状态」 |
| 7 | **契约不漂移** | **28 路径不变**（2026-10-08 实测，比 P5-H 提示词写的 26 多 2 —— **以脚本为准**）；`frontend/src/types/api.d.ts` 经 `npm run gen:api` 后 **git diff 为空**（tag 描述不进 TS 类型 ⇒ 预期零变更，**以 CI 为终裁**） |
| 8 | **m6 spec 状态是事实** | `:261` 写明"merge / split / rename 已实装（P5-G），active / confirm / cold-start / cost dashboard 仍占位"；**编号未重排**（R5） |
| 9 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0；`check_seams.py` 仍 ERROR 0 / WARN 0 / OK 12 |
| 10 | **隔离不倒退** | G-9 T1（跨 org 越权）/ G-10 T2（并发串租户）**仍全绿且断言未放宽** —— 版本号变了 ⇒ 这两类测试是「改唯一键字段却没串租户」的最后一道证据 |
| 11 | **pytest 不降** | CI **≥ 1137 passed / 5 skipped / 0 failed**；既有守卫**不许为让它绿而改断言**（本批两处测试改动见 §5 P5I0-2，**都是清理/读取辅助，不是语义断言**） |
| 12 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |
