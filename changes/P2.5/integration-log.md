# P2.5 集成日志 —— 第 1 个真插件 + 变体骨架（2026-10-04）

> 批次：**P2.5**（原 P1-E / P1-F）｜日期：2026-10-04｜本次为**在线**批次（三条裁决由用户拍板）
> 任务清单：`changes/P2.5/tasks.md`｜提案：`changes/P2.5/proposal.md`
> 环境：Windows 11 + Docker Desktop（`graphrag-pg` = `postgres:16-alpine`）+ Python 3.11 / uv

---

## 1. 起跑状态（**实测**）

| 项 | 起跑（P2.5 开工前实测） |
|---|---|
| `pytest -q` | **850 passed / 3 skipped / 6 xfailed** |
| 6 条 xfailed | G-10 / G-12 / **G-14** / **G-22** / G-23 ×2 |
| `plugins/` / `deploy/variants/` / `contracts/plugins/` | **均不存在** |
| `check_startup_readiness.py` | 已生效 **10** 组 / 部分生效 2 组 / 挂起 3 组 |
| compose backend `build.context` | `../backend` |

---

## 2. 实际做的 vs 计划的差异

| # | 计划 | 实际 | 差异性质 |
|---|---|---|---|
| 1 | E1：`plugins/<id>/plugin.yaml` | ✅ `plugins/json-csv-export/plugin.yaml` | 无 |
| 2 | E2：`deploy/variants/<客户>.yaml` | ✅ `deploy/variants/baseline.yaml`（**1 个**，不是 2 个） | 无（G-12 仍挂起属预期） |
| 3 | E3：Dockerfile 构建期 COPY | ✅ 改 compose context + Dockerfile COPY，**并实测构建成功** | 超计划（多做了**前置** `.dockerignore`，见 §3.1） |
| 4 | F：G-14 随首个插件并入 | ✅ `test_g14_customer_token_source_exists` 转正 | 无 |
| 5 | — | 🆕 `test_g22_plugin_entry_points_are_importable` | **新增**（理由见 §3.2：不补这条，空壳能全绿） |
| 6 | — | 🆕 更新 G-12 的 xfail reason（原写"当前 0 个变体"，已过时） | 新增（否则开工自检报告会误导） |

---

## 3. 三处**计划外但不得不做**的事（逐条写明理由）

### 3.1 仓库根 `.dockerignore`（E3 的前置，**安全相关**）

改 `build.context` 到仓库根后，**`backend/.dockerignore` 静默失效**——Docker 只认
context 根目录的 `.dockerignore`。那份里排除了 `.env`（`deployment-spec.md` §3 密钥禁入镜像）
⇒ 漏了它就是**安全事件，不是构建小问题**。

⇒ 新建仓库根 `.dockerignore`，规则用 `**/` 前缀覆盖 backend / frontend 两个子目录，
**并实测验证**：镜像内 `test -e /app/.env` ⇒ **`NO_DOTENV_CLEAN`**（无泄漏）。
`backend/.dockerignore` **保留不删**（守 R5），顶部加了"本文件当前不生效"的警示注释。

### 3.2 `entry_point` 可导入断言（否则 GA 硬门槛没有机械保证）

G-22 的主断言只验 5 个字段**非空** ⇒ 写一句 `entry_point: a.b:C` 也能**全绿**——
这正是需求基线 §300 明令禁止的「为转护栏而造空壳插件」。

⇒ 新增 `test_g22_plugin_entry_points_are_importable`：解析 `模块:类名`，
**真的 import 并检查是类**。
**负向验证已做**：把 `entry_point` 改成 `...:NotExist` ⇒ 该用例 **FAIL** ⇒ 拦得住（不是恒绿）。

### 3.3 `seam` 必须写**字符串**（ADR 示例与判据冲突）

ADR-0007 §3.6 示例写的是裸数字 `seam: 1`，而 G-22 判据要求
`isinstance(value, str)` ⇒ 照示例写会被判**「缺字段」**（实测 FAILED）。

⇒ manifest 里写 `seam: "6"`，并在文件内注释说明。
**ADR-0007 原文不改**（守 R5），差异登记在此。

---

## 4. 转正流程（两条，均守「先真通过再摘标记」）

