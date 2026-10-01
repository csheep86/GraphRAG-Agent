# CODEBUDDY.md - GraphRAG-Agent 项目规则

## 开工自检（**每次动手写代码前先看本节**）

本仓库的交付护栏（**G 编号**）**一大半是 `xfail` 骨架**——意思是：

> **pytest 全绿 ≠ 护栏在拦**

所以不要凭文档里的 ✅ / 🟡 下结论（文档会过期）。开工前先跑这一条，拿**机器结论**：

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

它按护栏的**真实状态**分成三档，照最后一列行事：

| 档 | 含义 | 该怎么做 |
|---|---|---|
| `[OK]` 已生效 | 测试红就是它拦的 | 正常开发；改坏了它**真的**会拦你 |
| `[~~]` 部分生效 | 一半在拦、一半挂着 | **挂着的那一半所管的需求，不得宣称完成** |
| `[--]` 挂起 | CI 绿，但没在拦任何东西 | 对应 DR **一律不得宣称完成** |

**三条硬规则**：

1. **结论只能来自脚本输出**，不能来自记忆或文档表格——脚本读的是测试源码。
2. **`[--]` / `[~~]` 转正的唯一方式**：让对应测试**真的通过**，再删掉它的 `@pytest.mark.xfail`。
   **只是往测试里补断言、却留着 xfail —— 不算转正。**
3. 标了「**恒绿失效**」的（如 `plugins/`、`deploy/variants/`、License 子系统尚不存在）：
   先让**校验对象真的存在**，转正才有意义（纪律 **R-9「恒绿即失效」**）。

脚本还顺带输出两块内容：

- **开工地雷**——是否已切 PG、`.env.example` 是否还是 SQLite、`users` 表是否建、
  License 是否零代码等（这些一旦判断错，整段工作会白做）。
- **反向守卫**——例如 `test_g21_production_sqlite_guard_still_present`，
  **必须始终通过**；清理 SQLite 时很容易把它当成"残留"一并删掉，那等于拆护栏。

> 需求 / 护栏 / 纪律的完整定义：
> [`docs/delivery-requirements-and-guardrails.md`](./docs/delivery-requirements-and-guardrails.md)
> ｜ 阶段排期：[`docs/delivery-plan.md`](./docs/delivery-plan.md)

## 过程中回切点（**写着写着跑偏时，靠这个回来**）

「开工自检」只管**动手前**，CI 只管**提交后**——**中间那一段是空的**，
而范围蔓延恰恰全发生在那段。历史病例几乎都落在这一段：

- `changes/Sprint9/c0-recon.md:72` ——「要让它产生 diff 就得新增端点（**范围蔓延**）」
- `changes/archive/2026-09-24-Sprint8.1/proposal.md:27 / :73 / :103` —— 三处主动踩刹车：
  「不改签名…那是动既有行为」「重造要花钱，且属范围蔓延」「先停下来升级，那不是顺手」
- `tests/README.md:12` ——「提交即真相」陷阱；`integration-log.md` §10 / §11 **两批同型病**

这些的共同点**不是不知道边界**——`Non-goals` 早就写在 proposal 模板里了，
而是**写完以后没人回去对照**。所以这个回切点做的是同一个动作，只是自动化：

```bash
cd backend && uv run python scripts/check_session_drift.py
```

**什么时候跑**（别攒到最后）：

| 时机 | 为什么 |
|---|---|
| **每个子任务收尾**，在说"做完了"之前 | 此刻发现最便宜；出口之后就要靠人回忆了 |
| 改完一个模块、正准备改下一个时 | 中途回切，避免最后一次性对不上账 |
| **CI 红了** | 先看是不是批次摊太大，**而不是先改测试让它绿** |

五条判据，**全部只看本次 `git diff`**（不做全仓库扫描 ⇒ 不会一上来红一片变成没人看的噪音）：

| 判据 | 防的是什么 |
|---|---|
| **S1** 读出当前批次的 Non-goals 并逐条列出 | **无边界开发** |
| **S2** 改动量超阈值（文件数 / 新增行） | 一次性摊太大 |
| **S3** `config.py` 新增字段 ⇒ `.env.example` 是否同步 | 加了开关没留模板 |
| **S4** 改了 `schemas/` `routes/` `contracts/` ⇒ 提醒该跑哪些命令 | 契约漂移 |
| **S5** 新增模块在仓库内无人引用 | **过度开发**（提前写了没人要的） |

