# 恢复演练留证（2026-10-13）

> ✅ **2026-10-13 已完成**：正式留证 = `docs/drills/restore-drill-20261013.md`（已落库）；
> 本文件仅作**过程留档**（填选框的来处），**不是**第 9 项判据。
>
> **本文件是骨架，不是留证。** 填完署名与结论后，**另存为**
> `docs/drills/restore-drill-20261013.md`（第 9 项只认这个路径与 `restore-drill-*.md` 这个文件名，
> `install_acceptance.py:681`）。**不要**把骨架直接丢进 `docs/drills/`。
>
> 机械读数由 AI 搬运（可复核的路径都标了）；**【待填】三处必须由执行者亲笔** ——
> §9.3 第 2 条：执行者 ≠ 见证者、两人当场在场；Non-goal 3：AI 不代写正文、不代判结论。

---

## 0. 性质声明

- **内部演练，非客户现场验收**（R-10）。
- 日期：**2026-10-13**。
- 演练类型：恢复演练（备份 → 独立环境恢复 → 冒烟 → 十项验收）。升级演练（含回滚）另排 2026-10-14。

## 1. 执行者与见证者（**【待填 1：wIlliam 亲笔】**）

> 下面这段请**照你的实际写法**写，AI 不代笔。要点：写清是谁执行、谁见证、**两人不同**、**当场在场**。

- 执行者：william
- 见证者：tianen
- 在场情况（何时、何地、是否全程在场）：2026-10-13,广州，全程在场
- 本人确认上述读数为当场实测，非事后补记：　签名 _william__tianen___　日期 __2026-10-13____

## 2. 演练环境（AI 搬运，可复核）

| 项 | 读数 | 出处 |
|---|---|---|
| 交付镜像 | `graphrag-agent/backend:1.6.0`（ID `2fcd0ed1389e`）、`frontend:1.6.0`（ID `6e0c62a6a2f6`） | 与 `delivery-plan.md` §9.4.1 登记一致 |
| compose | 交付 compose 的**演练副本** `backend/reports/delivery/docker-compose.drill-20261013.yml`（仅把 neo4j 宿主端口改 7688 / 7475，**容器内端口未动**） | 源环境 `graphrag-neo` 占用 7687 / 7474 |
| 项目名 / 卷 | `COMPOSE_PROJECT_NAME=graphrag-drill`；卷 `graphrag-drill_pg_data`、`graphrag-drill_neo4j_data`、`graphrag-drill_neo4j_logs` | 与源环境 `graphrag-agent_*` **分离** ⇒ 独立环境 |
| 健康状态 | 四服务全 healthy；`GET /api/v1/health` = **200** | `docker compose ps` + curl |

## 3. 备份集（第 8 项，AI 搬运）

目录 `backend/reports/backup/drill-20261013/`，**演练当天现跑**（`scripts/backup.py`）。
图库 dump 时源环境图库处于停止状态（`backup.py` 的停容器分支，`:153-190`），完成后已 `docker start` 复原。

| 对象 | 大小 | SHA-256 |
|---|---|---|
| postgres | 192,157 B | 校验通过（值见 `backup-manifest.json`） |
| neo4j | 6,028,528 B | 校验通过 |
| storage | 114,688,000 B | 校验通过 |
| license | 580 B | 校验通过 |
| config（脱敏副本） | 3,632 B（6 项密钥置 `<redacted>`） | 校验通过 |

清单另记录：PG active 版本 `20261012T064951Z-inc-569555ad`。

## 4. 恢复过程（AI 搬运）

| 对象 | 结果 | 备注 |
|---|---|---|
| PG | ✅ 已恢复到库 `graphrag` | `restore.py --apply` |
| 图库 | ❌ `neo4j-admin load` 退出码 1 ⇒ 补做：停演练栈图库 + `docker run --volumes-from` 一次性容器 load ⇒ **42 files / 268.3 MiB** | 见 §6 发现 1 |
| 图库数据校验 | 恢复后 **11668 个节点**、**176 个 `:KgVersion`** | cypher-shell 实测 |
| storage | ⚠️ 解开到**宿主** `backend/storage`（落点错位） | 见 §6 发现 4 |
| license | ⚠️ 恢复到**宿主** `deploy/license/app.lic`（同源 580B）；演练栈容器内 License 未受影响（588B，仍 `active`） | 同上 |
| License | 容器内指纹 `4d0e04e0…`（machine-id `208c9ebe…`）⇒ 重签 ⇒ `status: active`，max_orgs 5 / max_seats 50 / 7 modules / 至 2027-12-31 | 首次用宿主指纹签 ⇒ `LICENSE_FINGERPRINT_MISMATCH` |

**§6.2 一致性**：**FAIL `ghost_version`** —— PG active `20261012T064951Z-inc-569555ad` 在图库无镜像节点，
退出码 2「不许启动」。

## 5. 十项验收（AI 搬运；报告 `backend/reports/delivery/acceptance-20261013.json`）

**汇总：PASS 5 / SKIP 4 / FAIL 1。** ⚠️ **SKIP 不是通过** —— 它是本环境没跑到，明细里都写了补什么才能跑。

