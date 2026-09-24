# 新会话启动提示词（Sprint 8 批次 A = Sprint 8.1，审计最小闭环）

> 开新对话时，**整段复制**下面代码块里的内容作为第一条消息即可。
> 本文件本身也可以直接让新会话读：「先读 `changes/Sprint8.1/new-session-prompt.md` 并按里面的指示开工」。

---

## 复制到新会话的提示词（推荐版）

```text
这是一个已执行到 Sprint 7（tag v1.3.0 已收尾、app_version = 1.3.0）的项目。本次只做 **Sprint 8 批次 A（Sprint 8.1）：审计最小闭环**，不做别的。

【必读（按顺序，读完再动手）】
1. 根 CODEBUDDY.md、backend/CODEBUDDY.md —— 项目纪律（重点：「功能预留原则」、「契约同步铁律」、「错误响应规范」）
2. changes/Sprint8.1/proposal.md —— 本批次范围、现状实测表、**盘点结论**节、决策 A1–A16、M5 §3 边界表、风险 7 条
3. changes/Sprint8.1/tasks.md —— 你的执行清单，从 §0 事前核实开始按序做（含 §9 门禁与 §10 收尾）
4. docs/v1.1.0-demo-mvp-plan.md §7（Sprint 8 批次划分 + 验收清单）与 §3.1（六步演示剧本）
5. docs/GraphRAG-Agent + Harness + SDD 多模态知识库全栈开发指南.md 阶段十七（5105–5182 行）
6. specs/m5-permission-audit.md §3 验收标准（8 条）+ §4.4 audit_log 字段表（97–109 行，权威）
7. specs/m3-graphqa-citation.md §4.3 qa_logs 字段表（82–95 行）
8. docs/dev-doc-status.md §9（开工 / 收尾必做）

【已完成的盘点：不要重做，直接引用】
2026-09-24 已按长指南 §17.1 完成九项现状盘点（只读、未改码），结论全部落在 proposal.md 的「现状」表与「盘点结论」节，**带行号**。
例如：models.py 只有 7 张表（无 audit_log / qa_logs）；trace_id 由 core/middleware.py:17-19 生成，但任务侧有第二个生成器 tasks/manager.py:233-241；问答 agents.py:194 全函数零 DB 写入；只读接口照 routes/documents.py:76-126；org_id 唯一来源是 CurrentIdentity（deps.py:45-80）。
**但**：§0 事前核实的每一项你仍要自己跑一遍命令确认（「别信二手结论」），数字必须是命令输出，不许推测。

【目标】
建 qa_logs + audit_log 两张表；加 GET /api/v1/audit（按租户列表）与 GET /api/v1/audit/trace/{trace_id} 两个只读端点；前端 audit 页关 Mock。
判据：演示路径（上传→解析→建图→提问→检测→复核）走一遍，审计页可见 **≥7 条**记录。

【决策 A1–A16 已按建议采纳，不要重新裁决】
- A1 审计写入 = 中间件全量写 + 路由 allowlist（排除 health）；A2 action 走路由元数据映射，未登记回落 http.<method>.<path> 并留日志
- A4 qa_logs 在 agents.py 产出响应后落一条（成功/拒答都落）；A5 detail 只写结构化字段、**绝不写响应体原文**（脱敏器属 S11）
- A6 actor_id 取 X-Actor-Id、actor_ip 取 request.client.host
- A9 主键用 UUID（不用 spec 的 BIGSERIAL，差异登记 ADR-0003）；A10 **不复用 EventBus**，直接同 session 写入（照 events/db.py:14-17 的「不自行 commit」范式）
- A13 真机**复用现有图谱、不重建**；A16 settings 页加「演示环境」标注（批次 D）
- 批次 B 的两条（A11 slowapi / A12 fail-open 保留逃生阀 + 审计留痕）**本批次不实现**，只在需要时保证不冲突

【纪律（违反即返工）】
- 勾选 ≠ 通过：每一项都要真跑命令，把输出摘要写进 changes/Sprint8.1/integration-log.md（该文件由你新建，格式参照 changes/archive/2026-09-24-Sprint7.1/integration-log.md）。
- **契约先行**：先改 contracts/openapi.yaml → 后端实现 → npm run gen:api → 前端。
- 新增端点**必须同步 CONTRACT_COVERED_PATTERNS**（src/api/client.ts），否则新端点走 mock，直接违反「关 Mock」硬门槛（S6.4 §2.1 撞过的坑）。
- **不改既有 7 张表的一行**；**不改 patch_suspicion_status() 签名**（复核的审计由中间件覆盖，改签名是范围蔓延）；只有 agents.py 需要引入 session。
- 审计写失败**只记日志、不抛异常**（审计缺陷不得变成全站 500）。
- 不许 bump app_version（Sprint 8 收尾统一 bump 1.4.0 + tag）；不许动接缝（保持 ERROR 0 / WARN 2，接缝 6 属批次 E）。
- 不许 push（推送由用户执行）；不许为了凑结果改阈值 / 伪造数据 / 静默降级。
- 环境：后端用 uv（uv run pytest -q / uv run ruff check .）；本机 Neo4j 容器常 Exited，跑真机前先 docker ps，不在就 docker start neo4j 并等约 25 秒。

【开工前必须先做的两件（阻塞项，别硬扛）】
1. **试装 slowapi**（批次 B 前置）：pyproject.toml 与 uv.lock 现均无 slowapi / limits。装不上就**停下来告诉我**，不要自造中间件。
2. **向我确认 DeepSeek 余额**：真机走查里「提问」要调 LLM。策略已定为复用现有图谱、不重建，但**余额数字不许推测**；单次预计超过 ¥1 就停下来问我。

【执行顺序】
tasks.md §0 事前核实（含跑一次 check_seams.py 记基线）→ §1 契约 → §2 两张表 → §3 审计中间件 → §4 qa_logs 写入 → §5 两个端点 → §6 前端 → §7 测试 → §8 真机 → §9 门禁 → §10 收尾。
每完成一小节向我汇报，不要一次性跑完所有项再汇报。

【开始方式】
先复述你理解的本次范围与禁止项（两三句即可），然后从 tasks.md §0 第一条开始按序执行。
```

