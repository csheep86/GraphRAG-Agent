# Sprint 9.6 集成日志（证据链）

> 全部数字为 2026-09-28 真机实跑，命令附后。

## 批次 G1：GOVERNED_BY 汇合（入图器）

- `ingest_attendance_csv.py` 新增 `fetch_policy_context` / `build_governed_by_relations`，
  边并入 `relation_rows`（自检 / 回滚自动覆盖）；连边 0 条拒绝置 active。
- 单测 `tests/test_ingest_governed_by.py` **8 条全过**：
  确定性 id / span 噪声不参与 / 碎片名靠 chunk 文本命中 / 未命中可见 / 空名跳过 /
  去重 / fetch 查询形状（MENTIONS→POLICY_CLAUSE）/ null 容忍。
- 全量门禁：`pytest -q` **506 passed**（498 → 506）；ruff check / format 通过。

## 批次 G2：重建图 + 真机验证

- `uv run python scripts/ingest_attendance_csv.py --purge-csv`（同 `attendance-demo-v1`）：
  实体 2625 / 关系 3496→**3576**（+80 GOVERNED_BY）；写入自检回读一致；版本 active + PG ready。
- `verify_cases` 7 用例全 OK，含新增：
  `E002 李静 → 岗位 → 工时制 → POLICY_CLAUSE：27 条可达`。
- 真机 `/agent/query`（问「李静的月加班超过上限了吗？」）：
  `reasoning_path` = `EMPLOYEE:E002 -HAS_POSITION→ POSITION:产线操作工
  -APPLIES_WORK_TIME→ WORK_TIME_SYSTEM:综合计算工时制 -GOVERNED_BY→ 加班规定（POLICY_CLAUSE）`，
  3 跳逐跳可回查；答案引用「每月加班时间不得超过 36 小时」条款（`citations=5`）。
- **顺带修复**：`reasoning._CYPHER_PATHS` 的 LIMIT 无 ORDER BY 截断缺陷——
  修前同问句路径只停在 1 跳 `SHIFT:S00039`（条款链从未进候选）；
  修后 Cypher 排序（中途排除 EMPLOYEE + 条款优先 + 跳数 + 终点 id 字典序），
  Python `_select_shortest_path` 精排保留兜底。

## 批次 G3：合规抽屉制度依据可读化（前端，契约不动）

- `finding-detail-sheet.tsx`：`graph:clause:ent_*` 回查 `GET /entities/{id}`
  显示条款标题，原 ref 降级为副标题；回查失败降级显示原 ref（不伪造）；
  `document:doc:…` 本就可读、不回查。lint / tsc 通过。

## 批次 G4：文档

- `dev-doc-status.md` R10 置「已修复」；`sprint-calendar.md` §5 新增 S9.6 行 + v1.9 变更记录。

## 复现命令

```bash
cd backend
uv run pytest -q
uv run python scripts/ingest_attendance_csv.py --purge-csv
uv run python scripts/demo_rehearsal.py --domain attendance --with-llm \
  --frontend-base http://127.0.0.1:3000
```

彩排最近一次全绿记录：`PASS 10 / FAIL 0 / SKIP 0`（含前端 4 页 200）。
