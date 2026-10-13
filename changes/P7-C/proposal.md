# P7-C · 收口 dev 身份兜底（B1）

> **日期**：2026-10-13 ｜ **来源**：[`docs/release-readiness-audit-2026-10-13.md`](../../docs/release-readiness-audit-2026-10-13.md) §4 B1
> **一句话**：让生产配置下**不可能**靠请求头伪造租户身份，并把这件事钉成护栏。

## 1. 起点与坐标（**逐条复核过，开工前再跑一遍命令确认行号**）

| 项 | 坐标 |
|---|---|
| dev 兜底实现 | `backend/app/core/auth.py:1,8,10-15`（文件头自称「Sprint 1 临时实现」） |
| dev 兜底开关相关 | `backend/app/core/config.py:400-406` |
| 契约里的过期声明 | `backend/app/core/openapi.py:29`、`contracts/openapi.yaml:3207,3215,3217,3225`（都写着「Sprint 3 必须移除」） |
| 已真实现的登录（本批不许破坏） | `changes/archive/2026-10-07-P2-C/proposal.md`、`backend/tests/test_login_flow.py` |
| RBAC 资源登记 | `backend/app/rbac/deps.py`（4 档） |

## 2. 做什么

1. **先判定再动手**：实测「非 dev 环境 + 不带 dev 头」时，兜底路径是否仍然可达。**这是本批的第一个交付物——一个事实结论**，不是推断。
2. 若可达 ⇒ 改为仅 `APP_ENV == development`（或既有 dev 开关）下装配，并在**生产路径上显式抛错**而非静默通过。
3. 把「生产不可达」写成**机械护栏**（反向守卫：删掉拦截就红）。
4. 清理契约与 `openapi.py` 里那批「Sprint 3 必须移除」的过期描述（属 B3 的部分**留到 P7-D**，本批只动 auth 相关）。

## 3. Non-goals（**改一条都要先回来登记理由**）

1. **不重构鉴权体系**（JWT / Session / RBAC 三粒度不在本批）。
2. **不做 SSO / AD**（DR-D9 后半，窗口在 v2.1.0）。
3. **不动 `users` 表结构**、不做账号 CRUD / MFA / 会话管理。
4. **不清 `X-Org-Id` 在测试里的使用**（既有上千条用例依赖它，改为 dev-only 即可，不要一次改 tests）。
5. **不顺手清理别的「Sprint N 必须移除」注释**——发现就登记到 `P7-D` 的坐标表，不在本批扩散。

## 4. 出口判据（每条都要能贴机器输出）

1. 生产口径（`APP_ENV=production` 或等价配置）下带 `X-Org-Id` / `Bearer dev.*` 的请求**被拒**（不是被忽略）。
2. 新增/改动的护栏用例本地 + CI 全绿；**反向守卫**（构造一个移除拦截的变体）必红。
3. `tests/test_login_flow.py` 7 条**一条不降**。
4. `pytest` 不降、`ruff check` / `ruff format --check` 干净、`check_seams.py` ERROR 0、`export_openapi.py --check` 零 diff（若动了契约则须连 `gen:api` 一起交）。

## 5. 升级用户的四种情况

1. 发现兜底路径**已被**生产开关关掉 ⇒ 停下报告，只补护栏，不改行为。
2. 发现关掉它会让大量既有测试用例失去身份来源 ⇒ 报告规模，**不擅自改 tests**。
3. 需要新增 `settings.*` 配置项 ⇒ 必须能指出读取它的代码行，否则不提交。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 自己的归因。
