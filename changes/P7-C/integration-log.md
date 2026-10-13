# P7-C · 集成日志（B1 收口：dev 身份兜底在**非开发形态**机械不可达）

> **日期**：2026-10-13 ｜ **基线 HEAD**：`40a23c8`（P6-T 判分 86/86 收口提交）
> **边界文档**：[`proposal.md`](./proposal.md)（Non-goals **5 条**）
> **来源**：[`docs/release-readiness-audit-2026-10-13.md`](../../docs/release-readiness-audit-2026-10-13.md) §4 **B1**
> **一句话**：B1 的真相是**分叉**的——`X-Org-Id` 早就关着，`Bearer dev.*` 全程开着；本批把两条收口到同一把开关，并钉成护栏 **G-27**。

---

## 0. 结论（先给事实，全部有机器读数）

| # | 事实 | 证据 |
|---|---|---|
| 1 | **B1 成立，但只成立一半**：交付形态下 `X-Org-Id` 已不可达（`None`），而 `Bearer dev.<org>.<actor>` **原样返回 `Identity`** ⇒ 无签名即可伪造任意租户身份 | §1 探针（改前） |
| 2 | **根因不是"没删兜底"，是"判据选错了坐标"**：dev token 分支只看 `settings.is_production`，而**交付 compose 从不注入 `APP_ENV`**（`deploy/docker-compose.delivery.yml` 的 `backend.environment` 里没有它）⇒ 客户现场取默认值 `development` ⇒ `is_production=False` ⇒ 那条拦截**从头到尾没生效过** | `backend/app/core/auth.py`（改前 `:56`）、`deploy/docker-compose.delivery.yml:114-135` |
| 3 | 修复后：交付形态 dev token ⇒ **401**；生产（即使开关开着）⇒ **401**；开发形态（开关开）⇒ **照旧可用** | §1 探针（改后）+ G-27 判据 1/2/3 |
| 4 | **兜底没有删除**（Non-goal 4：上千条用例的身份来源就是它）⇒ B1 的另一半「删除兜底」**仍未做**，已登记 | §4 F-P7C-2 |

> ⚠️ 换句话说：审计 §4 B1 写的「dev 身份兜底未删除」与「可伪造任意租户身份」是**两件事**。
> 本批解决的是后者（可伪造）；前者（删除）是有意不做——它会一次性改掉全部测试的主体。

---

## 1. 探针读数（改前 / 改后，**同一条命令**）

```bash
# 交付形态 = 无 .env（_env_file=None）+ APP_ENV 未设（⇒ development）+ ALLOW_DEV_ORG_HEADER 未设
uv run python -c "from app.core.config import Settings; from app.core.auth import parse_bearer_token, identity_from_dev_headers; ..."
```

**改前（`40a23c8` + 本批改动前）**：

```
allow_dev_org_header= False   is_production= False   dev_org_header_enabled= False
DEV_TOKEN= Identity(org_id=UUID('...0001'), actor_id=UUID('...00aa'), roles=(), source='bearer_token')   # ← 伪造成功
HEADER= None                                                                                            # ← 这条早就关着
```

**改后**：

```
DEV_TOKEN= AppError UNAUTHORIZED Development token requires ALLOW_DEV_ORG_HEADER=true
HEADER= None
```

> 为什么必须自己构造 `Settings(_env_file=None, ...)` 而不能 `get_settings()`：
> `backend/.env` 里 `ALLOW_DEV_ORG_HEADER=true`、conftest 还会把 `APP_ENV=test` 写进 `os.environ`，
> 拿到的都不是客户现场那一档。这条坑直接写进了护栏用例的 `_settings()` helper 注释里。

---

## 2. 本批做了什么（3 个文件 / 47 行，见回切点 S2）

| # | 改动 | 坐标 |
|---|---|---|
| ① | 新增 `Settings.dev_identity_enabled`（**显式开关 + 非生产**，两条件同时满足）；`dev_org_header_enabled` 改为委托它 ⇒ 两条兜底共用一把开关 | `backend/app/core/config.py:414-437` |
| ② | dev token 分支补一道拦截：生产 ⇒ 原 message；非生产但开关未开 ⇒ 新 message（**两条 message 故意不同**，延续 B5「不向生产环境透露 dev 兜底存在」的口径） | `backend/app/core/auth.py:60-79` |
| ③ | 新增护栏 **G-27** 5 项（判据 1~4 + 反向守卫） | `backend/tests/test_guardrails_dev_identity.py` |
| ④ | 登记 G-27 到需求基线（护栏真源） | `docs/delivery-requirements-and-guardrails.md`（G-26 行之前） |
| ⑤ | 模块 docstring 去「Sprint 1 临时实现」的自称、回登 P7-C 结论 | `backend/app/core/auth.py:1-16` |

