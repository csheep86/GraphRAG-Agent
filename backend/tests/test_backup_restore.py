"""P6-W（**W-a**）：备份清单 / §6.2 一致性的判据。

分四组，**每组最要紧的都是"反例"，不是正例**：

1. **清单自校验**（第 8 项核心）：正的 CASE 一个也不能少，但真正的判据是
   「改一个字节 ⇒ 必须红」「删一个文件 ⇒ 必须红」「清单里记 skipped ⇒ 不许算完整」。
   只测"文件存在"的实现会在这里全部红掉（**R-9 恒绿失效**的第一种形态）。
2. **`restore` 的 Storage / License 还原**：真打包、真解开、逐字节比对。
3. **§6.2 判定逻辑**：四个分支逐一钉死（含「图库连不上 ⇒ 判失败，不许静默」）。
4. **真图探针**（`GRAPH_REAL_NEO4J_*`）：验极薄的那层适配层**真的会去问图库**
   ——CI 上缺失即 fail（与 `tests/test_guardrails_graph.py` 同款口径）。

**刻意不做的**：不去写业务数据到真 Neo4j（只读），不去连 S3，不碰调度 / 加密（Non-goals 1 / 2）。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tarfile
from pathlib import Path

import pytest

from app.services.backup import (
    CODE_CONSISTENT,
    CODE_GHOST_VERSION,
    CODE_GRAPH_UNREACHABLE,
    CODE_NO_ACTIVE_VERSION,
    FILE_OBJECT_NAMES,
    KG_RECORDED,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA_VERSION,
    STATUS_SKIPPED,
    ActiveKgVersion,
    BackupManifest,
    ObjectEntry,
    evaluate_manifest_vs_pg,
    evaluate_version_consistency,
    file_entry,
    missing_file_objects,
    redact_env_text,
    sha256_of,
    skipped_entry,
    split_pg_dsn,
    verify_manifest,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]

_REAL_URI_ENV = "GRAPH_REAL_NEO4J_URI"
_REAL_USER_ENV = "GRAPH_REAL_NEO4J_USER"
_REAL_PASSWORD_ENV = "GRAPH_REAL_NEO4J_PASSWORD"


def _real_graph_env() -> tuple[str, str, str]:
    """与 `tests/test_guardrails_graph.py::_\real_graph_env` 同款：**CI 上缺失即 fail**。"""
    uri = os.environ.get(_REAL_URI_ENV, "").strip()
    user = os.environ.get(_REAL_USER_ENV, "").strip() or "neo4j"
    password = os.environ.get(_REAL_PASSWORD_ENV, "").strip()
    missing = "未设 GRAPH_REAL_NEO4J_URI / GRAPH_REAL_NEO4J_PASSWORD"
    if not uri or not password:
        if os.environ.get("CI"):
            pytest.fail(
                f"{missing} ⇒ CI 上 §6.2 的真图交叉校验跑不了，"
                "这是**门禁失效**不是环境问题"
            )
        pytest.skip(f"{missing}（本地未设 ⇒ 跳过；CI 上为 fail）")
    return uri, user, password


# --------------------------------------------------------------------------- #
# 夹具：造一套**真实文件**构成的备份集
# --------------------------------------------------------------------------- #


@pytest.fixture
def seed_dir(tmp_path: Path) -> Path:
    """模拟 `settings.storage_root` 的一棵文件树。"""
    root = tmp_path / "storage"
    (root / "org-a" / "doc-1").mkdir(parents=True)
    (root / "org-a" / "doc-1" / "raw.pdf").write_bytes(b"%PDF-1.7 fake")
    (root / "org-a" / "doc-1" / "chunks.json").write_text(
        '{"chunks": [{"id": "c1"}]}', encoding="utf-8"
    )
    (root / "org-b").mkdir()
    (root / "org-b" / "note.txt").write_text("另一租户的原件", encoding="utf-8")
    return root


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / "deploy.env"
    path.write_text(
        "# 现场 .env（构造用）\n"
        "APP_ENV=production\n"
        "DATABASE_URL=postgresql+psycopg://app_rls:super-secret-pw@db:5432/graphrag\n"
        "NEO4J_PASSWORD=another-super-secret\n"
        "PRIVATE_DEPLOY_ENABLED=true\n"
        "MASK_SALT=plain-salt-value\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def license_file(tmp_path: Path) -> Path:
    path = tmp_path / "app.lic"
    path.write_text("-----BEGIN LICENSE-----\nfake-body\n", encoding="utf-8")
    return path


@pytest.fixture
def backup_set(tmp_path: Path, seed_dir: Path, env_file: Path, license_file: Path):
    """一套**五类齐全**的真实备份集（Present 齐全 ⇒ 才有资格谈"校验通过"）。

    Storage / License / Config 三类用的是**产品自己的采集器**（`collect_*`），
    哈希全是真算的；PG / Neo4j 两类依赖外部工具（pg_dump / neo4j-admin），
    在 CI 与多数开发机上都没有 ⇒ 这里用两个**真文件**占位，**只**为了让
    "完整备份集"成立。**它们缺工具时的真实默认行为**由
    `test_run_backup_marks_missing_pg_dsn_as_skipped` 覆盖（那条验的是 skipped + 原因）。
    """
    module = _load("backup", BACKEND_ROOT / "scripts" / "backup.py")
    out_dir = tmp_path / "backupset"
    out_dir.mkdir(parents=True)

    entries = [
        file_entry(
            name="postgres",
            path=_touch(out_dir / "postgres.dump", b"pgdump-bytes"),
            base_dir=out_dir,
            method="pg_dump -Fc",
        ),
        file_entry(
            name="neo4j",
            path=_touch(out_dir / "neo4j.dump", b"neo4j-bytes"),
            base_dir=out_dir,
            method="neo4j-admin database dump",
        ),
        module.collect_storage(out_dir=out_dir, storage_root=seed_dir),
        module.collect_license(out_dir=out_dir, license_file=license_file),
        module.collect_config(out_dir=out_dir, env_file=env_file),
    ]
    manifest = BackupManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        generated_at=_utc_now(),
        app_version="1.6.0",
        objects=tuple(entries),
        active_kg_version=ActiveKgVersion(
            status=KG_RECORDED,
            source="pg:kg_versions",
            version="v-p6w-1",
            pg_status="ready",
            ready_at=_utc_now(),
        ),
    )
    manifest.write(out_dir)
    return module, out_dir, manifest, verify_manifest(out_dir)


def _touch(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def _utc_now() -> str:
    from app.services.backup import utc_now_iso

    return utc_now_iso()


def _fake_record(*, version: str, status: str):
    """给 `collect_active_kg_version` 注入用的一条 record（只为两个字段）。

    探针的输入形状不该成为被测对象；本文件对 PG 侧另有真库用例在外面覆盖。
    """
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.services.kg.versioning import KgVersionRecord

    return KgVersionRecord(
        id=uuid4(),
        org_id=uuid4(),
        version=version,
        status=status,
        source_doc_ids=(),
        entity_count=3,
        relation_count=2,
        error_code=None,
        error_detail=None,
        ready_at=datetime.now(UTC),
        trace_id=uuid4(),
    )


def _load(name: str, path: Path):
    """按需加载 CLI 脚本（``scripts/`` 不是包，与既有做法一致）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# 1. 清单自校验（第 8 项）
