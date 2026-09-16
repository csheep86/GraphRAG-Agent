---
name: finishing-a-development-branch
description: 开发分支收尾：最终验证、审查、合并与清理。适用于分支上全部任务完成、准备合并回主线时。
---

# 技能名称：finishing-a-development-branch（分支收尾）

## 用途
让分支有始有终：合并前完成最后一道验证与审查，合并时保持历史清晰，合并后彻底清理，不留僵尸分支与残留环境。

## 触发条件
- 分支上全部计划任务勾选完成且通过 verification-before-completion。
- 用户要求"收尾 / 合并 / 清理分支"。
- 变更归档条件满足（OpenSpec 变更已 sync/archive）。

## 执行步骤
1. **最终验证**：完整跑一遍该分支的测试（`tests/unit|integration|e2e` + 前端构建 / lint），确认全绿。
2. **最终审查**：完成 requesting-code-review 流程，确认无未关闭的阻塞项。
3. **自查清单**：
   - 契约、前端类型、后端模型三方一致（接口对齐清单核对）
   - 调试代码与临时文件已清理
   - `.env.example` 与文档已更新
   - `uv.lock` 已提交（如后端依赖有变）
4. **整理提交**：按 Conventional Commits 规整提交信息；不使用破坏性命令（force push、跳过 hook）除非用户明确要求。
5. **合并**：将分支合并回主线（合并方式遵循用户或仓库既有约定）；推送前确认用户意图。
6. **清理**：删除功能分支；如有 worktree 一并 remove（配合 using-git-worktrees）。
7. **归档**：对应 OpenSpec 变更执行归档（archive），变更文档移入 `changes/archive/`。

## 输出格式
- **收尾清单**：验证结果 / 审查结论 / 自查项 → 状态
- **合并记录**：分支 → 目标分支 → 合并方式 → 提交号
- **清理确认**：已删除分支 / worktree 清单
- **归档说明**：变更文档去向