**没有做**（对照 proposal Non-goals 逐条）：① 没重构鉴权体系（JWT / Session / RBAC 未动）；② 没做 SSO / AD；
③ 没动 `users` 表；④ **没清 `X-Org-Id` 在 tests 里的使用**（conftest 仍 `ALLOW_DEV_ORG_HEADER=true`，开发通道完整保留）；
⑤ 没顺手清别的「Sprint N 必须移除」注释（已登记给 P7-D，见 §4 F-P7C-3）。

---

## 3. 机器读数（出口判据逐条核销）

| 判据 | 读数 | 结论 |
|---|---|---|
| 出口 1：生产 / 交付形态下 `X-Org-Id` / `Bearer dev.*` **被拒**（不是被忽略） | 交付形态 `AppError UNAUTHORIZED`；生产形态 `"not accepted in production"` | ✅ |
| 出口 2：新增护栏本地全绿 + **反向守卫**在 | `tests/test_guardrails_dev_identity.py` **5 passed**；`test_g27_dev_token_guard_still_present` 已在开工自检的「🛡 反向守卫」区列出 | ✅ |
| 出口 3：`tests/test_login_flow.py` 不降 | **5 passed / 0 failed** ⚠️ proposal 写「7 条」，实测 **5** ⇒ 文档口径过期，见 §4 F-P7C-4 | ✅（不降） |
| 出口 4：pytest 不降 + 三件套干净 | 见下 | ✅ |

```text
uv run pytest -q                         → 3 failed, 1259 passed, 46 skipped   # 3 条与本批无关，见 §4 F-P7C-5
uv run ruff check .                      → All checks passed!
uv run ruff format --check .             → 298 files already formatted
uv run python scripts/check_seams.py     → 汇总：ERROR 0 / WARN 0 / OK 12
uv run python scripts/export_openapi.py --check → [OK] contracts/openapi.yaml 与后端模型一致（零 diff）
uv run python scripts/check_startup_readiness.py → 🟢 已生效 16 条（G-27 5 项）｜🟠 部分 0｜🟡 挂起 0
```

**CI 读数**（commit `ef62188`，2026-10-13）：

| job | 结论 |
|---|---|
| 后端（ruff + pytest） | ❌ **3 failed / 1298 passed / 7 skipped** —— 三条即 F-P7C-5（CI 带图环境 ⇒ passed 比本地多 39 条）。首条断言实测 `assert 0.8333333333333334 is None`，正是"多跳已判分 ⇒ 正常出数" |
| 前端（lint + gen:api） | ✅ success |
| 契约校验（漂移门禁） | ✅ success |
| 流水线汇总 | ❌（随后端 job 失败） |

⇒ **本批改动没有让任何一个 job 变红**：前端与契约两个 job 全绿；后端 job 的红是 P6-T 判分落库留下的，
且在 HEAD `40a23c8` 上（`git stash -u` 后）复跑同样 3 failed。**修它需用户裁决**（§5）。

**G 编号 15 → 16**：`check_startup_readiness.py` 现在把 G-27 列在 🟢 区（真在拦），反向守卫单独列出。

**回切点**（`check_session_drift.py`）：S2 3 文件 / 47 行（阈值内）、S3 无新增 `Settings` 字段（只加 property，无 env 变量）、
S4 未触契约、S5 无孤儿模块 ⇒ **未发现漂移**。
⚠️ 脚本 S1 读到的是 `changes/P8-Release/proposal.md`（4 条边界）——**它认错了批次**，本批实际对照的是
`changes/P7-C/proposal.md` 的 5 条 Non-goals（上面已逐条手写核对）。

**三条自检问句（脚本拦不住）**：

1. 有没有顺便做的？⇒ 没有。唯一"多出来"的是⑤改 docstring，它属于 B1 本体（那句"临时实现"自称就是审计引的证据）。
2. 有没有绕路？⇒ 没有。**没有**用"把 `APP_ENV` 改成 production"来关兜底——那是假的安全感（交付形态根本不注入它），
   判据 1 刻意写在 `development` 下就是这个原因。
3. 判据是真跑出来的？⇒ 全是：探针两次、pytest、三件套、readiness 都是命令输出。

---

## 4. 遗留登记（**不在本批处置**）