| 护栏 | 证据 | 处置 |
|---|---|---|
| `test_g22_plugin_source_exists` | 建完 `plugin.yaml` 后跑 ⇒ **[XPASS(strict)] ⇒ FAILED**（strict xfail 下 XPASS 判红，即"真通过"的证据） | 摘 xfail，转常驻 |
| `test_g14_customer_token_source_exists` | 同样 **[XPASS(strict)] ⇒ FAILED** | 摘 xfail，转常驻 |

⚠️ **只删 xfail 标记不算转正**——本仓反复强调的一条，两条都先跑到了 XPASS 才摘。

---

## 5. 收尾数字

| 检查 | 起跑 | P2.5 后 |
|---|---|---|
| `pytest -q` | 850 passed / 3 skipped / **6 xfailed** | **853 passed / 3 skipped / 4 xfailed**（两条 xfailed 转正 ⇒ passed **+2**；新增 entry_point 断言 **+1**；**无失败**） |
| `check_startup_readiness.py` | 已生效 10 组 | **已生效 12 组**（+G-14 2 项、+G-22 3 项）；挂起 **3 组**（G-10 / G-12 / G-23） |
| `ruff check .` / `ruff format --check .` | 双绿（214 files） | 双绿（214 files） |
| `export_openapi.py --check` | 零漂移 | **零漂移**（A 类插件不碰契约，达成） |
| `check_seams.py` | ERROR 0 / OK 10 | **ERROR 0 / OK 10**（未新增接缝实现，判据 1 / 4 不受影响） |
| `check_session_drift.py` | S1–S5 OK | S1–S5 OK |
| **构建实测** | — | ✅ `docker compose build backend` **成功**；镜像内确含 `/app/plugins/json-csv-export/plugin.yaml`；**无 `.env`** |

**实测命令（带占位环境变量）**：compose 在 `build` 阶段也会校验 `${POSTGRES_PASSWORD:?}` /
`${NEO4J_PASSWORD:?}` ⇒ 必须提供，否则**连 build 都起不来**（实测踩到）。
本次用临时环境变量（**未建 `.env`**，避免密钥落盘）。

---

## 6. 遗留（不在本批边界内）

| # | 事项 | 去向 |
|---|---|---|
| 1 | **G-12 仍挂起**：1 个变体 < 启用条件 ≥2 | 真有第二个真实部署形态时再做，**不凑** |
| 2 | **变体名 `baseline` 与需求基线 §300 字面（`demo` / `default`）不一致** | 已在 `proposal.md` §7 与基线文档该行**追加登记**理由；**基线原文不改**（守 R5） |
| 3 | `backend/.dockerignore` 现**不生效**（context 已改） | 保留 + 顶部警示注释；若再改构建方式须复核 |
| 4 | `config_schema` 动态表单（DR-A5）已降级 | 暂不驱动 |
| 5 | `scripts/build_contract.py --variant`（ADR-0007 §3.6 提到）不存在 | B 类插件出现前不需要（DR-A4 已作废） |
| 6 | **`docker compose build` 需要 `.env`（或环境变量）**，README 未写明 | 建议补进 `deploy/README.md`——**未做**（属文档小修，留给你决定要不要顺手） |

---

## 7. 边界声明（防止被日后外推）

- **G-14 / G-22 转正 ≠ 插件交付形态完成**。本批只做了：**1 个 A 类插件清单 + 1 个变体 + 构建期 COPY**。
  没有 B 类插件、没有契约分片、没有变体矩阵构建（G-12 仍挂起）。
- **本批零新增业务代码**：`entry_point` 指向**已投产**的 `JsonCsvExportSink`，
  只是给既有能力补一份交付形态声明 ⇒ 谈不上"导出功能有变化"。
- **`plugins/` 下目前只有 manifest，没有插件代码**——这是 ADR-0007 §3.6 的本意
  （示例 `entry_point: app.services.auth.ldap:LdapAuthProvider` 同样是"实现在 `app/` 里"），
  **不是**没做完。
- **镜像内已含 manifest ≠ 插件已被装配**：构建期烘焙的**装配逻辑**（按 variant 选插件）
  尚未实现；当前只是把清单放进镜像使其**可自证**（ADR-0007 §4 负面项）。
