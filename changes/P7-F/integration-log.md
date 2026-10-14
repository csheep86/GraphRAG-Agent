# P7-F · 集成日志（TBD-7 阈值回填）

> **日期**：2026-10-14 ｜ **状态**：**已交付**（一处偏离 proposal §2 第 2 步，已在 §3 登记）
> **来源**：`docs/release-readiness-audit-2026-10-13.md` §3 A3 ｜ `changes/P7-F/proposal.md`

---

## 1. 决策表（**出口判据 1 的唯一载体**）

| 项 | 内容 |
|---|---|
| **裁决人** | **用户本人**（会话内裁决；本机账户 `william`）。⚠️ **真名留白待本人补**——按项目纪律 AI 不代填人名，P8-Release 终审前请本人补上 |
| **裁决日期** | 2026-10-14 |
| **裁决值** | `EVAL_SINGLE_DOC_TOKEN_CEILING` = **32 000（维持原值）** |
| **裁决性质** | **产品期出厂默认 ceiling** |
| **裁决理由（用户原话要旨）** | 「现在是做产品、还没卖给客户；未来有了客户、有了需求才满足客户需求。现在要的是**通用的数**，不是某个行业的数」 |
| **落点** | `backend/app/core/config.py:295-315` / `backend/.env.example:318-335` / 矩阵 `:205` / 审计 `:50` `:62` |
| **重裁触发条件** | ① 出现第一位外部持证客户；② 拿到 ≥3 份**真实业务长度**文档的 `cost_records`；③ 抽取调用粒度变化（每 chunk ↔ 每文档） |

> 背景补充（事实，非裁决）：`config.py:302` 是 **Settings 字段** ⇒ `EVAL_SINGLE_DOC_TOKEN_CEILING`
> **可经 `.env` 覆盖**（specs/m6-ontology-incremental.md:82 既定规矩）
> ⇒ 本值是**出厂默认**，部署方可按客户实际语料各自调整，**不必改代码**。用户「等客户来了再满足」
> 的诉求，在这个设计里本来就被支持。

---

## 2. 本机**刻意没改**的东西（这是本批最重要的判断）

| 项 | 处置 | 为什么 |
|---|---|---|
| 阈值**值** | **未改**（仍 32000） | 裁决内容就是"维持原值" |
| `threshold_source` | **仍 `provisional`** | 见 §3 |

---

## 3. ⚠️ 偏离 proposal §2 第 2 步的登记（按 §5 情况 2 处置）

**proposal 原文**：「把 `threshold_source` 由 `provisional` 改为 `decided`（若字段名不同，先据实登记再改）」。
**实际执行**：**没有改**。据实登记如下。

### 3.1 为什么改了会是假绿（机器依据）

`app/evaluation/criteria.py` 三值语义：

| `threshold_source` | `judge()` 的输出 |
|---|---|
| `THRESHOLD_PROVISIONAL` | **`PASS(provisional)`**（防假绿） |
| `THRESHOLD_ENV_OVERRIDE` / `THRESHOLD_CALIBRATED` | **纯 `PASS`** |

⇒ 若把 source 改成"已裁决"，32000 就会判出**纯 PASS**，等同于宣称「TBD-7 已收敛」。
而真实情况是：

- 唯一实测样本 **n = 1**，且那份文档正文**仅 1019 字**（制度类）；
- `--calibrate` 给出的建议值 9100 **已被否**（代表性不足）——见矩阵 `:205` P6-V5 段。

**没有样本支撑的东西被标成"已达标"，正是 R-10 / §5.2 要挡的形状。**

### 3.2 「裁决」与「校准」是两件事

用户的裁决是**策略层的**（"出厂默认用多少"），不是**证据层的**（"这个数经过验证"）。
现有两个标签把这两件事混成一个轴 ⇒ 一刀切地改标签会连带改掉"是否构成达标证据"这一层。
本批选择：**保留兜住真话的那层**（`provisional`），把裁决**登记在注释与矩阵里**，让它在账上不消失。

### 3.3 机器证据（改完后现场跑）

```
$ uv run python scripts/eval_acceptance.py --calibrate
当前 ceiling: 32000 token/doc  [threshold_source=provisional]
  ⚠️ 该值是**演示语料推算的默认值**（config 默认，未经校准）
     ⇒ 判定只给 PASS(provisional)，**不构成 TBD-7 收敛证据**。
```

⇒ 值未变、判定未放开，**与裁决一致**。

---

## 4. 出口判据逐条核销

