# 新会话启动提示词（Sprint 7.0）

> 开新对话时，**整段复制**下面代码块里的内容作为第一条消息即可。
> 本文件本身也可以直接让新会话读：「先读 `changes/Sprint7.0/new-session-prompt.md` 并按里面的指示开工」。

---

## 复制到新会话的提示词（推荐版）

```text
这是一个已执行到 Sprint 6（v1.2.0 已收尾）的项目。本次只做 Sprint 7 的**前置还债批次 Sprint 7.0**，不做别的。

【必读（按顺序，读完再动手）】
1. 根 CODEBUDDY.md、backend/CODEBUDDY.md —— 项目纪律与已登记缺口（重点看 §4 的 S6-4/S6-5/S6-6）
2. changes/Sprint7.0/proposal.md —— 本批次的目标、三条事实证据、三条替代路径为何不可行、副作用
3. changes/Sprint7.0/tasks.md —— 批次级勾选项，这就是你的执行清单（**含 §4 预算护栏，务必照做**）
4. changes/Sprint7.0/demo-docs-checklist.md §8 —— 演示素材已完成预检的结论与原始证据，**别自己重做一遍**
5. （了解背景）docs/release-notes/v1.2.0.md 与 v1.1.0.md 的 §6 已知限制

【目标】
把抽取链路从「正则占位器」换成「真实调用 LLM」：
- LangextractClient.from_settings()（langextract.py 267-276 行）当前不传 LLM client，走 _default_extract_chunk（191-196 行正则，只出 ORG/PERSON/MONEY/DATE）；_evaluate_client_call_llm 全仓无实现。
- 必须走已有的 app/services/providers/llm.py 的 build_chat_model()，不要新建第二套 LLM 客户端（接缝 3）。
- 新增显式开关（建议 settings.extraction_engine，档位 llm/mock），未知档位显式报错、**绝不静默回退**（这是 plan §4.4 纪律）。
- CI/单测靠注入 mock 保持零外部依赖；失败/超时/非法 JSON 抛 LangextractError，由外层 tenacity 重试；**严禁失败后静默回落 mock**（那会把基础设施故障伪装成业务结论）。
- Prompt 用现有 prompts/kg_extraction_v1.md，**不要改 Prompt 模板内容**（扩类型属 Sprint 7.1 批次 A 的事）。

【预算约束（真实扣费，违反即失职）】
DeepSeek 账户余额 **¥8.37**。这笔钱**够跑完本批次的验证，但不够全量重建演示图谱**：
- ✅ **允许**：§4 真机验证只跑**定向切片**——取年报「第二节 公司简介和主要财务指标」或前 5–10 页，10–20 个 chunk，单次成本 **¥0.1 以内**；
- ❌ **禁止**：全量重抽整份年报（一份 250 页约 ¥1.5–3，跑 3 份加迭代需 ¥10–25）。尤其**不要碰招商银行那份**（30MB / 数百页）；全量重抽属于 Sprint 7.1 批次 A，届时我会先充值；
- ❌ **禁止**：为了「再确认一遍」而把已经有人类证据的结论重跑——见下条 D6②；
- 每次真机调用都在 integration-log 里记下 chunk 数与 token 量级；**预计单次超过 ¥1 就停下来问我**。

【纪律（违反即返工）】
- 勾选 ≠ 通过：每一项都要真的跑命令，把输出摘要写进 changes/Sprint7.0/integration-log.md（该文件由你新建，格式参照 changes/Sprint6.1/integration-log.md）。
- 不许为了凑结果改阈值 / 伪造数据 / 静默降级。
- 不许 push 仓库（我这边的网络到 github.com 经常超时，推送由我来，你只需 commit 与否听我安排）。
- 不许 bump app_version（那是 Sprint 7 四个批次全完成后与 tag v1.3.0 同一动作）。
- 不许动 Sprint 7.1 批次 A 的代码（图节点 / 算法 / risk.detect 一律不做）。
- 环境：后端用 uv（uv run pytest -q / uv run ruff check .）；本机那个 Neo4j 容器经常 Exited，跑真机前先 docker ps，不在就 docker start neo4j 并等约 25 秒。

【执行顺序】
先做 tasks.md 的 §0 事前核实（复现三条事实：from_settings 不传 LLM client、_RE_ORG 能命中“本报告汇总了集团”这类坏样例、_evaluate_client_call_llm 无实现），再动手写代码，最后做 §4 真机验证。

【真机验证必须给出两条结论（D6）】
**素材已就位**：本机 `docs/annualreport/` 已有 4 家招商局系公司 2025 年报（公路 / 蛇口 / 轮船 / 银行，共约 47MB，已被 .gitignore 忽略）。**先读 `changes/Sprint7.0/demo-docs-checklist.md` §8**，那里有 2026-09-23 已完成的预检结论与原始提取证据：
- D6①「能否抽出可用的法人 / 地址」→ 已预检为**能**（三份各有明确的法定代表人 + 注册地址 + 办公地址）；
- D6②「文档间是否存在真实交叉」→ 已预检为**零交叉**（法人三人各异、地址三地各异），原因是年报天然只披露一家公司的信息。

你开工后的动作：**D6①** 用现有年报的**定向切片**跑通链路给出答案；**D6② 直接引用 checklist §8 的人类提取证据**（法人三人各异、地址三地各异）得出「零交叉」，**不需要也不许花钱重跑来确认**。
得出零交叉后，把「建议改用**关联交易公告 / 募集说明书**（能同时披露多个关联主体的名称 + 法人 + 住所）」写进 integration-log 作为建议，**就此停手**——不要去找新素材验证，那部分我来。
**注意一个误报陷阱**：三家年报都含「北京市东城区东长安街 1 号东方广场东 2 座办公楼 8 层」——那是**会计师事务所 / 财务顾问**的地址，**不是公司自身地址**；若抽取出「共享地址」疑点，务必先判断是否打到了这个伪交叉上。
不得代我下载新素材（本机到巨潮 / 上交所可达，但巨潮公开列表 API 已收紧，需人工介入）；需要新文档时**停下来问我**。
这两条结论是 Sprint 7.1 的开工依据，含糊=失职。

【开始方式】
先复述你理解的本次范围与禁止项（两三句即可），然后从 tasks.md §0 第一条开始按序执行，每完成一小节向我汇报结果，不要一次性跑完所有项再汇报。
```

