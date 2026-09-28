# Sprint 9.5 集成日志（真机证据链）

> **日志性质**：本文档只记录**真机跑出来的东西**，不记录"应该是什么"。
> 每条结论后附可复跑的命令；没跑过的（LLM 问答）明确标 **未跑**。

---

## 0. 前置核实（跑之前先确认环境是什么）

| 项 | 取值 / 结果 | 核实方式 |
|---|---|---|
| 后端 | `http://127.0.0.1:8000`，`version=1.4.0`，`database=up` | `scripts/demo_rehearsal.py` 步骤 0 |
| 图谱版本 | `attendance-demo-v1`（活跃版本） | A1 响应 `kg_version` 字段 |
| **LLM 凭据** | **未配置**（`LLM_API_KEY` 为空）⇒ `/agent/query` 到 LLM 侧必然 501 | 只读 `.env.development` 的**键长度**，不打印密钥 |
| Neo4j / PG | 均可用（A1~A3 全走真库） | 彩排 PASS |
| 前端 | `USE_MOCK=true`（默认）与 `USE_MOCK=false` **两种都跑了** | 见 §4 |

**为什么先把「LLM 未配置」写在最前面**：它决定了本文档里
「政策问答」这一条**只有推理路径是真机、答案侧不是**。不写清楚，
读日志的人会把 E2 页面上的占位答案当成真机产出（已登记 `dev-doc-status.md` **R13**）。

---

## 1. 门禁（全量，逐条实跑）

| 门禁 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `uv run pytest -q` | **498 passed, 1 warning**（0 xfail） |
| 后端 lint | `uv run ruff check app/ tests/ scripts/` | 通过（`--fix` 后复跑 0 问题） |
| 后端格式 | `uv run ruff format app/ tests/ scripts/` | 通过 |
| 契约零漂移 | `uv run python scripts/export_openapi.py --check` | 无 diff |
| 接缝纪律 | `uv run python scripts/check_seams.py` | `ERROR 0 / WARN 0 / OK 9` |
| 前端类型 | `npx tsc --noEmit` | 通过 |
| 前端 lint | `npx eslint src --max-warnings 0` | 通过 |
| 前端构建 | `npx next build` | 编译通过（**14 路由**） |

---

## 2. 真机跑数（考勤域彩排，2026-09-28）

```
uv run python scripts/demo_rehearsal.py --domain attendance
```

```
[PASS] 步骤 0 服务健康: version=1.4.0 checks={'database': 'up'}
[PASS] 步骤 A1 异常清单: total=1 kg_version=attendance-demo-v1 首条=张伟 / 2026-10-16
[PASS] 步骤 A2 合规扫描: total=8（high 2 / medium 6） 规则值 7 条全部带出处；
       样例 李静「月排班 216h（22 天）− 月标准 174h = 加班 42h > 上限 36h」
[PASS] 步骤 A3 异常归因: 张伟 2026-10-16 ⇒ 外勤出勤成立（置信度 1.0 = 1/1，
       4 项原因、政策出处 2 条）
[SKIP] 步骤 3 提问: ¥0 默认跳过（真实 LLM 烧 token）
[PASS] 步骤 6 审计回放: trace 7d2a2b37 共 3 条，action 齐全
彩排结束：PASS 5 / FAIL 0 / SKIP 2
```

**观察日推进**（`--as-of 2026-12-15`，验「调休临期升级」）：

```
[PASS] 步骤 A2 合规扫描: total=8（high 6 / medium 2） 规则值 7 条全部带出处
```

⇒ 同一批数据在更靠近季度末的观察日下，high 由 **2 → 6**、medium 由 **6 → 2**，
临期升级**按设计生效**（不是数据变了，是观察日变了）。

**含前端页**（`--frontend-base http://127.0.0.1:3000`，`USE_MOCK=false`）：

```
彩排结束：PASS 9 / FAIL 0 / SKIP 1
```

⇒ 4 个页面（域首页 / 合规预警 / 异常归因 / 政策问答）在**关 Mock** 下均返回
预期关键词；Mock 模式（`USE_MOCK=true`）下同样 PASS 9 / FAIL 0。

---

## 3. 关键发现（**都是跑出来才看见的**，不是设计时想到的）

### 3.1 数据层：结构化事实与制度条款**不连通**

```
MATCH (:Entity{entity_type:'EMPLOYEE'})-[*1..3]-(:Entity{entity_type in ['POLICY_CLAUSE','REGULATION']})
⇒ EMPLOYEE 0 条 / OVERTIME 0 条 / ATTENDANCE_RECORD 0 条 / WORK_ORDER 0 条
```

