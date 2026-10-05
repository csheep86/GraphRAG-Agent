# P6-G · 归还 D1 技术债（`_ensure_chat` 根因）

> **日期**：2026-10-05 ｜ 上一批：`changes/P6-F`（C1 首次出数 0.0909）
> **性质**：**还债** —— 不还它，后面每一批都要各自补一次补丁，且每次都会撞同一种看不懂的报错
> **一句话**：让 AgentService 的 LLM 装配**自洽**（谁用谁 ensure），从而**删掉** P6-F 在评测侧留下的绕路补丁

---

## 1. 这个债是怎么来的（必须写明，否则看不懂为什么现在才修）

P6-F 为了让 C1 出数，在 `app/evaluation/baseline.py` 里写了这么一段注释 + 一行调用：

```python
agent = AgentService()
agent._ensure_chat()          # ← 绕路补丁
raw_answer, _ = await agent._invoke_chat_with_retry(...)
```

当时**为什么不在产品侧改**：P6-F 的 Non-goals 第 6 条写着「不动被测链路」（`agents.py` /
`graphs.py` / prompt 属被测对象），而本批要出的是 C1 的数字 —— 动了被测链路，那次测出来的
数字就要重新解释。所以当时的选择是**在评测侧补装配 + 把根因登记成 D1 待修**。

**为什么现在必须还**：

1. **D1 不是评测侧的私有问题**。它是「任何绕开 HTTP 路由直接调 `AgentService` 的调用」的通病 ——
   后台任务、批量脚本、未来的 worker 都会踩，且**每次都要有人重新排一次错**；
2. 报错形态极难定位：`AttributeError: 'NoneType' object has no attribute 'ainvoke'`，
   **不是** `AgentUnavailableError` ⇒ 上层（含路由的 501 映射与评测的 `blocked_by`）全都读不出真因；
3. 本人验过：P6-F 第一次跑 C1 时，报告只甩出三行 `AttributeError("'NoneType' object has no
   attribute 'ainvoke'")`，我花了整一轮才查到是 LLM 客户端没装配。

## 2. D1 的确切形状（已核实，非推测）

| 位置 | 代码 | 说明 |
|---|---|---|
| `agents.py:174` | `def _ensure_chat(self)` | **幂等**懒加载：已有则直接返回，否则装配并校验 KEY / LangChain |
| `agents.py:449` | `self._ensure_chat()` | 全仓**唯一**调用点，在 `answer()` 里；注释写明「仅为触发前置检查」 |
| `agents.py:553` | `await self._chat.ainvoke([...])` | **直接用 `self._chat`**，从不 ensure ⇒ 绕过 `answer()` 就是 `None` |

⇒ 走 HTTP 路由（→ `answer()`）没事；**评测基线侧的 `answer_with_dense` 直接调
`_invoke_chat_with_retry`** ⇒ 必炸。这条路径是 P6-F 新增的（dense top-k 基线），
所以这个坑是在 P6-F 才第一次被踩到。

## 3. 修法（极小）

在 `_invoke_chat_with_retry` 开头调用一次幂等的 `self._ensure_chat()`。

**为什么这样就够 / 且是「零行为变化」**：

- `_ensure_chat()` 第一段就是 `if self._chat is not None: return self._chat` ⇒ HTTP 路径
  （已在 `answer()` 里装配过）**多这一次调用是无操作**，不是重新装配、不会重新读 KEY；
- 失败语义不变：仍抛 `AgentUnavailableError`（KEY 缺失 / LangChain 装配失败）⇒ 路由层照旧 501，
  评测侧照旧把它翻译成可读的 `blocked_by`；
- 于是 `answer()` 里那句 `_ensure_chat()` 从「唯一救命稻草」降级为「尽早失败的检查」，
  **保留**（它让 KEY 缺失在跑重活之前就炸，而不是等检索完了才炸）。

## 4. Non-goals（**冻结，drift S1 会逐条读出来**）

1. 不改 `_ensure_chat` 的**失败语义**与抛出的异常类型（仍是 `AgentUnavailableError`）；
2. 不改变 HTTP 路由可见的行为（`/agent/query` 的成功/失败/状态码**一律不变**）；
3. 不动 `contracts/openapi.yaml`、不加任何 `settings` 配置项、不动 ADR；
4. 不顺手修 H6 引用回溯 403、制度入图器「条款数一致」自检恒 FAIL、P7-B readiness 静默 skip、G-12；
5. 不碰 C1 / C2 任一条判据的**逻辑与阈值**（阈值属阶段 ⑤ TBD-7）；
6. 不改 prompt（`kg_qa_v5`）、不改重试策略（`tenacity` 步长与次数）；
7. **不扩大受控题集**（P6-F 已实测「14 题 ⇒ 单题翻转 ±7.1pp」，扩集合另开批次讨论）；
8. 除「`agents.py` 加一行 ensure」与「`baseline.py` 删补丁」之外**不改动其它任何文件**
   ⇒ 本批 `git diff` 应**只有 3 个文件**：`agents.py` / `baseline.py` / 新增测试。

## 5. 出口判据

| # | 判据 | 怎么验证 |
|---|---|---|
| E1 | 评测侧绕路补丁**已删除**，且 C1 仍能出数 | `baseline.py` 里 `agent._ensure_chat()` 消失 ⇒ live 复跑 C1，值仍应为 **0.0909** |
| E2 | **不经 `answer()`** 直接调 `_invoke_chat_with_retry` 也能工作 | 新增单元测试（mock LLM 客户端）⇒ 绿 |
| E3 | 反向验证：**撤掉**根因修复 ⇒ 上述测试**必须红** | 变异测试 ⇒ 用真实 AttributeError 判红（不是我以为它会红） |
| E4 | HTTP 路径**零行为变化** | 既有 agent 路由测试全绿 + 契约零 diff |
| E5 | 假绿检查：不许用「打桩把 `_chat` 预先塞好」来让 E2 变绿 | E2 用例里 `AgentService._chat` 初始必须是 `None`（由 reset 保证） |

> **注意 E5**：这条最容易被自己绕过 —— 若先 `service._chat = fake` 再调，
> 就算没修也一样绿。测试必须从「**从未装配**」的状态起步。

## 6. 顺序

```
T1 边界文档（本文件，已冻结）
T2 修根因（agents.py 1 行）+ 删评测侧补丁
T3 补 D1 的根因级回归测试（含 E5 约束）
T4 反向验证：撤修复 ⇒ 判红；还原 ⇒ 全绿
T5 live 复跑 C1 确认还是 0.0909（补丁删了没退化）
T6 门禁 + 集成日志 + 提交
```
