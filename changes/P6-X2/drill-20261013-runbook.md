# 恢复演练 ① 命令序列（2026-10-13）

> **执行者**：`wIlliam`　**见证者**：`tianen`（两人不同、当场在场，§9.3 第 2 条）
> **AI 角色（红线，Non-goal 3）**：只**搬运 / 校验 / 跑命令 / 回登**。
> **命令由 wIlliam 逐条确认后 AI 代敲，tianen 看读数**；**留证正文由人写，AI 一个字不代写**。
> 演练性质：**内部演练，非客户现场验收**（R-10）。

---

## 0. 前置核验（**已跑，2026-10-13 实读**）

| 项 | 读数 | 结论 |
|---|---|---|
| 固定 tag 镜像 | `graphrag-agent/{backend,frontend}:1.6.0`（`2fcd0ed1389e` / `6e0c62a6a2f6`） | ✅ 与 §9.4.1 一致 |
| 交付 compose | `deploy/docker-compose.delivery.yml`，**无 `build:`**，四服务有 healthcheck | ✅ |
| 库名 / 账号 | `POSTGRES_DB=graphrag`、`POSTGRES_USER=graphrag`（`:62-64`）；backend 连库用 `app_rls`（`:118`） | ✅ 恢复目标库**已存在**（`restore` 不建库，正合要求） |
| License | `deploy/license/app.lic`（580B，10-11 18:41）**在**；签发私钥 `~/.graphrag-license/private.pem`（119B）+ `public.b64`（46B）**在** | ✅ 第 2 项**可重签**（不签则必 FAIL） |
| 既有备份集 | `backend/reports/backup/20261012-p6w/`、`full2/` **仍在**（含 `license.lic`） | ⚠️ 更正 P6-X2 早先登记：旧集**未被清**；但仍建议**当天现跑一次** |
| drill 资产 | `backend/reports/delivery/.env.drill`（8 键，含 `PRIVATE_DEPLOY_ENABLED` / `LICENSE_PUBLIC_KEY`）、`drill-license-override.yml`（给 backend 注入验签公钥） | ✅ 第 10 项的 `--env-file` **有现成且真实存在** |
| **端口冲突** | 源环境容器占 **7687 / 7474**（`graphrag-neo`）、**5432**（`graphrag-pg`）；交付栈 PG **不映射**宿主端口 ⇒ 只冲突 neo4j 两个 | ⚠️ 见 §1 待确认 **C1** |

---

## 1. 开工前须 wIlliam 拍板的 3 项（**AI 不默认**）

| # | 选择点 | 选项 | AI 建议 |
|---|---|---|---|
| **C1** | neo4j 宿主端口 7687/7474 被源环境占用，怎么起独立栈 | (a) 停源环境 `graphrag-neo`；(b) **复制 compose 到 `reports/delivery/` 改宿主端口 7688/7475 后用它起**（不动源环境）；(c) 云上另起 | **(b)** —— Non-goal 6「不许碰源环境」；⚠️ 注意 compose 对 `ports:` 是**追加**不是替换，所以**不能**用 override 改端口，必须改副本 |
| **C2** | 备份集 | (a) **当天现跑一次** `scripts/backup.py`；(b) 用既有 `20261012-p6w` | **(a)** —— 第 8 项给了不存在的目录 = **FAIL 不是 SKIP**（`:591-592`）；现跑最稳，且留证可写"演练当天产出" |
| **C3** | 恢复的数据来源 | 用**本机开发库**的备份（只读导出）恢复到独立栈 | 可接受（**不是生产数据**），但**留证必须写明**「演练数据 = 开发库副本，非客户现场数据」 |

**诚实标注（写进留证，不许略）**：本次是**同机**起独立栈 ⇒ 宿主 machine-id 与源环境**相同**
（compose `:136-145` 把宿主 machine-id 挂进容器）⇒ **「换机 ⇒ License 失效、须重新签发」这条规格本次未真验到换机场景**。
若要真验，须换一台机器（属 O-2，可排在 n=2 的第二轮或另立批）。

---

## 2. 命令序列（**逐条确认后执行；每条都贴读数**）

> 约定：`PROJECT=graphrag-drill`（容器名随之 = `graphrag-drill-postgres-1` / `-neo4j-1` / `-backend-1` / `-frontend-1`）。

### 序 1 — 起独立环境（**由固定 tag 镜像起，不许源码起**）

```powershell
cd d:/AIProject/GraphRAG-Agent
# C1 选 (b) 时：先复制并改掉 neo4j 的宿主端口（7687→7688、7474→7475），内部端口不动
docker compose -p graphrag-drill `
  -f deploy/docker-compose.delivery.yml `
  -f backend/reports/delivery/drill-license-override.yml `
  --env-file backend/reports/delivery/.env.drill up -d
