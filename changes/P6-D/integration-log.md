# P6-D · 集成日志（L2 端到端）

> **日期**：2026-10-05 ｜ **边界文档**：`a94a198e`（第一步，只写文档）
> **本批结论一句话**：**L2 端到端打通了 H1–H5，H6 卡在 RBAC 授权（403）**；
> 打通靠的是修掉**三个串行阻塞**，而这三个都不是"演示图难造"，是**脚本/数据级缺陷**。

---

## 1. 采纳的既有口径（有建议项 ⇒ 直接采纳）

`proposal.md` §1 已登记：判据 = **语料是否经 M2 抽取**
（依据 `gold-affiliation-v2.json::source.corpus_layer_note` + DR-A8′）。
⚠️ **ADR-0007 的 L0/L1/L2 是「定制分档」**，与语料层**编号同形含义不同** ⇒ 不混用。

## 2. 逐跳实测结果（**不是读代码得出的**）

| 跳 | 判据 | 实测（2026-10-05，本机真 Neo4j + 真 MinerU + 真 DeepSeek） |
|---|---|---|
| **H1** 真机文档 → M1 解析 | `Document` 节点 + `full.md` 产物 | ✅ **通**：6 份 docx 全部经 MinerU 云解析（如 `attendance-policy-2025.docx` → 1567 字符 full.md） |
| **H2** M2 抽取 | `ent_*` 产物实体 > 0 | ✅ **通**：**180 个**（6 份文档合计抽取实体 ~180） |
| **H3** 入图 + 两链路汇合 | `:Chunk` > 0 **且** `GOVERNED_BY` > 0 | ✅ **通**：Chunk **213**、MENTIONS **374**、GOVERNED_BY **93**、POLICY_CLAUSE **83**；B3 验收路径 **210 条 / 员工 18 人 / 工时制 2 个 / 条款 14 条**；PG `attendance-demo-v1` → **ready**（实体 2805 / 关系 3623） |
| **H4** 检索 | 图侧检索 + 证据链 | ✅ 通（问答实际带回 7 条引用，即检索生效） |
| **H5** 问答 | `POST /agent/query` 200 + citations | ✅ **通**：HTTP **200**，`kg_version=attendance-demo-v1`，`refused=false`，**citations=7**（带 `chunk-2867eb84cd00` 等可溯源 id）；跑了 **2 次**（两次都 200） |
| **H6** 引用回溯 | `GET /documents/{id}/chunks/{chunk_id}` 命中 | ❌ **未通过**：**403 `FORBIDDEN` / `no_role_assignment`（roles=[]）** |

### 2.1 H6 的处置与"我试了什么"

1. 先按 `documents.py::get_document_chunk` 的端点直连 ⇒ **403**；
2. 跑 `scripts/seed_dev_rbac.py` ⇒ 输出「dev 默认主体授权 = ['admin']」⇒ 重试仍 **403**；
3. 重启后端排除角色缓存 ⇒ 仍 **403**，响应体给出 `reason: no_role_assignment, roles: []`
   ⇒ 即**运行态读到的授权仍是空**。

⇒ **如实登记**：H6 本轮**未取得 200 命中**。它属于**授权种子与运行态不一致**（dev 环境/RBAC 条线），
**不是** L2 链路本身的缺陷（回查逻辑与 404 语义已由既有单测覆盖）。**不顺手修**（Non-goals 第 6 条）。

## 3. 三个串行阻塞 = 本批真正的根因（**都是先撞上、再定位、再修**）

| # | 撞到的现象 | 根因 | 处置 |
|---|---|---|---|
| **①** | CSV 入图 `GOVERNED_BY 连边为 0` ⇒ 硬失败回滚；而制度入图器报「没有 WORK_TIME_SYSTEM 节点」 | **引导顺序死锁**：CSV 侧硬性要求汇合边 > 0（需条款先在），制度侧硬性要求工时制节点先在（来自 CSV）⇒ 两边互相等待，**都回滚，演示图永远建不起来** | 改 `ingest_attendance_csv.py`：**条款语料为 0 时**（= 制度文档尚未入图）**不硬失败**，改为醒目提示 + 跳过该项自检。**护栏本意保留**：条款明明在却连不上（R10）**仍然硬失败** |
| **②** | `TaskSpec.__init__() missing 1 required positional argument: 'org_id'` ⇒ M1/M2 段**一进来就崩** | `TaskSpec.org_id` 已是必填位（G-26 判据 ⑩ / ADR 显式绑 org），该脚本从未跟上 ⇒ 说明**这条脚本在当前代码上从未跑通过** | `run_stage()` 加 `org_id` 形参并给 3 个调用点显式传值 |
| **③** | M2 抽取跑完但 **0 条 `POLICY_CLAUSE`**（只出 `CONTRACT_CLAUSE` / `REGULATION`） | 本体词表里**没有** `POLICY_CLAUSE` ⇒ 模型无从产出该类型 | 跑 `scripts/seed_attendance_ontology.py`（写入 13 实体 / 14 关系类型，version=1 active）⇒ 重跑即抽出 `POLICY_CLAUSE=14` |

> ① 的修法值得单独说明：**没有**加"跳过护栏"的开关。判据改成
> 「条款语料为 0 ⇒ 属**引导未完成**，不是连通性失败」；一旦条款存在而连边仍 0，**照样硬失败**。
> 否则就是给 R10 开后门。

## 4. T4：`corpus_layer` 不再写死（**假绿入口已封**）

