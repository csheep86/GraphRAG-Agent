# P5-I0 集成实录 · **版本号定长** + M6 文档状态对账（GUI 批次的前置）

> **日期** 2026-10-08　**分支** `main` 直推　**执行模式** 无人值守
> **上游** [`../P5-H/integration-log.md`](../P5-H/integration-log.md)（`main` = `f503e8a4`，CI run `37769050202` 四 job 全绿）
> **边界** [`proposal.md`](./proposal.md) §3（**10 条** Non-goals）｜**任务** [`tasks.md`](./tasks.md)
> **性质** 这不是"技术债洁癖"，是**卸掉一个 GUI 上线当天就会被撞到的 500**；
> 文档那一段是对同一句话的三个副本做纠偏（其中一处会把 GAP-F2 讲反）。

---

## 1. 一句话

把增量版本号从「在 base 上拼后缀」（每级 +11 字符）改成**定长**
（`<%Y%m%dT%H%M%SZ>-inc-<8hex>` = 恒 **29** 字符），
顺手把三处已经过期、且有一处会误导的 M6 文档状态更正过来。¥0、无迁移、无新依赖。

## 2. 为什么是这一刀

### 2.1 事实链（全部实读，不是推算）

| 环节 | 事实 | 位置 |
|---|---|---|
| 生成规则 | `f"{base}-inc-{uuid4hex6}"` —— **每级 +11 字符**，且 base 自己也是拼出来的 | `backend/app/services/kg/incremental.py:522`（改前） |
| 列宽 ① | `kg_versions.version` = `String(64)` | `backend/app/db/models.py:286` |
| **列宽 ②③** | `ontology_actions.kg_version` / `result_kg_version` **也是 `String(64)`** | `backend/app/db/models.py:1069` / `:1071` |
| 基线号格式 | `YYYYMMDDTHHMMSSZ-<8hex>` = **25 字符** | `backend/scripts/import_to_neo4j.py:583-585` |

```
1 级 36 ✓ ／ 2 级 47 ✓ ／ 3 级 58 ✓ ／ 4 级 69 ✗
```

⇒ **连续第 4 次校正必然抛 PG「value too long」**，形态是 **500**，
走不到任何既有业务错误码（不是 404 / 409 / 501）⇒ 前端只能显示"未知错误"。

> **⚠️ 本批最重要的一个修正**：动手前我以为限制面只有 `kg_versions` **一列**；
> 写代码时才核出 **三列**（`ontology_actions` 那两列同样 64）。这直接决定了
> §5 第 1 条那个自我纠错 —— 见那里。

### 2.2 为什么必须排在 GUI 之前

**P5-H 收口指针第 2 条就是 GUI**（m6 §1.1 批次 B）。GUI 的本质是把「连续校正」
开放给人手 ⇒ **人手连点 4 次 rename 是常规操作** ⇒ 这是**上线当天**的事，
不是"用久了可能遇到"。所以它是 GUI 的**前置**，不是可选项。

### 2.3 为什么不塞进 GUI 批次

- ① 要改 `incremental.py` ⇒ 与 GUI 的 Non-goal「不改后端写侧」相邻，
  混进去就变成"GUI 批次里顺手改了写侧"，正是要防的那一类；
- ②③ 纯文档，塞进去会让该批次 `check_session_drift` 的 S2 一次摊太开；
- 三者各自 **¥0 / 无迁移 / 无新依赖**，半天收得干净 ⇒ 单独成批最便宜。

## 3. 决策补录（**执行期才需要回答的部分**）

| # | 冲突点 | 取法 | 理由 |
|---|---|---|---|
| **P5I0-1** | 版本号不再自带父子信息 | 接受，并在 `_next_version` docstring 写明真源 | 父子链的唯一真源是 `ontology_actions` 两个版本列（**ADR-0008 §3**），版本号字符串从来不是消费者；`incremental.py` 完成日志本来就同时打了 `base_version` / `new_version` |
| **P5I0-2** | 两处测试依赖 `<base>-inc-%` 前缀 | 改为**不依赖字符串格式** | 见 §5 第 2 条 |
| **P5I0-3** | `base` 形参怎么办 | **删**（调用方只有一处） | 留着会成为"将来有人用"的入口，而它已经不参与生成 |
| **P5I0-4** | 要不要顺手把三列都扩到 255 | **不要** | 见 §4.3 的方案对比；扩列要写迁移 + 触碰 **G-6 迁移等价性**，而收益是"继续允许版本号无限增长" —— 那是把问题往后挪 |

