# tests/（当前是空壳，请勿误用）

这三个目录（`unit/` / `integration/` / `e2e/`）是 PRD 既定的**分层落点**，
`specs/_template/tasks.md` 至今仍按这个分层下发任务——**所以目录保留，不是垃圾**。

但**当前它们里面没有任何测试**，写在这里的测试也不会被收集：

- pytest 配置见 `backend/pyproject.toml`：`testpaths = ["tests"]`，
  该路径是相对 `backend/` 解析的 ⇒ 实际收集的是 **`backend/tests/`**
- CI 的后端 job 也是在 `backend/` 下跑 `uv run pytest`

⇒ **现在要加测试，加到 `backend/tests/`**。把测试放进本目录的后果是：
它不会在任何一次 CI 运行里执行，却看起来"已经被提交、已经在仓库里"——
正是本项目反复出现的「提交即真相」陷阱（参见
`changes/Sprint9/integration-log.md` §10 / §11 的两批同型病）。

分层重构落地时再启用本目录，届时需同步改 `testpaths` 与 CI 的工作目录，
并**在那一次改完后立刻抓 CI 日志确认真的收集到了**——别只看流水线是绿的。
