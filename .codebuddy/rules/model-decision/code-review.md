# 代码审查规则（model-decision）

本规则由模型根据任务上下文自主判断是否启用：在审查代码、评估变更质量、或用户要求 review 时适用。

## 何时启用
- 用户明确要求 code review / 审查 / 检查代码。
- 完成一个功能分支或较大变更，准备提交前。
- 同步修改了 `contracts/`、`frontend/`、`backend/` 中任意两者以上。

## 审查清单
1. **契约一致性**：接口字段是否与 `contracts/openapi.yaml` 一致；前端 TS 类型是否由 `npm run gen:api` 生成而非手写偏离。
2. **输入校验**：所有外部输入是否有 Pydantic 严格校验（类型、长度、格式、白名单）。
3. **错误处理**：异常是否由全局处理器统一拦截，返回结构是否为 `{code, message, detail, trace_id}`；HTTP 状态码与业务错误码是否分离。
4. **异步任务**：长耗时操作是否异步化并返回 `task_id`；失败是否支持 tenacity 指数退避重试；状态流转是否为 `pending → processing → completed → failed`。
5. **限流与安全**：对外 API 是否配置 slowapi 限流；日志是否泄露密钥 / Token / 密码。
6. **Prompt 硬编码**：是否出现内联 Prompt 字符串（应通过 `prompt_loader.py` 从 `prompts/` 加载）。
7. **测试覆盖**：新增逻辑是否有对应测试；测试是否放在 `tests/unit|integration|e2e/` 合理层级。

## 输出格式
审查结论按以下结构输出：
- **结论**：通过 / 需修改 / 阻塞
- **问题清单**：按严重程度排序（阻塞 → 建议），每条注明文件与行号
- **接口对齐清单**（涉及前后端联动时）：列出契约字段、前端实现、后端实现三方状态