CSV 派生的考勤事实与 M2 抽取的制度条款混在同一 `kg_version` 里，但**彼此没有任何边**。
⇒ 「问句 → 锚点 → …… → 制度条款」的链**走不到条款**；D1 的路径只能落到「事实记录」，
制度侧另由 `search_policy_sentences`（**PG 文本层**）取 ⇒ 两条证据链**不同源**。
已登记 **R10**；要打通需改入图器（语料 / 本体变更 + 重建图），**本 Sprint 未做**。

### 3.2 同一 `kg_version` 混住两类节点，噪声会压过真身

问「张伟…」时锚点定位到的不是 `EMPLOYEE:E001`，而是 `ent_91505c0c108f`
（M2 span 抽取的碎片实体，名字恰好也匹配）。因为「长名优先」，噪声还**赢过**结构化节点
⇒ 链为空。修法：锚点只认 `NAMESPACE:ID` 形态的**确定性派生**节点
（`reasoning._is_deterministic_node_id`，与 `attribution.list_anomaly_cases` 的
`STARTS WITH 'EMPLOYEE:'` 同一条纪律）。已登记 **R11**。

### 3.3 子图采样会把锚点类型挤出子图

`fetch_all_subgraph(node_limit=2000)` 返回的 2000 个节点里**没有 `EMPLOYEE:E001`**
（SHIFT 880 条 / ATTENDANCE_RECORD 数百条把它挤掉了），而问答主链路默认 `node_limit=500`
⇒ 演示现场大概率零命中。加了一层「按名字直查确定性派生实体」的兜底
（`_fallback_anchors`，记 `reasoning_path_anchor_fallback` 日志）。
**这是工程性补救不是根治**（根因：用一次截断子图当问答上下文）。已登记 **R12**。

### 3.4 路径排序必须按「解释力」而非「最短」

三次排序迭代的实测结果：

| 排序口径 | 真机结果 | 问题 |
|---|---|---|
| 跳数最少 | 每条问句都是「员工 → 门禁记录」 | 门禁无解释力，等于没推理 |
| + 终点证据价值 | 张伟 → **罗伟(同事)** → 郑州出差单 | 每步都是真边，但**落到同事头上** |
| **+ 中途禁止经过 `EMPLOYEE`** | 张伟 → 工单；李静 → 考勤记录 → 排班 | ✅ 采用 |

### 3.5 D2 守卫当场揪出的 2 条既有违规（已修，非豁免）

1. `rules/engine.py::_rule_comp_off` 的 `threshold=0.0` 是裸代码常量 ⇒ 提为
   `SENTINEL_UNUSED_BOUNDARY` 并在 `calculation` 里说出语义；
2. `rules/attribution.py` 的 `action` 无条件硬编码「系统自动补卡」，制度缺失时
   `policy_refs=()` 却仍声称制度动作 ⇒ 改为 `sentences` 非空才给制度动作。

守卫**未放宽**：xpass 时 `xfail(strict=True)` 会把测试打红，所以两条都**修掉**而非豁免 ———
现在 `pytest` 是 **498 passed、0 xfail**。

---

## 4. 未触碰项（**没做的，逐条列出**）

| # | 项 | 原因 |
|---|---|---|
| 1 | **真实 LLM 问答**（`--with-llm`） | 本机无 `LLM_API_KEY`；推理路径不出 LLM 故已取真值，**答案侧从未真机跑过**（R13） |
| 2 | 受控问题集**未覆盖考勤域** | `eval_controlled_qset.py` 的 14 问仍是关联交易语料；不得据本 Sprint 声称 M3-1 终局达标 |
| 3 | 事实 ↔ 条款的本体 link | 需改入图器 + 重建图（R10），属范围变更 |
| 4 | `fetch_all_subgraph` 采样策略根治 | 只做了兜底（R12） |
| 5 | 语料标注的**全局机制** | 目前是页面文案各写一句（R9） |
| 6 | 归档 / tag | 归档会移动目录，待本 Sprint 收尾时执行 |

---

## 5. 收尾确认

- [x] 后端 5 条门禁全绿（pytest / ruff / 契约 / 接缝 / 格式）
- [x] 前端 3 条门禁全绿（tsc / eslint / build）
- [x] 考勤域彩排 `--domain attendance`：**PASS 5 / FAIL 0**（含前端页时 PASS 9）
- [x] 关 Mock（`USE_MOCK=false`）下同样 PASS 9 / FAIL 0
- [x] 推理路径**真机实跑**取到链（李静 2 跳 / 张伟 1 跳）
- [x] 4 份文档同步（`sprint-calendar` §5 S9.5 + §6 v1.8 / `dev-doc-status` §8 R9~R13 /
      `acceptance-traceability-matrix` M3 + M3-1 + 步骤 5 / `03-prd` §2.1）
- [ ] 真实 LLM 问答（**待有凭据时补跑**，不得对外声称已走通）
- [ ] 归档 + tag
