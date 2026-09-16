---
name: using-superpowers
description: 技能体系总入口：说明本项目 13 个 Superpowers 技能的定位、选择方法与典型组合。适用于不确定该用哪个技能时。
---

# 技能名称：using-superpowers（技能体系入口）

## 用途
作为技能体系的地图与调度入口：在开始任何开发工作前，先判断当前阶段，选择合适的技能或技能组合，避免盲目动手。

## 触发条件
- 不确定当前任务应该采用哪个技能。
- 用户问"有哪些技能 / 该怎么用"。
- 开始一个新功能或新变更，需要确定工作流。

## 技能地图

| 阶段 | 技能 | 说明 |
|---|---|---|
| 想清楚 | brainstorming | 需求澄清与方案探索 |
| 定计划 | writing-plans | 产出可执行 checklist |
| 干起来 | executing-plans | 逐项执行计划 |
| 写代码 | test-driven-development | 红-绿-重构循环 |
| 排问题 | systematic-debugging | 证据链定位根因 |
| 保质量 | verification-before-completion | 完成前强制验证 |
| 求审查 | requesting-code-review | 发起与处理代码审查 |
| 大任务 | subagent-driven-development | 调度者/执行者模式 |
| 并行干 | dispatching-parallel-agents | 多代理并行派发 |
| 多分支 | using-git-worktrees | git worktree 隔离开发 |
| 做收尾 | finishing-a-development-branch | 分支验证与合并清理 |
| 造技能 | writing-skills | 编写新技能 |
| 查用法 | using-superpowers（本技能） | 技能选择入口 |

## 典型组合
- **新功能**：brainstorming → writing-plans → executing-plans（内含 TDD）→ verification-before-completion → requesting-code-review → finishing-a-development-branch
- **修 bug**：systematic-debugging（含复现测试）→ verification-before-completion
- **大重构**：writing-plans → subagent-driven-development（或 dispatching-parallel-agents）→ verification-before-completion

## 执行步骤
1. 判断当前任务所处阶段（探索 / 计划 / 实现 / 调试 / 验证 / 审查 / 收尾）。
2. 对照技能地图选择技能；跨阶段则按典型组合串联。
3. 加载对应技能并遵循其执行步骤。
4. 过程中阶段变化（如实现中发现需求不清），回到 brainstorming 重新澄清。

## 输出格式
- **任务阶段判断**：一句话
- **所选技能 / 组合**及选择理由
- **下一步动作**：加载哪个技能、做什么
