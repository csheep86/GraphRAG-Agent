"""接缝 8「外部数据导入」的收口目录（ADR-0004 §2.1，Sprint 7.2 批次 B）。

内网无法实时调工商 / 涉诉 API，数据形态是**离线文件包**（ADR-0004 §2.1 注），
所以本接缝的形式是「定义导入文件 schema + 手工导入 CLI」，**不是**拉取器。

范围纪律（plan §6.2 批次 B）：

- **不建表**：外部数据落地到接缝 7 的 ``external_refs`` 映射表，不为某个数据源单建表；
- **不做真实对接**：没有 HTTP 客户端、没有调度、没有增量同步；
- **不是框架**：只有一种文件形态（JSON 数组 / CSV），一个 CLI 入口。
"""

from app.services.external_data.schema import (
    REQUIRED_COLUMNS,
    ImportRecord,
    LoadResult,
    load_file,
)

__all__ = [
    "REQUIRED_COLUMNS",
    "ImportRecord",
    "LoadResult",
    "load_file",
]
