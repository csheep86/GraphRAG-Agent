"""处理管线阶段解析（接缝 4，Sprint 5 批次 A2）。

``settings.pipeline_stages`` 是管线**启停与顺序**的唯一真源：
- 顺序即执行顺序（默认 parse → extract → kg.build → risk.detect）；
- 删除某项 = 停用该阶段；
- 未在 :data:`app.tasks.registry.EXECUTOR_REGISTRY` 登记执行体的阶段自动跳过
  （批次 B 登记 ``document.extract`` / ``kg.build``、Sprint 7 登记
  ``risk.detect`` 后即自动生效，无需改本模块）。
"""

from __future__ import annotations

from app.core.config import get_settings
from app.tasks.registry import EXECUTOR_REGISTRY

#: 默认四阶段（与 Settings.pipeline_stages 默认值一致；测试断言用）
DEFAULT_STAGES: tuple[str, ...] = (
    "document.parse",
    "document.extract",
    "kg.build",
    "risk.detect",
)


def resolve_pipeline_stages() -> list[str]:
    """按配置顺序返回「已启用且有执行体」的阶段列表。

    ``settings.pipeline_stages`` 的**唯一消费点**（check_seams 判据 2）。
    """
    settings = get_settings()
    return [stage for stage in settings.pipeline_stages if stage in EXECUTOR_REGISTRY]


def first_pipeline_stage() -> str | None:
    """上传链路的入口阶段（管线第一个已启用阶段）；全停用时返回 None。"""
    stages = resolve_pipeline_stages()
    return stages[0] if stages else None


__all__ = ["DEFAULT_STAGES", "resolve_pipeline_stages", "first_pipeline_stage"]
