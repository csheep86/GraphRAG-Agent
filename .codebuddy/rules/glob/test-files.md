# 测试文件规则（glob）

<!-- 触发条件（glob 匹配）：
  **/tests/**
  **/test_*.py
  **/*_test.py
  **/*.test.ts
  **/*.test.tsx
  **/*.spec.ts
  **/*.spec.tsx
-->

仅当创建或修改匹配上述模式的测试文件时，本规则生效。

## 测试组织
- 单元测试 → `tests/unit/`；集成测试 → `tests/integration/`；端到端测试 → `tests/e2e/`。
- 后端测试文件命名 `test_<module>.py`，与被测模块同名（如 `app/tasks/` 对应 `tests/unit/test_tasks.py`）。
- 前端测试文件与被测文件同目录，命名 `<component>.test.tsx` / `<module>.test.ts`。

## 编写约定
- 后端使用 pytest，断言风格统一 `assert` + 明确错误信息；需要时用 fixture 管理临时文件与 Mock。
- 前端使用 Vitest / Jest + Testing Library，优先测行为而非实现细节。
- 涉及 API 的测试必须基于 `contracts/openapi.yaml` 的 Mock 数据，禁止臆造与契约不符的字段。
- 涉及异步任务的测试必须覆盖状态流转（`pending → processing → completed → failed`）与失败重试路径。

## 质量要求
- 每个测试一个明确目的，测试名描述行为（如 `test_upload_returns_task_id`）。
- 不测第三方库内部行为；对外部服务用 Mock / 录制的实测结果（以本地实测输出为准）。
- 新增 `.env` 相关测试配置时，同步更新 `.env.example`，禁止提交真实密钥。
