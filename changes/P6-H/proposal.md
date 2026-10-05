# P6-H · 受控题集扩容（v3: 14 题 → v4: 40 题）

> **日期**：2026-10-05 ｜ 前序：`P6-F`（C1 首次出数 0.0909）／`P6-G`（归还 D1）
> **这一步是 ⑤ 阈值校准的前置**：不扩容先校准，等于在会跳 ±7.1pp 的分母上刻读数
> **一句话**：14 → **40 题**，单题翻转灵敏度 **7.14pp → 2.5pp**；v3 **归档不改写**，
> 全部 40 题两侧共 **80 条答案**判完才谈阈值。

---

## 1. 为什么必须先扩容（依据来自实测，不是理论）

P6-F 的实测结论：

- C1 = **0.0909**，阈值 10% ⇒ 差 **0.9 个百分点**；
- 受控题集只有 **14 题** ⇒ **单题翻转 = 1/14 = ±7.14 个百分点**。

⇒ **灵敏度（7.14pp）比结论本身（0.9pp）大 8 倍**。在这个分母上做 ⑤ 的阈值校准，
校准出来的精度是假的：今天校出 10%，明天换一次判分就 ±7pp 地摆动，校准结论毫无意义。

| 题数 | 单题灵敏度 |
|---|---|
| 14（v3，现状） | **±7.14pp** ← 不可用 |
| 30 | ±3.33pp |
| **40（v4，本批目标）** | **±2.50pp** |
| 50 | ±2.00pp |

选 40 而非 50：40 题两侧判分已是 **80 条人工判分**，再往上是用**判分质量下降**换数字稳定，
得不偿失 —— 判错了比题少了更糟。

## 2. v3 → v4 的关系：**子集 + 追加**，不是重出

> **v4 = v3 的 14 题（原题面、原顺序、原 `should_refuse` 一字不改）+ 26 道新题追加在后**

为什么坚持这条：

1. **历史可比**：0.0909 是在 v3 上测的。若 v4 改了旧题，那个数字就变成"曾经不可复现的一次"；
2. **可比自查**：同一批 v3 的 14 题在 v4 上重跑 ⇒ 若值变了，说明换版污染了数字，必须停下来查；
3. qset 历史上 v1→v2→v3 三次换版**全部重出题**，每次都导致「不同源 ⇒ 全拒答 ⇒ 假结论」
   （见 `eval_controlled_qset.py` docstring 第 6–19 行）。本批**不许第四次**。

## 3. 40 题配额与来源（依据 `demo/attendance/` 的真源，非估计）

语料真源（已核实存在）：

- **6 份制度 Markdown 源** `demo/attendance/policies/*.md`：`attendance-policy-2025` /
  `attendance-policy-2026` / `fieldwork-attendance-rules-2025` / `fieldwork-attendance-rules` /
  `overtime-and-comp-off` / `worktime-system-rules`；
- **9 张业务表** `demo/attendance/corpus/*.csv`：employees / shifts / attendance_records /
  leave_requests / overtime_records / business_trips / work_orders / access_records / location_records。

| 配额 | 题数 | 说明 |
|---|---|---|
| 制度条文题 | **24** | 6 份制度 × 4 题，每题注明「第几条 → 期望要点」 |
| 结构化事实题（CSV） | **12** | 覆盖主干表，含跨表（员工 ↔ 排班 ↔ 请假）的多跳场景 |
| 库外拒答题 | **4** | 原 2 题保留 + 新 2 题；**刻意选语料里完全不存在的主体**（库外问若带库内高词频词会被误召回 ⇒ 拒答判据失真） |
| **合计** | **40** | = 旧 14（12 库内 + 2 库外）+ 新 26 |

## 4. 出题硬规则（**防止我把题出坏**）

1. **每题必填 `source_doc` + 出处条款/行** —— 没有出处的题不许进 JSON（判分人和三个月后的我都据此复核）；
2. **入库前必须先实测**：跑 `--diagnose`（¥0，只复算候选集不调 LLM）确认
   ① 库内题**能召回证据**；② 库外题**确实拒答**。跑不通的题**不许靠降低 `expected_points` 硬塞**；
3. **2025 / 2026 同名制度**的题**必须带时点**：`MANIFEST.json` 的 `dirty_data_handling` 第 2 条写明
   「涉及该条的问题必须带时点，否则判分时按『未指明版本』视为要点缺失」⇒ 出题时就要避开歧义；
4. **不许为了让题答得上来而放宽 `should_refuse`** —— 那是把"答非所问"改写成"答对了"；
5. **`expected_points` 必须可在源文中逐条引证** —— 不许出现"常识补充"类要点（否则造成系统性判错）。

## 5. 版本接线清单（**漏一处 ⇒ 报告拿 v4 的题写着 v3 的名字骗人**）