# --------------------------------------------------------------------------- #


def test_manifest_records_six_objects_and_active_version(backup_set) -> None:
    """§6.1 六类齐全：五类文件 + 清单里的 active `kg_version`。

    `postgres` / `neo4j` 在无外部工具的机器上会被 `skipped`，那不是本条要判的
    （另有专门用例）；本条钉的是**清单结构**该有的都在。
    """
    _module, out_dir, manifest, _verification = backup_set

    assert (out_dir / MANIFEST_FILENAME).is_file()  # 清单确实落盘了（不只是返回对象）

    rendered = {item.name: item for item in manifest.objects}
    assert set(rendered) == set(FILE_OBJECT_NAMES)
    assert missing_file_objects(manifest) == ()

    for name in ("storage", "license", "config"):
        entry = rendered[name]
        assert entry.status == "present", f"{name} 应当是 present"
        assert entry.sha256 and len(entry.sha256) == 64
        assert entry.size and entry.size > 0
        assert entry.collected_at

    active = manifest.active_kg_version
    assert active.status == KG_RECORDED
    assert active.version == "v-p6w-1"
    assert active.pg_status == "ready"
    assert active.source == "pg:kg_versions"


def test_verify_passes_on_a_pristine_backup_set(backup_set) -> None:
    _module, out_dir, _manifest, verification = backup_set
    assert verify_manifest(out_dir).ok is True
    assert verification.failures == ()


