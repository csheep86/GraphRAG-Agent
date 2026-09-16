# ADR-0002 · Neo4j ↔ PostgreSQL 一致性边界：PG 为 Source of Truth + Saga 补偿

| 项 | 内容 |
|---|---|
| **ADR 编号** | ADR-0002 |
| **对应 TBD** | **TBD-2**（Neo4j ↔ PostgreSQL 一致性边界） |
| **状态** | **Accepted（已接受）** |
| **决策日期** | 2026-09-16 |
| **决策者** | 架构师 |
| **关联模块** | M2（主写入）、M3（消费）、M4（消费） |
| **关联规格** | [`specs/m2-extract-kg.md`](../../specs/m2-extract-kg.md) §3 验收 4 / §4.4 / §5.4、[`specs/m3-graphqa-citation.md`](../../specs/m3-graphqa-citation.md) §4.1 / §5.4、[`specs/m4-affiliation-detection.md`](../../specs/m4-affiliation-detection.md) §3 验收 2 |
| **关联硬约束** | H11 / **H12（F3：引用覆盖率 < 100% → 直接 NO-GO）** |

---

## 1. 背景（Context）

M2 的一次抽取需**同时写两个存储**：

- **Neo4j**：`:Document` / `:Chunk` / `:Entity` / `:Evidence` 及关系；
- **PostgreSQL**：`kg_versions` 版本记录、`entity_merge_candidates` 消解候选。

**两者不共享事务**（Neo4j 不支持 XA），因此必须显式定义一致性边界，否则会出现两类脏数据：

| 失败形态 | 后果 | 严重度 |
|---|---|---|
| **幽灵版本**：PG 成功、Neo4j 失败 | `kg_versions` 标 `active` 但图谱无数据 → M3 查不到证据却以为版本有效 → **要么拒答、要么诱发 LLM 编造引用** | 🔴 **致命（触发 F3 NO-GO）** |
| **孤儿图数据**：Neo4j 成功、PG 失败 | 图谱有节点但无版本记录 → M3 按 `kg_version` 过滤时**静默漏数据** | 🟠 高（隐性正确性缺陷） |

**决策底线**：**绝不允许「幽灵版本」**。

---

## 2. 决策（Decision）

**PostgreSQL 为 Source of Truth；写入顺序严格「先 PG 后 Neo4j」；以 Saga 补偿（状态机 + 幂等重放 + 对账）收敛不一致。**

写入时序（**不可调换**）：

| 步 | 动作 | 存储 | 版本状态 |
|---|---|---|---|
| **1** | 在 `kg_versions` **插入**记录（`status = writing`） | PostgreSQL | `writing` |
| **2** | 写入 Neo4j 节点 / 关系（带 `kg_version`） | Neo4j | — |
| **3a** | 成功 → `UPDATE kg_versions SET status = 'active'` | PostgreSQL | `active` |
| **3b** | 失败 → `UPDATE kg_versions SET status = 'failed'` + 记录错误 → **不对外提供该版本** | PostgreSQL | `failed` |

**查询层（M3 / M4）只认 `status = 'active'` 的 `kg_version`。**

---

## 3. 关键设计约束

### 3.1 版本状态机

```
writing ──Neo4j 成功──▶ active ──新版本激活──▶ superseded
   │
   └──Neo4j 失败 / 对账判定中断──▶ failed
```

- `writing` 是**新增状态**（原 M2 §4.4 枚举为 `active / superseded / failed`，**必须补入 `writing`**）。
- `superseded`：新版本置 `active` 时，同 scope 旧版本转为 `superseded`（**仅标记，不删**，对齐 M2 §3 验收 4）。
- `failed` 版本**永不对外提供**，但**保留记录**以支撑审计与 `kg_version` 回滚（TBD-3）。

### 3.2 查询层强制过滤

- `GET /internal/kg/active` **只返回 `status = 'active'`** 的最新版本。
- M3 §4.1 `kg_version` 缺省值 = 最新 `active`；**若请求显式指定了非 `active`（`writing` / `failed` / `superseded`）版本，必须显式拒绝（409 `KG_VERSION_NOT_ACTIVE`），不允许静默降级到最新版**——静默降级会掩盖不一致，是最危险的失败模式。
- M4 场景节点必须与 M2 通用节点**共享同一 `active` `kg_version`**（M4 §3 验收 2：不分裂版本）。

### 3.3 幂等（Saga 重放的前提）

