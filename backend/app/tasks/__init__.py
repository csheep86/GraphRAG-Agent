"""异步任务层（Sprint 1 为空实现）。

**Sprint 3 待补（ADR-0001 §3.2）**：
1. `TaskManager.submit()`：上传受理后把解析任务投递到 `asyncio.Queue` 并由 worker 消费；
2. `TaskManager.recover()`：**应用启动时**扫描 `documents.status IN ('pending','processing')`
   的孤儿记录，置 `failed` + `error_code = TASK_INTERRUPTED`（M5 §3 验收 4 要求该码呈现）；
3. 重试策略：`tenacity` 指数退避，上限 3 次（`documents.retry_count`）。

当前选择「不注册执行体」的后果已登记在 `backend/CODEBUDDY.md` §4 缺口表：
上传后的文档会停留在 `pending`，`TASK_INTERRUPTED` 因此暂时不会被真实产生。
"""

__all__: list[str] = []
