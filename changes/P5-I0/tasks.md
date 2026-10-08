# P5-I0 · 任务拆解

> **边界**：[`proposal.md`](./proposal.md) §3（10 条 Non-goals）
> **执行模式**：无人值守，逐任务验证通过即提交
> **起点**：`main` = `f503e8a4`（CI run `37769050202` 四 job 全绿）

---

## T1 · 版本号定长（**后端开发 B**）

- [ ] `backend/app/services/kg/incremental.py::_next_version`：
  - [ ] 删掉 `base` 形参（调用方只有 `:243` 一处）
  - [ ] 改为 `<%Y%m%dT%H%M%SZ>-inc-<uuid4hex8>`（**恒 29 字符**，与级数无关）
  - [ ] docstring 写清实测反哺：`models.py:286` 是 `String(64)`，旧写法每级 +11
        ⇒ 25 + 3×11 = 58 ✓ / **4 级 69 ✗**；P5-H 写多级链用例时实测撞到 `value too long`
  - [ ] 写明 **版本号不承载父子关系**（指向 `ontology_actions` 两列；ADR-0008 §3）
  - [ ] 保留既有的「重名重试 8 次」唯一性检查（不改）
- [ ] ⚠️ **不碰** 同文件里其它任何东西（`rebuild_incrementally` / `_rewrite_subgraph` / P5F-3）

## T2 · 测试（**后端开发 B**，同一笔提交）

- [ ] `backend/tests/test_kg_incremental_rebuild.py`：
  - [ ] **新增**：连续 **8 次** `_next_version()`（走真 PG）⇒ 每次长度恒 29 且 ≤ 64
  - [ ] **新增看门狗**：用旧口径算出「第 4 级 = 69」并断言 `> 64`
        ⇒ 把"为什么必须定长"钉成可执行事实，防止有人改回 `<base>-inc-*`
  - [ ] **改（P5I0-2）** `:617` 的 `version.like(f"{base}-inc-%")` ⇒ 改为**调用前后快照对比**
        （统计该 org 的 `KgVersion` 行数没变多）—— 语义更强且不依赖字符串格式
  - [ ] **改（P5I0-2）** `pg_fixture` 的清理（`:315`）⇒ 改为按 `trace_id` 精确清理
        （新版本行不再带 base 前缀，`like(f"{base}%")` 漏删 ⇒ 会污染后续用例）
- [ ] `backend/tests/test_version_read_view.py:235-237`：更新 workaround 注释
      （限制已解除 ⇒ 不再需要最短后缀），并把 `-i<N>` 改回真实后缀

## T3 · `ontology` tag 描述纠偏 + **契约同步五步**（**架构师** + B，走完整流程）

- [ ] `backend/app/core/openapi.py:69-79`（**真源**，不是 `openapi.yaml` 产物）：
  - [ ] 删「⚠️ 当前全部为占位骨架，恒返回 501」⇒ 改为**事实**：merge / split / rename
        自 **P5-G** 起已实装（返 200 `OntologyActionResponse{kg_version, status:"applied"}`）
  - [ ] 改「只有 `POST /ontology/confirm` 会写生效状态」⇒ 澄清 **GAP-F2 的真正口径**是
        「**严禁 LLM 自动修改本体**」，三个改本体的动作**都是人工触发**（人工回车才执行），
        LLM 建议侧`cold-start` 仍需 `confirm` 才生效
  - [ ] 列明**仍是占位**的端点（`active` / `confirm` / `cold-start` / `cost/dashboard`）
  - [ ] **不改** `cost` tag（那句「占位骨架」**仍为真**）
- [ ] 契约同步：`uv run python scripts/export_openapi.py`（不是 `--check`）⇒ `git diff` 应只有描述行
- [ ] 前端：`cd frontend && npm run gen:api` ⇒ **预期 `src/types/api.d.ts` 零变更**
      （tag 描述不进 TS 类型）；若有变，**以 CI 为终裁**

## T4 · spec 状态 + 追踪矩阵 + DR 对账（**架构师**，单独一笔提交）

- [ ] `specs/m6-ontology-incremental.md:261`：端点状态改为事实
      （merge / split / rename 已实装 P5-G；其余四个仍占位）；**编号不重排**（R5）
- [ ] 同文件 §10.1（实现批次状态表）：补 P5-F / P5-G / P5-H / **本批** 的落地登记；
      ⚠️ 批次 B（GUI）**仍未完成** —— 不许写成已完成
- [ ] `docs/acceptance-traceability-matrix.md` M6 行：追加 **P5-I0** 状态与仍缺项
- [ ] **DR-B6 / DR-B7 ↔ G-9 / G-10 口径对账**（纯 docs，不改判据强度）：
      需求侧明细行仍写「⏳ 零代码」而护栏侧已 ✅ 转正 ⇒ 改成**一致的事实表述**，
      并保留"该项依旧依赖 G-9 T1 / G-10 T2 在 PG 上执行、禁止 `local_only` 绕过"这一条约束

## T5 · 门禁与收口

- [ ] `uv run ruff check .` + `uv run ruff format --check .`
- [ ] `export_openapi.py --check` 零 diff、**28 路径不变**（判据 6 / 7）
- [ ] `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0（判据 9）
- [ ] `check_seams.py` 仍 ERROR 0 / WARN 0 / **OK 12**
- [ ] `check_session_drift.py`（S1 应读到**本批 10 条** Non-goals；S2 应远低于阈值；
      S5 对本批无新模块的答案是"无新增模块"，或指出 T3 的产物 indeed 被引用）
- [ ] G-9 T1 / G-10 T2 全绿且断言未放宽（判据 10 —— **版本号变了，这两类是最后一道**）
- [ ] 本地 pytest（带 `GRAPH_REAL_NEO4J_*` 三开关）
- [ ] integration-log 撰写 + 分段提交 + 推送 + CI 四 job 全绿（判据 12）