| 编号 | 内容 | 出处 / 建议落点 |
|---|---|---|
| **F-P7C-1** ⚠️ | **交付形态仍以 `APP_ENV=development` 运行** ⇒ G-21（禁 SQLite）与 `_guard_production_jwt_secret`（禁默认 JWT 密钥）在客户现场**同样不生效**。本批只堵了"伪造身份"这一条，**没有**把交付栈改成生产模式：那会连带要求注入 `AUTH_JWT_SECRET`、改 `deploy/.env.example`、动安装文档与 `install_acceptance.py` ⇒ 属 P7-E（B4/B6 部署侧）或单开批次 | `deploy/docker-compose.delivery.yml:114`（env 无 `APP_ENV`）、`backend/app/core/config.py:403` |
| **F-P7C-2** | **dev 兜底仍未删除**（只收口到开关）。上千条用例的身份来源是它，删除属另一批 | `backend/app/core/auth.py`、`backend/tests/conftest.py:38` |
| **F-P7C-3** | 三处「Sprint 3 必须移除」过期文案仍未清：`app/api/deps.py:30-38`（会落进契约）、`contracts/openapi.yaml` 的 `X-Org-Id` description ×N、`app/core/openapi.py:29`。属 **B3（契约说谎）** ⇒ 留给 **P7-D**，本批不动（动了就要重生成契约 + `gen:api`） | 同上 |
| **F-P7C-4** | `proposal.md` 出口判据 3 写「`test_login_flow.py` **7 条**」，实测 **5 passed** ⇒ 文档口径过期，已在此登记，未改 proposal（史实保留） | `backend/tests/test_login_flow.py` |
| **F-P7C-5** 🚩 | **P6-T 后坐力：3 条既有断言在 HEAD 已红**（`test_eval_baseline_a1.py::test_multihop_without_judgement_exposes_answer_texts`、`test_evaluation_dataset.py::test_multihop_all_items_are_really_multihop`、`test_export_judging_sheets.py::test_sheets_never_carry_correct`）。**机械证明与本批无关**：`git stash -u` 后在 `40a23c8` 上复跑 ⇒ 同样 3 failed。成因 = 86 题判分落库后，这三条断言所编码的「默认全部未判分」前提失效。**需用户裁决修法**（都踩在 A3「脚本不得代判分红线」上，改守卫措辞 = 放宽红线，不得由 AI 擅自定） | 见 §5 |

---

## 5. F-P7C-5 的三条红：坐标 + 候选修法（**待裁决**）

| # | 失败断言 | 成因 | 候选修法（都不在本次动） |
|---|---|---|---|
| 1 | `test_eval_baseline_a1.py:512` `assert result.value is None` | gold 多跳集已判完 ⇒ `multihop_accuracy` **正常出数**，不再 `blocked_by=A3` | (a) 用 monkeypatch 造一份 `correct=None` 的副本，**保住"缺判分时吐原文"的原意图**（推荐，不动产品代码）；(b) 改断言承认已出数（会丢掉 D3 那条覆盖） |
| 2 | `test_evaluation_dataset.py:138` `assert all(item.correct is None)` | 同上：判分后 `correct` 不再是 `None` | 改为「要么全 `None`（未判分），要么全为 bool **且** gold 集带 `_judging.judged_by`」⇒ 反而**加强**了"非匿名判分"的要求 |
| 3 | `test_export_judging_sheets.py:108` `assert "judged_by" not in keys` | P6-T 给 `MANIFEST.json` 的 `rubric.supplements[*]` 写了 `judged_by: wIlliam`，而判分表把 rubric 元数据一起导出 ⇒ 该键出现在产物里 | (a) 守卫只扫**题行**层级、不扫 rubric 元数据（推荐）；(b) MANIFEST 里改字段名（如 `decided_by`），避开守卫；(c) 判分表不再内联 rubric 元数据 |

> 三者共同点：**都是"判分完成"这个新事实推翻了断言前提**，不是产品缺陷。
> 修它们等于改**判分红线的机器表述** ⇒ 按纪律升级用户，**不得由本批顺手改**。

---

## 6. 不许外推

- 本批**不等于**「dev 兜底已删除」——它还在，只是非开发形态不可达（F-P7C-2）。
- 本批**不等于**「客户现场跑在生产模式」——`APP_ENV` 仍是默认 `development`（F-P7C-1）。
- G-27 绿灯**不等于**端到端鉴权达标：它只验"非开发形态下两条兜底不可达"，
  RBAC / 会话 / 令牌吊销一概没验。
- 出口判据 4 里的「pytest 不降」是在**承认 3 条既有红（F-P7C-5）**的前提下说的：
  本批改动**没有新增**任何失败（已用 `git stash -u` 机械对照）。