---

## 备用：精简版（适合上下文紧张时）

```text
读 changes/Sprint7.0/proposal.md 与 tasks.md（以及根 CODEBUDDY.md / backend/CODEBUDDY.md 的纪律部分），按 tasks.md 从 §0 事前核实开始执行 Sprint 7.0：把抽取链路从正则占位器换成真实 LLM 调用（走 app/services/providers/llm.py 的 build_chat_model()），新增 llm/mock 显式开关且禁止静默回退，最后用 2-3 份关联公司年报做 mock vs llm 对照，给出 D6 两条结论（能否抽出可用的法人/地址、文档间是否存在真实交叉）。禁止：push、bump 版本、动 Sprint 7.1 的图/算法代码、改 Prompt 模板。每项都要有真机证据，写进 changes/Sprint7.0/integration-log.md。每完成一节向我汇报。
```

---

## 新会话常见的三个坑（提前说，免得重踩）

1. **别信任何二手结论**：每条关键判断都要落到具体文件行号；本机性能/行为以你自己跑出来的为准。
2. **Neo4j 假死**：容器常 `Exited (255)`，`docker ps` 无脑看一眼，异常就 `docker start neo4j` 再等 ~25s，否则会误判成"图写不进去"。
3. **别手改 counts/finish**：integration-log 里的数字必须是命令输出，不接受"推测应该没问题"。
4. **别烧钱**：这是真实余额（¥8.37）的真实扣费。跑之前先想清楚这次调用要多少个 chunk，**宁可用小样本证明链路通了，也不要一次把整份年报灌进去**。
