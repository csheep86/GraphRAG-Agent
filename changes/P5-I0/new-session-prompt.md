# 新会话开场提示词 · P5-I0（**版本号定长** + M6 文档状态对账）

> 📌 **本文件是事后补录**（2026-10-08 写成）。P5-I0 是在**同一个会话内**完成并推送的，
> 当时没有做跨会话交接 ⇒ 没有留下这份文件。为了让批次链路（`changes/P5-*/new-session-prompt.md`）
> 完整、将来回看时能读到「当时凭什么开工」，这里按同款结构把它补齐。
> **它不是当时的执行依据**，执行依据见 [`integration-log.md`](./integration-log.md)。
>
> 🔒 **执行模式**：无人值守（用户已预授权），不索过程性确认，只在 §10 列的四类升级边界停下找用户。
>
> 📦 **起点**：`main` = `f503e8a4`（P5-H 收口，CI run `37769050202` 四 job 全绿）。
>
> ⚠️ **本批是单角色批次**：后端（B）为主，架构师段（docs / 契约描述）在后 → 两段单独提交。
> **没有 GUI / 前端业务代码**（唯一前端产物是 `npm run gen:api` 的生成物，且预期零变更）。

---

## 0. 本批一句话

把增量版本号从「**在 base 上拼后缀**」改成「**定长生成**」，消掉一个 **GUI 上线当天就会被撞到的
500 `DataError`**；顺手把三处已经过期、且有一处**会误导**的 M6 文档状态修正过来。

```python
# 改前（每级累积 +11 字符 —— 第 4 级撑爆 String(64)）
candidate = f"{base}-inc-{uuid.uuid4().hex[:6]}"

# 改后（恒 29 字符，与级数无关）
candidate = f"{stamp}-inc-{uuid.uuid4().hex[:8]}"   # stamp = %Y%m%dT%H%M%SZ
```

三刀：

1. **版本号定长** + 一条「连续 8 级长度不增长」的用例 + 一条**看门狗**用例。
2. **`backend/app/core/openapi.py` 的 `ontology` tag 描述**：删掉两处已过期陈述（其中一处**会把
   GAP-F2 讲反**），走完整契约同步。
3. **`specs/m6-ontology-incremental.md` 端点状态 + 追踪矩阵 M6 行 + DR-B6 / DR-B7 口径对账**。

**不做**：GUI（下一批 P5-I）、任何迁移、任何 schema 改动、任何成本相关的东西。

---

## 0.5 开工前必读（三份文件）

| 文件 | 为什么必须读 |
|---|---|
| **`changes/P5-H/integration-log.md` §5 / §6** | 上一批实录。**§5** 登记了 P5-H 写多级版本链用例时**实测撞到** `value too long` 的那件事 —— 本批就是来解除它的 |
| **`backend/app/core/openapi.py:69-79`** | tag 描述的**真源**。`contracts/openapi.yaml` 是 `export_openapi.py` 的**导出产物**，手改它会被 `--check` 判漂移 ⇒ **不要改 yaml** |
| **`backend/app/services/kg/incremental.py::_next_version`** | 唯一改动点。它旁边就是 `rebuild_incrementally` / `_rewrite_subgraph` —— **那些一行都不许动**（P5F-3 必须继续成立） |

---

## 1. 执行模式：无人值守 + 角色隔离 + 分支

**替代真源映射**（沿用 P5-B~P5-H 的同一张表）：

| 技能步骤 | 原真源 | 本批替代真源 |
|---|---|---|
| 1 定位进度 | `sprint-calendar.md` §5（**文件已不存在**） | 本提示词 §5 决策表 + §4 Non-goals |
| 2 SDD 事前 | `dev-doc-status.md` §9.1 | 照做；`proposal.md` + `tasks.md` 落在 **`changes/P5-I0/`**（开工第一步就建） |
| 3 契约先行 | `backend/CODEBUDDY.md` §3 | **会动一格**：只动 tag description（不是 schema / 字段）⇒ 仍走同步五步。**不算升级** |
| 5 免请求提交 | — | 沿用：任务验证通过即自行 Conventional Commits 提交 |
| 7 收尾 | `dev-doc-status.md` §9.2 | 照做；「更新 `sprint-calendar.md` §5」一步**无文件可更新** ⇒ 跳过并登记理由 |

**角色隔离**（两段，**每段单独提交**）：