def test_verify_detects_a_single_flipped_byte(backup_set) -> None:
    """**本批最要紧的一条**：清单写着原哈希，实际文件被改一个字节 ⇒ 必须判失败。

    只看"文件在不在"的实现在这里会绿，而它恰恰是 §10 第 8 项要拦的事。
    """
    _module, out_dir, manifest, _verification = backup_set
    target = next(i for i in manifest.objects if i.name == "license")
    path = out_dir / str(target.path)
    original = path.read_bytes()
    path.write_bytes(original + b"\x00")  # 追加一个字节：文件仍在、哈希已变

    failures = verify_manifest(out_dir).failures
    assert len(failures) == 1
    assert "SHA-256 不符" in failures[0]
    assert "license" in failures[0]


def test_verify_detects_a_deleted_backup_file(backup_set) -> None:
    _module, out_dir, manifest, _verification = backup_set
    target = next(i for i in manifest.objects if i.name == "storage")
    (out_dir / str(target.path)).unlink()

    verification = verify_manifest(out_dir)
    assert verification.ok is False
    assert any("文件不存在" in item for item in verification.failures)


def test_verify_treats_skipped_object_as_incomplete(tmp_path: Path) -> None:
    """清单里写着 `skipped` ⇒ **不许判完整**（§6.1「缺一不可复现」）。"""
    out_dir = tmp_path / "set"
    out_dir.mkdir()
    payload = out_dir / "pg.dump"
    payload.write_bytes(b"x" * 16)
    manifest = BackupManifest(
        schema_version="1.0",
        generated_at="2026-10-10T00:00:00+00:00",
        app_version="1.6.0",
        objects=(
            file_entry(
                name="postgres", path=payload, base_dir=out_dir, method="pg_dump"
            ),
            *[
                skipped_entry(name=name, reason="本机没有该工具")
                for name in ("neo4j", "storage", "license", "config")
            ],
        ),
        active_kg_version=ActiveKgVersion(
            status="recorded", source="pg:kg_versions", version="v-x"
        ),
    )
    manifest.write(out_dir)

    verification = verify_manifest(out_dir)
    assert verification.ok is False
    assert sum(1 for item in verification.failures if "备份集不完整" in item) == 4


def test_verify_on_a_directory_without_manifest(tmp_path: Path) -> None:
    """备份目录里没有清单 ⇒ 明确报错，不许被读成"这份备份没问题"。"""
    verification = verify_manifest(tmp_path)
    assert verification.ok is False
    assert verification.failures and MANIFEST_FILENAME in verification.failures[0]


def test_verify_rejects_incomplete_manifest_entry(tmp_path: Path) -> None:
    """`present` 却没写 sha256 ⇒ 清单本身不全，判失败（不许默认放行）。"""
    out_dir = tmp_path / "set"
    out_dir.mkdir()
    target = out_dir / "pg.dump"
    target.write_bytes(b"payload")
    (out_dir / MANIFEST_FILENAME).write_text(
        '{"schema_version": "1.0", "generated_at": "x", "app_version": "1.6.0",'
        ' "objects": [{"name": "postgres", "status": "present", "path": "pg.dump"}],'
        ' "active_kg_version": {"status": "recorded", "source": "pg", "version": "v"}}',
        encoding="utf-8",
    )
    verification = verify_manifest(out_dir)
    assert verification.ok is False
    assert any("缺 path/sha256/size" in item for item in verification.failures)


# --------------------------------------------------------------------------- #
# 2. restore：Storage / License 的真实还原
# --------------------------------------------------------------------------- #


def test_storage_archive_roundtrip_is_byte_identical(
    tmp_path: Path, seed_dir: Path
) -> None:
    """真打包 → 真解开 → 逐字节比对（这条链路不依赖任何外部命令 ⇒ CI 必过）。"""
    module = _load("backup", BACKEND_ROOT / "scripts" / "backup.py")
    restore = _load("restore", BACKEND_ROOT / "scripts" / "restore.py")

    out_dir = tmp_path / "set"
    out_dir.mkdir()
    entry = module.collect_storage(out_dir=out_dir, storage_root=seed_dir)

    target = tmp_path / "restored"
    _top, count = restore.extract_storage_archive(out_dir / str(entry.path), target)
    assert count > 0

    for source in sorted(seed_dir.rglob("*")):
        if source.is_dir():
            continue
        mirrored = target / source.relative_to(seed_dir)
        assert mirrored.is_file(), f"还原后少了 {mirrored}"
        assert mirrored.read_bytes() == source.read_bytes()


