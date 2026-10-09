# P6-V2 集成日志（2026-10-09）

- **批次**：[`../docs/delivery-plan.md` §9.2 序 5c](../../docs/delivery-plan.md)
- **主题**：M2 抽取侧 token 落点 + `cost_metrics.stage` 列（偏离 **X-6**）
- **起点**：P6-V1 收口（HEAD `adc8ea2`），工作区干净；CI 绿
- **状态**：✅ X-6 已落地 + 9 条新判据全绿；⏳ **C3-a / C3-b 仍 BLOCKED**（见 §7）
- **边界文件**：[`proposal.md`](./proposal.md)（10 条 Non-goals + 决策表 Y1–Y6）

---

## 1. 交付（五个提交，代码 / 测试 / 文档分列）

| # | 提交 | 内容 |
|---|---|---|
| 1 | `d022747` | `langextract.py`：`LlmInvokerFn` 返回 `(原文, usage)`、`_UsageTotals` 逐 chunk 累加、`ExtractionResult.llm_usage` 带出 + 本批 `proposal.md` |
| 2 | `44669fe` | 测试替身同步（**实为 9 处**，见 §4 第 1 条） |
| 3 | `bf535b8` | `models.py` `stage` 列 + `UNIQUE (org_id, metric_date, stage)` + 迁移 `a1f7c2b93d04` + `cost_metrics` 写入侧 + `registry._do_extract` 接线 |
| 4 | `6c808cb` | 判据用例：`tests/test_cost_metrics_extraction.py`（6 条）+ 抽取层用量三条 |
| 5 | （本次） | 回登 spec §10.1.1 第 13 / 14 项 + 本日志 + 下一批提示词 |

## 2. 判据实读（[`probe_extraction_cost_rows.py`](./probe_extraction_cost_rows.py)，洁净 org）

同一份文档当天**抽两次**（150 × 2）+ **问一次**（15）：

```
=== 当日 cost_metrics 实读 ===
  stage=answer     in=10   out=5   total=15   doc_count=1 single_doc_cost=15.00   docs=['ab050be1…']
  stage=extraction in=240  out=60  total=300  doc_count=1 single_doc_cost=300.00  docs=['ab050be1…']
=== 仪表盘（同日两 stage）实读 ===
  token_usage_total=315  (期望 300+15=315)
  single_doc_cost  =315.00  (期望 315/1=315)
  cost_ratio       =0.00  (无写入方 ⇒ 恒 0.0)
[OK] X-6 落地 + Y6 跨行去重，均为实读
```

要点：

- **两行并存**：同一 `(org, 日)` 下 `extraction` 与 `answer` 各行一行 ⇒
  旧约束会撞 `UNIQUE`、或者挤成一行；现在每行各成口径（`15.00` vs `300.00`）。
- **抽取两次 = 300，但 `doc_count` 仍为 1** ⇒ `counted_doc_ids` 去重生效（判据 3）。
- **`single_doc_cost = 315.00` 而不是 `157.50`** ⇒ 跨 stage 按文档 id 去重生效
  （决策 **Y6**）。若退回"各行 doc_count 求和"，同一份文档会被数两次、分母翻倍。

pytest（有图口径，三个 env 都设）：

```
1173 passed → 1182 passed / 5 skipped   （净增 9 条判据，无下降）
```

## 3. 关键设计口径

- **`stage` 常量位置**：`app/db/models.py::COST_STAGE_EXTRACTION / COST_STAGE_ANSWER`
  —— `cost_metrics` 服务 import 它，迁移**刻意不 import**（重放历史产物）⇒
  迁移里 literal `'answer'` 与之一一对应，注释里点明了这条对应关系。
- **既有表加 NOT NULL 列**：`server_default='answer'` + 回填；既有行本来全是
  问答侧写的，回填是把**已知事实**落到新列上，不是猜。
- **`downgrade` 删 `stage <> 'answer'` 的行**：旧形状装不下两个 stage，
  代价写在迁移 docstring 里显式交代（不偷偷丢数据）。
- **迁移文件名刻意不含 `_rls_`**：G-26 的 `*_rls_*.py` glob 用来盯**租户表集合**，
  本迁移改的是列，混进去会让那条警戒范围失真。
- **记账必须旁路**：`_do_extract` 里 `record_extraction_usage` 用 try 包住，
  失败只落 `document_extract_usage_record_failed` —— LLM 钱已经花了，
  抽取主链路再被拖垮等于白抽（有用例：注入异常后 `extract_status` 仍 `completed`）。

## 4. 本批踩到的坑（**提示词坐标过期两处**）

