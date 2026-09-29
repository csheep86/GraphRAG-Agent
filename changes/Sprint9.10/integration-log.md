# Sprint 9.10 · R19 处置 —— 实测证据链

> 完成日期：2026-09-29。范围：只动 `frontend/src/store/use-document-store.ts`；
> `contracts/openapi.yaml` **零变更**（门禁已验）。

## 0. 结论

上传后的状态流转由「`setTimeout` 假推进 + 编造实体数」改为**后端真实轮询**：
**屏上不再出现后端从未返回的实体数**，状态取不到就停在 `pending`。

## 1. 改动清单

| # | 文件 | 改动 |
|---|---|---|
| ① | `store/use-document-store.ts` | 删 `scheduleProgress`（2 个 `setTimeout` + `entity_count = 1024 + random(0~900)`） |
| ② | 同上 | 新增 `pollStatus`：真实轮询 `GET /api/v1/documents/{id}/status`，只写回 `status`；失败 / 超 12 次即停 |
| ③ | 同上 | 终态后 `load()` 回拉列表，用后端真值回填 `entity_count` |
| ④ | `store/use-affiliation-store.ts:67-73` | 修注释：原写「documents 页那套是 `setTimeout` 假推进」已**失效**，避免误导下一个核查者（R13 同类教训） |

## 2. 门禁

| 门禁 | 命令 | 结果 |
|---|---|---|
| 类型 | `npx tsc --noEmit` | 退出码 **0** |
| Lint | `npm run lint` | 无输出，0 error / 0 warning |
| 契约零漂移 | `npm run gen:api` 后 `git status --porcelain contracts/ src/types/api.d.ts` | **空** |

## 3. 点验（真机：`USE_MOCK=false` + 真实后端 + Neo4j）

| 项 | 命令 / 依据 | 实测结论 |
|---|---|---|
| 状态端点真值 | `GET /api/v1/documents/2b721483…/status` | `{"task_id":"2b721483…","status":"completed","progress":1.0,"error":null}` |
| 反证编造数 | 同上响应体 | **无 `entity_count` 字段** ⇒ 旧实现那个数是凭空生成的 |
| 列表真值 | `GET /api/v1/documents` 首条 | `entity_count: 2625`（与首页 KPI 实体数同源），证明实体数**只能**由后端给 |
| 前端页面可访问 | `GET http://127.0.0.1:3000/documents` / `/` / `/qa` | 均 **200**，dev server 编译无错 |
| 确为真机模式 | dev server 启动日志 `- Environments: .env.local, .env.development` | `.env.local` 的 `NEXT_PUBLIC_USE_MOCK=false` **优先于** `.env.development` 的 `=true` 生效 ⇒ 本次点验确实关了 Mock（否则证据不成立） |

### 3.1 真实上传端到端（用户 2026-09-29 裁决「上传并提交」，已执行）

| 步骤 | 实测 |
|---|---|
| 上传 | `POST /api/v1/documents/upload`（`demo/attendance/corpus/leave_requests.csv`，816 B，`type=text/csv`）⇒ `task_id=921b2567-3ede-41d8-b576-d068b8d3d78c`、`status=pending` |
| 轮询 | 同一 `task_id` 轮询 `GET /documents/{id}/status`：**4s 内 `pending → completed`（`progress=1.0`）** —— 状态由**后端**给出，非前端计时器 |
| 列表回填 | `GET /documents` 首条即新文档：`status=completed`、`entity_count=**null**` ⇒ UI 按既有分支显示 `--` |
| 对照 | 旧实现此刻会写入 `1024 + random(0~900)` 的**编造实体数**；新实现因该文档**未参与建图**（`kg_version_id IS NULL`）如实留空 |
| 图谱未变 | 上传前后 `GET /graph/overview` 均为 `doc=4 / ent=2625` —— 上传=入库，建图属另一条流水线，**不会**因上传即时涨数（前端亦不再假涨） |

> 注：`README.md` 直传被拒（`UNSUPPORTED_MEDIA_TYPE`，契约只允许 pdf/docx/csv），改用 CSV 复验。
> 演示库文档数 **13 → 14**（已在裁决时告知，不可逆：后端无 DELETE 文档接口）。

**无浏览器截图**：本机未装 playwright / puppeteer，无 Python 环境，故点验落在 HTTP 层而非像素层——不伪造截图。

### 3.2 为什么原先没做

原因：后端**没有删除文档的接口**
（契约内 `/api/v1/documents` 只有 `GET`，另有 `upload` / `{id}/status` / `{id}/chunks/{cid}` / `{id}/graph`），
上传后该文档会**永久**留在演示库（13 → 14 份）并可能改变图谱 `entity_count`，
**不可逆**。故先挂起；用户 2026-09-29 裁决「上传并提交」后执行，代价**已发生**（13 → 14 份），
但实测图谱 `entity_count` **未变**（见 §3.1 末行），比预估的"可能改变"更轻。

## 4. 红线自查

- **零新增数字**：本批次只**删除**编造数字来源（`1024 + random`），
  终态 `entity_count` 取自后端列表真值，未补任何替代数字。
- **无契约外调用**：轮询端点 `GET /api/v1/documents/{id}/status` 在
  `api/client.ts` 的 `CONTRACT_COVERED_PATTERNS` 覆盖范围内。
- **无静默兜底**：轮询失败即停止（保留原状态），不用 `setTimeout` 假装完成。
