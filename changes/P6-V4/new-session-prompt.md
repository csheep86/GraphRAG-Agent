# ⛔ 本文件已作废 —— 请看 v2

> **P6-V5 的提示词已改版，正文不在这里。**

| 项 | 内容 |
|---|---|
| **当前有效版本** | **v2 · 2026-10-12** → [`../P6-V6/new-session-prompt.md`](../P6-V6/new-session-prompt.md) |
| 本文件（v1 · 2026-10-11） | **作废**，仅保留此存根以免两处都有正文时分不清哪个新 |

**为什么作废**：v1 写于 P6-V6 之前，其中两条口径**已被 2026-10-12 的实测推翻**：

1. §2 理由 #2「`cost_metrics` 在本机 / CI **均空**」⇒ 不再成立
   （本机已有 1 行 `stage='extraction'` 的**测试残留**）；
2. §8 基线 `1249 passed / 43 skipped` ⇒ 现为本机 **1251 / 43**、CI **1287 / 7**。

**要看 v1 原文**（本文件有版本历史，未删除内容）：

```bash
git -C <repo> log --follow -- changes/P6-V4/new-session-prompt.md
git -C <repo> show <那个提交>:changes/P6-V4/new-session-prompt.md
```

---

**正文约定**：提示词一律落在 **`changes/<当前批次>/new-session-prompt.md`**
（当前批次目录下、写给下一批）。故 P6-V5 的 v2 落在 `changes/P6-V6/`，
本目录这一份**不再维护**，请勿在此修改。