def test_restore_storage_rejects_path_traversal(tmp_path: Path) -> None:
    """**安全底线**：tar 是不可信输入；带 `../` 的成员不许穿出去。

    Python 3.11 的 `extractall` 没有 `filter="data"` ⇒ 这条由脚本自己保证，
    而本用例是保证真的在拦（把它删了这句 equate 会红）。
    """
    restore = _load("restore", BACKEND_ROOT / "scripts" / "restore.py")
    archive = tmp_path / "evil.tar"
    with tarfile.open(archive, "w") as handle:
        payload = tmp_path / "evil.txt"
        payload.write_text("pwned", encoding="utf-8")
        handle.add(payload, arcname="storage/../../evil.txt")

    with pytest.raises(restore.RestoreTarError, match="越界"):
        restore.extract_storage_archive(archive, tmp_path / "target")


def test_restore_license_writes_the_file_back(
    tmp_path: Path, license_file: Path
) -> None:
    restore = _load("restore", BACKEND_ROOT / "scripts" / "restore.py")
    out_dir = tmp_path / "set"
    out_dir.mkdir()
    source = out_dir / "license.lic"
    source.write_text(license_file.read_text(encoding="utf-8"), encoding="utf-8")

    target_root = tmp_path / "deploy" / "license"
    entry = ObjectEntry(
        name="license", status="present", path="license.lic", sha256="x", size=1
    )
    name, message = restore.restore_license(
        backup_dir=out_dir, entry=entry, target_path=target_root / "app.lic"
    )
    assert name == "license"
    assert "已恢复" in message
    assert (target_root / "app.lic").read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )


