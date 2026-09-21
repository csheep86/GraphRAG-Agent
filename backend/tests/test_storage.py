"""存储抽象层测试（Sprint 5 批次 A / M1 §4.3 验收 6）。

覆盖：
1. ``LocalFSStorage`` put/get/delete/exists/size 基础读写；
2. ``get`` 的 org 前缀越权拦截（ADR-0003 §3.5）；
3. 路径注入防护（``..`` / 绝对路径 / 反斜杠 / 盘符）；
4. ``build_storage_key`` 键格式（文件名原文不出现在键中）。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.storage import (
    StorageKeyError,
    build_parse_artifact_key,
    build_storage_key,
    get_storage,
)
from app.storage.local_fs import LocalFSStorage, validate_key

ORG_A = uuid4()
ORG_B = uuid4()
DOC_A = uuid4()


@pytest.fixture
def storage(tmp_path: Path) -> LocalFSStorage:
    return LocalFSStorage(tmp_path)


def test_build_storage_key_hides_filename() -> None:
    """键 = {org}/{doc}/{sha256}，文件名原文与扩展名均不出现（ADR-0003 §3.5）。"""
    key = build_storage_key(org_id=ORG_A, doc_id=DOC_A, filename_hash="a" * 64)
    assert key == f"{ORG_A}/{DOC_A}/" + "a" * 64
    assert ".pdf" not in key


def test_put_get_roundtrip(storage: LocalFSStorage) -> None:
    key = build_storage_key(org_id=ORG_A, doc_id=DOC_A, filename_hash="b" * 64)

    returned = storage.put(key, b"%PDF-1.4 bytes")
    assert returned == key
    assert storage.exists(key) is True
    assert storage.get(key, org_id=ORG_A) == b"%PDF-1.4 bytes"
    assert storage.size(key) == len(b"%PDF-1.4 bytes")


def test_get_rejects_cross_org_prefix(storage: LocalFSStorage) -> None:
    """跨租户键前缀必须抛 StorageKeyError，而非返回内容（越权防线）。"""
    key = build_storage_key(org_id=ORG_A, doc_id=DOC_A, filename_hash="c" * 64)
    storage.put(key, b"secret")

    with pytest.raises(StorageKeyError):
        storage.get(key, org_id=ORG_B)


@pytest.mark.parametrize(
    "bad_key",
    [
        "../escape",
        f"{ORG_A}/../..",
        "/abs/path",
        f"{ORG_A}\\{DOC_A}",
        f"{ORG_A}/{DOC_A}/C:/win",
        "",
        f"{ORG_A}//double",
    ],
)
def test_validate_key_rejects_injection(bad_key: str) -> None:
    with pytest.raises(StorageKeyError):
        validate_key(bad_key)


def test_put_rejects_traversal_key(storage: LocalFSStorage) -> None:
    with pytest.raises(StorageKeyError):
        storage.put("../evil", b"x")


def test_get_missing_raises(storage: LocalFSStorage) -> None:
    with pytest.raises(StorageKeyError):
        storage.get(f"{ORG_A}/{DOC_A}/" + "d" * 64, org_id=ORG_A)


def test_delete_is_idempotent(storage: LocalFSStorage) -> None:
    key = f"{ORG_A}/{DOC_A}/" + "e" * 64
    storage.put(key, b"x")
    storage.delete(key)
    storage.delete(key)  # 幂等
    assert storage.exists(key) is False


def test_parse_artifact_key_inherits_org_prefix() -> None:
    """解析产物键与源文件同前缀族，get(org_id) 校验同样生效。"""
    key = build_parse_artifact_key(org_id=ORG_A, doc_id=DOC_A, filename="full.md")
    assert key == f"{ORG_A}/{DOC_A}/parse/full.md"


def test_get_storage_reflects_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """工厂不缓存：monkeypatch settings.storage_root 后即时生效。"""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_root", tmp_path)
    backend = get_storage()
    key = f"{ORG_A}/{DOC_A}/" + "f" * 64
    backend.put(key, b"data")
    assert (tmp_path / key).is_file()