| 项 | 结论 | 读数 |
|---|---|---|
| 1 全 healthy + health 200 | PASS | 四服务 healthy、HTTP 200 |
| 2 License 生效 | PASS | `status: active`，四维度齐全 |
| 3 License 拒绝可达 | PASS | G-23 复用 `1 passed` |
| 4 上传→解析→建图 | SKIP（登记过） | 未给 `--pipeline-sample`，本批不碰真解析器 / LLM |
| 5 问答可溯源 | SKIP（登记过） | 未给 `--ask-question` |
| 6 审计留痕 | **FAIL** | 生产形态需 Bearer token，验收脚本无认证入口 ⇒ 读 `audit_log` 401（数据本身够：演练栈 `audit_log` 862 条 ≥ 7） |
| 7 跨 org 拦截 | SKIP | g9 `4 passed`、g26 `30 passed`；目标环境子项因 401 SKIP |
| 8 备份成功 | PASS | 五类齐全、SHA-256 全过 |
| 9 恢复演练 | SKIP → **本留证落库后转 PASS** | 判据只认留证真实存在 |
| 10 生产配置 | PASS | `PRIVATE_DEPLOY_ENABLED=true`；5 个密钥值在 1 份日志里均未出现 |

## 6. 发现与缺陷（AI 搬运）

1. **F-P6X-7**：`restore.py` 图库恢复只走 `docker exec`（而 `load` 要求停服），且 `--from-path` 传宿主路径、容器内不可达
   ⇒ 宿主编排 → 容器执行形态下图库恢复不可行；`backup.py` 已用 `--volumes-from` 解决同款问题，恢复侧没有 ⇒ 两侧不对称。
2. **F-P6X-8**：`install_acceptance.py` 无认证入口 ⇒ 生产形态下第 6 项必 FAIL（工具读不到，非数据不足）。
3. **§6.2 `ghost_version`**：F-P6X-1 的**历史**部分 —— 本批修复只管新版本同步，历史节点须迁移脚本补（Non-goal 6 ⇒ 本批不执行）。
4. **落点错位**：`restore.py` 的 storage / license 默认取本机 `settings` ⇒ 恢复写到了宿主而非演练栈；
   容器化独立环境的恢复须在目标环境内跑，或显式给 `--storage-root` / `--license-file`。

**诚实标注（不许略）**：
- 本次**同机**起独立栈 ⇒ **未覆盖**「换机 ⇒ License 失效、须重新签发」场景；
- 容器内 machine-id 与宿主不同（Windows 上 `/etc/machine-id` 挂载无效，指纹回落容器 MAC）；
- 第 3 / 7 项的 pytest 委派跑在**本机**测试库，**不是**演练栈。

## 7. 过程观察（**wIlliam 亲笔**）

> 2026-10-13 由 wIlliam 从 AI 提供的候选措辞中**逐条选定**（选项只含机械读数，判断归人）。

- 2026-10-13 _09_:30__ 起独立环境，四服务 healthy（见证者核对：新卷，非源环境）
- 备份（09:45–09:50）：备份第一次 FAIL：PG 漏给 `--pg-dsn`（须 BYPASSRLS 角色）、图库在线被拒；
  补上 dsn 并**停源图库**后重跑 ⇒ 五类齐全（PG 192157B ／图库 6028528B ／storage 114688000B）；
  随即 `docker start` 复原源图库，**源数据未改**。
- 恢复（09:53–09:55）：`--apply` 后 PG 已恢复；图库 load 失败（退出码 1，要求停服）⇒ 补做：
  停演练栈图库 + 一次性容器 `--volumes-from` load ⇒ 42 files ／268.3 MiB、11668 节点。
  ⚠️ storage 与 license **落点错位到宿主**（演练栈内没有），已当场记录。
- 十项验收（09:55–10:00）：**PASS 5 ／ SKIP 4 ／ FAIL 1**：第 6 项 FAIL 因生产形态要 Bearer token
  而验收脚本无认证入口（401）；`audit_log` 实测 **862 条 ≥ 7** ⇒ 判据可达。
  第 9 项此刻 SKIP（留证尚未落库）。**SKIP 不是通过**。
- 其它观察：**两处与预期不一致** —— ① 首次用**宿主**指纹签 License ⇒ `FINGERPRINT_MISMATCH`
  （容器内指纹与宿主不同，Windows 上 `/etc/machine-id` 挂载无效）；
  ② `restore.py` 的 storage / license 默认落点是本机 `settings` ⇒ 恢复写到了宿主而非演练栈。
  两处均**照实记录，未回改**。

## 8. 结论与判分（**【待填 3：wIlliam 亲笔】**）

> **AI 不代判。** 下面把"判"拆成 4 个**带机械依据的选型** —— 你**打勾**即可（勾选就是你的判断，
> 理由可补一句）；依据是 AI 搬运的，结论不是。

### 8.1 本次恢复演练是否达到「环境可复现」？

