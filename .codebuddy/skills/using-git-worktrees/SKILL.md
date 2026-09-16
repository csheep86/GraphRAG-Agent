---
name: using-git-worktrees
description: 使用 git worktree 在独立目录中并行开发多个分支，避免频繁切换或目录污染。适用于需要并行推进多个变更、或大改期间保持主分支可用时。
---

# 技能名称：using-git-worktrees（git worktree 使用）

## 用途
用 `git worktree` 为不同分支建立相互隔离的工作目录，实现：多变更并行开发互不干扰、大重构期间保留可用环境、对比调试不同实现。

## 触发条件
- 需要同时推进两个以上互不合并的变更（如一边修 bug 一边开发新功能）。
- 某分支处于半完成状态，但需要基于 main 处理紧急问题。
- 需要并行运行两个分支的代码做对比验证。

## 执行步骤
1. **确认分支**：明确涉及的分支名与对应变更（建议分支名 `feature/<change-id>`）。
2. **创建 worktree**：`git worktree add ../GraphRAG-Agent-<branch> <branch>`；新分支用 `git worktree add -b feature/<id> ../<dir> main`。
3. **隔离工作**：在各自 worktree 目录中独立开发；注意依赖目录（如 `node_modules`、`.venv`）每个 worktree 需独立安装，不共享。
4. **遵守环境规则**：每个 worktree 内后端环境仍用 uv 创建独立 `.venv`；`.env` 不提交（每个 worktree 本地维护）。
5. **同步主线**：定期 `git merge main`（或 rebase，需用户确认）保持分支新鲜；契约变更时先同步 `contracts/` 避免后期大冲突。
6. **收尾清理**：分支合并后 `git worktree remove <dir>` 并 `git branch -d <branch>`；用 `git worktree list` 确认无残留。

## 输出格式
- **worktree 布局表**：目录 → 分支 → 对应变更 → 状态
- **操作记录**：创建 / 同步 / 清理的命令与结果
- **收尾状态**：剩余 worktree 清单与清理确认