## 4. 方案对比：**为什么不扩列**（这是本批唯一真正的技术决策）

| | **A：定长（采纳）** | B：扩到 255 |
|---|---|---|
| 迁移 | 无 | 要写 Alembic 迁移 |
| **G-6 迁移等价性** | 不触碰 | **必须举证** |
| 语义 | 版本号长度与校正次数**解耦**（根本解法） | 只是把阈值从"4 级"推到"20 级"，之后仍会撞 |
| 副作用 | 版本号不再自带父子信息（P5I0-1，已登记） | 父子信息靠字符串长度硬撑，本身就是脆弱设计 |

安全性**逐条核过**：全仓 grep 确认**没有任何业务代码**从版本号字符串反解父子链；
真正依赖 `-inc-` 前缀的只有**两处测试辅助**（清理 / 读取），本批已改为不依赖格式。

## 5. 本批踩到的坑（**这三条都值得留档**）

### 5.1 ⚠️ 差点把「测试数据限制」当成「产品限制」（自我纠错）

改完 `_next_version` 后，我去把 P5-H 那条被迫用短后缀（`-i1`）的 5 级链用例
改回**产品真实后缀** `-inc-000001` —— 看起来像"限制已解除，绕行代码该清了"。

跑之前核了一下列宽才发现：**那条用例的版本号会写进 `ontology_actions` 的两列**，
而它们也是 `String(64)`；5 级真实后缀会让 head 到 **72 字符 ⇒ 照样撑爆**。

两者的区别是：

| | 谁产出的 | P5-I0 解决没有 |
|---|---|---|
| 产品生成的版本号 | `_next_version` | ✅ 已解决（恒 29 字符，多少级都安全） |
| 测试自己造的多级字符串 | 用例里的 f-string | ❌ 不存在"解决" —— 那是测试数据自己选的长度 |

⇒ 最终那条用例**保持短后缀**，只把注释改成准确的说法（写明"这是测试数据限制，
与产品无关；产品侧的格式监督见本批新增的看门狗用例"）。

**教训**：`String(64)` 这种限制有两个面 —— **产品产物** 与 **写入方的数据**。
改产品格式只解决前者；看到"测试里有个绕行"就急着"清理技术债"，
很容易把两件事混成一件事。⇒ 判断标准：**去读那个值最终落到哪一列**。

### 5.2 前缀依赖 = 产品格式泄漏进测试（P5I0-2）

`test_kg_incremental_rebuild.py` 有两处靠 `LIKE '<base>-inc-%'` 认领"本用例产出的行"：

| 位置 | 用途 | 改成 |
|---|---|---|
| `:617` | 断言"失败路径一行都没落" | **调用前后快照对比**（直接数没多出行 —— 语义更强，不再靠命名约定推断） |
| `pg_fixture` 清理 | 删干净本用例的行 | 按 **`trace_id`** 精确删（新版本行由 `create_pending` 继承 action 的 trace） |

改完的断言**更强**：原来"没匹配到前缀"只能推出"没落符合该格式的行"，
现在推出的是"这个 org 下**行数量一个都没多**"。
且将来再改版本号格式时它们不会静默失效。

### 5.3 契约描述有两处副本（**其中一处会把 GAP-F2 讲反**）

```
openapi.yaml:5267（ontology tag）      ← 过期的文本，但它是**导出产物**
真源却在  backend/app/core/openapi.py:72-77
```

`contracts/openapi.yaml` 是 `export_openapi.py` 的**导出产物** ⇒ 手改它会被
`--check` 判漂移（同一句话也同步进了 spec §5.5 的注释，给下一个人看）。

第二处更值得说：原文那句「**只有 `POST /ontology/confirm` 会写生效状态**（其余端点不改本体）」
是 GAP-F2「严禁 LLM 自动修改本体」的落点，但**自 P5-G 起它会把约束讲反** ——
三个改本体的动作确实存在，只是**全部由人工触发**（人在 GUI 上回车才执行），
LLM 侧只有 `cold-start` 产出建议、建议必须再经 `confirm` 才生效。
⇒ 把话说成"其余端点不改本体"，读的人会以为"它们还不能改"。

## 6. 实测结果（**全部是跑出来的**）

### 6.1 本批新增 / 改动的用例

| 文件 | 结果 |
|---|---|
| `tests/test_kg_incremental_rebuild.py` | **9 ⇒ 11 passed**（+ 定长用例 + 看门狗用例） |
| 同上，两处前缀依赖改造 | 改后**仍绿**，且断言更强（§5.2） |
| `tests/test_version_read_view.py` | 只动注释；**13 passed** |

