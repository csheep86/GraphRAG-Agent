# Proposal: <变更名称>

> 使用说明：复制本模板到 `changes/Sprint<N>.<M>/proposal.md`（与 `design.md` / `tasks.md` / 联调证据 `integration-log.md` **同目录**）；填写后随批次一起维护；批次收尾后**整目录**移入 `changes/archive/<日期>-Sprint<N>.<M>/`。
> **定位**：本模板产出**事前计划**；同目录的 `integration-log.md` 记录**事后实测证据**（前置核实 / 跑数 / 关键发现 / gap / 未触碰项 / 收尾确认）。两者互补，**不可互相替代**。落点决议见 `docs/v2.0.0-ship-backward-plan.md` §6。

## Why

<为什么要做这个变更？解决什么问题或抓住什么机会？引用 specs/ 或 openspec/ 中相关规格。>

## What Changes

- <变更点 1>
- <变更点 2>
- <变更点 3>

## Impact

**影响的契约（contracts/openapi.yaml）**

- <无 / 列出变更的 endpoint 与字段>

**影响的前端（frontend/）**

- <无 / 需同步的 TS 类型、页面、Mock>

**影响的后端（backend/）**

- <无 / 需同步的 Pydantic 模型、接口逻辑、异步任务>

**影响的 Prompt（prompts/）**

- <无 / 新增版本号，如 kg_qa_v2.md>

## Non-goals

- <明确不在本次范围内的内容，防止范围蔓延>
