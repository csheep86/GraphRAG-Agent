"""存储抽象层（M1 §4.3 / CODEBUDDY.md「存储规范」）。

依据：
- `CODEBUDDY.md`「存储规范」：文件存储使用抽象层，开发用本地文件系统，生产可切 S3；
- `docs/adr/ADR-0003-tenant-isolation-rls.md` §3.5：
  存储键必须为 `{org_id}/{doc_id}/{filename_hash}`，**文件名不得以原文出现在对象键中**。

实现（v1.1.0 批次 A）：
- :class:`app.storage.local_fs.LocalFSStorage`（开发 / 测试）；
- S3 / OSS 实现属生产接入，**不做 stub**（ADR-0004 §3 第 2 条）。
"""

from __future__ import annotations

from uuid import UUID

from app.storage.base import StorageBackend, StorageKeyError
from app.storage.local_fs import LocalFSStorage


def build_storage_key(*, org_id: UUID, doc_id: UUID, filename_hash: str) -> str:
    """构造符合 ADR-0003 §3.5 的对象存储键。"""
    return f"{org_id}/{doc_id}/{filename_hash}"


def build_parse_artifact_key(*, org_id: UUID, doc_id: UUID, filename: str) -> str:
    """解析产物键：`{org_id}/{doc_id}/parse/{filename}`（同前缀族，继承租户隔离）。"""
    return f"{org_id}/{doc_id}/parse/{filename}"


def build_extract_artifact_key(*, org_id: UUID, doc_id: UUID, filename: str) -> str:
    """抽取产物键：`{org_id}/{doc_id}/extract/{filename}`（与 parse 同族，券商隔离段前缀）。"""
    return f"{org_id}/{doc_id}/extract/{filename}"


def build_kg_artifact_key(*, org_id: UUID, doc_id: UUID, filename: str) -> str:
    """KG 中间产物键：`{org_id}/{doc_id}/kg/{filename}`（stage-1/2/3 三段输入暂存）。

    **不进契约**——仅 ``kg.build`` 执行体内部存读，不暴露给前端。
    """
    return f"{org_id}/{doc_id}/kg/{filename}"


def get_storage() -> StorageBackend:
    """按配置返回存储后端（v1.1.0 仅本地 FS；生产实现随部署阶段接入）。

    不缓存实例：settings 可被测试 monkeypatch，工厂须即时反映。
    """
    from app.core.config import get_settings

    return LocalFSStorage(get_settings().storage_root)


__all__ = [
    "StorageBackend",
    "StorageKeyError",
    "LocalFSStorage",
    "build_storage_key",
    "build_parse_artifact_key",
    "build_extract_artifact_key",
    "build_kg_artifact_key",
    "get_storage",
]
