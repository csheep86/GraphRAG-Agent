# P5-G · M6 批次 B'：**三端点接线** merge / split / rename

> **日期**：2026-10-08　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-F/integration-log.md`](../P5-F/integration-log.md)（`main` = `b581e240` → `70513cf7`，CI run `37732319117` 四 job 全绿）
> **边界**：本文件 §3（**11 条** Non-goals，逐条对照）｜**花销**：预期 ¥0（图操作 + PG 写入，不调 LLM）
> **任务拆解**：[`tasks.md`](./tasks.md)

---

## 1. 目标（一句话）

把 `specs/m6-ontology-incremental.md` §3.2 验收 3 / 4 / 5 的三个校正端点从**占位骨架**做成真的：
`POST /ontology/merge` / `/split` / `/rename` 各自完成 图操作 → 写 `ontology_actions` →
**调用 P5-F 落地的增量重算** → 回 `{kg_version, status: "applied"}`。

四刀：

1. **三端点实现**（服务层 `app/services/kg/correction.py` + 路由编排）：
   - `merge`：`:Entity` 合并（`MERGE` 幂等键 `(id, kg_version)`，ADR-0002 §3.1）；受影响 = 左右两个；
   - `split`：创建 N 个新 `:Entity`（`new_entities[]` ≥ 2）并按「**默认同名**」规则迁移关系，
     原节点置 `status='split'`（m6 §4.5）；受影响 = 原节点；
   - `rename`：改 `:Entity.canonical_name`，旧名写入 `:Entity.aliases`（沿用 M2 §4.3）；受影响 = 该实体。
2. **RBAC 接线**：三端点各挂 `require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)`（照 `ontology.py:144`
   的形态），并在 `tests/test_rbac.py:62 PROTECTED_ENDPOINTS` 登记三条（6 → 9）。
3. **`entity_merge_candidates.status = applied`** + **升版 `specs/m2-extract-kg.md`**
   （§4.5 注脚 + §3 验收 3，M2 spec 注脚自己点名要求「M6 落地时须先升版本表」）。
4. **裁决并落地 P5F-4**（D9）：新版本图完整性 —— 见 §5 D9 与 §6 判据 9。

## 2. 为什么是这一刀

- **前置已全部兑现**：契约侧三条路径（`contracts/openapi.yaml` `:5006` / `:5146` / `:5076`）与
  `status: const: applied`（`:2535`）**已在**；DB 侧 `entity_merge_candidates.status` 的 CheckConstraint
  **已含 `applied`**（`models.py:524-525`）；**增量重算（唯一的真代码前置）P5-F 已落地**
  ⇒ 五步里只剩「升版 M2 spec」这一个文档动作，而它按 M2 注脚原文应当**与代码同批**（本批）。
- **三端点是「契约承诺了却没实现」的最大一块**：`routes/ontology.py:179/200/223` 的 summary
  明写「占位骨架」，恒返回 501。
- **它是 M6 用户故事的主干**：§2 第二条（"合并 / 拆分 / 改名"）与第三条（"校正触发增量重算、
  不要全量重建"）用户故事**都**要靠它落地；没有它，P5-F 的增量重算永远"只有测试引用它"
  （P5-F §4 已登记的 S5 状态）。
- **本批 ¥0 且判据可机械**：三个动作都是**图操作 + PG 写入**，不调 LLM。

### 2.1 ⚠️ 契约同步五步里**有三步在本批不适用**（别照抄去做）

| 五步里的步骤 | 现状（2026-10-08 实读） | 本批处置 |
|---|---|---|
| ① 升版 M2 spec（§4.5 枚举加 `applied` + §3 验收 3 补一条） | M2 §4.5 表 `:128` 与注脚 `:132-136` 已预留，但仍是「M6 前向预留、本阶段不实现」口径 | ✅ **本批做**（与代码动作同批）。**只改注脚与验收 3 的那句注，不重排编号**（R5） |
| ② 改 Pydantic `EntityMergeStatus` 枚举 | **该枚举不存在**（`grep EntityMergeStatus` 全仓 0 命中）；`entity_merge_candidates` **只写不读、不进契约**（`models.py:516-518` 注释明写「不为走出 diff 而造端点」） | ❌ **无对象** —— 不新造一个不进契约的枚举。③ 的位置改由**代码动作**（真写 `status='applied'`）兑现 |
| ③ 重导契约 / ④ `gen:api` / ⑤ CI 零漂移 | 契约里三条路径 + `const: applied` **都在** | ✅ 用 `export_openapi.py --check` **证明**。**但**路由的 `summary` / `responses` 会从「占位 501」改成真错误语义 ⇒ 触发 **D6**，须走完整同步五步（见 §5 D6） |

三条不适用的会在 `integration-log.md` 里**逐条写明为什么不适用**。

## 3. 明确不做（**11 条 Non-goals**，逐条对照）

1. **不做 GUI / 前端业务代码**：m6 §1.1 批次 B 的 GUI 是另一批；本批**只**在 D6 判定必需时再生 `api.d.ts`。
2. **不改 `specs/m6-ontology-incremental.md`**：M6 规格齐全。⚠️ **升版 `specs/m2-extract-kg.md` 是本批必做项，不属本条**。
3. **不动 RLS / RBAC 的判定逻辑**：只做「端点挂上 `require_permission`」这个接线动作；`rbac/deps.py:54` 一行不改。
4. **不碰成本仪表盘 / `cost_metrics` / `COST_RATIO_ALERT_THRESHOLD`**：批次 D。
5. **不动 P5-F 的增量重算状态机语义 / P5-E 的脱敏器 / P5-D 的私域守卫**：本批**调用**增量重算，**不重写**它。
6. **不新增第三方依赖**：现有 `neo4j` 驱动 + 标准库即可。
7. **不新增错误码**（预期）：跨 org 复用 `FORBIDDEN`；实体不存在复用 `ENTITY_NOT_FOUND`；
   无 active 版本复用 `KG_VERSION_NOT_ACTIVE`；增量重算失败沿用 P5-F 的落库码。
   若确有必要 ⇒ `errors.py` **四处**字典齐加。
8. **不改 `kg_versions` / `entity_merge_candidates` 的状态机取值**：复用既有 CheckConstraint（`applied` 已含）。
9. **不做"全量重建兜底"**：校正失败就**显式失败**并落 `error_code`，不得静默回落全量重建。
10. **不做成本度量 / token 打点**：属批次 D。
11. **不动契约**（除非 D6 判定必需）：三个端点的请求 / 响应模型契约里全有。

## 4. 采纳的决策（来自新会话开场提示词 §5）

| # | 决策 | 处置 |
|---|---|---|
| D1 | 主题 | ✅ 定 **M6 三端点接线** |
| D2 | 是否新增配置 | **预期不新增**；若确需 ⇒ ① 有真实消费者 ② 同步 `.env.example` ③ 不得占位 |
| D3 | 图操作在哪实现 | **新增服务层** `app/services/kg/correction.py`；路由层只做编排 + 错误映射（路由层不写 Cypher） |
| D4 | 动作行怎么落 | **先落 `ontology_actions`（拿 `action_id`）→ 再调增量重算**；`target_entities` 按动作给（merge 2 / split 1+N / rename 1） |
| D5 | `kg_version` 字段 | 动作行的 `kg_version` = **操作时的 active 版本**；新版本由 `result_kg_version` 承载 |
| D6 | 契约会不会动 | 请求 / 响应模型**零改动**；但 `summary` / `responses` 必然变 ⇒ **走同步五步**，**不算升级** |
| D7 | 跨 org | 目标实体必须属当前租户 ⇒ 否则 **403 `FORBIDDEN`**，**不**降级为「只处理同租户的那个」 |
| D8 | 审计 | **不**手写 `audit_log`：M5 的 `AuditMiddleware` 已全量写；本批只**实测确认有一条**并登记 |
| D9 | P5F-4 完整性 | 取**建议最小形态**：新版本仍只含受影响子图（沿用 P5-F），并新增一条**显式断言**把它变成已知事实 + integration-log 登记缺口 |
| D10 | 成本敞口 | 本批**预期 ¥0** |

## 5. 本批需要登记的**决策补充**（spec 未写清处，按「先缩范围、后登记」处置）

| # | 冲突点 | 本批取法 | 登记理由 |
|---|---|---|---|
| **P5G-1** | 校正变换落在**哪个版本**上：spec §3.2 验收 3 文本顺序是「更新 `:Entity` 节点 → 触发增量重算」，但「更新旧版本节点」违反 ADR-0002「历史版本不删不改 / 旧版本一条不动」 | **先增量重算**（受影响集 = base 里**已存在**的实体）→ 产新版本 → **再在新版本上施加校正变换** | 这是唯一同时满足「旧版本一条不动」+「split 的 N 个新节点不在 base 中（rebuild 的 probe 会拒绝）」的顺序 |
| **P5G-2** | 新版本 `source_doc_ids` 填什么 | **留空数组**：校正是**实体级**动作，本批不做「实体 → 文档」反查 | 编一个「受影响文档集」需要 `:Chunk-[:MENTIONS]->:Entity` 反查（本批无判据要求）⇒ 先留空并登记，避免造一个测不出的数据 |
| **P5G-3** | split 的「关系迁移规则」（spec 只写「按规则匹配：曾用名 / 同名 / 其他，**默认同名**」） | 取**最小可证形态**：关系的**对端实体** `canonical_name` **等于**某个新实体 `canonical_name` ⇒ 迁到那个新实体（保方向）；**匹配不上 ⇒ 留在原节点**（不丢、不猜） | §10 第 2 类的三步自检：① 不在 Non-goal 里 ② 可整体缩小到「默认同名」这一条并登记 ③ 故不升级 |
| **P5G-4** | merge 的右侧节点怎么处理 | 属性并入左侧（`aliases` 吸收右名 + 右别名，`confidence` 取 max），**右侧的关系按原方向重挂到左侧**，右节点 `DETACH DELETE` | 契约 description 已明写「被并入侧的实体 id（合并后不再独立存在）」 |
| **P5G-5** | P5F-4 消费侧完整性 | **本批不解决**，做成显式断言 + 缺口登记（D9） | 解决它 = 把全图复制进新版本 ⇒ 直接违反 P5F-3「增量重写节点数 = 校正节点数」的机械判据 |

## 6. 验收判据（**每条都要能贴机器输出**）

1. **三端点不再是 501**：三端点各一条 200 用例，响应 `{kg_version, status: "applied"}`；
   且 `kg_version` **不等于**操作前的 active 版本。
2. **图操作是真的（真 Neo4j）**：merge ⇒ 新版本只剩左侧节点且属性按预期合并；
   split ⇒ 新增 N 个节点且原节点 `status='split'`；rename ⇒ `canonical_name` 变了且 `aliases` 含旧名。
   **断言对象是图里的实际节点 / 属性，不是响应体**。
3. **增量重算真被触发**：`ontology_actions` 对应行 `result_kg_version` **非空**（真 PG 读回），
   且 `kg_versions` 新增一行 `status='ready'`。
4. **`entity_merge_candidates.status = applied`**：merge 后对应候选行由 `human_review` → `applied`（真 PG 读回）。
5. **M2 spec 已升版**：`specs/m2-extract-kg.md` §4.5 注脚与 §3 验收 3 口径已改为「M6 已落地」；**编号未重排**（R5）。
6. **RBAC 生效**：三端点挂了 `require_permission`；`PROTECTED_ENDPOINTS` 已登记三条 ⇒ 参数化用例
   **自动**给每条端点一条「无授权 ⇒ 403」；另有一条「有角色无该权限 ⇒ 403」。
7. **跨 org 403**：以 A org 身份操作 B org 的实体 ⇒ **403 `FORBIDDEN`**，且**不**产生任何图变更。
8. **失败路径显式失败**：注入一次增量重算失败 ⇒ 端点返回明确错误、`ontology_actions.error_code` 落库、
   `result_kg_version` 仍 NULL、**没有**回落全量重建（旧版本节点数不变）。
9. **P5F-4 已裁决且有判据**：「以新 `kg_version` 读图 ⇒ 只看到被校正的节点」这条例外的**显式断言**
   + integration-log 的缺口登记。
10. **契约零漂移**：走完 D6 同步五步后 `export_openapi.py --check` 零 diff、**26 路径不变**。
11. **护栏不倒退**：`check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0。
12. **pytest 不降**：CI **≥ 1103 passed / 5 skipped / 0 failed**；既有守卫（含 P5-F 新增的
    `test_kg_incremental_rebuild.py` 9 条）**不许为让它绿而改断言**。
13. **CI 四 job 全绿**，`gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log。
