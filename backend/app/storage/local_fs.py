"""本地文件系统存储实现（开发 / 测试环境，M1 §4.3）。

布局：``{storage_root}/{org_id}/{doc_id}/...``，与对象存储键一一对应，
生产切换 S3 时仅需替换实现类，不改调用方。
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from app.storage.base import StorageBackend, StorageKeyError

#: 合法 key：纯 ASCII 的 uuid / sha256 十六进制段与少量安全文件名段，
#: 以斜杠分隔。显式拒绝 `..`、反斜杠、盘符、绝对路径（路径注入防护）。
_KEY_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_FORBIDDEN_SUBSTRINGS = ("..", "\\", ":")


def validate_key(key: str) -> None:
    """校验存储键格式；非法即抛 :class:`StorageKeyError`。"""
    if not key or key.startswith("/") or key.endswith("/"):
        raise StorageKeyError(f"非法存储键（空段 / 绝对路径）: {key!r}")
    for part in key.split("/"):
        if not part or not _KEY_SEGMENT_RE.match(part):
            raise StorageKeyError(f"非法存储键段: {part!r} (key={key!r})")
    low = key.lower()
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        if forbidden in low:
            raise StorageKeyError(f"存储键含禁止串 {forbidden!r}: {key!r}")


class LocalFSStorage(StorageBackend):
    """本地文件系统后端（开发档）。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _resolve(self, key: str) -> Path:
        validate_key(key)
        path = (self._root / key).resolve()
        root = self._root.resolve()
        if not path.is_relative_to(root):
            raise StorageKeyError(f"存储键越出根目录: {key!r}")
        return path

    def put(self, key: str, data: bytes) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str, *, org_id: UUID) -> bytes:
        if not key.startswith(f"{org_id}/"):
            raise StorageKeyError(
                "存储键前缀与 org_id 不符（越权读取拦截，ADR-0003 §3.5）"
            )
        path = self._resolve(key)
        if not path.is_file():
            raise StorageKeyError(f"对象不存在: {key!r}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def size(self, key: str) -> int:
        path = self._resolve(key)
        if not path.is_file():
            raise StorageKeyError(f"对象不存在: {key!r}")
        return path.stat().st_size


__all__ = ["LocalFSStorage", "validate_key"]