1. **替身不是「3 个」是 9 处**：提示词 §5 说只有三个 `-> lx.LlmInvokerFn` 公共替身，
   实查另有 **6 处函数内联 `_invoke` 闭包**返回 `str`。它们的症状也不直白：失败信息是
   `ValueError: too many values to unpack`（先炸在"解包失败"，而不是"调用约定变了"）。
   ⇒ 全部改成 `(原文, 定值 _FAKE_USAGE)`，顺带让"用量有没有被累加"可断言。
2. **本地持久测试库不会被 `create_all` 加列**：CI 每次起新 PG 容器 ⇒ `create_all`
   天然带新列；本地 `graphrag_test` 是持久库，而 `alembic upgrade head` 会从 base
   重跑全套 DDL、撞已存在的表 ⇒ 补了一个本地同步脚本：
   [`sync_local_test_db_stage.py`](./sync_local_test_db_stage.py)（只补同一段 DDL）。
   **生产 / CI 的升级路径由 `test_migrations_baseline.py` 验**（临时库真跑
   upgrade + downgrade base，本批实跑通过）。
3. **探针第一次读数被污染**：用了默认 org，而本地库里今天早就有上一轮遗留的
   问答行（`total=29119 / doc_count=6`）。⇒ 探针改成**随机 org**，数字才对得上账。
   （本地库残留是持久库的脏数据，不是产品缺陷；但提醒：读表做判断前先看是不是干净租户。）

## 5. 范围回切（开发中 / 子任务收尾各跑一次）

`check_session_drift.py` 全绿：

- **S1** 读出本批 10 条 Non-goals（其中第 7 条「不许只加列不改去重」正是本批最容易漏的）；
- **S2** 5 个文件 / 新增 279 行 —— 在阈值内（新迁移与新测试文件当时尚未入库，不计入）；
- **S3**（配置须留模板）/ **S4**（契约联动）/ **S5**（孤儿模块）均无命中。

## 6. 自问三句（脚本拦不住，**必须自己答**）

1. **有没有顺手做的？** 有一样擦边：`build_dashboard` 的 `doc_count` 改为跨行去重。
   它不是"凑一个多余的功能"——是加了 stage 之后**本批自己引入**的双计数风险
   （不修就是分母翻倍的假账），已在 `proposal.md` §6 决策 **Y6** 里先裁决后实施。
2. **有没有为躲坑而绕路？** 没有。最想绕的是"本地库加列"——但那是**本地**环境的
   同步工具，不是迁移替代品：生产路径仍由 `alembic` + 迁移基线测试把关。
3. **验收是真跑出来的还是读代码得出的？** 是跑出来的：§2 的数是**真落 PG 后读行**
   得到的（探针走完整执行体，不绕 pytest）；pytest 那条链路是同一组数的第二重确认。
   没有一条判据来自读代码。

## 7. 仍 BLOCKED（**不许外推**）

- **C3-a**：阈值 **TBD-7 未拍板** ⇒ 即使现在分子分母齐了，也不构成达标。
- **C3-b**：`incremental_cost` / `full_rebuild_cost` **仍无任何写入方**
  ⇒ `cost_ratio` 恒 `0.00`（探针实测也是 0.00）。归 **P6-V3**。
- **失败 chunk 的 token 记不到**：`_extract_chunk_tolerant` 抛错时拿不到 usage
  ⇒ 抽取侧分子**偏保守**；不回填、不猜数（登记在 spec §10.1.1 第 14 项）。

## 8. 门禁读数（动工前 → 收口，**全部实跑**）

| 项 | 动工前 | 收口 |
|---|---|---|
| `check_startup_readiness.py` | 17 / 0 / 0 | **17 / 0 / 0** |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 | **ERROR 0 / WARN 0 / OK 12** |
| `export_openapi.py --check` | 零 diff | **零 diff** |
| `extract_seam_signatures.py --check`（G-11） | 一致 | **一致**（本批未动 8 个冻结接缝） |
| `ruff check` / `ruff format --check` | 通过 | **通过** |
| `pytest`（有图口径） | 1173 passed / 5 skipped | **1182 passed / 5 skipped** |

## 9. 下一批指针

- **P6-V3**（序 5d）：C3-b 取证。**⚠️ 仍卡在未决前提**：增量重算零 LLM ⇒ token 口径下
  分子恒 ≈ 0 ⇒ `cost_ratio` 会假性「显著 < 1.00」。**在"耗时 / 图写操作数 / 受影响节点数"
  定案前不得开工、不得宣称达标** —— 这一条要一直传到用户裁决为止。
- **dashboard 按 stage 切片**：属**契约变更**（跨角色：`openapi.yaml` + 前端 `gen:api`），
  已登记在 spec §10.1.1 第 14 项，本批照 X-6 口径没做。
- **P6-T 判分 86 题**：继续传承到每一批，直到 P8-Release 零缺口对账前判完。