**依据**：PG ✅ 已恢复到 `graphrag` 库；图库 ✅ 补恢复 42 files / 268.3 MiB（11668 节点、176 个 `:KgVersion`）；
storage ⚠️ 解开到**宿主**而非演练栈；license ⚠️ 同样落到宿主（演练栈容器内另有 588B 的 active License）；
**§6.2 `ghost_version` FAIL ⇒ 按 ADR-0002 §3.2「不许启动」**。

> **裁决记录（2026-10-13，wIlliam）**：以下四问由 AI 提供**选项 + 建议**，**勾选由 wIlliam 拍板**。

- [ ] **A 达标**：数据已复现；落点错位属工具形态问题，另行登记
- [x] **B 部分达标** ✅ **（wIlliam 裁决）**：数据复现了，但**环境未通过启动门禁**（§6.2 不许启动）
- [ ] **C 不达标**：没恢复到目标环境（storage / license 都没进演练栈）

### 8.2 第 6 项 FAIL 归哪一类？

**依据**：演练栈 `audit_log` = **862 条**（判据要 ≥7 ⇒ **数据够、判据可达**）；失败原因是验收脚本
**无认证入口**读不到（401）⇒ **不是数据不足，是工具缺能力**。

⚠️ **口径冲突（须你裁决；AI 不改判据也不改期望值表）**：`proposal.md` §3.2 登记的是
「**主体未授权 ⇒ SKIP**」，而脚本对第 6 项判的是 **FAIL** —— **同一个 401 原因**，第 7 项判 SKIP、
第 6 项判 FAIL。按 Non-goal 1 / 9，我不改任何一边来迁就。

- [ ] **A 照实记 FAIL**：不改判据、不改环境（Non-goal 1 / 9）
- [x] **B 记 FAIL，同时把「口径与实现不一致」另立缺陷** ✅ **（wIlliam 裁决）**：第 6 项最终按哪个口径，交下一批裁决
- [ ] **C 改记为 SKIP**（按登记口径）⇒ ⚠️ 这要改判据或改期望值表，**本批不许**

### 8.3 §6.2 未过（环境不许启动）怎么处置？

**依据**：根因是 F-P6X-1 的**历史**部分 —— 历史 active 版本在图库无镜像节点；补它要执行迁移脚本，
而迁移**会写源环境** ⇒ 当前卡在 Non-goal 6。

- [x] **A 本次到此为止** ✅ **（wIlliam 裁决）**：留证照实记，历史迁移另立批（不动源环境）
- [ ] **B 授权动源环境**：修改 Non-goal 6 边界后执行 `migrate_kg_version_org.py --apply` 补齐并复验
- [ ] **C 只在演练栈内补镜像节点复验**（不动源环境，但属人工构造，须在留证写明）

### 8.4 F-P6X-7 / F-P6X-8 是否单独立批？

- [x] **A 合并进下一批** ✅ **（wIlliam 裁决）**（与历史迁移一起做）
- [ ] **B 各自单独立批**（F-P6X-7 改 `restore.py`；F-P6X-8 给验收脚本加认证入口）
- [ ] **C 只登记，暂不排期**

### 8.5 综合结论

> ✅ **2026-10-13 由 wIlliam 从 AI 提供的候选中选定并确认**（AI 拟稿、人定稿；判断归执行者）。

数据可复现（PG 已恢复到演练栈 `graphrag` 库；图库 42 files / 268.3 MiB ⇒ 11668 节点、176 个 `:KgVersion`），
但**环境未通过 §6.2 启动门禁**（`ghost_version`，ADR-0002 §3.2 不许启动），且 storage / License 恢复
**落点错位到宿主** ⇒ 判定为**部分达标**（8.1-B）：恢复链路可用；工具与历史数据各有一处缺口，
均另立批处置（8.4-A）。第 6 项 FAIL 属**工具缺认证能力**、非数据不足（8.2-B），照实记录。

### 8.6 后续处置

> ✅ **2026-10-13 由 wIlliam 从 AI 提供的候选中选定并确认**（AI 拟稿、人定稿；判断归执行者）。

1. **合并立下一批**：① F-P6X-7（`restore.py` 图库恢复在「宿主编排 → 容器执行」形态下不可行）；
   ② F-P6X-8（`install_acceptance.py` 无认证入口 ⇒ 生产形态第 6 项必 FAIL）；
   ③ 历史镜像节点迁移（补 `ghost_version`，须写源环境 ⇒ 本次不执行，8.3-A）；
2. **口径裁决（下批）**：第 6 项判据 —— 登记口径「主体未授权 ⇒ SKIP」（`proposal.md` §3.2）
   **vs** 实现「401 ⇒ FAIL」，二者不一致 ⇒ 交下批裁决；本批照实记 FAIL，不改判据、不改期望值表；
3. **不动源环境**：历史迁移会写源环境 ⇒ 本次不执行（守 Non-goal 6）；升级演练（10-14）前同样不动；
4. **n=2 第二轮**（O-3，建议 10-15 / 10-16）：待上述缺口处置后另排，两轮读数都贴（n=1 不得当上限）。
