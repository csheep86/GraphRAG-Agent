"""R30：主体锚点的**引用口径** —— 严格视图孤儿必须为 0。

**R30 原文（`docs/dev-doc-status.md` §8）**：`users` 行补上之后才看得见的残留——
① **1 条跨租户引用**（`user_roles` 在 org B，`user_id` 却指向 org A 的主体）；
② 3 条 `documents.uploaded_by` 指向随机 UUID；③ 2 条 `audit_log.actor_id`。
R30 给 P2-C 留下的判据建议原文是「把『**严格视图孤儿 = 0**』写成机械断言」——
本文件就是那条断言。

**为什么"全局视图"抓不到它**：只连 `user_roles.user_id == users.id` 的话，
org B 那条授权**连上**了 org A 的主体 ⇒ 孤儿数 0，看着完全正常。
只有把 `org_id` 也拉进来比对（`id` 与 `org_id` **都**相等）才抓得到——
而 R30 恰恰是在**没有**这条断言的情况下被手工抓到的。

**范围（不扩大，也不缩水）**：

- **本文件只管 `user_roles` ↔ `users` 这一对**（R30 第 ① 条）。
  ②③（`documents.uploaded_by` / `audit_log.actor_id` 的随机 UUID）属**演示库数据**，
  且 R30 对第 ③ 条已明写「系统触发**不编造 UUID** ⇒ 不补」⇒ 保持登记，本批不动数据。
- **租户清单是写死的**（默认租户 + `OTHER_ORG_ID`），**不**走 `list_tenant_orgs()`
  枚举——那个枚举源只覆盖有业务数据的租户，拿它当分母会在"某租户只有账号没有文档"
  时让本断言**恒绿**（纪律 R-9「恒绿即失效」）。写死 + 断言锚点行存在，才不会空转。
"""

from __future__ import annotations

from uuid import UUID

from conftest import OTHER_ORG_ACTOR_ID, OTHER_ORG_ID
from sqlalchemy import and_, func, select

from app.core.config import get_settings
from app.db.models import User, UserRole
from app.db.session import session_scope


def _tenant_pairs() -> tuple[tuple[UUID, UUID], ...]:
    """与 conftest 播种的那两个租户一一对应（`users.id` 是主键 ⇒ 每个租户各一个主体）。"""
    settings = get_settings()
    return (
        (settings.default_org_id, settings.default_actor_id),
        (UUID(OTHER_ORG_ID), OTHER_ORG_ACTOR_ID),
    )


def test_every_tenant_has_its_own_actor_anchor() -> None:
    """**防恒绿**：先证明"锚点真的存在"，再谈孤儿。

    少了这一条，下面的"孤儿 = 0"会在播种失败（或 `users` 被清空）时也照样绿——
    那正是 R-9 要防的"恒绿即失效"。
    """
    for org_id, actor_id in _tenant_pairs():
        with session_scope(org_id=org_id) as session:
            row = (
                session.query(User)
                .filter(User.org_id == org_id)
                .filter(User.id == actor_id)
                .one_or_none()
            )
            assert row is not None, (
                f"租户 {org_id} 缺少主体锚点（users.id={actor_id}）——"
                "播种失败会让下面的孤儿断言恒绿，先修这条"
            )
            assert row.org_id == org_id, (
                f"主体 {actor_id} 落在了租户 {row.org_id}，却被当成 {org_id} 的主体"
            )

    # 反向：两个租户**不得**共用同一个主体 UUID（R30 第 ① 条的根因）
    actor_ids = [actor_id for _, actor_id in _tenant_pairs()]
    assert len(set(actor_ids)) == len(actor_ids), (
        f"两个租户共用了同一个 actor_id {actor_ids}——`users.id` 是主键，"
        "共用必然意味着其中一方的授权挂在另一方的账号上"
    )


def test_user_roles_have_no_strict_orphans() -> None:
    """**R30 的正主**：严格视图（`id` 与 `org_id` 都相等）下孤儿数 = 0。

    逐租户查是**必须**的：`users` 与 `user_roles` 都是租户表，RLS 下不带 org
    的会话一行都看不到 ⇒ 不分租户就只能得到"0 个孤儿"这个无意义的答案。
    """
    for org_id, _actor_id in _tenant_pairs():
        with session_scope(org_id=org_id) as session:
            orphans = session.scalar(
                select(func.count())
                .select_from(UserRole)
                .outerjoin(
                    User,
                    and_(
                        User.id == UserRole.user_id,
                        User.org_id == UserRole.org_id,
                    ),
                )
                .where(User.id.is_(None))
            )
            granted = session.scalar(select(func.count()).select_from(UserRole))
            assert orphans == 0, (
                f"租户 {org_id} 有 {orphans}/{granted} 条授权挂在**不存在**"
                "（或不属于本租户）的主体上 —— R30 第 ① 条"
            )
            # 反向：授权也不能是空的，否则上面同样恒绿
            assert granted >= 1, (
                f"租户 {org_id} 一条授权都没有 ⇒ 上面的断言没有在验任何东西"
            )