def test_restore_cli_refuses_to_touch_data_when_manifest_is_broken(
    tmp_path: Path, seed_dir: Path
) -> None:
    """**清单不过 ⇒ 一步都不恢复**（退出码 1），且校验报告出现在 stdout 上。"""
    import subprocess

    out_dir = tmp_path / "set"
    out_dir.mkdir()
    target_root = tmp_path / "must-not-change"
    target_root.mkdir()

    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        [
            sys.executable,
            str(BACKEND_ROOT / "scripts" / "restore.py"),
            "--backup-dir",
            str(out_dir),
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 1
    assert "拒绝恢复" in proc.stdout
    assert list(target_root.iterdir()) == []  # 真的什么都没动


# --------------------------------------------------------------------------- #
# 3. §6.2 判定逻辑（四个分支逐一定死）
# --------------------------------------------------------------------------- #


def test_consistency_ok_when_version_node_exists() -> None:
    result = evaluate_version_consistency(
        active_version="v-1", neo4j_version_exists=lambda _version: True
    )
    assert (result.code, result.ok) == (CODE_CONSISTENT, True)


def test_consistency_fails_on_ghost_version() -> None:
    """PG 有 active 版本、图库里没有 ⇒ **幽灵版本，必须报错**（ADR-0002 §3.2）。"""
    result = evaluate_version_consistency(
        active_version="v-ghost", neo4j_version_exists=lambda _version: False
    )
    assert (result.code, result.ok) == (CODE_GHOST_VERSION, False)
    assert "不许静默启动" in result.message


def test_consistency_fails_when_graph_is_unreachable() -> None:
    """图库连不上 ⇒ **判失败**（不是判成"没得错位"那条通过分支）。

    把它判成通过的话，客户现场图库一挂，restore 会照样放行一个错版本的系统。
    """

    def _boom(_version: str) -> bool:
        raise RuntimeError("connection refused")

    result = evaluate_version_consistency(
        active_version="v-1", neo4j_version_exists=_boom
    )
    assert (result.code, result.ok) == (CODE_GRAPH_UNREACHABLE, False)


def test_consistency_without_active_version_says_it_did_nothing() -> None:
    """无 active 版本 ⇒ 通过，但 message 必须写明**什么都没验证**（不许被读成已验证）。"""
    result = evaluate_version_consistency(
        active_version=None, neo4j_version_exists=lambda _version: True
    )
    assert (result.code, result.ok) == (CODE_NO_ACTIVE_VERSION, True)
    assert "未做任何一致性验证" in result.message


def test_manifest_vs_pg_detects_version_drift() -> None:
    ok = evaluate_manifest_vs_pg(manifest_version="v-a", active_version="v-a")
    assert ok.ok is True

    drift = evaluate_manifest_vs_pg(manifest_version="v-a", active_version="v-b")
    assert drift.ok is False
    assert "版本错位" in drift.message


# --------------------------------------------------------------------------- #
# 4. 纯工具：脱敏 / 连接串切分 / 哈希
# --------------------------------------------------------------------------- #


def test_env_redaction_masks_secret_keys_only(env_file: Path) -> None:
    text, keys = redact_env_text(env_file.read_text(encoding="utf-8"))
    assert set(keys) == {"DATABASE_URL", "NEO4J_PASSWORD", "MASK_SALT"}
    assert "super-secret-pw" not in text
    assert "another-super-secret" not in text
    assert "plain-salt-value" not in text
    # 连接串**只遮口令** ⇒ 主机 / 库名留着，恢复时还有得看
    assert (
        "DATABASE_URL=postgresql+psycopg://app_rls:<redacted>@db:5432/graphrag" in text
    )
    # 非密钥项**照原样**留下（脱敏器只认登记表/key 名，不许顺手全掩）
    assert "APP_ENV=production" in text
    assert "PRIVATE_DEPLOY_ENABLED=true" in text


def test_run_backup_marks_missing_pg_dsn_as_skipped(
    tmp_path: Path, seed_dir: Path, env_file: Path, license_file: Path
) -> None:
    """没给备份库连接串 ⇒ `postgres` 必须落成 `skipped + 原因`，不许假装成功。"""
    module = _load("backup", BACKEND_ROOT / "scripts" / "backup.py")
    out_dir = tmp_path / "set"
    manifest, _verification = module.run_backup(
        out_dir=out_dir,
        env_file=env_file,
        license_file=license_file,
        storage_root=seed_dir,
        active_probe=lambda: None,
    )
    postgres = next(item for item in manifest.objects if item.name == "postgres")
    assert postgres.status == STATUS_SKIPPED
    assert "BYPASSRLS" in (postgres.reason or "")
    assert not (out_dir / "postgres.dump").exists()


def test_split_pg_dsn_reads_host_port_user_password_db() -> None:
    assert split_pg_dsn("postgresql+psycopg://graphrag:pw@localhost:5432/graphrag") == (
        "localhost",
        5432,
        "graphrag",
        "pw",
        "graphrag",
    )


def test_sha256_is_stable_and_sensitive_to_content(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    first = sha256_of(path)
    path.write_bytes(b"abd")
    assert first != sha256_of(path)


def test_backup_verify_subcommand_reports_nonzero_on_corruption(backup_set) -> None:
    """`backup.py --verify` 这条 CLI 入口也得判得出来（不只是库函数）。"""
    import subprocess

    _module, out_dir, manifest, _verification = backup_set
    target = next(i for i in manifest.objects if i.name == "config")
    (out_dir / str(target.path)).write_bytes(b"tampered")

    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        [
            sys.executable,
            str(BACKEND_ROOT / "scripts" / "backup.py"),
            "--verify",
            str(out_dir),
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 1
    assert "SHA-256 不符" in proc.stdout


def test_skipped_entry_is_not_present() -> None:
    entry = skipped_entry(name="neo4j", reason="图库在线，dump 需在停服窗口做")
    assert entry.status == STATUS_SKIPPED
    assert entry.reason


# --------------------------------------------------------------------------- #
# 5. 真图探针（GRAPH_REAL_NEO4J_*：CI 上缺失即 fail）
# --------------------------------------------------------------------------- #


def test_real_neo4j_probe_distinguishes_existing_and_missing_version() -> None:
    """适配层**真的去问了图库**：存在的版本 True、不存在的 False。

    若把探针换成恒 True / 恒 False 的桩，`evaluate_version_consistency` 的两个
    分支会各自恒绿 ⇒ §6.2 从头到尾没验过。本条就是堵它的。
    """
    _uri, _user, _password = _real_graph_env()
    module = _load("restore", BACKEND_ROOT / "scripts" / "restore.py")

    missing_version = "v-p6w-definitely-not-there"
    try:
        assert module.default_neo4j_probe(missing_version) is False
        existing = module.default_pg_active_probe()
        if existing is not None:
            assert module.default_neo4j_probe(str(existing.version)) is True
    except Exception as exc:  # noqa: BLE001 - 连通性即判据
        if os.environ.get("CI"):
            pytest.fail(f"CI 上读不到 Neo4j（缺 §6.2 的交叉校验）: {exc}")
        pytest.skip(f"本机 Neo4j 不可达: {exc}")
