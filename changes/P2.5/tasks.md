# P2.5 — 第 1 个真插件 + 变体骨架（DR-A1 / DR-A2 / DR-A3 + G-14）

> **出处**：本批即 `changes/P1/tasks.md` 第 185-191 行的 E1 / E2 / E3 / F 四项
> （2026-10-01 裁决「E / F 组整批推到 P2 之后」，记为 P2.5）。
> **搬迁说明**：P1 那份清单**不动**（守 **R5**：历史记述只追加不删改），此处是执行落点。
> **裁决记录**：见 `changes/P2.5/proposal.md` §7（2026-10-04 用户采纳三项建议）。

---

## 裁决记录（2026-10-04，用户已拍板）

| # | 裁决 | 关键证据 |
|---|---|---|
| **1** | 第 1 个真插件 = **`json-csv-export`**（ADR-0004 接缝 6，`JsonCsvExportSink`） | 五个候选中**唯一**「已在登记集合 + 已有真实实现 + 天然 A 类」；`ldap-auth` / `oa-webhook` 被 ADR-0004 §3 第 4 条**点名**为登记外实现，`IngestionSource` 为 0 实现（必是空壳） |
| **2** | 变体命名为 **`baseline`**，**不**用文档 §300 字面的 `default` / `demo` | 实测基座契约词频：`default` **10 次**、`demo` **3 次**、`baseline` **0 次**；`_customer_tokens()` 用**子串**匹配 ⇒ 照字面命名会结构性假红 |
| **3** | E3 的 `COPY` ⇒ **改 compose 的 `build.context` 为仓库根** | `PLUGIN_ROOT` = 仓库根 `plugins/`，而 context 现为 `../backend` ⇒ `COPY plugins` 无源 |

---

## ⛳ 开工前置

1. **本机必须先起 PostgreSQL**（同 P2-B，漏了 pytest 全红且看起来像代码坏了）：

```bash
docker run -d --rm --name graphrag-pg \
  -e POSTGRES_USER=graphrag -e POSTGRES_PASSWORD=graphrag -e POSTGRES_DB=graphrag_test \
  -p 5432:5432 postgres:16-alpine
until docker exec graphrag-pg pg_isready -U graphrag -d graphrag_test; do sleep 1; done
```

2. **开工自检**：`cd backend && uv run python scripts/check_startup_readiness.py`
   ⚠️ 它**恒退 0**（只报告非门禁）⇒ 自己读四档数字，别把输出当"通过"。

3. **起跑基线（实测 2026-10-04）**：`pytest` = **850 passed / 3 skipped / 6 xfailed**；
   6 条 xfailed = G-10 / G-12 / **G-14** / **G-22** / G-23 ×2。
   `plugins/`、`deploy/variants/`、`contracts/plugins/` **均不存在**。

---

## E1 / DR-A2 — `plugins/json-csv-export/plugin.yaml`

- [x] 建目录与清单，字段取 ADR-0007 §3.6 全量（G-22 只强制其中 5 个，其余按 ADR 补）：

```yaml
id: json-csv-export
version: 1.0.0
base_version: "1"
class: A                  # A 类：纯配置，不碰契约、零前端改动
seam: 6                   # ADR-0004 接缝 6 数据输出
entry_point: app.services.export.json_csv:JsonCsvExportSink
config_schema: null       # DR-A5 已降级 ⇒ 暂不驱动动态表单
openapi_fragment: null    # 仅 B 类才填
```

- [x] **入口真实性（本批新增，针对 GA 硬门槛「不许造空壳」）**：
      G-22 只验 5 个字段非空 ⇒ **写一句假 `entry_point` 也能转绿**——那是标准的空壳假绿。
      ⇒ 加一条断言：`entry_point` 的**模块可导入且类存在**（按 `模块:类名` 解析）。
      建议落点：`tests/test_guardrails_delivery.py`，与 `test_g22_plugin_manifests_are_valid` 同组。
- [x] 出口：**先**让 `test_g22_plugin_source_exists` **真通过**，**再**摘 xfail
      ⚠️ 只删 xfail 标记不算转正（本仓反复强调的一条）
- [x] 登记：`docs/delivery-requirements-and-guardrails.md` 的 G-22 行同步为「部分 → 已生效（1 个真插件）」

⚠️ **不搬实现代码**：`entry_point` 指向既有的 `app/services/export/json_csv.py`
（ADR-0007 §3.6 的示例 `app.services.auth.ldap:LdapAuthProvider` 就是同款写法）
⇒ `check_seams.py` 的判据 1 / 4 **不受影响**（`SCAN_DIRS` 只含 `app` / `scripts`，实现留在 `app/`，未新增实现类）。

---

## E2 / DR-A1 — `deploy/variants/baseline.yaml`

