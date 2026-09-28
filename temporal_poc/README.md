# 知识过期治理选型 PoC：自研 vs 开源

> **【Sprint 9 批次 B2 已收口，先读这一句再往下看】**
> Track S 的**判分口径已迁入正式测试集** `backend/tests/test_temporal_track_s.py`：
> 同一份语料、同一组判据，默认零外部依赖（CI 可跑），设 `TEMPORAL_TRACK_REAL_URI`
> 即可连真机重跑同一组断言（`pytest tests/test_temporal_track_s.py`）。
> 本目录的两轨脚本保留为**实验原迹**——它是 ADR-0005 决策的证据源，
> 不要再在这里改判据；判据改动一律走正式测试集。
>
> 目的：用**同一份语料、同一组判分口径**把「继续自研」和「引入开源（Graphiti）」
> 放在一起实测，用数据而不是感觉决定路线。
> 日期：2026-09-27　结论：**采用路线 S′（自研 + 抄 Graphiti 双时态模型）**，Graphiti 转备选。
>
> **本实验是 [`docs/adr/ADR-0005-temporal-knowledge-model.md`](../docs/adr/ADR-0005-temporal-knowledge-model.md) 的证据源**：
> 决策（自研 vs 引入）由本文实测数据拍板，字段模型与仲裁规则见 ADR §4 / §5，排期见 ADR §6。
> 判据脚本已被 `specs/m2-extract-kg.md` §3 验收 9 / 10 引用为**机械判据原型**（S9 批次 C 迁入 `backend/tests/`）。

---

## 1. 为什么做这个实验

我要解决的是「知识图谱随时间过期」：同一家公司在不同日期的披露文件里，
法定代表人 / 注册资本 / 住所会变。静态图谱会把新旧事实**并存**，
而正确行为是：**旧事实失效但保留可回溯，新事实成为当前值**。

候选路线：

| 路线 | 做法 |
|---|---|
| **Track S（自研）** | 现有 DeepSeek 抽取链路 + 自写时态字段 + 自写失效仲裁 |
| **Track G（Graphiti）** | 引入 graphiti-core，用其内建双时态与**自动矛盾失效** |

这类能力不能靠读文档判断，只能实测——因为成败取决于**你的模型供应商**是否扛得住它的结构化输出要求。

## 2. 实验设计（可复现）

- **语料** `corpus.py`：同一家公司两期文本，`fact_date` 分别为 `2023-12-31` 与 `2025-05-01`，
  覆盖三类易过期事实：**实体型**（法定代表人 张三→李四）、**数值型**（注册资本 10 亿→20 亿）、**地址型**（住所）；
- **判分**（两轨完全一致）：① 当前值是否正确；② `as-of 2024-06-01` 回溯是否得到旧值；
  ③ 历史是否保留（失效边未被物理删除）；④ 是否自动判失效；
- **重复 3 轮**：单次成功只能证明"能跑"，重复才能证明"敢进生产"。

```powershell
# Track S（用项目自身环境）
cd backend
uv run python ../temporal_poc/run_track_s.py

# Track G（独立虚拟环境）
cd temporal_poc
.venv\Scripts\python.exe repeat_g.py      # n=3 稳定性实验
.venv\Scripts\python.exe diag_g.py        # 用 backend 环境查 G 的落盘结果
```

## 3. 实测结果

| 指标 | Track S（自研） | Track G（Graphiti） |
|---|---|---|
| 时态字段抽取 | ✅ DeepSeek 稳定产出，`valid_from` 覆盖率 **100%** | ✅ `valid_at/invalid_at` + `created_at/expired_at` 双时态齐全 |
| **当前值正确** | ✅ **3/3** | ⚠️ 视同环比，见下 |
| **as-of 回溯正确** | ✅ **3/3**（2024-06-01 → 张三） | 未计入（当前值尚不稳） |
| **自动判失效（过期治理）** | ✅ **3/3**（确定性规则） | ❌ **1/3** |
| 历史保留 | ✅ 3/3（总边 15–16，存活 5–7） | ✅ 自动打 `expired_at`，历史不删 |
| 单轮耗时 | ≈ 8.5s，**2 次** LLM 调用 | ≈ 10–11s，**多次** LLM 调用（抽取+去重+矛盾判定） |
| 新增依赖 | **0**（复用现有 DeepSeek 通道） | graphiti-core + **必须补 Embedding** + 可在位编码 |
| 失败模式 | 确定、可定位（见 §4 坑 5） | 概率性，且出现入二中抛异常留半成品图 |

### Track G 三轮明细（`repeat_g.py hash` 占位向量）

```
第 1 轮: 10s, 边=9,  自动失效=2, 旧法人已失效=False, 新法人在位=True,  过期治理OK=False
第 2 轮: 10s, 边=9,  自动失效=2, 旧法人已失效=True,  新法人在位=True,  过期治理OK=True
第 3 轮: 11s, 边=10, 自动失效=2, 旧法人已失效=False, 新法人在位=True,  过期治理OK=False
过期治理命中 1/3 轮
```

### 对照组：换真实中文语义 Embedding（`repeat_g.py semantic`，bge-small-zh-v1.5）

