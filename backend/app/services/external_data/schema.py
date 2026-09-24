"""外部数据导入文件 schema（接缝 8；ADR-0004 §2.1）。

只定义**文件形态**：

- JSON：对象数组，每个对象是一条 :class:`ImportRecord`；
- CSV：表头含 ``object_type`` / ``local_id`` / ``external_system`` / ``external_id``
  （顺序不限，缺失列直接报错）。

两条诚实性纪律：

1. **逐条报告失败**：CSV 第 7 行少一列，就报「第 7 行少一列」，**不**默默跳过也不整体失败
   ——导入是企业数据接入的第一步，错在这一步不被看见，后面全是脏数据；
2. **不做值猜测**：``local_id`` / ``external_id`` 一律按字符串收，外部 ID 未必是 UUID，
   强行转 UUID 就是编数据。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

#: 必需列（与 ADR-0004 §4 的 `external_refs` 业务字段逐字对应）
REQUIRED_COLUMNS: tuple[str, ...] = (
    "object_type",
    "local_id",
    "external_system",
    "external_id",
)
#: 合法对象类型（ADR-0004 §4）
_OBJECT_TYPES = frozenset({"entity", "document", "org"})


@dataclass(frozen=True, slots=True)
class ImportRecord:
    """一条外部 ID 映射记录。"""

    object_type: str
    local_id: str
    external_system: str
    external_id: str

    def validate(self) -> str | None:
        """返回第一条错误信息；合法返回 ``None``。"""
        if self.object_type not in _OBJECT_TYPES:
            return f"object_type 非法: {self.object_type!r}（应为 {sorted(_OBJECT_TYPES)}）"
        for name in ("local_id", "external_system", "external_id"):
            if not getattr(self, name).strip():
                return f"{name} 为空"
        return None


@dataclass(slots=True)
class LoadResult:
    """导入文件的加载结果（**不**抹掉坏行：留着给调用方看）。"""

    records: list[ImportRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _from_row(raw: dict[str, object], *, where: str) -> ImportRecord | str:
    """一行 → :class:`ImportRecord`；缺列返回错误字符串。"""
    missing = [
        name for name in REQUIRED_COLUMNS if not str(raw.get(name) or "").strip()
    ]
    if missing:
        return f"{where} 缺少必需列: {', '.join(missing)}"

    record = ImportRecord(
        object_type=str(raw.get("object_type") or "").strip(),
        local_id=str(raw.get("local_id") or "").strip(),
        external_system=str(raw.get("external_system") or "").strip(),
        external_id=str(raw.get("external_id") or "").strip(),
    )
    problem = record.validate()
    if problem is not None:
        return f"{where} {problem}"
    return record


def load_file(path: str | Path, *, fmt: str = "auto") -> LoadResult:
    """读 JSON / CSV 导入文件。

    :param fmt: ``json`` / ``csv`` / ``auto``（按扩展名判断）。
    :returns: :class:`LoadResult`——**坏行进 ``errors``，异常不上抛**（调用方 decide 怎么处理）。
    """
    file_path = Path(path)
    if fmt == "auto":
        fmt = "json" if file_path.suffix.lower() == ".json" else "csv"

    result = LoadResult()
    if not file_path.exists():
        result.errors.append(f"文件不存在: {file_path}")
        return result

    if fmt == "json":
        try:
            raw_items = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            result.errors.append(f"JSON 解析失败: {exc}")
            return result
        if not isinstance(raw_items, list):
            result.errors.append("JSON 顶层必须是对象数组")
            return result
        for index, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                result.errors.append(f"第 {index} 条不是对象")
                continue
            outcome = _from_row(raw, where=f"第 {index} 条")
            if isinstance(outcome, str):
                result.errors.append(outcome)
            else:
                result.records.append(outcome)
        return result

    with file_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            result.errors.append("CSV 无表头")
            return result
        missing = [name for name in REQUIRED_COLUMNS if name not in reader.fieldnames]
        if missing:
            result.errors.append(f"CSV 表头缺少必需列: {', '.join(missing)}")
            return result
        for line_no, raw in enumerate(reader, start=2):  # +2：跳过表头行
            outcome = _from_row(raw, where=f"第 {line_no} 行")
            if isinstance(outcome, str):
                result.errors.append(outcome)
            else:
                result.records.append(outcome)
    return result


__all__ = [
    "REQUIRED_COLUMNS",
    "ImportRecord",
    "LoadResult",
    "load_file",
]