| 段 | 角色 | 允许改的范围 | 顺序 |
|---|---|---|---|
| ① 代码 | **后端开发 B** | `backend/app/services/kg/incremental.py` + 两个测试文件 | 第一 |
| ② 契约 + docs | **架构师** | `backend/app/core/openapi.py`、`contracts/openapi.yaml`（由脚本导出）、`specs/` `docs/` | 第二 |
| ③ 生成物 | — | `frontend/src/types/api.d.ts`（`npm run gen:api` 生成，**预期零变更**，不手改） | 第二之后 |

**分支**：沿用前序批次 —— **在 `main` 上直推**，不另开分支。

---

## 2. 为什么是这一刀

### 2.1 三条机械理由

1. **它是 GUI 批次的前置，不是顺手做的债**：GUI 的本质是把「连续校正」开放给人手，
   而人手连点 4 次 rename 是常规操作 ⇒ **上线当天就能炸**（详见 §2.2 的算账）。
2. **三刀各自 ¥0 / 无迁移 / 无新依赖**，半天收得干净 ⇒ 单独立批最便宜，
   塞进 GUI 批次会让那份 `check_session_drift` 的 S2 一次摊太开。
3. **②③ 是同一句话的三个副本**，已经有副本在讲**不真**的话 —— 其中 `openapi.py` 那句
   还会把 **GAP-F2** 讲反（见 §2.3）。文档错错的代价是下一个人照着错的口径做设计。

### 2.2 事实链（**全部实读，不是推算**）

| 环节 | 事实 | 位置 |
|---|---|---|
| 列宽 ① | `version = String(64)` | `backend/app/db/models.py:286` |
| **列宽 ②③** | `ontology_actions.kg_version` / `result_kg_version` **也是 `String(64)`** | `backend/app/db/models.py:1069` / `:1071` |
| 生成规则 | `f"{base}-inc-{uuid4hex6}"` —— **每级 +11 字符** | `backend/app/services/kg/incremental.py:522` |
| 基线格式 | `YYYYMMDDTHHMMSSZ-<8hex>` = **25 字符** | `backend/scripts/import_to_neo4j.py:583-585` |

```
1 级 36 ✓ ／ 2 级 47 ✓ ／ 3 级 58 ✓ ／ 4 级 69 ✗
```

⇒ **连续第 4 次校正必然抛 PG「value too long」**，形态是 **500**，走不到任何既有业务错误码
（不是 404 / 409 / 501）⇒ 前端只能显示「未知错误」。

**这不是推算**：P5-H 写多级版本链用例时**实测撞到**，当时被迫用最短后缀 `-i1` 绕过。

> ⚠️ **动手前容易少算的一条**：限制面不是 1 列而是 **3 列**（`ontology_actions` 那两列同宽）。
> 写代码时才核出来 ⇒ 这决定了后面 §5 **P5I0-2** 那条疏忽的自我纠错。

### 2.3 ② 是文档在讲一个已经不真的话（**其中一句还讲反了安全口径**）

`backend/app/core/openapi.py` 当时写着：

- 「⚠️ **当前全部为占位骨架，恒返回 501**」⇒ **已假**：merge / split / rename 自 P5-G 起返回 200；
- 「**只有 `POST /ontology/confirm` 会写生效状态**，其余端点不改本体」⇒ **会误导**：
  GAP-F2 的真正口径是「**严禁 LLM 自动修改本体**」，而这三个动作**确实改本体、但是人工触发**。
  照原文读会以为「它们还不能改」—— 而这恰恰是 GUI 批次要用到的那句话。

③ 的 `specs/m6-ontology-incremental.md` 是同一句的镜像。

---

## 3. 开工自检（**动手写代码前先跑，结论只能来自脚本**）

```powershell
cd d:\AIProject\GraphRAG-Agent\backend
uv run python scripts/check_startup_readiness.py      # 期望：[OK] 17 / [~~] 0 / [--] 0
uv run python scripts/check_seams.py                  # 期望：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check       # 期望：零 diff（**28 路径**）
uv run pytest -q                                      # 本地口径基线见 §7
cd d:\AIProject\GraphRAG-Agent ; gh run list --limit 1 # 确认起点是绿的（否则先别动代码）
```

> 本机 Neo4j / PG 容器若停了：`docker start graphrag-neo graphrag-pg`。
> 真图用例三开关：`GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` /
> `GRAPH_REAL_NEO4J_USER=neo4j` / `GRAPH_REAL_NEO4J_PASSWORD=ci-graph-pw-2026`。

---

## 4. 明确不做（**10 条 Non-goals**，逐条对照）

1. **不做 GUI / 前端业务代码**：唯一的前端产物是 `gen:api` 的**生成物**（预期零变更）；
   不写一个 `.tsx`、不改一份 UI 逻辑。