```

**预期读数**：4 个服务（neo4j / postgres / backend / frontend）+ `db-init` 一次成功退出。
**见证点（tianen）**：`docker ps --filter name=graphrag-drill` 里**没有** `graphrag-neo` / `graphrag-pg`（确认是**新栈**不是源环境）。

### 序 2 — 等全 healthy（第 1 项）

```powershell
docker compose -p graphrag-drill ps        # 四服务状态须全 healthy
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8000/api/v1/health   # 期望 200
```

### 序 3 — License（第 2 项，**不签必 FAIL**：`:351-352`）

先看现有 `deploy/license/app.lic` 在新栈里是否 `active`：

```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/license/status
```

非 active ⇒ 用 `tools/license/issue_license.py issue` 重签（`--fingerprint` 取 `license_cli fingerprint` 的输出，
`--private-key-file ~/.graphrag-license/private.pem`，`--out deploy/license/app.lic`），重载后再查一次。

### 序 4 — 现跑备份集（第 8 项，**C2 选 (a)**）

```powershell
cd backend
uv run python scripts/backup.py --out-dir reports/backup/drill-20261013 `
  --pg-container graphrag-pg --neo4j-container graphrag-neo --env-file .env
```

**预期读数**：`backup-manifest.json` 产出、SHA-256 校验通过。**记住这个目录路径**（第 8 项要用）。

### 序 5 — 恢复（**演练主体：人执行，AI 代敲**）

```powershell
uv run python scripts/restore.py --backup-dir reports/backup/drill-20261013 --apply `
  --pg-container graphrag-drill-postgres-1 --target-db graphrag `
  --neo4j-container graphrag-drill-neo4j-1
```

⚠️ 先跑**不带 `--apply`** 的校验版看一遍，再由 wIlliam 决定是否 `--apply`。
**见证点**：恢复后 PG / 图库读数、`--target-db graphrag` 库确实存在。

### 序 6 — 冒烟 + 打满审计（第 6 项，**陷阱项，¥0**）

```powershell
1..8 | ForEach-Object { curl.exe -s -o NUL -w "%{http_code} " http://127.0.0.1:8000/api/v1/documents?page_size=1 }
```

**为什么 8 次**：判据要 `audit_log` 新增 **≥7 条**（`:496-497`）；`AuditMiddleware` 对 `/api/v1/*`
非 health **全量写**、在 `finally` 里写（`middleware.py:139-147`）⇒ **403 也留痕**，不起 LLM 即可达标。

### 序 7 — 十项验收

```powershell
uv run python scripts/install_acceptance.py `
  --base-url http://127.0.0.1:8000 `
  --compose-file deploy/docker-compose.delivery.yml `
  --backup-dir reports/backup/drill-20261013 `
  --env-file ../backend/reports/delivery/.env.drill `
  --log-file <真实存在的日志文件> `
  --org-a 00000000-0000-4000-8000-000000000001 `
  --org-b 5dea8f62-0c67-579a-9509-8b4ce98eadea `
  --out reports/delivery/acceptance-20261013.json
```

**三条硬约束**：
- **不给** `--pipeline-sample` / `--ask-question` ⇒ 第 4 / 5 项是**登记过的 SKIP**（Non-goal 4），**当天不许补跑**；
- **不加** `--skip-pytest`（第 3 / 7 项的委派子项要真跑，空跑 `ran == 0` = **FAIL**，`:229-235`）；
- `--log-file` **必须真实存在**（文件不存在会被判 leaked ⇒ FAIL，`:763-764`）⇒ 先从容器 `docker cp` 出一份真日志。

**预期汇总**：**PASS 7 / SKIP 3 / FAIL 0**（SKIP = 第 4、5 项登记过 + 第 7 项目标环境子项拖整项）。
⚠️ `render` 的汇总行会明写「SKIP **不是**通过」⇒ 留证里照抄，不许读成"9 项通过"。

### 序 8 — 人写留证（**AI 不代笔**）

`docs/drills/restore-drill-20261013.md`（文件名**必须**匹配 `restore-drill-*.md`，`install_acceptance.py:681`），
须含：日期、**执行者 wIlliam / 见证者 tianen 两人署名**、「内部演练，非客户现场验收」、
镜像 tag 与 tar SHA-256、十项逐项读数、**同机未验换机场景**的说明（§1 诚实标注）。

### 序 9 — AI 回登

确认第 9 项转 PASS 后再跑一次验收脚本 → 把读数回登 `integration-log.md` → 提交推送 → 等 CI。

---

## 3. 回滚 / 中止

任一序失败 ⇒ **停下、读数贴进留证**，不重试掩盖。收尾清理：

```powershell
docker compose -p graphrag-drill down -v     # 只动演练栈的卷，不碰源环境
```