- 删掉 `runner.py::QSET_CORPUS_LAYER = "L1"` 常量；
- 新增 `app/evaluation/corpus_layer.py::detect_corpus_layer()`：
  图内存在 M2 抽取产物（实体 id 前缀 `ent_`）⇒ **L2**；有数据但无 M2 产物 ⇒ **L1**；
  **图不可用 ⇒ `None`（不猜）**；
- `_detect_layer()` 多版本**取最高层**（跑到过 L2 就不许被同批 L1 图拉低）。

**判别标记的区分度已实测**：`attendance-demo-v1` = 180 个 ⇒ L2；`affiliation-demo-v2` = 0 个 ⇒ L1；不存在的版本 ⇒ `None`。

**反向验证 2 次**（故意破坏 ⇒ 确认判红）：

| 变异 | 判红的测试 |
|---|---|
| `if m2_count > 0:` → `if False:`（把 L2 判成 L1） | `test_m2_products_mean_end_to_end` ✅ `1 failed` |
| 图不可用时 `return None` → `return LAYER_ALGORITHM`（图挂了就猜 L1） | `test_graph_unavailable_yields_none_not_guess` ✅ `1 failed` |

## 5. T5：可复现冒烟脚本（实跑输出）

`backend/scripts/probe_l2_e2e.py --kg-version <版本>`（只读，逐跳打印通/不通 + `corpus_layer`）：

```
===== attendance-demo-v1 =====          ===== affiliation-demo-v2（L1 对照）=====
[OK  ] H1 文档        15                [OK  ] H1 文档        5
[OK  ] H2 ent_* 产物 180                [FAIL] H2 ent_* 产物   0
[OK  ] H3 :Chunk     213                [OK  ] H3 :Chunk     988
[OK  ] H4 MENTIONS   374                [OK  ] H4 MENTIONS  1056
[OK  ] H3+ GOVERNED_BY 93               [FAIL] H3+ GOVERNED_BY 0
corpus_layer: L2                        corpus_layer: L1
```

⇒ **同一份判据在两侧给出了不同答案**，说明它不是"永远输出 L2 的橡皮图章"。

## 6. 门禁实测数字

```
pytest（真 Neo4j / PG 16.15 + app_rls）    957 passed / 3 skipped / 3 xfailed   ← 基线 950 ⇒ +7，0 回归
ruff check .                               All checks passed!
ruff format --check .                      229 files already formatted
check_seams.py                             ERROR 0 / WARN 0 / OK 10
export_openapi.py --check                  [OK] 契约零 diff
check_session_drift.py                     S1 读到 7 条 Non-goals ✅｜S2 4 文件/+115 ✅｜S3 ✅｜S4 ✅｜S5 新模块均有引用 ✅
```

## 7. 收尾三问（自答）

1. **有没有"顺便做的"？** 没有。**唯一的边界外动作**是 `graphs.py` 新增 `count_m2_entities()`
   （只增不改）—— 它是 `corpus_layer` 判定的**唯一数据源**，属 T4 本体。
   顺带**发现但没动**的两处既有缺陷（只登记）：
   - ⚠️ `ingest_attendance_policies.py` 的「**条款数一致**」自检在**多文档场景恒 FAIL**
     （它拿"本次抽取条数"比"图内累计条数" ⇒ 文档一多必然不等）。**不阻断**（仍置 ready），
     但它让"静默丢失"这条判据**失去意义** ⇒ 归制度入图器所属需求，不在本批改。
   - ⚠️ H6 的 RBAC 授权种子与运行态不一致（§2.1）。
2. **有没有为躲坑而绕路的实现？** 没有。特别是 ①：没有加 `--no-bridge` 之类的旁路开关，
   而是把判据改精确（条款不存在 ≠ 连不上）。另外**没有**为了省事用合成语料顶替 L2（Non-goals 第 7 条）。
3. **结论是真跑出来的还是读代码得出的？**
   - H1–H5：**真跑**（真 MinerU 云 + 真 LLM + 真图 + 真 PG），数字均在本文；
   - H6：**真跑过且失败**（403），如实登记，没拿单测冒充；
   - `corpus_layer` 判别：真图实跑 + 2 次反向验证判红。

## 8. 对后续阶段的**重要**影响（必须写下来的发现）

> **演示图现在是 ready 的**：PG `attendance-demo-v1` = ready，图内 实体 2805 / 关系 3623 /
> POLICY_CLAUSE 83 / GOVERNED_BY 93，**且真机问答已返回 200 + 7 条引用**。

⇒ **阶段 ④（Q8 拒答误伤）与 C2-c 真机评测的前置阻塞（"agent/query 恒 501"）已经解除**，
下一批可以直接跑 `--live`，不必再等"演示图重建"。
（C1 仍缺 **embedding 服务**——那条阻塞与本批无关，见 P6-C 日志 B-2。）

## 9. 阶段小结

| 项 | 数 |
|---|---|
| 完成 | T1（根因）/ T2（修 ① ② ③）/ T3（H5 打通）/ T4（归因 + 反向验证）/ T5（冒烟）/ T6（H6 未通 ⇒ 已如实登记） |
| 降级登记 | **1**（H6 未通过：403 `no_role_assignment`，非静默——已写明卡点与归属） |
| 升级用户 | 0（H6 的处置属 dev 环境/RBAC 条线，有明确下一步，不构成"无建议项"） |
| 新增测试 | 7 条（`tests/test_eval_corpus_layer.py`，不连真图 ⇒ CI 必过） |
| 反向验证 | 2 次变异，均判红 |
| 实测产物 | 6 份 docx 全链入图；真机问答 2 次均 200 |
