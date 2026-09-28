# Sprint 9.6 —— R10：事实与条款本体连通（GOVERNED_BY 汇合）

> 登记日期：2026-09-28。动机：`docs/dev-doc-status.md` **R10**（结构化事实与
> `POLICY_CLAUSE` 在图里不连通，推理链只能落到「事实记录」，走不到条款）。
> 前置：Sprint 9.5 已归档（`changes/archive/2026-09-28-Sprint9.5/`）。

## 1. 真机事实（2026-09-28 探针 `_tmp_probe_r10.py`，结论决定方案）

1. `WORK_TIME_SYSTEM` 类型有 **17 个 M2 span 节点**（含「系统」「核心在岗时段」等
   噪声）+ **3 个 CSV 派生节点**（`WORK_TIME_SYSTEM:标准工时制` 等，演示链路实际连的
   就是它们）⇒ GOVERNED_BY **只能**从 CSV 派生节点出发，按 id 前缀 `WORK_TIME_SYSTEM:`
   圈定，span 一律不参与。
2. `POLICY_CLAUSE` 共 60 条，`canonical_name` 多为碎片（「第七条」「2026 年 1 月 1 日」）
   ⇒ 按节点属性匹配**必失败**；但每条条款都有 `Chunk -MENTIONS-> clause` 入边，
   **chunk 文本才是完整句子**（含「综合计算工时制」等 28/34/14 处）⇒ 匹配走
   「clause ← MENTIONS ← chunk.text CONTAINS 工时制名」。
3. CSV 证据 chunk（R14，员工行）也含工时制名，但它们只 MENTIONS 到 `EMPLOYEE`
   ⇒ 上面的匹配模式天然排除，不会把事实行连到条款。

## 2. 方案

mapping.yaml 尾部**已预留 B3 设计**（批次 A3 写下）：
`WORK_TIME_SYSTEM -[:RELATION {relation_type:'GOVERNED_BY'}]-> POLICY_CLAUSE`。
本 Sprint 把预留落地：

- **入图器内做**（不新建脚本）：`ingest_attendance_csv.py` 在 MERGE 实体**之后**、
  自检**之前**，从库内读「POLICY_CLAUSE + 其 MENTIONS chunk 文本」，在 **Python 侧**
  做确定性包含匹配，产出的边**并入 `relation_rows`**——复用现有
  MERGE / 写入自检 / 失败回滚全链路，不另起写入通道。
- **重跑方式**：同 `kg_version` + `--purge-csv`（只清 CSV 派生节点，
  M2 的 `ent_*` 保留）——GOVERNED_BY 的 head 是 CSV 节点，DETACH DELETE 连带清边，
  重跑天然幂等。
- **连通后的链**（3 跳，`reasoning.py` 的 `*1..3` 可达，终点优先级本就
  `POLICY_CLAUSE` 最高）：`EMPLOYEE -HAS_POSITION→ POSITION -APPLIES_WORK_TIME→
  WORK_TIME_SYSTEM -GOVERNED_BY→ POLICY_CLAUSE`。
  预期演示效果：「李静的月加班超过上限了吗？」推理链落到「每月加班不得超过 36 小时」条款。

## 3. 批次

| 批次 | 内容 | 验收 |
|---|---|---|
| G1 | 入图器 GOVERNED_BY 汇合（fetch + Python 匹配 + 并入 relation_rows）+ 单测 | 单测覆盖：命中 / span 不参与 / CSV chunk 不参与 / 空名跳过 / id 确定性 |
| G2 | 重建图（`--purge-csv`）+ `verify_cases` 新增「李静 3 跳可达条款」用例 | 真机问答推理链落到 POLICY_CLAUSE |
| G3 | 合规抽屉「制度依据」可读化：`graph:clause:ent_<hex>` → 显示条款标题 | 演示不再出现裸哈希 id（截图点验暴露） |
| G4 | 文档：R10 状态更新 / sprint-calendar S9.6 / integration-log | 引用无死链 |

## 4. 明确不做

- **不给 17 个 span 噪声节点建任何边**（R12 同族教训：噪声边只会加剧子图采样劣化）；
- **不动契约**（G3 若需新字段另行评审）；
- **不让 LLM 参与匹配**（确定性纪律，与 mapping.yaml 头部三条一致）。