---

## 备用：精简版（上下文紧张时）

```text
读根 CODEBUDDY.md / backend/CODEBUDDY.md 的纪律部分 + changes/Sprint8.1/proposal.md 与 tasks.md，按 tasks.md 从 §0 开始做 Sprint 8 批次 A（审计最小闭环）：建 qa_logs + audit_log 两表（UUID 主键、org_id 打头索引、不写迁移脚本），加 GET /api/v1/audit 与 GET /api/v1/audit/trace/{trace_id} 两个只读端点（契约先行 + 同步 CONTRACT_COVERED_PATTERNS），前端 audit 页关 Mock。审计由中间件全量写（排除 health、action 走路由映射、失败只记日志不抛异常），qa_logs 在 agents.py 产出响应后落一条（成功/拒答都落、不记原文）。决策 A1–A16 已采纳，不要重裁。禁止：push、bump app_version、改既有 7 张表、改 patch_suspicion_status 签名、动接缝、写响应体原文进 detail。开工前两件阻塞项：试装 slowapi、向我确认 DeepSeek 余额。每项都要有真机/命令证据，写进 changes/Sprint8.1/integration-log.md。每完成一节向我汇报。
```

---

## 新会话常见的坑（提前说，免得重踩）

1. **别信二手结论**：proposal 里的盘点结论带行号，但**每条都要自己跑命令复核**；数字必须是命令输出。
2. **「≥7 条」的口径**：实测链路里有多个 trace_id（HTTP 一个，后端任务由 tasks/manager.py:233-241 另生成一个），所以**不是**「同一个 trace_id 下 7 条」。按「审计页可见全程 ≥7 条、每条带 trace_id、可按 trace_id 过滤回看」执行，并在 integration-log 里**显式登记这个解读**。
3. **中间件顺序**：审计中间件必须挂在 TraceIdMiddleware 之后才拿得到 trace_id；main.py:58-59 注明「后加者在外层」。
4. **Neo4j 假死**：容器常 Exited，`docker ps` 看一眼，异常就 `docker start neo4j` 再等 ~25s，否则会误判成「图写不进去」。
5. **别手改 counts/finish**：integration-log 里的数字必须是命令输出。
6. **批次 B 的预警**（本批次不做，但别埋雷）：429 必须在 errors.py:122-132 的 HTTP_STATUS_TO_ERROR_CODE 加 `429: RATE_LIMITED`，否则兜底成 HTTP_ERROR（映射 500），直接违反矩阵 :133 判据。
7. **别烧钱**：真机走查复用现有图谱，不许全量重抽语料。
```

（本文件由 2026-09-24 的开工盘点会话产出；盘点结论本体在 `proposal.md`，不要在本文件里复制第二份，避免"第二真源"。）
