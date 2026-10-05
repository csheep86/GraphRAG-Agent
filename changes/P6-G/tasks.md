# P6-G · 任务清单（归还 D1 技术债）

> 对应 [`proposal.md`](./proposal.md)；**Non-goals 8 条已冻结**。
> 性质：**还债**。不还它，后面每一批（含 ⑤）都要各自补一次补丁，且每次撞同一种看不懂的
> `AttributeError: 'NoneType' object has no attribute 'ainvoke'`。

- [x] **T1** 写 proposal + tasks，冻结 Non-goals 8 条
- [ ] **T2** 根因修复：`agents.py::_invoke_chat_with_retry` 开头调幂等的 `self._ensure_chat()`
      ⇒  HTTP 路径零行为变化（`_ensure_chat` 已有则直接返回）
- [ ] **T3** **删掉** P6-F 在 `baseline.py` 留下的绕路补丁（13 行注释 + 1 行 `agent._ensure_chat()`）
- [ ] **T4** 补根因级回归测试（**E5 约束**：必须从「从未装配」状态起步，不许先塞 `_chat` 再调）
- [ ] **T5** 反向验证：撤修复 ⇒ 判红；还原 ⇒ 全绿（用真实报错判红，不是我以为）
- [ ] **T6** live 复跑 C1 ⇒ 补丁删了之后仍应为 **0.0909**（守 E1：不许退化）
- [ ] **T7** 门禁（pytest / ruff / format / seams / 契约零 diff / drift）+ 集成日志 + 提交
