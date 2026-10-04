# P6-A 任务清单 —— A8：语料扩标 200/500/100/20 + 统计口径

> 边界见 `proposal.md` §3（**开工前先读 Non-goals**）。起跑：`pytest` **903 passed**。

- [x] **A1** `scripts/gen_affiliation_corpus.py`：受控生成器（固定 seed ⇒ 确定性）
      - 产出 `demo/affiliation/generated/`：contracts 200 / invoices 500 / vouchers 100 / suppliers 120 / shareholders
      - 三张单据表加**正文列**（`contract_text` / `invoice_text` / `voucher_text`）⇒ 文本证据
      - 噪声约束：除植入外，地址 / 电话 / 法人**全局唯一**（防误报）
- [x] **A2** `data/eval/gold-affiliation-v2.json`：20 组（五类 × 4），`node_ids` 按命中规则写
      - shared_* 只写 2 个主体；cycle 写环上 N 个；amount_mismatch 写三个单据 id
      - `kg_version=affiliation-demo-v2`、`corpus_layer=L1`、每组 `text_evidence`
- [x] **A3** `ingest_affiliation_sources.py`：加 `--corpus-dir`（不改字段映射）
- [x] **A4** `app/evaluation/stats.py`：Clopper-Pearson 精确单侧界（纯 Python）
- [x] **A5** 判定用界：detail 增 `n` / 界；新增 `underpowered` 语义（界不达标 ⇒ 不得标 PASS）；报告带 `corpus_layer`
- [x] **A6** 实测：导入 v2 → `--live` 出真值（召回 / 误报 + 界），**如实登记**（含误报条数）
- [x] **A7** CI 改跑 v2 语料 + 重设基线（日志写明实测值与界）
- [x] **A8** 测试：`stats` 单测（对照裁决基准值 0.82 / 0.75 / 0.62 / 0.139 / 0.18）+ 生成器单测
- [x] **A9** 反向验证：去掉界判定 / 放宽 gold / 生成器去正文 ⇒ 各自判红
- [x] **A10** 文档与日志：需求基线 / spec 缺口 S13 / README / 集成日志

## 不做（改完回头逐条对照）

1. 宣称达标（本批只造"能判"）
2. 改 spec 规模、改 `specs/m4-affiliation-detection.md`
3. L2 端到端（真机 + M2 抽取）
4. A1（向量基线 / 双侧判分）
5. A6+L8 的含拒答档与拒答误伤判据
6. 改检测算法 / 阈值 / 匹配键
7. 改契约 / ADR 原文、动租户隔离代码
