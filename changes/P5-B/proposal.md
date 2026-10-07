# P5-B · J3 前端虚线 + 演示图谱恢复 + G3 回归 + D4 收口

> 日期：2026-10-07　执行模式：**无人值守**（用户已预授权）　分支：`main` 直推
> 角色隔离：本批跨前后端，**分段执行** —— T1–T2 前端 A（只改 `frontend/`）／T3–T5 后端 B（只改 `backend/` + 跑脚本）
> 上游依据：[`../archive/2026-10-07-P5-A/integration-log.md`](../archive/2026-10-07-P5-A/integration-log.md)

---

## 1. 为什么做这一批

P5-A 以「依据失效、停下升级」收尾，四条实测证明其立项依据全部过期：

| # | 实测 | 后果 |
|---|---|---|
| ① | 本地演示图谱**不存在**（Neo4j 空实例、PG 库不在） | G1/G2/G3 一行都跑不出来 |
| ② | 出路 **A** 已于 2026-09-30 裁决**并执行过**（`valid_to` 2→48、`valid_from` 7→108） | 「裁决 A」是历史，不是待办 |
| ③ | 出路 **B**（R4-b）已核准 + 已落地（`inconsistent` 259→**352**） | G2 早就翻面 |
| ④ | `inconsistent=0` 是探针 `LIMIT 4000` 的采样盲区（全库 19 万+ 链） | 「G2 未通过」是被它骗出来的 |

⇒ 本批**不**裁决 A/B/C，也不重跑那两个已被证伪的探针。
DR-D4 真正剩下的只有 **J3（前端虚线，一行未写）** 与 **G3（受控题集回归）**。

---

## 2. 目标 / 非目标

### 2.1 In-goals

- **J3**：推理路径上 `valid_to` 已过期的跳，前端画成**虚线置灰**，不再与有效边同色。
- **图谱恢复**：把 `attendance-demo-v1` 演示库重建起来（G3 与 J3 端到端验收的硬前置）。
- **G3**：`eval_controlled_qset.py` 40 题 v4 回归，比对 P6-H 基线 **C1 = 0.0294**。
- **D4 收口**：三门禁 + 护栏不倒退 + CI 全绿。

### 2.2 Non-goals（**10 条，改一条都要先回来登记理由**）

1. **不改契约**：`valid_from` / `valid_to` 已在 `ReasoningPathHop`（`api.d.ts:3287` / `:3292`），本批 `npm run gen:api` 后 `git diff` 应为空。出现 diff 说明走了弯路，先停下来判断。
2. **不改后端推理逻辑**：逐跳时态由 `reasoning.py:425-430` 填好，本批不动。
3. **不做 as-of 的前端交互**（时点选择器 / 双时点对比 UI）：J4 是后端判据，前端入口不在本批。
4. **不引入前端测试框架**：仓库 `package.json` 无任何测试框架，靠 `typecheck` + `lint` + `build` + 真机 DOM 断言。
5. **不改演示语料**：`demo/attendance/policies/*.md` 与 `corpus/*.docx` 一个字不动。
6. **不做 D2（M6）/ D1 / D3 / D5 / D7 / D8**：排期在 D4 之后。
7. **不做实体消解 / M4 完整化**（DR-D5，另一阶段）。
8. **不改 `specs/` 与 ADR**：J3 是渲染，不是口径变更。
9. **不改 `docs/delivery-plan.md` 与 `docs/delivery-requirements-and-guardrails.md` 的陈旧口径**（留待专门的口径订正批）。
10. **不订正 `_bridge_window.py:3` 的「（待核准记录）」注解漂移**（不影响行为）。

---

## 3. 决策（**已裁决；执行中若发现依据有误则停下升级，不默默改道**）

