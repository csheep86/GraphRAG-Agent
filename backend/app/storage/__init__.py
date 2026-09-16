"""存储抽象层（Sprint 1 仅有 key 约定，无实际读写）。

依据：
- `CODEBUDDY.md`「存储规范」：文件存储使用抽象层，开发用本地文件系统，生产可切 S3；
- `docs/adr/ADR-0003-tenant-isolation-rls.md` §3.5：
  存储键必须为 `{org_id}/{doc_id}/{filename_hash}`，**文件名不得以原文出现在对象键中**。

接口（Sprint 3 实现）：
- `Storage.put(key, stream) -> None`
- `Storage.open(key) -> BinaryIO`
- `Storage.delete(key) -> None`
"""

from __future__ import annotations

from uuid import UUID


def build_storage_key(*, org_id: UUID, doc_id: UUID, filename_hash: str) -> str:
    """构造符合 ADR-0003 §3.5 的对象存储键。"""
    return f"{org_id}/{doc_id}/{filename_hash}"


__all__ = ["build_storage_key"]