2. **不改写侧语义**：`rebuild_incrementally` 的流程、`_rewrite_subgraph`、P5F-3
   （「增量重写节点数 = 校正节点数」）**全部维持**。本批改的**只是版本号字符串怎么生成**。
3. **不动 `correction.py` 的三个 transform**。
4. **不写数据库迁移**：不扩 `String(64)` ⇒ **不触碰 G-6 迁移等价性**。
5. **不给 `kg_versions` 加 `parent_version` 列**：P5-H §11 指针的另一半，本批不裁。
6. **不改 `ontology_actions` 的任何语义 / 字段**：版本链的**真源**仍是它（ADR-0008）。
7. **不动 `KgVersioningService.get_active` / `resolve_read_versions` / 三条读路径**：P5-H 的行为零变化。
8. **不动 `cost` tag**（它那句「占位骨架」**仍然为真**）与**成本仪表盘**（批次 D）。
9. **不新增配置项 / 不新增错误码 / 不新增第三方依赖**。
10. **不做 P5-H §11 里剩下的任何一条**：P5H-6 多跳跨版本、P5H-4 概览统计值口径、
    剩余读路径切换、`alert` 表、DR-B6 / DR-B7 之外的对账 —— **本批只做点名的三刀**。

---

## 5. 决策表（**本批需要自己裁决并在 integration-log 登记**）

| # | 决策 | 处置 |
|---|---|---|
| **D1** | 主题 | ✅ 定 **版本号定长 + M6 文档状态对账** |
| **D2** ⚠️**必答** | 版本号怎么办 | **取 A（定长，不写迁移）**：`<%Y%m%dT%H%M%SZ>-inc-<8hex>` = **29 字符**。<br>**B（扩列到 255）不选**：要写 Alembic 迁移 + 触碰 **G-6 迁移等价性**；而且那只是把阈值从"4 级"推到"20 级"，它还会再撞回来。<br>**A 为什么安全（已核）**：全仓确认**没有任何业务代码**从版本号字符串反解父子链；真正依赖它的只有两处测试辅助，本批改为不依赖格式（**P5I0-2**）。**且与 ADR-0008 一致**：父子链真源是 `ontology_actions` |
| **D3** | 定长后怎么保证唯一 | 时间戳 + 8hex，**且**保留既有的「重名则重试 8 次」的唯一性检查（原来就有，不改） |
| **D4** | 是否保留 `base` 形参 | **删**：调用方只有一处。留着会成为"将来有人用"的入口，而它已经不参与生成 |
| **D5** | 契约会不会动 | **会动一格**：只动 **tag description**（不是 schema / 不是字段）⇒ 仍走同步五步；**路径数不变（28）** |
| **D6** | 文档状态怎么改 | **改成事实**，并写明"哪批做的、还剩哪几个端点占位"；**不改启用条件 / 不降标准** |
| **D7** | DR 对账范围 | **只**做 **DR-B6 / DR-B7 ↔ G-9 / G-10** 的口径对账（纯 docs，**不碰护栏代码、不改判据强度**） |
| **D8** | 审计 / 成本 | 本批不新增审计点；**¥0** |

### 本批需要登记的「决策补充」

| # | 冲突点 | 取法 | 理由 |
|---|---|---|---|
| **P5I0-1** | 版本号不再自带父子信息 | 接受；在 `_next_version` docstring 写明真源指向 `ontology_actions` | 父子链唯一真源是 `ontology_actions.kg_version` / `result_kg_version`（ADR-0008 §3）；运营侧溯源查该表即可，完成日志本来就打了 `base_version` / `new_version` |
| **P5I0-2** | 两处测试依赖 `<base>-inc-%` 前缀（`:617` 断言"失败时一行都没落" + fixture 清理） | **改为不依赖字符串格式**：前者用「调用前后快照对比」，后者按 `trace_id` 精确清理 | 前缀依赖 = 产品格式泄漏进测试。改完的断言**更强**（直接数没多出行，而不是靠命名约定推断） |
| **P5I0-3** | `test_version_read_view.py` 的 `-i1` 短后缀 workaround 怎么办 | **保持短后缀，只改注释** | ⚠️ 这条当初差点写错 —— 见 §9 第 1 条：**那是测试数据限制，不是产品限制** |

---

## 6. 已完成（**前序批次，别重做**）

