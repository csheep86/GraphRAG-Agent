# Sprint 9 —— 知识时效改造（L0/L1）+ M4 四源对齐（ADR-0005 / R14）

> 动工日：2026-09-28。`ADR-0005` 已 Accepted，`sprint-calendar` §4 把
> **CP-T1（S9 首日 schema 冻结含时态四字段）** 定成硬闸门——错过即全链路返工。

## 1. CP-T1：schema 冻结（**定义于批次 A 全部冻结，落库分批**）

冻结结论三条，**此后不得改名 / 改语义**：

| # | 冻结对象 | 定义 | 落地状态 |
|---|---|---|---|
| 1 | **关系四字段**（事实维 + 摄入维 + 血缘） | `valid_from` / `valid_to` / `created_at` / `expired_at` + `source_document_id`；`valid_to=NULL` 即仍有效 | 抽取侧（事实维）批次 A 已落；**摄入维 + 血缘落 Neo4j 关系属性＝L1，批次 B** |
| 2 | `Document.document_date` | `Date`、**可空**、不进契约；`valid_from` 的兜底源（R4 不猜值） | ✅ 批次 A 已落（ORM + 迁移 `7989c2c821da`） |
| 3 | **`relation_type → 有效期策略` 配置表** | 表名 `relation_expiry_policies`；键 `(org_id, relation_type)`；策略枚举 `single_current`（唯一当前，新事实封旧）/ `append_only`（多值并存，如"对外投资"）；`unknown` 键兜底 | **定义冻结于本文，落表＝批次 B**（与 R1–R4 仲裁同批） |

**为什么第 3 条分期而不立刻建表**：它的唯一真实消费者是 R1–R4 仲裁（批次 B）。
现在建表 ⇒ 一张**无消费者**的表，违反 ADR-0004 §3「禁止无消费者的组件」的同一原则。
CP-T1 要防的是「字段语义未定导致后期返工」，而**语义已在此冻结**，落表推后一周不影响该防线。

## 2. 批次划分

| 批次 | 内容 | 状态 |
|---|---|---|
| **A（已完成）** | L0 前两项 + CP-T1 冻结：`document_date` + `kg_extraction_v3.md`（含 `{{document_date}}` 与 `valid_from`/`valid_to`）+ 抽取侧解析 + 迁移 + 8 条测试 | ✅ 2026-09-28 |
| **B（下批，＝**CP-T2**）** | **L1 全套**：四字段落 Neo4j 关系属性 + R1–R4 仲裁 + `relation_expiry_policies` 落表并消费 + Cypher 默认过滤 `valid_to IS NULL` + as-of 查询 + **L0 第三项**「答案模板：依据截至 X 日的披露文件」+ **PoC `temporal_poc/run_track_s.py` 迁入 `backend/tests/`** + 真机复跑 n≥3 达 3/3 | ⏳ |
| C 及以后 | M4 四源对齐（R14）、多跳路径时序（L2 部分）、验收矩阵「当前 vs 过期」验收项 | ⏳ |

> **批次 B ＝ CP-T2 的判定点**（`sprint-calendar` §4：未达不得宣称 L1 完成）。
> 其中的「PoC 迁入 `backend/tests/`」是日历的强制项——只有迁进正式测试集，
> n≥3 的 3/3 才是**可持续复算**的，而不是存在临时目录里的一次性脚本。
> 上一版任务清单曾漏掉这一条，复读时发现。

## 3. 纪律

- 每次 schema 变更**必须带 Alembic 迁移**（S9.7 建立的等价性测试会把「忘写迁移」变 CI 红）；
- Prompt 只增不改：v1 / v2 文件保持零改动；
- 注释/文档不得出现无消费者的字段与配置。