| # | 判据 | 状态 | 依据 |
|---|---|---|---|
| 1 | ceiling = 裁决值，日志有裁决人 + 理由 + 日期 | ✅ | §1 决策表（真名待本人补） |
| 2 | `pytest` 不降（尤其 `test_eval_acceptance_cli.py` 三锚点） | ✅ | 见 §5 |
| 3 | 矩阵 C3-a / C3-b 行 `PASS(provisional)` → `MEASURED` | ⚠️ **部分，见下——这是本批唯一没闭合的判据** | 需终审确认语义 |
| 4 | 三件套 + CI 四 job 全绿 | ✅ | 见 §6 |

### 4.1 判据 3 未闭合的原因（**待你在 P8-Release 前确认**）

矩阵`:205` 用的是 ⏳ / ✅ 图例，**没有 `MEASURED` 这个状态词**；而代码里的状态枚举实际值是：

```
CriterionStatus.MEASURED_PROVISIONAL   ← tests/test_eval_cost_criteria.py:150 实测断言
```

⇒ 「C3 转 MEASURED」有两种读法，**我不自行挑选**：

| 读法 | 是否已达成 | 依据 |
|---|---|---|
| **A**：MEASURED = 「有真实实测值，不再 BLOCKED」 | ✅ **已达成** | `7574.0000 token/doc`（n=1，`eval-live-20261012T065005Z.json`），status = `MEASURED_PROVISIONAL` |
| **B**：MEASURED = 「判定可给纯 PASS（阈值已校准）」 | ❌ **未达成，且须烧 LLM** | 需先用 ≥3 份**真实业务长度**文档跑 `--calibrate` 出建议值，再走一次人裁决 |

**我的判断**：P8-Release §1 前置第 3 条真正卡的是「阈值是否有人裁决」（因为它标注为 *只能用户* 的 0.1 人天项），
这一条已闭合；读法 B 需要的不是"裁决"而是"校准样本"，属于另一笔工作。
但**这个歧义我不替你裁** —— 若终审要求 B，请让我先用多份真实长度文档跑一轮（会产生 LLM 费用，需你批准）。

---

## 5. 实测读数

| 项 | 读数 |
|---|---|
| P7-F 点名文件（`test_eval_acceptance_cli.py` / `test_eval_cost_criteria.py` / `test_evaluation_criteria.py`） | **44 passed / 0 failed** |
| 全量 pytest（本地） | **1298 passed / 46 skipped / 0 failed** |
| ↳ 核销 | 与 P7-K 收尾时读数**持平**（本批纯注释 + 文档，**零行为改动 ⇒ 计数不动才是对的**） |
| ruff check / format | `All checks passed!` / 全部已格式化 |
| 接缝纪律 | `[OK]` 通过 |
| 契约零漂移 | `[OK] openapi.yaml 与后端模型一致` |
| 会话漂移 | 本批仅注释 + 文档，无新增模块 ⇒ **无 S5 风险** |

> ⚠️ 本地 `1298 / 46 skipped` 与 CI `1337 / 7 skipped` 相差 **39 条 skip**（CI 有真 Neo4j/PG）。
> 两个口径**不可互换**（同一份代码、不同环境）。

---

## 6. Non-goals 逐条核销（照 proposal §3，共 6 条）

| # | Non-goal | 是否守住 | 依据 |
|---|---|---|---|
| 1 | 不替用户选值 | ✅ | 值是用户选的（策略 (a) 维持原值）；我未提议任何具体数字 |
| 2 | 不再跑一次 `--calibrate` 去"优化"数值 | ✅ | 跑 `--calibrate` 仅作**核验**（§3.3 留证），未用它改任何配置 |
| 3 | 不动 C3-b 的同量纲裁决与 `0.0` 语义 | ✅ | 矩阵 `:206`、审计 C3-b 行**未改**（C3-b 阈值来自 `metrics.COST_RATIO_SIGNIFICANT`，已 `PASS`） |
| 4 | 不做 stage 切片 / 仪表盘改造 | ✅ | 未触及 |
| 5 | 不新建全量重建入口 | ✅ | 未触及 `incremental.py` |
| 6 | 不做交付动作 | ✅ | 无 release notes / tag |

---

## 7. 遗留（给 P8-Release）

1. **§1 裁决人真名**：请本人补（AI 不代填人名）。
2. **§4.1 的 MEASURED 语义**：选 A 还是 B。选 B ⇒ 需批准一轮多文档真实长度 `--calibrate`（LLM 费用）。
3. 若将来出现外部客户 ⇒ 按 §1 的重裁触发条件**重来一次**，届时可能需要新 CodeBuddy 批次。