- ✅ **版本链读侧**（P5-H，`f503e8a4`）：三条读路径按**版本继承读**读图（**ADR-0008**）。
- ✅ **M6 三端点接线**（P5-G）：merge / split / rename 真实现 + RBAC（6 ⇒ 9）+ `entity_merge_candidates.status = applied`。
- ✅ **增量重算**（P5-F）/ **M5 统一脱敏**（P5-E）/ **私域出向管控**（P5-D）/ **M6 第一批**（P5-C）。
- ⚠️ **继续有意不做**：GUI（下一批 **P5-I**）、成本仪表盘（批次 D）、剩余读路径切换、
  `alert` 表（P2，**已连续多批**有意不做）。

---

## 7. 基线（**全部来自脚本 / CI 的实读输出，不许凭文档或记忆填报**）

| 项 | 基线值 |
|---|---|
| `pytest`（**CI 口径**） | **1137 passed / 5 skipped / 0 failed**（run `37769050202` / commit `44ed3133`，2026-10-08） |
| `pytest`（本地口径，需补 `GRAPH_REAL_NEO4J_*` 三开关） | P5-H 实读 **1136 passed / 4 skipped / 2 failed** —— 2 条 failed 是**本地特有的既有环境债**（两条 g25：`test_eval_ci_gate.py::test_g25_real_graph_detection_is_not_empty` 与 `test_eval_corpus_a8.py::test_g25_v2_corpus_meets_thresholds_by_confidence_bound`，依赖 CI 才有的受控种子语料；**CI 上有导入步骤 ⇒ 那 2 条在 CI 上绿**） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（**28 路径**；比 P5-H 提示词里写的 26 多 2 —— **以脚本为准**） |
| `PROTECTED_ENDPOINTS` | `backend/tests/test_rbac.py:62`，现 **9 条** |
| 最近一次绿 CI | **不要照抄写死的 run id**。开工时 `gh run list --limit 1` 实读 |

---

## 8. 验收判据（**每条都要能贴机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **版本号定长，与级数无关** | 真 PG：连续 **8 次** `_next_version()` ⇒ 长度恒为 **29**，全部 ≤ 64，且互不重复 |
| 2 | **看门狗：旧写法确实会撑爆** | 用旧口径算出「第 4 级 = 69」并断言 `> 64` ⇒ 把"为什么必须定长"钉成可执行事实 |
| 3 | **写侧判据没被打掉** | `test_kg_incremental_rebuild.py` **9 条全绿**；P5F-3 断言**未改** |
| 4 | **P5-H 的读侧判据没被打掉** | `test_version_read_view.py` 13 条 + `test_version_chain_readers.py` 6 条 + `test_ontology_correction_actions.py` 12 条**全绿且断言未改** |
| 5 | **版本链不受影响** | `ontology_actions` 是真源、与版本号无关 ⇒ 由判据 4 直接覆盖 |
| 6 | **`ontology` tag 描述已是事实** | `export_openapi.py --check` 零 diff；描述里**不再**出现「全部为占位骨架」与「只有 confirm 会写生效状态」 |
| 7 | **契约不漂移** | **28 路径不变**；`npm run gen:api` 后 `frontend/src/types/api.d.ts` **git diff 为空**（tag 描述不进 TS 类型 ⇒ 预期零变更） |
| 8 | **m6 spec 状态是事实** | 端点状态句写明谁已实装、谁仍占位；新增 §10.1.1 落地状态表；**编号未重排**（R5） |
| 9 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0；`check_seams.py` 仍 OK 12 |
| 10 | **隔离不倒退** | G-9 T1 / G-10 T2 **全绿且断言未放宽** —— 版本号变了 ⇒ 这两类是「改唯一键字段却没串租户」的最后一道证据 |
| 11 | **pytest 不降** | CI **≥ 1137 passed / 5 skipped / 0 failed**；既有守卫**不许为让它绿而改断言** |
| 12 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |

---

## 9. 本批不许外推（**完成本批 ≠ 以下任何一条**）

1. ⚠️ **别把「测试数据限制」当成「产品限制」**（本批最容易栽的一处）：
   产品侧自本批起版本号恒 29 字符 ⇒ 产品超限问题**已解除**；
   但**测试自己造的多级字符串**仍会写进同为 `String(64)` 的 `ontology_actions` 两列
   （5 级真实后缀会让 head 到 72 字符 ⇒ 照样撑爆）。
   ⇒ 那条用例**保持短后缀**，只改注释。**判断标准：去读那个值最终落到哪一列。**
2. **版本号不炸了 ≠ 本体校正可用**：GUI（批次 **P5-I**）**仍未开工** —— 三端点已实装，
   但**没有 UI 就走不到人工触发**这一环。