**两条硬规矩**：

1. **S1 报「没有 Non-goals」⇒ 先停下来补边界**，不许边写边定边界——那等于没有边界。
2. **S5 命中不代表该删**，但**必须回答它属于本批次的哪一条需求**；答不上来，就是顺手做的。

脚本拦不住、**必须自己答**的三句：

1. 这批改动里，有没有一样东西是**顺便做的**？它属于哪条 DR / G？
2. 有没有为了**躲一个坑**而绕路的实现？（绕出来的简化，日后都会回来收费）
3. 验收判据是**真跑出来的**，还是读代码得出的？

> 想只看单个提交而非全部未提交改动：`--since HEAD~3`；阈值可调：`--max-files` / `--max-lines`。
> **退出码恒 0**——它是**报告**不是门禁，`CI` 才是门禁（纪律 **R-10**）。

## 仓库根 MVP / POC 目录 —— **不可删除清单**

根目录这几个目录**看起来像废弃原型，实际是「实测结果反哺规则」的唯一证据**。
要清东西前先看本节——删掉任何一个，都会让对应的 spec / ADR 变成无源之水：

| 目录 | 它支撑的东西 | 删了会怎样 |
|---|---|---|
| `temporal_poc/` | **ADR-0005（Accepted）§3 的双轨 PoC 实测依据**；§7.4 再审条件写明要重跑 `repeat_g.py` | ADR 断证据链；**再审条件无法执行** |
| `mineru_mvp/` | `docs/mineru_cloud_api_spec.md`（状态**生效**）的实测依据 + 落地实现 | 「生效」的 spec 无法复验 |
| `langextract_mvp/` | `docs/langextract_spec.md` 的落地实现 | 同上 |
| `bridge_web_demo/` | `docs/bridge-pipeline-specification-v1.0.md`（状态**生效**）的落地目录 | 同上 |
| `langchain_mvp/` | Agent 工具层（Sprint 2.7）产物 | 选型依据丢失 |

同样**不可删**（看着像冗余，实为有意保留）：

- **`tests/`（根目录）** —— 看着是空壳（`unit/` `integration/` `e2e/` 全空），
  实为 PRD 既定的分层落点，`specs/_template/tasks.md` 仍按这个分层下发任务。
  **为什么里面的测试不会被收集、启用时要改什么，都写在 `tests/README.md` 里——先看它再动。**
- **`openspec/`** —— 决议 **O-1**：目录**保留、工具链未启用**，12 个技能/命令已加停用围栏。
  删掉会让围栏失去指向（见 `dev-doc-status.md` F15）。

> **判据**：第三方组件的对接规范以**本地实跑结果**为唯一标准（见「实测结果反哺规则」）。
> 这些 MVP 就是那个"本地实跑结果"。**真要清理，必须先迁健壮但证据 再删目录**，
> 且要在 `dev-doc-status.md` 登记，不能只删。

## 角色隔离
- 处理 frontend/ 时，你是前端开发（A），只允许修改 frontend/。
- 处理 backend/ 时，你是后端开发（B），只允许修改 backend/。
- 处理 specs/ 和 contracts/ 时，你是架构师。

## 契约同步铁律
1. 修改任何接口字段，必须先更新 contracts/openapi.yaml。
2. 更新完契约，必须检查并更新 frontend/ 的 TS 类型和 Mock 数据。
3. 更新完契约，必须更新 backend/ 的 Pydantic 模型和接口逻辑。
4. 前端必须运行 npm run gen:api，确保 TS 类型与契约一致。

## 功能预留原则（极其重要！）
1. 暂时无法匹配的功能先预留空位，不要强行同步开发。
2. 严禁 AI 在前后端不匹配时，自动去补全另一端的逻辑。
3. 一旦发现不匹配，立刻停止，报告给我，并输出一份"接口对齐清单"。

