# P6-G · 集成日志（归还 D1：`_ensure_chat` 根因）

> **日期**：2026-10-05 ｜ **边界文档**：见本目录 `proposal.md`（Non-goals 8 条已冻结）
> **性质**：**还债** —— P6-F 为守住「不动被测链路」而在评测侧补了 1 行绕路补丁；
> C1 既已出数，这行补丁连同它的根因一起归还。
> **一句话**：产品侧 **`+13` 行（其中实际代码 1 行）**，评测侧 **`−14` 行**，C1 复跑仍是 **0.0909**。

---

## 1. 这个债是怎么来的、为什么现在还

P6-F 写 C1 的时候，`app/evaluation/baseline.py` 里留了这么一段：

```python
agent = AgentService()
agent._ensure_chat()          # ← 绕路补丁 + 13 行"为什么不在这里修根因"的说明
raw_answer, _ = await agent._invoke_chat_with_retry(...)
```

当时不动产品代码的理由写在 P6-F 的 Non-goals 第 6 条（被测链路不许动）——那是对的，
因为那批要出的是 C1 的数字，动了链路那次数字就得重新解释。

**现在必须还的三个理由**（见 `proposal.md` §1）：

1. 它是**通病**不是评测侧私事：任何绕开 HTTP 路由直接调 `AgentService` 的调用方
   （后台任务 / worker / 批量脚本 / 未来的异步 quality_check）都会踩，**每次都要有人重新排一次**；
2. 报错形状极难定位：`AttributeError: 'NoneType' object has no attribute 'ainvoke'`
   **不是** `AgentUnavailableError` ⇒ 路由层的 501 映射、评测的 `blocked_by` 全都读不出真因。
   P6-F 首跑 C1 时报告只甩出三行这个异常，**我为此排查了整整一轮**；
3. 债不加 divergence 地放着，会变成后面每一批的隐性税。

## 2. 改了什么（**总计 3 个文件**）

| 文件 | 改动 | 行数 |
|---|---|---|
| `app/services/agents.py` | `_invoke_chat_with_retry` 开头补一次幂等的 `self._ensure_chat()` + 说明为什么必须兜住 | +13（**代码 1 行**） |
| `app/evaluation/baseline.py` | **删掉**绕路补丁与其说明 | −14 |
| `tests/test_agent_llm_assembly.py` | 新增根因级回归测试 3 条 | +（新文件） |

⇒ 与 `proposal.md` Non-goals 第 8 条自承诺的「只有 3 个文件」一致（drift S2 已核对）。

### 为什么这是「零行为变化」

`_ensure_chat()` 的第一行就是 `if self._chat is not None: return self._chat` ⇒
HTTP 链路在 `answer()` 里已装配过，**这一次调用是无操作**：不重新读 KEY、不重建客户端。
失败语义也没变：KEY 缺失仍抛 `AgentUnavailableError` ⇒ 路由层照旧 501。

## 3. 反向验证（**撤掉修复 ⇒ 必须真的红**）

| 步骤 | 结果 |
|---|---|
| 删除 `_invoke_chat_with_retry` 里的 `self._ensure_chat()` | **2 failed / 1 passed**，报错是真实的 `AttributeError: 'NoneType' object has no attribute 'ainvoke'`（`agents.py:564`） |
| 还原 | **3 passed** |

⇒ 不是「我以为它会红」，是撤了它就红。两条失败的正是有含金量的那两条：
① 绕过 `answer()` 直接调用（E2）；② KEY 缺失时应当抛 `AgentUnavailableError` 的语义守卫。
第 3 条（`_ensure_chat` 幂等性）本来就不依赖这次修复，保持绿是预期的。

### 顺带钉住的一条假绿入口（E5）

新的测试用例**一律**从 `AgentService.reset()` 之后的**从未装配**状态起步。
如果谁图省事先写 `service._chat = fake` 再调用，那么就算产品代码根本没修、测试也照样绿 ——
那种测试保护的是「本坑恰恰不起作用的那部分」。E5 把它写成了显式约束。

## 4. 出口判据逐条核销

| # | 判据 | 实测 |
|---|---|---|
| E1 | 补丁删了 C1 仍出数 | ✅ live 复跑 `c1_graph_gain` = **0.09090909**（graph 0.8571 / baseline 0.7857 / `corpus_layer=L2` / `blocked_by=None`），与 P6-F 三遍**完全一致** |
| E2 | 不经 `answer()` 直接调用也能工作 | ✅ 新增测试绿；撤修复 ⇒ 红 |
| E3 | 撤修复 ⇒ 判红 | ✅ 2 failed（真实 AttributeError），还原 3 passed |
| E4 | HTTP 路径零行为变化 | ✅ 既有 agent 路由测试全绿 + **契约零 diff** |
| E5 | 不许预塞 `_chat` 骗取绿灯 | ✅ 用例均以 `reset()` 后「从未装配」起步 |

## 5. 门禁数字

```
pytest（真 Neo4j / 真 PG + app_rls）   966 passed / 3 skipped / 3 xfailed   ← 963 ⇒ +3，0 回归
ruff check .                           All checks passed!
ruff format --check .                  232 files already formatted
check_seams.py                         [OK] 接缝纪律通过
export_openapi.py --check              [OK] 契约零 diff
check_session_drift.py                 S1 读到 changes/P6-G/proposal.md 的 8 条 Non-goals ✅
```

## 6. 收尾三问（自答）

1. **有没有"顺便做的"？** 没有。本批 `git diff` **只有 3 个文件**，且全部服务于
   「归还 D1」这一件事。H6 403、制度入图器自检恒 FAIL、P7-B、G-12 **一个没碰**。
2. **有没有为躲坑而绕路的实现？** **本批正是在拆上一次的绕路** —— 没有新增绕路。
   唯一要交代的是：修完后 `answer()` 里那句 `_ensure_chat()` 从「唯一救命稻草」降级成
   「尽早失败的检查」，我**保留**了它（理由：KEY 缺失应在跑检索之前就炸，而不是跑完才炸）。
3. **验收判据是真跑还是读代码？** 全部实测：单元测试 + 变异反向验证 +
   **live 复跑 C1**（真图 + 真 LLM + 真 PG + 真 embedding 服务）确认数字未退化。

## 7. 接下来（不在本批范围内，仅登记）

- **阶段 ⑤ TBD-7 阈值校准** —— 排期里的下一站；
- ⚠️ **但有一个前置结论必须一起带上**：P6-F 实测「14 题 ⇒ 单题翻转 ±7.1 个百分点」，
  而 C1 当前值离 10% 阈值只差 0.9 ⇒ **在这个分母上校准出来的阈值站不住**。
  建议 ⑤ 之前先讨论是否把受控题集扩到 30+ 题（**另开批次，不在本批动**，
  Non-goals 第 7 条已把它列为不许顺手做的项）；
- 其余在案未决：H6 引用回溯 403、制度入图器「条款数一致」自检恒 FAIL、P7-B。