### 6.2 反向判据：**既有批次的判据一条都没被打掉**

| 套件 | 结果 | 说明 |
|---|---|---|
| `test_version_read_view.py` + `test_version_chain_readers.py` + `test_ontology_correction_actions.py` | **31 passed** | P5-H / P5-G 的判据全在，**断言未改** |
| `test_kg_incremental_rebuild.py` 原 9 条 | 全绿 | P5F-3（增量重写节点数 = 校正节点数）仍成立 |

### 6.3 全量

| 项 | 结果 |
|---|---|
| 本地全量（带 `GRAPH_REAL_NEO4J_*`） | **1138 passed / 4 skipped / 2 failed** —— 比本批开工基线 **+2**（正是新增那两条）；2 条 failed 是**已知的本地环境债**（g25 两条，依赖 CI 才有的受控种子语料，CI 上有导入步骤 ⇒ 那 2 条在 CI 上绿） |
| **G-9 T1 / G-10 T2**（本批最相关：改的是唯一键字段） | `test_guardrails_graph.py` + `test_guardrails_rls.py` + `test_guardrails.py` = **47 passed**；`-k "g9 or g10 or t1 or t2"` = **11 passed**；断言**未放宽** |
| `check_startup_readiness.py` | 摘要计数（`OK=77 ~~=1 --=1 !!`…）与开工时**逐字相同** ⇒ 未倒退（主要护栏仍是 17 条 `[OK]`、`[~~]` 0 条、`[--]` 0 条） |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff，**28 路径不变**（比 P5-H 提示词写的 26 多 2 —— **以脚本为准**，已在 proposal 判据 7 更正） |
| `frontend` `npm run gen:api` | 生成成功且 **`src/types/api.d.ts` 零变更**（tag 描述不进 TS 类型，与预期一致） |
| `check_session_drift.py --since HEAD~2` | S1 读到 **10 条** Non-goals；S2 **8 文件 / 170 新增行**（阈值 25 / 600）；S3 无事；**S4 命中 ⇒ 已执行 `gen:api`（零变更）**；S5 无新增模块 —— 全部 `[OK]` |
| 清理 filepath verification | 单独跑 `test_kg_incremental_rebuild.py`（11 passed）后回读 PG：该 org 下 `kg_versions` **只剩基线那 1 行**、`ontology_actions` **0 行** ⇒ 新的 `trace_id` 清理**没有漏删** |

### 6.4 ⚠️ 一次**伪失败**（值得单独记一笔，避免下一个人绕远路）

跑 `-k version` 子集时遇到过：

```
FAILED tests/test_kg_build_executor.py::test_kg_build_reuses_existing_kg_version_row
E   AssertionError: assert 9 == 1
```

第一反应当然是"我把版本号改坏了"。实际不是 —— 那条用例的最后一句是

```python
rows = session.execute(select(KgVersion.id).where(KgVersion.org_id == org)).all()
assert len(rows) == 1
```

它断言的是**整个 org 下只有一行**，而当时库里躺着 **8 行别的用例的残留**
（我前面反复跑 `-k` 子集时中断留下的），只要脏一行就让
`test_kg_build_executor` 红 —— **与本批改动无关**。

核实方式（三条，都做了）：

1. 手动回读 PG：把残留行逐条列出来，确认它们不是本批产出的；
2. 清干净后**单独**跑 `test_kg_build_executor.py` ⇒ **5 passed**；
3. 清干净后跑 `-k version` ⇒ **95 passed**，且**跑完残留为 0** ⇒ 本批改的那套
   `trace_id` 清理没有泄漏。

**留下的坑**：`assert len(rows) == N` 这种**全局计数断言**会被任何残留击穿，
误报成本很高 —— 它看起来像"某个Assert 被修改坏了"，实际是环境污染。
判据应该改成"与自己有关的行"而不是全表计数。本批没动它（不在边界内），
登记为下一批顺手项。

## 7. 提交（分段，便于整笔 revert）

| # | 提交 | 范围 |
|---|---|---|
| 1 | `a8a89631` `fix(m6)`: 版本号定长 | `backend/app/services/kg/incremental.py` + 两个测试文件 |
| 2 | `0105e8d6` `docs(m6)`: 三处状态更正 | `backend/app/core/openapi.py` + `contracts/openapi.yaml` + `specs/m6-*.md` + `docs/delivery-requirements-and-guardrails.md` + `docs/acceptance-traceability-matrix.md` |
| 3 | `docs(chore)`: 本批 SDD 产物 | `changes/P5-I0/` |