4. **预留字段一律 nullable 且不进 API 契约**：为未来企业系统集成预留的数据库字段（如 `source_type` / `acl_scope` / `content_hash` / `external_refs` 等），只落库、**不进 `contracts/openapi.yaml`**；只有真正启用某个集成时才把对应字段提升到契约。判定口径：`uv run python scripts/export_openapi.py --check` 无 diff。
5. **预留必须有登记**：任何新增的预留字段/表必须同步登记到 `docs/adr/0004-integration-seams.md`（接缝清单 + 字段用途 + 启用条件），禁止无登记的"顺手预留"。
6. **接口实现集合 = ADR-0004 §2.1 登记集合（不多不少）**：抽象允许有 N 个接口，但每个接口的实现类必须恰好等于登记的集合——通常 1 个（如 `LocalAuthProvider`），**唯一例外是接缝 5 事件出口的 `db` + `log` 两个本地实现**；出现登记外实现（如 `LdapAuthProvider`）即越界，少一个即少做。新增任何 `settings.*` 配置项必须能指出读取它的代码行，**无消费者的配置不得提交**（历史病例：`task_retry_multiplier` 声明存在、**任务退避路径从未读取**；注意此类"读它的地方不全"本判据拦不到）。两者均由 `uv run python scripts/check_seams.py` 机械校验；**登记集合与 `docs/adr/0004-integration-seams.md` §2.1 登记行的一致性也由该脚本核对**——新增实现时先扩写 ADR 登记行、再改门禁，漏改任一侧 CI 必红（见 ADR-0004 §3 第 4 条）。

## 实测结果反哺规则
1. 所有第三方组件的对接规范，必须以本地实际跑通的结果为唯一标准。
2. 若官方文档与本地实际输出冲突，以本地实际输出为准。

## 环境与依赖规则
1. 每个子项目只允许使用 uv 创建 .venv，禁止混用 conda、poetry、pipenv。
2. 必须提交 uv.lock 到 Git。
3. 必须提供 .env.example 作为模板，.env 及变体必须加入 .gitignore。
4. 通过 APP_ENV 环境变量切换环境配置，默认 development。
5. 前端使用 NEXT_PUBLIC_ 前缀暴露变量，禁止硬编码 Base URL。

## 密钥管理规则
1. 生产环境密钥通过 GitHub Secrets 或云厂商 KMS 注入。
2. 开发环境使用 .env.development，不得包含生产密钥。
3. 任何密钥泄露，必须立即在对应平台轮换。

## 日志与可观测性规则
1. 后端统一使用 loguru，输出 JSON 格式日志。
2. 每个请求携带 trace_id，贯穿整个调用链。
3. 关键路径打点记录耗时和 token 用量。

## 错误响应规范
1. 所有异常统一由全局异常处理器拦截，返回 JSON：{code, message, detail, trace_id}。
2. HTTP 状态码与业务错误码分离。

## 异步任务规范
1. 长耗时任务必须异步处理，上传接口立即返回 task_id。
2. 前端通过轮询 /documents/{id}/status 获取进度。
3. 任务状态流转：pending → processing → completed → failed。
4. 任务失败必须支持重试，使用 tenacity 实现指数退避。

## 存储规范
1. 文件存储使用抽象层，开发用本地文件系统，生产可切 S3。
2. 上传文件大小限制 100MB，MIME 类型白名单校验。

## Prompt 版本管理规范
1. 所有 LLM Prompt 存放在根目录 prompts/ 下，带版本号（如 kg_qa_v1.md）。
2. Prompt 修改必须新增版本，不允许原地覆盖历史版本。
3. Python 代码通过 prompt_loader.py 从文件系统加载 Prompt，禁止硬编码。

## 安全底线
1. 所有外部输入必须经 Pydantic 严格校验。
2. 所有对外 API 必须配置限流（slowapi）。
3. 日志中禁止输出密钥、Token、密码等敏感信息。

## 代码质量规范
1. 后端格式化与静态检查**只用 Ruff**（`uv run ruff check .` + `uv run ruff format .`）——**本项目未使用 Black**（依赖里没有），照旧规矩装 Black 会与 `ruff format --check` **互相改写**，两边都过不了（需求基线护栏 **G-1**）；前端 ESLint + TypeScript（**G-5**）。
2. 提交前必须通过本地检查（后端 ruff check/format、前端 lint/typecheck）；推送后以 CI 全量门禁（ruff / pytest / eslint / tsc / 契约零漂移 / **接缝纪律门禁**）为最终裁决。pre-commit hook 暂未启用，需求与排期见 [`delivery-plan.md`](./delivery-plan.md)。

## Git 提交规范
使用 Conventional Commits：feat / fix / docs / chore / refactor / test
