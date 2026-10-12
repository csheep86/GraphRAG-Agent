"""P6-X2：图库 ``:KgVersion`` 镜像同步（**F-P6X-1** / **F-P6X-5**）。

**为什么单独成文件**：建图（``app/tasks/registry.py``）与增量重算
（``app/services/kg/incremental.py``）**两处**完成路径都要在 PG 置 ``ready`` 之后
同步一次镜像。抽成一处才不会再犯"两处各写一遍、结果一处都没写"的错 ——
F-P6X-1 这个缺口正是这么来的（建图只写 PG，没人同步镜像 ⇒ §6.2 恒判 ``ghost_version``）。

**旁路语义（重要，别改成上抛）**：同步失败**不**推翻已经完成的建图 —— 图数据是真的，
判 failed 是造假。但它也**不静默**：§6.2 的一致性判据
（:func:`app.services.backup.evaluate_version_consistency`）会把「PG 有 active 版本、
图库没有对应节点」照出来并判 ``ghost_version`` **FAIL**，不许静默启动。
⇒ 真正的 fail-closed 关卡在 §6.2，**不在这里**。

**租户维度（F-P6X-5）**：镜像的 ``superseded`` 只在**同 org** 内生效；
``org_id`` 为 ``NULL`` 的历史节点（导入脚本直写、没带 org）**一律不动** ——
无法证明归属，写死成当前 org 是污染，supersede 掉是越权处置。
"""

from __future__ import annotations

from uuid import UUID

from loguru import logger


def sync_kg_version_mirror(*, version: str, org_id: UUID, trace_id: str) -> bool:
    """同步 **Neo4j 镜像**：本版本置 ``active``，**同 org** 的其余版本置 ``superseded``。

    :param version: PG 真源刚置为 ``ready`` 的版本号。
    :param org_id: 该版本所属租户（镜像按它隔离，见 :data:`graphs._CYPHER_SUPERSEDE_OTHER_VERSIONS`）。
    :param trace_id: 链路 ID，只用于落日志与镜像节点的 ``trace_id`` 属性。
    :returns: 是否同步成功。失败**只记日志、不抛**（见模块 docstring 的旁路语义）。
    """
    # 延迟导入：本模块同时被 tasks 与 kg 两个方向依赖，导入期不能牵上图库连接
    # （``graphs`` 被 ``agents`` 依赖，方向不能反）。
    from app.services.graphs import GraphService

    try:
        GraphService.instance().activate_kg_version(
            version=version, org_id=org_id, trace_id=trace_id
        )
    except Exception as exc:  # noqa: BLE001 - 旁路：镜像同步失败不推翻已完成的建图
        logger.bind(
            kg_version=version,
            org_id=str(org_id),
            trace_id=trace_id,
            reason=type(exc).__name__,
        ).warning("kg_version_mirror_sync_failed")
        return False
    return True


__all__ = ["sync_kg_version_mirror"]
