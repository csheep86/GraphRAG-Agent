"""存储抽象层接口（M1 §4.3 / CODEBUDDY.md「存储规范」）。

职责边界：
- 开发环境：本地文件系统（:class:`app.storage.local_fs.LocalFSStorage`）；
- 生产环境：S3 / OSS / MinIO（实现阶段切换，**本阶段不写 stub**——
  CODEBUDDY.md 功能预留原则 / ADR-0004 §3 第 2 条）。

安全约束（ADR-0003 §3.5）：
- 存储键必须为 ``{org_id}/{doc_id}/{filename_hash}`` 前缀格式，
  **文件名不得以原文出现在对象键中**；
- ``get`` 必须校验 key 前缀与当前 ``org_id`` 一致，防止越权读取他人文件。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class StorageKeyError(ValueError):
    """非法存储键（格式不符 / 路径注入 / 前缀越权）。"""


class StorageBackend(ABC):
    """存储后端抽象（M1 §4.3 接口契约）。"""

    @abstractmethod
    def put(self, key: str, data: bytes) -> str:
        """写入 ``data`` 到 ``key``，返回实际写入的 key。"""

    @abstractmethod
    def get(self, key: str, *, org_id: UUID) -> bytes:
        """读取 ``key`` 的内容。

        **必须**校验 ``key`` 前缀与 ``org_id`` 一致（ADR-0003 §3.5 越权防线），
        不一致抛 :class:`StorageKeyError`。
        """

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除 ``key``（不存在时静默，幂等）。"""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """``key`` 是否存在。"""

    @abstractmethod
    def size(self, key: str) -> int:
        """``key`` 的字节数（不存在抛 :class:`StorageKeyError`）。"""


__all__ = ["StorageBackend", "StorageKeyError"]