```
第 1 轮: 11s, 边=9,  自动失效=2, 旧法人已失效=False, 过期治理OK=False
第 2 轮: 11s, 边=12, 自动失效=2, 旧法人已失效=False, 过期治理OK=False
第 3 轮: 10s, 边=8,  自动失效=2, 旧法人已失效=False, 过期治理OK=False
过期治理命中 0/3 轮
```

**干扰项被证伪**：换成真实语义向量后没有变好（1/3 → 0/3），
说明失败**不是**占位 Embedding 造成的，而是在"DeepSeek + `json_object` 降级"这个组合下，
它的**矛盾/失效判定**本身不够可靠。

### 根因（`diag_g.py` 抓到的现场）

Graphiti 针对变更句单独建了一条边，并**把这条"变更陈述边"判失效**，
而真正该过期的那条旧边**依然存活**：

| 边的 fact | invalid_at | 结果 |
|---|---|---|
| 招银金融租赁有限公司的注册地为上海市浦东新区 | 2025-05-01 | 失效（这条是重复陈述，不是我们关心的） |
| 招银金融租赁有限公司的法定代表人**由张三变更为李四** | 2025-05-01 | 失效 ← **错杀了陈述边** |
| **招银金融租赁有限公司的法定代表人为张三** | **None** | ❌ 该过期的反而活着 |
| 自 2025 年 5 月起…法定代表人变更为李四 | None | ✅ 存活 |

即：**「张三」和「李四」同时是当前事实**——正是我们想消灭的静态图谱病态。

为什么自研反而不犯这个错？因为**我们有受控 schema**：`relation_type` 是枚举
（`LEGAL_REP`），同一 `(head, relation_type)` 下出现不同 tail 就是**结构性矛盾**，
精确匹配即可判定，不需要 LLM 比较两句自然语言。Graphiti 是**开放抽取**，
事实写作是自由文本（"为张三" vs "变更为李四"），它只能靠语义相似度
+ LLM 判断，噪声大得多。**这是本次实验最有价值的发现。**

## 4. 踩过的坑（留给后续实施）

1. **DeepSeek 不支持 `json_schema`**：Graphiti 默认结构化输出直接 400
   （`response_format type is unavailable`）。解法是 `structured_output_mode="json_object"`
   ——Graphiti 源码注释里点名 DeepSeek 属于这一类；代价是 schema 不再被强约束，
   改由 prompt 引导，**这也是 G 侧不稳定的原因之一**。
2. **Graphiti 默认 cross-encoder 要求 `OPENAI_API_KEY`**：哪怕你完全不用 OpenAI，
   不传 `cross_encoder` 就会在构造时抛"缺凭据"。
3. **判分字符串空格**：模型对「陆家嘴环路 500 号」是否带空格不稳定，
   不去空格归一会把"答对了"误判成"答错"（两轨都差点栽在这）。
4. **PowerShell 会把 `$gid` 吞掉**，内联 Cypher 直接语法错误 —— 一律写成脚本文件跑。
5. **Track S 首版仲裁过度失效**（最关键的一条）：
   条件是 `valid_from <= 新值` 且未排除同 episode。而变更句「由张三变更为李四」
   会让 DeepSeek 把**旧值和新值都抽成同一锚点日期**的边，
   于是先写的"李四边"被后写的"张三边"反过来封掉，**当前值全线阵亡**。
   修法是两条确定性规则：跨 episode 只封**严格更早**的边；同 episode 同锚点则
   保留原文中最晚出现的值。

## 5. 决策：路线 S′

**保留自研主干，把 Graphiti 的双时态数据模型抄过来。**

理由（都来自上面的实测）：

1. DeepSeek **能稳定做时态抽取**（100% 覆盖率），这块不必换组件；
2. Graphiti 的**数据模型**比它的**自动仲裁**更值钱：`valid_at/invalid_at`（事实维）
   + `created_at/expired_at`（摄入维）+ Episode 血缘，这套四字段设计直接照搬；
3. 关键取舍：**我们有受控 schema（`relation_type` 枚举）**。
   判重可以走 `(head, relation_type)` **精确匹配**，而 Graphiti 是开放抽取，
   只能靠 embedding 语义召回再做 LLM 判断 —— 在这一点上自研反而结构性占优，
   **不需要 embedding 就能拿到比它更高的确定性**；
4. 失败可调：自研规则出错是确定的、能定位（见 §4 坑 5）；
   Graphiti 出错是概率性的，且依赖外部 LLM + embedding 质量。

**落地三步**（与页面改造可并行）：

```
L0  Document.document_date + 抽取 v3 加 valid_from/valid_to  → 已验证可行
L1  写入 ~(head, relation_type) 精确匹配仲裁 + 双时态四字段 → PoC 已跑通
L2  疑点机制接入矛盾、页面「失效」视觉语义、验收矩阵补验收项
```

**Graphiti 留在备选**：若日后引入真实中文 Embedding（如 `bge-small-zh`），
重跑本实验（`repeat_g.py` + `semantic_embedder.py`）；若 n=3 命中 ≥2/3，
再把图谱引擎层换掉也不迟 —— 因为 L1 已经按它的模型在写字段，届时是**平替**不是重写。
