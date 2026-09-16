# Tasks: <变更名称>

> 使用说明：复制本模板到 `changes/<change-id>/tasks.md`。按依赖顺序拆解，每项控制在可独立验证的粒度；完成后勾选。

## 1. 契约更新
- [ ] 更新 `contracts/openapi.yaml`（endpoint / schema / 错误码）
- [ ] 评审契约：确认字段命名、分页、错误结构符合全局规范

## 2. 后端实现（backend/）
- [ ] 更新 / 新增 Pydantic 模型
- [ ] 实现接口逻辑与全局异常处理
- [ ] 如为长耗时操作：异步任务 + `task_id` + 状态轮询 + tenacity 重试
- [ ] 单元测试（`tests/unit/`）与集成测试（`tests/integration/`）

## 3. 前端实现（frontend/）
- [ ] 运行 `npm run gen:api` 生成 / 更新 TS 类型
- [ ] 更新页面与 Mock 数据（与契约一致）
- [ ] 组件测试（`frontend/src/**/__tests__/`）

## 4. 验证
- [ ] 端到端验证（`tests/e2e/`）
- [ ] 前后端联调，输出接口对齐清单核对结果
- [ ] 日志与 trace_id 贯穿验证

## 5. 收尾
- [ ] 更新 `.env.example`（如有新配置项）
- [ ] 更新 README / docs（如涉及使用方式变更）
- [ ] 通过 pre-commit（Black + Ruff / Prettier + ESLint）
