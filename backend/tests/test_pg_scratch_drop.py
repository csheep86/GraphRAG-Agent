"""P6-V6：``tests/pg_scratch.py::drop_database()`` 的**正向 + 反向**守卫。

为什么单开一个文件：本批修的是「删库失败会被静默略过」这条最危险的路。
只验「正常情况下删得掉」是不够的——**它在修之前也是绿的**；真正要钉住的是
**删不掉时必须响**（纪律 **R-9「恒绿即失效」**）。

反向守卫怎么造（P6-V6 §9「可控复现法」的确定性版本）：
CI 那次撞的是一行 ``autovacuum worker``（以 bootstrap superuser 身份挂在库上，
``usename`` 为 NULL）。等它自然出现既慢又不可靠 ⇒ 改用 **owner 必定杀不掉的
角色** ``app_rls`` 占住库——``app_owner`` 不是它的成员 ⇒ 同样 terminate 不动、
同样阻塞 ``DROP DATABASE``，是与 CI 同构、且**必现**的场景。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pg_scratch import (
    create_database,
    database_exists,
    database_url_for,
    drop_database,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db.rls import APP_ROLE

#: 与 ``scratch_database`` 同款命名（一次性随机名 ⇒ 不会撞上别人的库）
_PREFIX = "graphrag_drop_guard"


def _scratch_name() -> str:
    return f"{_PREFIX}_{uuid4().hex[:12]}"


def _rls_url(name: str) -> str:
    """指向同一个临时库、但走**受限角色**的连接串（owner 杀不掉它）。"""
    return (
        make_url(database_url_for(name))
        .set(username=APP_ROLE, password=APP_ROLE)
        .render_as_string(hide_password=False)
    )


def test_drop_database_kicks_own_role_connections() -> None:
    """**正向**：自己角色开的连接必须被踢掉，否则"删库"就是一句空话。

    这条同时是 P6-V6 那个过滤条件的**存活证明**：若
    ``usename = current_user`` 被写错（或将来换了 owner 角色名），
    这里会以 ``ObjectInUse`` 立刻红——而不是等到 CI 上偶发一次再猜。
    """
    name = _scratch_name()
    create_database(name)
    engine = create_engine(database_url_for(name))
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        # 归还连接池后**物理连接仍在**（idle）⇒ 库上确实还挂着一个 client backend
        drop_database(name)
        assert not database_exists(name)
    finally:
        engine.dispose()


def test_drop_database_raises_instead_of_silently_leaving_db() -> None:
    """**反向守卫**（本批最关键）：杀不掉的连接 ⇒ 必须**报错**，不许静默。

    ``app_rls`` 占着库时 owner 既 terminate 不动、也 DROP 不掉。若哪天有人把
    实现改成 ``try/except`` 吞掉，本例会**绿着通过**、把库留在那里 ⇒
    下一次跑测以「名字冲突 / 状态不干净」回来报复。所以这里断言的是
    「抛错」且「库还在」。
    """
    name = _scratch_name()
    create_database(name)
    holder = create_engine(_rls_url(name))
    connection = holder.connect()
    connection.execute(text("SELECT 1"))
    try:
        with pytest.raises(RuntimeError, match="删不掉"):
            drop_database(name)
        assert database_exists(name), "删不掉就必须还留在那里，绝不能假装删掉了"
    finally:
        connection.close()
        holder.dispose()
        drop_database(name)
    assert not database_exists(name)