| # | 决策点 | 裁决 | 依据 |
|---|---|---|---|
| **D1** | 虚线判定口径 | **`valid_to` 非空 且 `valid_to <= 今天` ⇒ 虚线置灰** | 后端 `reasoning.py:545-546`：`valid_to is not None and str(valid_to) <= as_of` 判为 unconfirmed。**不为前端重写一套过滤条件**（13 号记录「本次踩到的坑」正是死在这上面）。契约注释 `api.d.ts:3290` 省了「在今天已过期」这个前提，当前语料上两者等价（`valid_to` 只有 `2025-12-31`），**严格口径以后端为准**并登记，**不改契约文本**（Non-goal 1） |
| **D2** | 改哪些文件 | 只改 `frontend/src/components/qa/reasoning-path.tsx`；判定函数放 `frontend/src/lib/reasoning.ts`（已有展示层映射，非新建模块） | 该文件是推理路径唯一渲染点（`:44-95`）。**不许**顺带改 `attribution-panel` / `evidence-panel` 的空状态卡片边框 |
| **D3** | 图谱恢复做不做 | **做**；设**闸门 G0**：若失败或成本失控，J3 独立收口提交，G3 转下一批 | 恢复不等于复刻（`docs/demo-seed-dataset.md:70` 写明 LLM 抽取非确定性），只保证同源 + 同规则 + 可校验 |
| **D4** | G3 基线 | **P6-H `C1 = 0.0294`**（graph 0.875 / baseline 0.850 / v4 / L2） | **绝不可**与 v3 的 `0.0909` 比，分母不同（14 对 40） |
| **D5** | 环境口令 | `.env` 的 `NEO4J_PASSWORD` 改为 **`ci-graph-pw-2026`** | 容器实测；`.env` 在 `.gitignore`，不进提交但要登记 |
| **D6** | 恢复路径 | **脚本直连**（`seed_attendance_ontology.py` 到 `ingest_attendance_csv.py` 再到 `ingest_attendance_policies.py`） | **不**走 `demo-seed-dataset.md` §4 的 HTTP 上传路，那是招商局系年报，不是 `attendance-demo-v1` |

---

## 4. 验收判据（**必须真跑出来，不是读代码得出**）

### T1–T2：J3（零成本，不依赖图谱）

1. `npm run typecheck` exit 0、**`npm run build`** exit 0、`npm run lint` exit 0。
   **`build` 才是前端真实门禁**（完整类型检查 + lint），不能只跑 `typecheck` 就宣称通过。
2. **契约零漂移**：`npm run gen:api` 后 `git diff --stat` 为空。
3. **行为（真机）**：起后端加 `npm run dev`，跑一次命中失效跳的问答，在渲染出的 DOM 中断言：
   该跳带**虚线**标记，同一条链上 `valid_to` 为空的跳**不带**。
   这条依赖图谱，排在 T3 之后；图谱恢复失败（D3 闸门）则改用 mock 快照做静态渲染断言，并**如实登记为降级**。

### T3：图谱恢复（有花费：MinerU + LLM）

4. PG 建库加迁移完成；Neo4j `attendance-demo-v1` 的 `Entity` / `Relation` 计数大于 0，`kg_versions` 行 `status=ready`。
   对照值（非硬指标）：原库 2855 / 3729。
5. **B3 汇合路径可查**：`ingest_attendance_policies.py` 自带的 `verify_and_close` 四项 `[OK]`。

### T4：G3（有花费：40 题 LLM）

6. `eval_controlled_qset.py` 跑完，读出 `C1` 与两侧 `graph` / `baseline`，与 0.0294 / 0.875 / 0.850 比对。
   判为不回归的条件是 `graph` 侧**不出现断崖式下降**（大于单题灵敏度 2.5pp 需登记并说明）。
7. **暴露回归就如实登记，不许压。**

### T5：收口

8. 三条门禁（J6）：`pytest` 不降、`check_seams.py` ERROR 0、`export_openapi.py --check` 零 diff。
9. 护栏不倒退：`check_startup_readiness.py` 出口仍为 `[OK]` 17 / `[~~]` 0 / `[--]` 0。
10. **CI 四 job 全绿**（R-10：CI 才是终裁），run id 回登 `integration-log.md`。