| 文件 | 改动 |
|---|---|
| `scripts/eval_controlled_qset.py` | `QUESTIONS` 追加 26 题；`QSET_VERSION` → `v4-2026-10-05` |
| `data/eval/controlled-qset-v3.json` | **不动**（历史数字 0.0909 的唯一依据，归档保留） |
| `data/eval/controlled-qset-v4.json` | 新建：40 题 + `source_doc` + `expected_points` |
| `app/evaluation/dataset.py` | `QSET_FILE` 常量指向 v4 |
| `app/evaluation/runner.py` | **至少 8 处** `dataset_version="controlled-qset-v3"` 硬编码 ⇒ 全改 v4 |
| `data/eval/MANIFEST.json` | 新增 v4 dataset 条目；v3 条目标注「历史版本，已停止加载」 |
| `tests/test_eval_qset_parity.py` | 硬编码 `== 14` ⇒ 改为从 **MANIFEST v4 的 items** 读 ⇒ 避免第三次出现"换了题数忘了改数字" |

> `runner.py` 那 8 处硬编码是本批**发现的最大隐患**：它不是"文档没同步"，而是报告里的
> `dataset_version` 字段会直接撒谎 —— 两次运行口径可比靠的就是这个字段。

## 6. Non-goals（**冻结，drift S1 会逐条读出**）

1. **不改 `rubric-v1`**（要点全覆盖才 true；要不要分层计分另行讨论，不在本批）；
2. **不校准任何阈值** —— 那是阶段 ⑤ TBD-7，本批只是让它"值得被校准"；
3. 不动 C1 / C2 任一条判据的**计算逻辑**；
4. **不改旧 14 题的题面 / 拒答标注 / `expected_points`**（第 2 节已说明为什么）；
5. **不顺手更新 MANIFEST 里已过期的语料统计** —— 实测 `chunks_in_neo4j` 已不是 224
   （③ 入图后是 1329，且该数混了 `attendance` 与 `affiliation` 两个 kg）；改它会污染本批 diff，
   **登记为独立待办**（它属 ③ 的善后，且 MANIFEST 自称该字段是单一真源 ⇒ 不能顺手改错）；
6. 不动 `contracts/openapi.yaml`、不加 `settings` 配置项、不动 ADR；
7. 不顺手修 H6 引用回溯 403 / 制度入图器「条款数一致」自检恒 FAIL / P7-B readiness / G-12；
8. **不为让某题答得上来而改 prompt（`kg_qa_v5`）、检索或拒答判定** —— 若发现系统性问题，**登记**；
9. 不在本批复跑并重判 v3 的旧数字（0.0909 就是它当时口径下的值，保持原样）；
10. 除第 5 节的 7 个文件外**不改动其它文件**。

## 7. 出口判据

| # | 判据 | 怎么验证 |
|---|---|---|
| E1 | 三处一致：script `QUESTIONS` / v4 JSON / MANIFEST `items` | parity 测试绿，且数量**来自 MANIFEST** 而非硬编码 |
| E2 | 报告里的 `dataset_version` 真的变成 v4 | live 跑一次读报告字段；且 `runner.py` 中 `controlled-qset-v3` **残留 0 处** |
| E3 | 新 26 题**入库前 100% 实测有据** | `--diagnose` 逐题核对：库内题召回非空、库外题拒答 |
| E4 | 灵敏度降到 2.5pp | 数学事实 1/40 = 2.5%，并在报告 `notes` 里写明，不许含糊 |
| E5 | **v3 文件未被改动** | `git diff --stat data/eval/controlled-qset-v3.json` 为空 |
| E6 | 两侧 **80 条**答案完成判分 ⇒ C1 出 v4 新数 | live 跑 C1；旧 14 题子集的值需与 v3 时期**对照说明**差异来源 |

## 8. 顺序

```
T1 边界文档（本文件 + tasks，Non-goals 10 条已冻结）
T2 读 6 份制度真源，起草 26 道新题（含出处 + expected_points）
T3 落 controlled-qset-v4.json + script QUESTIONS 追加 + dataset.py / MANIFEST 接线
T4 parity 测试改为读 MANIFEST items（连同后面 runner.py 8 处版本硬编码一起改）
T5 E3 实测：逐题 diagnose 校验有据性
T6 E2 验证：live 跑一次，确认报告 dataset_version=v4
T7 E6 判分：两侧 80 条按 rubric-v1 人工判 ⇒ C1 出 v4 数字 + 灵敏度记录
T8 门禁 + 集成日志 + 提交
```

## 9. 风险登记（先说出来，别事后才发现）

| 风险 | 说明 | 本批处理 |
|---|---|---|
| **判分工作量** | 80 条答案要按 rubric-v1 逐题人工判，是本批最大成本 | 分步跑（先图侧后基线侧），判分表分文件存放，便于分批 |
| **检出率下降风险** | 新题更细 ⇒ 可能拉低 C1 的表观值 | **不许**因此回头挑题（出题在判分之前冻结）。若表观值下降，那是**真信息** |
| **v4 与 v3 不可比** | 分母变了 ⇒ v4 出的数**不等于** v3 的 0.0909 | 在报告 `notes` 与日志里显式写明；0.0909 永远标注为 v3 口径 |
