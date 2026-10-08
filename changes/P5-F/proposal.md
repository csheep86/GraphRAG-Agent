# P5-F · M6 批次 C：**增量重算**（三端点唯一剩余的硬前置）

> **日期**：2026-10-08　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-E/integration-log.md`](../P5-E/integration-log.md)（`main` = `489d534c`，CI run `37728846287` 四 job 全绿）
> **边界**：本文件 §3（**11 条** Non-goals，逐条对照）｜**花销**：预期 ¥0（图操作 + PG 写入，不调 LLM）
> **任务拆解**：[`tasks.md`](./tasks.md)

---

## 1. 目标（一句话）

把 `specs/m6-ontology-incremental.md` §3.3 验收 6 / 7 的**增量重算**从零做成真的：校正动作触发后
**只重写受影响子图、不重建全图**，产出**新的文档级 `kg_version`**（不全局翻），并把它回填进
`ontology_actions.result_kg_version`。

三刀：

1. **增量重算服务**（`app/services/kg/incremental.py`）：入参 = 受影响的实体集合 + 所属文档，
   产出 = 新 `kg_version` 行（**复用** `KgVersioningService`，不另起状态机）+ 重写受影响子图
   + 回填 `ontology_actions.result_kg_version`；失败**显式失败**（落 `error_code` / `error_detail`），
   **不**静默回落全量重建。
2. **配置 `INCREMENT_REBUILD_BATCH_SIZE`**（spec §6，默认 100）：**必须有真实消费者**
   （`check_seams.py` 判据 2）+ **必须同步 `.env.example`**（S3）。
3. **同步测试 + 确认零契约漂移**（D6）：增量重算不进 API ⇒ 用 `export_openapi.py --check` **证明**它没动。

## 2. 为什么是这一刀

- **它是 M6 三端点唯一**剩余**的硬前置**：`specs/m6` §3.2 验收 3 / 4 / 5 三条**都**写着
  「**AND** 触发增量重算」+ §4.4「未走完前 5 步，`/api/v1/ontology/merge` 端点不得对外实现」。
  实读确认：契约侧三条路径（`contracts/openapi.yaml` `:5006` / `:5146` / `:5076`）与
  `status: const: applied`（`:2535`）**已在**；DB 侧 `entity_merge_candidates.status` 的
  CheckConstraint **已含 `applied`**（`models.py:524-525`）⇒ **真正的代码前置只剩增量重算**。
- **三端点是占位骨架 = 契约承诺了却没实现**（`routes/ontology.py:179/200/223`，summary 明写
  「占位骨架」）。拆掉它的正确顺序是**先补前置（本批）、再接线（下一批）**，
  不是一口气把四件事凑一批。
- **本批 ¥0 且判据全机械**：增量重算是**图操作 + PG 写入**，不调 LLM；判据是「节点数增量 = 校正节点数」
  「新 `kg_version` 行 + 状态流转」「`result_kg_version` 真被回填」三个可计数的事实。
  CI 已具备 `postgres:16-alpine` + `neo4j:5.26-community` 两个 service。

### 2.1 ⚠️ 对上一版指针的**更正**（已实读，不照抄去做）

P5-E 提示词 §12 第 1 条 / P5-C 实录 §11 第 3 条的「契约同步五步」**大半已作废**：

| 五步里的步骤 | 现状（2026-10-08 实读） |
|---|---|
| ① 升版 M2 spec（§4.5 枚举加 `applied`） | **未做**；DB CheckConstraint 已含 `applied`，该表只写不读、不进契约 ⇒ 与 ③ 同批做 |
| ② 改 Pydantic `EntityMergeStatus` 枚举 | **该枚举不存在**（`grep EntityMergeStatus` 全仓 0 命中）；契约里的 `applied` 走的是 `OntologyActionResponse.status: Literal["applied"]`（`schemas/ontology.py:273`） |
| ③ 重导契约 / ④ `gen:api` / ⑤ CI 零漂移 | **已做**（三条路径 + `const: applied` 均在，CI 契约 job 绿） |

⇒ **剩下的真前置只有增量重算**。① 本批不做（留到真正实现 merge 那一批，与「更新
`entity_merge_candidates.status = applied`」这个**动作**同批做，避免先改文档后无代码兑现）。

## 3. 明确不做（**11 条 Non-goals**，逐条对照）

1. **不实现 merge / split / rename 三个端点**：它们是占位骨架，接线归下一批。本批只补它们的前置。
2. **不改 `specs/m6-ontology-incremental.md` / M2 spec / ADR**：规格齐全（验收 6 / 7 写得很具体），
   要改 ⇒ 第 2 类升级。**含** §2.1 第 ① 步「升版 M2 spec 加 `applied`」——本批不做。
3. **不动 RLS / RBAC / 租户隔离**：DR-B4 / DR-B9 各有门禁。
4. **不碰成本仪表盘 / `cost_metrics` 表 / `COST_RATIO_ALERT_THRESHOLD`**：批次 D，另一条价值链。
5. **不动 P5-E 的脱敏器（`app/core/masking.py`）与 P5-D 的私域守卫（`app/core/egress.py`）**：两批刚收口。
6. **不新增第三方依赖**：现有 `neo4j` 驱动 + 标准库即可。
7. **不做 GUI / 前端**：本批连端点都不做。
8. **不改 `kg_versions` 的状态机语义**：复用 `KgVersioningService`；新增版本走既有三段式，**不全局翻**。
9. **不做"全量重建兜底"**：增量失败就**显式失败**并落 `error_code` / `error_detail**，
   **不得**静默回落全量重建（那会让"增量/全量成本比"永远测不出来）。