3. **文档改成 ✅ ≠ 需求变了**：DR-B6 / DR-B7 的判据强度一字未动（仍是必须 PG / CI 必过 / 禁 `local_only` 三条），
   改的只是"和护栏状态码同步"。
4. **`ontology` tag 描述改了 ≠ 端点实现变了**：它描述的是 **P5-G** 的实现；`cost` tag 没动，因为那句**仍为真**。
5. **不需要迁移 ≠ 可以随便改版本号格式**：任何再次引入「把 base 拼进来」的改动，看门狗用例会**先红**。
6. **三列仍是 `String(64)`**：将来任何"版本号要承载更多信息"的设计（加 org 前缀 / 时间戳到秒以下）会重新撞到它。
7. **本地绿 ≠ CI 绿**：本机 Neo4j 常是停的，且本地有 2 条 g25 失败（缺 CI 种子语料）⇒ **以 CI 为终裁**（R-10）。
8. **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着「pytest 全绿 ≠ 护栏在拦」。
9. ⚠️ **跑子集时的伪失败**：`test_kg_build_executor.py::test_kg_build_reuses_existing_kg_version_row`
   的最后一句是**全表计数**（`assert len(rows) == 1`），库里有任何残留都会让它红，
   症状看起来像"最近的改动把它弄坏了" ⇒ **先回读库确认，别急着查自己的 diff**。

---

## 10. 提交推送纪律 + 升级用户的四类情况

**提交**：按 **代码（B）/ 契约 + docs（架构师）/ integration-log** **分段** Conventional Commits；
跨侧改动**不得混在一个提交**。推送后 **以 CI 为终裁**（R-10）；
CI 红了先看是不是批次摊太大，**不许先改测试让它绿**。

**只在以下四类停下找用户**：

| # | 情况 | 例子 |
|---|---|---|
| 1 | **前置不成立** | 开工自检与 §7 基线不符且不属已知环境债 |
| 2 | **要动 spec / ADR 才能继续**（**先做完三步自检再报告**） | 发现限制面其实是 3 列而不是 1 列 ⇒ 要先决定"扩列还是定长"（本批用 §5 D2 的对比表自行裁决，**未升级**） |
| 3 | **边界冲突** | 实现中必须触碰 §4 的某条 Non-goal |
| 4 | **CI 红了且复核两遍仍红** | 带上 job 名 + 失败行 + 自己的归因 |

### ⚠️ 第 2 类的正确处置顺序：**先缩范围，后报告**

1. 卡住的那条**是不是本来就在 §4 Non-goal 里**？
2. 能不能**整体推到下一批**并登记？
3. 真不行了 —— **报告时带上**：哪份 spec / ADR 的哪一行、要加 / 改什么、为什么绕不过去、
   **你试过的替代方案**。不接受"spec 没写所以做不了"这种笼统结论。

---

## 11. 下一批指针（**实际执行后的去向**）

本批收口后，指针第 2 条指向的 **GUI 批次** 已启动：

→ **[`../P5-I/new-session-prompt.md`](../P5-I/new-session-prompt.md)**（M6 批次 B：本体校正 GUI）

其余指针保持：

1. **剩余读路径切换** + **`agents.py` 接线**：M4 端到端才算真正吃到版本继承读。
2. **多跳推理改为 id 级图遍历**（取消 **P5H-6** 限制）。
3. **`GET /cost/dashboard` + `cost_metrics`**（批次 D）；`cost_ratio` 阈值 TBD-7 **Sprint 13** 收敛前拿不到判据。
4. **给 `kg_versions` 加 `parent_version` 列**（需迁移 + **G-6**）；若要让版本号承载更多信息，
   **先**回答三列的 `String(64)` 怎么够 —— 与本批 §5 D2 的方案 B 是同一笔账。
5. **概览三个统计值口径**（P5H-4）：有了 GUI 才有消费者，建议与 GUI 的后续迭代同批裁。
6. **`human_review` 队列读端点**（M2 的 S9.13-2）。
7. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2）。
8. **`test_kg_build_executor.py` 的全表计数断言**改为"只数与本用例有关的行"
   （§9 第 9 条；**纯健壮性，并入任一批次顺手做，不单独开工**）。
9. **`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `COST_RATIO_ALERT_THRESHOLD`**（m6 §6 另两个配置项）：
   在对应批次回填，**别顺手补齐**。
10. **日志 `message` 正文的脱敏**：逐个把 `mask()` 补到写敏感值的日志语句上。
