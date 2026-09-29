# Sprint 9.10 —— R19 处置：上传后的状态推进改为真实轮询

> 登记日期：2026-09-29。**临时插入的微批次**，承接 `docs/dev-doc-status.md`
> **R19**（Sprint 9.9 收尾时同红线但未处置、已登记遗留的那条）。

## 1. 为什么做

R18 清零后做同红线自查，发现上传链路仍有一处"看起来能用"的假动作：

`store/use-document-store.ts::scheduleProgress` 在**真实上传成功之后**，用两个
`setTimeout`（1.2s / 3s）把条目按时序推
`pending → processing → completed`，并写入 **`entity_count = 1024 + random(0~900)`**。

- 流转是 **time-based**，不是后端真实状态 ⇒ 后端还在处理时屏幕可能已显示「已完成」；
- `entity_count` 是**后端从未返回的编造数字** ⇒ 直接踩 plan §7.2「零假数据」+ A16「诚实可核」。

与 R18 同红线，但**不在 9.9 裁决范围内**，故单列本批次。

## 2. 改什么

| # | 处置 | 诚实性依据 |
|---|---|---|
| ① | `scheduleProgress` → `pollStatus`：改为真实轮询 `GET /api/v1/documents/{id}/status`（**契约内已实装**，在 `CONTRACT_COVERED_PATTERNS` 内） | 状态来自后端唯一真源；`pending / processing / completed / failed` 严格按 M1 硬约束 H1 的状态机 |
| ② | 只写回 `status`，**不再写任何 `entity_count`**；轮询失败 / 超 12 次即停，**停在 `pending` 不猜** | 取不到就是取不到：宁可显示未完成，也不假称完成 |
| ③ | 终态（`completed` / `failed`）后回拉一次列表 `load()`，用后端真值回填 `entity_count` | 实体数是**建图产物**，只能由后端给；未建图时 UI 按既有逻辑显示 `--`（`document-table.tsx:86-90`） |

轮询节奏：首次 2s，前 3 次间隔 2s，之后 10s，最多 12 次（约 2 分钟内收敛）。

## 3. 明确不做

- **不动契约、不碰后端**（纯前端批次；契约零漂移由门禁校验）
- 不做 WebSocket / SSE 推送（后端现状是同步上传 + 轮询状态，改推送属独立范围）
- **不新增任何数字**：本批次只**删除**编造数字来源，不补一个替代数字
- **已做**真实文件上传的端到端点验（用户 2026-09-29 裁决「上传并提交」）：代价是演示库
  文档数 **13 → 14**（后端无 DELETE 文档接口，不可逆），实测图谱 `entity_count` 未变
  ——见 `integration-log.md` §3