| 4 | `166e4122` `docs(chore)`: 回登 CI 终裁 | `changes/P5-I0/integration-log.md` |

CI 为终裁（R-10）：**run `37786962196`**（commit `166e4122`）**conclusion = success**，
`gh run watch --exit-status` **退出码 0**；后端 job 内 `check_seams` **OK 12**、
pytest **1139 passed / 5 skipped / 0 failed**（基线 1137 ⇒ **+2**，正是新增那两条）；
前端 job `gen:api` 无漂移。

## 8. 本批**不许外推**（完成本批 ≠ 以下任何一条）

- **版本号不炸了 ≠ 本体校正可用**：**批次 B（GUI）仍未开工**；三端点虽已实装，
  但**没有 UI 就走不到人工触发**这一环。
- **文档改成 ✅ ≠ 需求变了**：DR-B6 / DR-B7 的**判据强度一字未动**
  （仍是「必须 PG / CI 必过 / 禁 `local_only`」三条），改的只是"和护栏状态码同步";
  口诀是「DR 那一行写的是事实，不是愿望」。
- **`ontology` tag 描述改了 ≠ 端点实现变了**：它<｜hy_place▁holder▁no▁813｜> 的是 **P5-G** 的实现。
- **不需要迁移 ≠ 可以随便改版本号**：任何再次引入「把 base 拼进来」的改动，
  看门狗用例会**先红**（这就是那条用例存在的全部理由）。
- **三列仍是 `String(64)`**：将来任何"版本号要承载更多信息"的设计
  （如加 org 前缀 / 时间戳精确到秒以下）都会重新撞到它。
- **`entity_merge_candidates` 仍无读端点**：GUI 批次要自己裁决（proposal D3）。
- **本地绿 ≠ CI 绿**：本机 Neo4j 常是停的，且本地有 2 条 g25 失败（缺 CI 种子语料）。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着
  「pytest 全绿 ≠ 护栏在拦」。

## 9. 下一批指针（**按本批实际结果更新**）

1. **本体校正 GUI（批次 B / m6 §1.1 第 2 条）** ✅ **前置已清，可以做**。
   开工第一步要裁决的仍是 **proposal D3**：`entity_merge_candidates` **没有读端点**
   （契约 28 条路径里没有），而 spec 明文要求 GUI「与该表**绑定**」⇒
   要么补 `GET /api/v1/ontology/candidates`（契约先行五步），
   要么显式登记偏离。**别顺手扩大**成复核工作流（那是 M2 的 S9.13-2）。
2. **`GET /cost/dashboard` + `cost_metrics`**（批次 D，MVP 准入 C3-a / C3-b）：
   `cost_ratio` 阈值 TBD-7 **Sprint 13** 才收敛 ⇒ 之前拿不到判据。
3. **剩余读路径切换 + `agents.py` 接线**（P5-H §9 指针 1）：M4 端到端仍单版本。
4. **多跳推理改为 id 级图遍历**（取消 **P5H-6** 限制）。
5. **给 `kg_versions` 加 `parent_version` 列**：如需让版本号自带父子信息，
   **先**得回答"三列的 64 怎么够" —— 与本批 §4 的方案 B 是同一笔账。
6. **概览三个统计值口径**（P5H-4）：等 GUI 有了再裁决（GUI 才有消费者）。
7. **`human_review` 队列读端点**（M2 S9.13-2）。
8. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2；**已连续六批**有意不做）。
9. **`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `COST_RATIO_ALERT_THRESHOLD`**（m6 §6 另两个配置）：
   在对应批次回填，**别顺手补齐**。
10. **`ontology/confirm` / `cold-start` / `active` 仍是占位**（批次 A）：
    契约不会告诉你是占位 —— 现在只有 `openapi.py` 的 tag 描述会，
    ⇒ 实现它们之前**先看那一段**。
11. **日志 `message` 正文的脱敏**：逐个把 `mask()` 补到写敏感值的日志语句上。
12. **`test_kg_build_executor.py::test_kg_build_reuses_existing_kg_version_row` 的
    `assert len(rows) == 1`**（§6.4）：全表计数断言 ⇒ 任何残留都会让它红，
    且症状看起来像"最近的改动把它弄坏了"。改成"只数与本用例有关的行"。
    **纯健壮性**，不涉及语义 ⇒ 并入任一批次顺手做，不单独开工。
