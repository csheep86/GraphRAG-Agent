# Sprint 9.12 · 批次 C2 实测证据（三类算法 + 三方金额不一致）

> 时间：2026-09-29 · 应用版本 **1.4.2**（未 bump）· LLM 调用 **¥0**（确定性，不经 LLM）
> 判据出处：`specs/m4-affiliation-detection.md` §4.7（**先冻结判据，后写算法** —— R14 + D-3）

## 1. 语料增补（算法要有输入，否则产出只能是 0 或造假）

`changes/archive/2026-09-29-Sprint9.12/gen_corpus.py` **幂等**生成（可复现，非手改）：

| 目标 | 增补 | 植入 |
|---|---|---|
| `shared_phone` | `suppliers.csv` 加 `phone` | S002 / S013 同号 → 1 组 |
| `shared_legal_rep` | `suppliers.csv` 加 `legal_rep_name` / `legal_rep_id` | S004 / S010 同人 → 1 组 |
| `shared_address` | 复用既有 `address` | S006 / S014 同址 → 1 组 |
| `cycle` | 新增 `shareholders.csv`（10 行） | 2 环 / 3 环 / 4 环 各 1 组 |
| `amount_mismatch` | `invoices.csv` / `vouchers.csv` 加 `trade_ref`；新增 `contracts.csv`（8 行） | TR-0002 / 0003 / 0004 三方不齐 → 3 组 |

**对齐率未被语料变更破坏**：仍 86/90 = 0.9556（≥ 0.95），4 条未对齐原因同 S9.11。

## 2. 干跑（--dry-run）

```
语料规模   : 供应商 20 / 发票 60 / 凭证 30 / 合同 8 / 持股 10
待对齐 90 行：命中 86 / 未对齐 4 ⇒ 成功率 0.9556
规范化结果 : 主体 21 / 发票 60 / 凭证 30 / 共享与合同 65 / 关系 172
证据层     : Document 5 / Chunk 128 / MENTIONS 138
```

共享节点 19 个地址 / 19 个法人 / 19 个电话（各恰有 1 组共享 ⇒ 20 家供应商里各有一对同值）。

## 3. 真机（Neo4j + PG）

```
[2/3] MERGE 主体 21 / 发票 60 / 凭证 30 / 共享与合同 65
[2/3] MERGE 关系 172 条（五类 + 三类增补）
[self-check] 回读 Entity=176 / Relation=172        ← 与提交量一致，无静默丢失
[evidence] Document 5 / Chunk 128 / MENTIONS 138
[3/3] KgVersion -> active（耗时 ~1.2 s）

----- 可用性回读（入图 ≠ 可查）-----
addresses 19 / legal_persons 19 / phones 19 / contracts 8
registered_at 20 / legal_rep 20 / contact_phone 20 / shares_holder 10 / party_to 16
[PG] affiliation-demo-v1 -> ready（实体 176 / 关系 172）
```

## 4. 算法真机产出（**核心证据**）

```
疑点总数: 9
按类型   : {'shared_legal_rep': 1, 'shared_address': 1, 'shared_phone': 1,
            'cycle': 3, 'amount_mismatch': 3}
```

- `cycle` 3 条：`cycle_length` = **2 / 3 / 4**（交叉持股也算环 —— 长度下限 2 的理由见 §4.7.2）；
- `amount_mismatch` 3 条：`severity=high`，`details` 给出「差额 + 三方各自金额」：

| trade_ref | 合同 | 发票 | 凭证 | max_diff |
|---|---|---|---|---|
| TR-0002 | 96000.00 | 96000.00 | **91500.00** | 4500.00 |
| TR-0003 | **143000.00** | 119000.00 | 119000.00 | 24000.00 |
| TR-0004 | 72000.00 | **76000.00** | 72000.00 | 4000.00 |

**五类全覆盖、与植入 9 组一一对应、误报 0**（植入外无多报）；
`dropped_no_evidence = 0`（引用覆盖率 100%，对应 §3 验收 4）。

端到端（算法 → 落 PG → 经 HTTP 契约回读）：

```
算法产出 9 条 → 落库 9 行 → GET /api/v1/affiliation/suspicions = 200 / total 9
amount_mismatch 3 条 details 完整；其余 6 条：规则型 3 条 null，cycle 3 条 {cycle_length: 2|3|4}
```

## 5. 真机暴露并修掉的 4 个缺陷（**不是**靠单测发现的）

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 1 | `amount_mismatch` 命中 3 条却**全部被丢弃** | `:Invoice` / `:Voucher` 的 `source_entity_ids` 只进了 row dict，**没写进 Cypher** ⇒ 图里为 null，证据链断 | 两条 MERGE 补 `n.source_entity_ids` |
| 2 | 同上（二次） | 共享节点收尾循环把 `:Contract` 的自指 `[自身 id]` **覆盖成 `[]`** | 只对共享节点覆盖，合同跳过 |
| 3 | 疑点里主体名/法人名恒为 `None` | 算法 Cypher 读 `s.name` / `l.name`（spec §4.1 的属性名），而摄入只写 `canonical_name` | **两者都写**（`name` 用于算法，`canonical_name` 用于读侧概览）；证件号仍只存哈希 |
| 4 | 入图 `CypherSyntaxError` | Cypher 注释是 `//`，我写了 SQL 的 `--`（**两次**） | 注释移出 Cypher 字符串 |

> 第 4 项顺带**验证了三段式回滚真的生效**：失败时 `KgVersion` 置 `failed` + 事务回滚，
> 不会留下「半个图 + 一个 active 版本」。

## 6. 门禁（全绿）

- `uv run ruff check .` / `ruff format --check .` → All checks passed
- `uv run pytest -q` → **597 passed, 3 skipped**（新增 5 条算法用例；既有 6 条因服务层归一而同步更新）
- `uv run alembic upgrade head` → `4e7759c33526 → 9c1b7d2ae4f3`（`details` 列 + 类型约束放宽）
- `uv run python scripts/check_seams.py` → 通过
- `uv run python scripts/export_openapi.py --check` → **本次是契约变更**（+3 枚举 + `details` 字段），重导出后零漂移
- 前端 `npm run gen:api` / `lint` / `tsc --noEmit` → 通过（`SUSPICION_TYPE_META` 是
  `Record<全部类型>` ⇒ 契约扩枚举**必然**让 tsc 红，这正是 CI 该抓住的）

## 7. 本批次未做（登记，不掩饰）

- **§3 验收 6 场景准入**（200 合同 / 500 发票 / 100 凭证 / 20 组植入 ⇒ 召回 ≥ 0.80、误报 ≤ 0.15）：
  语料规模**远不足**（20 供应商 / 60 发票 / 30 凭证 / 8 合同 / 9 组），
  **维持未做** → 缺口 **S13**。本批次**不**拿 9/9 冒充召回率。
- `contracts.csv` 是 **PDF 合同的合成替身**（spec §4.6.6 已登记偏离）；真机合同仍须走 M2。
- `unaligned_subjects` 读端点（缺口 **S9.11-1**）未动。
- `missing_check_in`（考勤域）不在本批次范围。
