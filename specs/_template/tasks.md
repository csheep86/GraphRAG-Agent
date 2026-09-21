# Tasks: <变更名称>

> 使用说明：复制本模板到 `changes/Sprint<N>.<M>/tasks.md`（**每个批次必填**，是"排计划"的直接依据）。按依赖顺序拆解，每项控制在可独立验证的粒度；完成后勾选；**收尾时须与同目录 `integration-log.md` 的实测结论对账**（勾选 ≠ 通过，须有实测证据）。落点决议见 `docs/v2.0.0-ship-backward-plan.md` §6。
>
> **与 plan 的分工**：`docs/v1.1.0-demo-mvp-plan.md` §16~§20 是 **Sprint 级**范围与验收清单（"这 3 周做什么"）；本文件是 **批次级**任务拆解与勾选（"今天勾哪一项"）。两者不互相复制。

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
