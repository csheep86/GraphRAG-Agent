# Sprint 9.10 · R19 处置任务卡（上传状态真实轮询）

> 承接 `docs/dev-doc-status.md` **R19**（Sprint 9.9 遗留的同红线项）。
> 证据链见 `integration-log.md`。

## 1. P1 删除假推进（① ②）

- [x] `store/use-document-store.ts`：删除 `scheduleProgress` 的两个 `setTimeout`
      与 `entity_count = 1024 + random` 编造数
- [x] 新增 `pollStatus`：真实轮询 `GET /api/v1/documents/{id}/status`（契约内），
      只写回 `status`
- [x] 取不到 / 超 12 次 ⇒ **停在 `pending`**，不猜状态、不许数

## 2. P2 终态回填真值（③）

- [x] `completed` / `failed` 后回拉列表 `load()`，由后端真值回填 `entity_count`
- [x] 未建图时 UI 显示 `--`（沿用 `document-table.tsx` 既有 null 分支，未新增显示逻辑）

## 3. P3 收尾门禁

- [x] `npx tsc --noEmit` 退出码 0
- [x] `npm run lint` 0 error / 0 warning
- [x] `npm run gen:api` 后 `contracts/` 与 `src/types/api.d.ts` **零漂移**
- [x] 契约层证据：`GET /documents/{id}/status` 真机返回
      `{"status":"completed","progress":1.0,"error":null}` —— **响应体内没有 `entity_count`**，
      反证旧实现的数字纯属编造
- [x] 端到端点验（真实上传 `leave_requests.csv`）：`pending → completed` 由后端给出，
      新文档 `entity_count=null` ⇒ UI 显示 `--`（未参与建图）；演示库 13 → 14 份，
      用户已裁决接受——见 `integration-log.md` §3

## 4. 不做什么（划界）

- 不动契约、不新增后端接口
- 不改上传为推送（SSE / WebSocket）
- 不自行上传文件污染演示数据集（后端无 DELETE 文档接口，不可逆）