- [x] 建 `deploy/variants/baseline.yaml`，按 ADR-0007 §3.2 示例：只描述「启用什么」，**不含业务代码**
- [x] `customer: baseline`（文件名与 `customer` 值**都用** `baseline`——实测契约 0 次，不会假红）
- [x] 顶层**不写** `id` 字段（避免与 `_customer_tokens()` 的 `id` 取值口径混淆）
- [x] ⚠️ **只产 1 个变体** —— G-12 启用条件写死 `≥ 2`，本批**不凑第二个**
      （需求基线 §300：❌ 不许为凑数捏造客户、❌ 不许放宽成 ≥1）
- [x] 出口：`test_g14_customer_token_source_exists` **真通过**后再摘 xfail

---

## E3 / DR-A3 — 构建期烘焙（COPY 插件进镜像）

⚠️ **前置子任务（不可跳过）**：`backend/.dockerignore` 只在 backend 下，
**改 context 到仓库根后它就失效了**（Docker 只读 context 根的 `.dockerignore`）。
⇒ **必须先新建仓库根 `.dockerignore`**，把 backend 那份规则搬过去，**尤其要含 `.env` / `.env.*`**
（`deployment-spec.md` §3：密钥禁入镜像）。**这一步没做完就不要动 context。**

- [x] 仓库根建 `.dockerignore`（含 `.env`、`.venv/`、`__pycache__/`、`.git/` 等）
- [x] `deploy/docker-compose.yml` 的 backend：`context: ..`（相对 `deploy/` ⇒ 仓库根）、`dockerfile: backend/Dockerfile`
- [x] `backend/Dockerfile`：COPY 路径加 `backend/` 前缀（`pyproject.toml` / `uv.lock` / `app` / `migrations` / `alembic.ini`），新增 `COPY plugins ./plugins`
- [x] **为什么 manifest 进镜像有意义**：ADR-0007 §4 负面列了「半年后无人知道客户 B 的镜像里烘焙了什么」
      ⇒ manifest 进镜像后，镜像内可直接自证（可 `cat /app/plugins/*/plugin.yaml`）
- [x] 出口（**实测**）：`docker compose build backend` 成功。
      ⚠️ 本机构建需拉 `python:3.11-slim` + `uv` 镜像，可能耗时/受网络影响 ⇒
      **若失败或超时，登记 `BLOCKED` 并说明，不阻塞 E1 / E2 / F**（勿让一处卡住整批）
- [x] G-19 复核：它只查 `image:` 与 tag，**不查 build.context** ⇒ 理论上不受影响；
      改完仍要实跑一次 `pytest tests/test_guardrails_delivery.py -k g19` 确认

---

## F / G-14 — 基座契约纯净性（随首个插件并入）

- [x] 随 E1 / E2 落地，`_customer_tokens()` 黑名单终于非空 ⇒ 守卫条转正
- [x] ⚠️ **预期管理**：主断言 `test_g14_base_contract_has_no_customer_specific_fields`
      之后**仍然恒绿**（基座契约里没有 `baseline` 字样）——**这是预期不是缺陷**，
      它的职责是"客户标识一旦泄进契约就红"。证明"它并非从没生效过"的是转正常驻的**守卫**那条。

---

## Non-goals（本批**不做**）

- ❌ **不改** `contracts/openapi.yaml`（契约零 diff；A 类插件不碰契约）
- ❌ **不做** B 类插件（无 `openapi_fragment` / 无前端 / 不建 `contracts/plugins/`）
- ❌ **不做**插件**运行期**动态装配（ADR-0007 §3.1 已裁决：构建期烘焙）
- ❌ **不新增**任何接缝实现（不碰 `LdapAuthProvider` / `OaEventSink` / `IngestionSource`）
- ❌ **不改** ADR-0007 / ADR-0004 原文（守 R5，差异追加登记）
- ❌ **不碰** RLS（P3）、SSO（P2-C）、License（P4）、G-10 / G-12 / G-23

---

## 出口判据（四条全绿）

| # | 判据 |
|---|---|
| 1 | `pytest` 全绿，且 passed **不少于 850**，**xfailed 6 → 4**（G-14 守卫 + G-22 守卫转正） |
| 2 | `ruff check .` 全过 |
| 3 | `export_openapi.py --check` **零漂移**（A 类插件 ⇒ 契约不动） |
| 4 | 两条 xfail 均**先真通过再摘标记**；G-12 **仍挂起**（1 < 2 变体，属预期） |

---

## 遗留（已知，不属本批）

| # | 事项 | 去向 |
|---|---|---|
| 1 | G-12 需要第 **2** 个变体才可能转正 | 真有第二个客户 / 第二个真实部署形态时再做，**不凑** |
| 2 | `config_schema` 的动态表单（DR-A5）已降级 | 暂不驱动 |
| 3 | `scripts/build_contract.py --variant`（ADR-0007 §3.6 提到）不存在 | 契约分片合并随 DR-A4 作废；B 类插件出现前不需要 |
| 4 | 变体命名与需求基线 §300 的**字面**命名（`demo` / `default`）不一致 | 已在本文档裁决记录登记理由；**不改**基线原文（守 R5） |