- Neo4j 写入**必须使用 `MERGE` 而非 `CREATE`**，以 `(id, kg_version)` 为幂等键。
- 补偿与重试**可安全重放**：重复执行不产生重复节点 / 关系。

### 3.4 对账兜底（Reconciliation）

进程在「PG 已提交 `writing`、Neo4j 结果未知」窗口崩溃时，**若无对账则会残留 `writing`**。故：

- **启动时 + 周期性**扫描 `status = 'writing' AND updated_at < now() - interval '15 minutes'` 的版本；
- 逐条探测 Neo4j 中对应 `kg_version` 是否存在完整数据：
  - **存在** → 置 `active`（补记 `reconciled_at`）；
  - **不存在 / 不完整** → 置 `failed`，并由清理任务按 `kg_version` 物理清除残留；
- 对账动作写 M5 审计（`action = kg.version.reconcile`）。

> **一致性级别声明**：本方案提供的是**最终一致（eventual consistency）+ 可对账**，**不是**跨库强一致。这是 Neo4j 不支持分布式事务下的现实上限。

---

## 4. 后果（Consequences）

### 正面
- ✅ **无幽灵版本**：Neo4j 失败即 `failed`，绝不对下游暴露。
- ✅ **单一真值源**：版本是否可用完全由 PostgreSQL 决定。
- ✅ **可重放 / 可对账**：`MERGE` 幂等 + 周期性对账，容忍崩溃窗口。
- ✅ **支撑 TBD-3**：`failed` / `superseded` 记录保留，为回滚 API 留出数据基础。

### 负面（已知并接受）
- ⚠️ **多一个中间状态**：`writing` 迫使下游严格过滤；**任何未过滤 `active` 的查询都是潜在 bug**（需 lint / 测试护栏）。
- ⚠️ **非强一致**：极端崩溃窗口依赖对账收敛（最长 15 分钟窗口）。
- ⚠️ **`writing` 残留需监控**：对账任务本身不可用时，会累积脏版本。

---

## 5. 备选方案与取舍

| 方案 | 拒绝理由 |
|---|---|
| **先 Neo4j 后 PG** | 直接产生**孤儿图数据**（有图无版本），M3 静默漏数据，且无 PG 记录可用于对账。 |
| **XA / 两阶段提交** | Neo4j 不支持 XA，**技术上不可行**。 |
| **Neo4j 为 Source of Truth** | 违背 PRD §6.3「PG 承载元数据 / 业务表 / 权限 / 审计」之分工；且版本表本身就在 PG。 |
| **事务性 Outbox（消息队列补偿）** | 需引入 Broker，与 **ADR-0001（零新增依赖）** 冲突；**记为未来升级选项**。 |
| **不做版本、直接覆盖写** | 违背 M2 §3 验收 4（历史版本不删除 / 不覆盖），丧失回滚能力。 |

---

## 6. 对既有规格 / 契约的影响（**需同步，勿自动补全**）

| # | 文件 | 需变更点 |
|---|---|---|
| 1 | `specs/m2-extract-kg.md` | §4.4 `kg_versions.status` 枚举 **补 `writing`**；§3 验收 4 补写时序（`writing → Neo4j → active / failed`） |
| 2 | `specs/m2-extract-kg.md` | §5.4 `GET /internal/kg/active` 明确「仅 `active`」；`kg_versions` 建议补 `error_code` / `error_detail` / `reconciled_at` |
| 3 | `specs/m3-graphqa-citation.md` | §4.1 / §5.4 明确 `kg_version` 必须为 `active`；补「显式指定非 `active` 版本即拒绝」语义 |
| 4 | `specs/m4-affiliation-detection.md` | §3 验收 2 明确「共享同一 `active` `kg_version`」 |
| 5 | `contracts/openapi.yaml`（实现阶段） | `kg_version` 查询端点返回 `status`；补 `409 / KG_VERSION_NOT_ACTIVE` 语义 |

> 按 `CODEBUDDY.md`「功能预留原则」，**以上变更须经人工确认后执行，不得由 AI 自动补全规格或契约**。

---

## 7. 参考
- `specs/m2-extract-kg.md` §3 验收 4 / §4.4 / §5.4
- `specs/m3-graphqa-citation.md` §4.1 / §5.4
- `specs/m4-affiliation-detection.md` §3 验收 2
- `docs/03-prd.md` §6.1 / §6.3 / §8（TBD-2、TBD-3）

---

> **ADR-0002 结束。** 状态 **Accepted**，落地前须完成 §6 的规格 / 契约同步。