10. **不做成本度量 / token 打点**：属批次 D。
11. **不动前端 / 不动契约**（除非 D6 判定必需）：增量重算是服务端内部行为。

## 4. 采纳的决策（来自新会话开场提示词）

| # | 决策 | 处置 |
|---|---|---|
| D1 | 本批主题 | ✅ 定 **M6 增量重算** |
| D2 | 配置 | 新增 `INCREMENT_REBUILD_BATCH_SIZE`（默认 100）：① 必须有真实消费者；② 必须同步 `.env.example`；③ 不得是占位 |
| D3 | 触发入口 | **本批不给 HTTP 入口**：做成服务层函数，由**测试直接调用**验证；**不为"走出 diff"造端点** |
| D4 | 版本粒度 | **仅文档级 `kg_version`**，**不全局翻**；状态流转沿用 ADR-0002 三段式 |
| D5 | 是否新增错误码 | **预期不新增**（复用 `KG_VERSION_NOT_ACTIVE` / `KG_TENANT_LEAK` / `ENTITY_NOT_FOUND` / `INTERNAL_ERROR`）。若确有必要 ⇒ `errors.py` **四处**字典齐加，漏一处 `export_openapi.py` 直接 `KeyError` |
| D6 | 契约会不会动 | **预期零改动**；用 `export_openapi.py --check` **证明**。若真动 ⇒ 走同步五步（**不算升级**） |
| D7 | 成本敞口 | 本批**预期 ¥0** |
| D8 | 「不重建全图」怎么算机械判据 | 取**真 Neo4j 的前后节点计数**做差：增量 = 校正节点数，**不是**全图节点数；断言对象是**图里的实际计数**与**PG 里读回的行**，不是函数返回值 |

## 5. 本批需要登记的**决策补充**（spec 未写清处，按「先缩范围、后登记」处置）

| # | 冲突点 | 本批取法 | 登记理由 |
|---|---|---|---|
| **P5F-1** | spec §3.3 验收 6 写 `status = writing → active`，而现行 `KgVersioningService`（`versioning.py:79`）的状态机是 `pending → building → ready`（`activate_by_version` docstring 明写「PG 真源的 **active 语义在本表中写作 `ready`**」） | **沿用代码真源的三段式**，spec 的 `writing` ⇄ `building`、`active` ⇄ `ready`；不改状态机（Non-goal 8） | 两者是**同一状态机的两套命名**，不是粒度冲突；改代码会让 `test_kg_versioning.py` / 图谱侧既有用例整体变红 |
| **P5F-2** | 「仅文档级 `kg_version`，不全局翻」的**机械含义** | ① 新版本行 `source_doc_ids` **只含受影响文档**（≠ 全量文档）；② 图侧**只重写受影响子图**（不重跑抽取、不复制全图） | 验收 7 要求「`status = active`（= PG `ready`）才对外可查」⇒ 新版本必须可查，否则 M3 / M4 消费不到；「不全局翻」指的是**图数据不重建**，不是「不产新版本」 |
| **P5F-3** | 「节点数增量 = 校正节点数」在图里的落点 | 新 `kg_version` 下**新增/重写的节点数 = 受影响实体数 M**；**旧版本节点一条不动**（前后计数不变）；M ≠ 全图节点数 N | 这是唯一能让"增量 vs 全量"被**数出来**的形态；全量重建会写出 N 个（且需重跑抽取） |
| **P5F-4** | 新版本图的**完整性**（未受影响节点不在新版本下） | 本批**不解决**，登记为下一批（三端点接线时）裁决项 | 真正的 merge / split / rename 会改变节点集合（合并 = 节点数 -1），"新版本如何包含未受影响节点"须与端点语义同批定义；本批只补前置 |
| **P5F-5** | 服务函数本批**只有测试引用**（S5 必命中） | 明写归属 = spec §3.3 验收 6，消费者 = 下一批的三端点 | 不为"走出 diff"造端点（`models.py:517` 既有裁决口径） |

## 6. 验收判据（**每条都要能贴机器输出**）

1. **增量重算服务落地且被测试驱动**：服务层函数存在；测试直接调用它（不经 HTTP，D3）。
2. **不重建全图（**真 Neo4j**）**：校正动作前后**真连 Neo4j 取节点计数**做差：增量 = 受影响节点数，
   **不等于**全图节点数；未受影响的节点 `id` / 属性**逐条不变**。
3. **新 `kg_version` 落库且状态流转正确**：PG 读回 `kg_versions` **新增一行**，走
   `pending → building → ready`；`source_doc_ids` **只含受影响文档**（P5F-2）。
4. **`result_kg_version` 真被回填**：`ontology_actions` 对应行的 `result_kg_version` 由 NULL
   变为新版本号（**真 PG 读回**，不是函数返回值）。
5. **失败路径显式失败**：注入一次失败 ⇒ 落 `error_code` / `error_detail`，**且**没有回落全量重建
   （`result_kg_version` 仍 NULL、该版本行 `status='failed'`）；`error_detail` 敏感 ⇒ 日志不输出原文。
6. **契约零漂移**：`export_openapi.py --check` 零 diff、26 路径不变。
7. **护栏不倒退**：`check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0。
8. **pytest 不降**：CI **≥ 1094 passed / 5 skipped / 0 failed**；既有正向守卫
   （`test_kg_versioning.py` / `test_guardrails_graph.py` / `test_guardrails.py:328`）**不许为让它绿而改断言**。
9. **配置有消费者且已同步**：`check_seams.py` 仍 **0/0**；`.env.example` 已同步（`check_session_drift.py` S3 不报）。
10. **CI 四 job 全绿**，`gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log。
