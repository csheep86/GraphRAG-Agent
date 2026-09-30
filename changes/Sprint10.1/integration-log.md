# S10 批次 B 真机验证记录（多跳的域覆盖）

> **日期**：2026-09-29 | **分支**：`feature/sprint-10`
> **环境**：Neo4j 5.26 ✅（bolt 7687）；**PostgreSQL ❌ 不可用** ⇒ 端到端问答（含 LLM）未跑，仅做图侧真机
> **探针**：`probe_b0_multihop_scope.py`（域分布）、`probe_b1_multihop_affiliation.py`（双域对照）

---

## 1. 域分布（改之前）

```
[attendance-demo-v1]  实体 2764 / 类型 14  命中多跳终点: 9 类      -> 多跳可用
[affiliation-demo-v1] 实体  176 / 类型  7  命中多跳终点: 0 类      -> 多跳必然取不到链（空）
[None]                实体    8 / 类型  1  命中多跳终点: 0 类      -> 空
```

根因两处（都写死在考勤本体上）：① 终点白名单 `TERMINAL_ENTITY_TYPES`；② Cypher 只走
`-[rels:RELATION*1..3]-`，而关联方域的边是 **`LEGAL_REP` / `SHARES_HOLDER` / `REGISTERED_AT` /
`ISSUED` / `POSTED_IN` / `PARTY_TO` / `CONTACT_PHONE`**（真机实测 7 类共 173 条，**都带**
`kg_version` 与 `org_id`）。

## 2. 双域对照（改之后，同一批锚点、同一张图）

| 域 | 旧口径 | 新口径 | 说明 |
|---|---|---|---|
| `affiliation-demo-v1`（锚点 3 个 SUBJECT） | **0 行** | **20 行** | 首条 `SUBJECT:北京恒信达科技股份有限公司 -> LEGAL_PERSON:李芳`（`LEGAL_REP`）——正是"共享法人"疑点链形态 |
| `attendance-demo-v1`（锚点 3 个 EMPLOYEE） | 20 行，首选 `EMPLOYEE:员工 -> POLICY_CLAUSE:每月加班时间不得超过 36 小时`（`GOVERNED_BY`） | 20 行，**首选同一条** | **无 regression**；额外出 2 跳链（`EMPLOYEE -> WORK_TIME_SYSTEM -> POLICY_CLAUSE`） |

改动两处（`reasoning.py`）：

1. 终点白名单 = 已登记域的**并集**（考勤 9 + 关联方 6 = 15 类）；未登记类型（`POSITION` /
   `DEPARTMENT` / `RELATED` / `PHONE`）**仍不是**合法落点 ⇒ 新域没登记时链自然为空，不编链；
2. 边类型**不限定**（`-[rels*1..3]-`）+ 补 `ALL(n IN nodes(p) WHERE n:Entity)` 防
   `(Entity)-(Chunk)-(Entity)` 伪链；关系名取 `coalesce(r.relation_type, type(r))`。

**为什么是并集而不是"先判域再选白名单"**：域判定若看本轮子图的类型分布，会被 500 采样
带偏（R12 同族失真——粒度粗的类型常被挤出子图，判成"未知域"就交白卷）。Cypher 侧本就按
`kg_version` + `org_id` 隔离 ⇒ 并集不会跨域连出链。

## 3. 门禁

| 项 | 数字 |
|---|---|
| pytest | **619 passed / 3 skipped**（批次前 616 ⇒ +3） |
| ruff check / format | 通过 / 169 files |
| 契约零漂移 | OK（**本次无契约变更**——`reasoning_path` 契约原已存在） |
| `check_seams` | ERROR 0 / WARN 0 / OK 10 |

## 4. 已完成 / 未完成

**已完成**：域无关化（终点 + 边类型）、双域真机对照、单测 3 条（并集覆盖两域 / 未登记类型排除 /
查询参数下发并集与 hub）、多跳答对率**口径冻结**（`proposal.md` §2）。

**未完成（不伪装）**：

| # | 项 | 原因 |
|---|---|---|
| 1 | 多跳答对率**实测**（≥0.80） | 需 PG + LLM，本机 PG 不可用 ⇒ 与批次 A 的端到端验证一起补（已登记在 `../Sprint10/integration-log.md` §4） |
| 2 | 单跳 / ≥3 跳分别可答的端到端验证 | 同上 |
| 3 | 跳数参数化 | **刻意不做**（裁决 D-G）：`_MAX_HOPS=3` 与 PRD「3 跳内」一致，参数化若无消费点即无消费者配置，违反 `CODEBUDDY.md` R4 |
