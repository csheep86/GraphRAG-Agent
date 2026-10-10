"""``backup`` —— DR-E2（P6-W / W-a）**六类对象 + 备份清单**。

用法::

    uv run python scripts/backup.py --out-dir <目录>            # 产出一次全量备份
    uv run python scripts/backup.py --verify <目录>             # 只校验既有备份集（第 8 项判据）

退出码
------
``0`` 一切对象都备份到且清单自校验通过；``1`` 有对象没备份到 / 清单校验未过；
``2`` 参数错误。

⚠️ **不静默降级**：任一类对象没备份到，清单里记为 ``skipped`` + 原因，
不为凑齐"六类齐全"而假装成功。

**F-P6W-1（2026-10-10 实测，务必先读）**：
G-26 要求 RLS ``ENABLE`` + ``FORCE`` ⇒ **``pg_dump`` 必须由 BYPASSRLS 角色执行**。
实测：受限账号 ``app_rls`` 与 owner ``app_owner`` 均 **EXIT=1**
（``query would be affected by row-level security policy``），超级用户 **EXIT=0**。
⇒ 备份库连接串请用 ``--pg-dsn``（或 env ``BACKUP_PG_DSN``）显式给，
**不是**应用运行时用的那个受限账号。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Windows 控制台默认 GBK，中文会 UnicodeEncodeError —— 强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.config import get_settings  # noqa: E402
from app.services.backup import (  # noqa: E402
    KG_RECORDED,
    KG_UNAVAILABLE,
    MANIFEST_SCHEMA_VERSION,
    ActiveKgVersion,
    BackupManifest,
    ManifestVerification,
    ObjectEntry,
    file_entry,
    redact_env_file,
    skipped_entry,
    split_pg_dsn,
    utc_now_iso,
    verify_manifest,
)

PG_DSN_ENV = "BACKUP_PG_DSN"

PG_DUMP_FILE = "postgres.dump"
NEO4J_DUMP_FILE = "neo4j.dump"
STORAGE_TAR_FILE = "storage.tar"
LICENSE_FILE = "license.lic"
CONFIG_FILE = "env.redacted"


# --------------------------------------------------------------------------- #
# 各对象采集器：一律返回 ObjectEntry（present / skipped + 原因）
# --------------------------------------------------------------------------- #


def collect_postgres(
    *, out_dir: Path, dsn: str | None, container: str | None = None
) -> ObjectEntry:
    """§6.1 ① PostgreSQL —— ``pg_dump``（custom format）。

    ``container`` 给了就走 ``docker exec``（目标环境常见形态：本机没有 client 工具，
    只有容器里有）；否则走本机 PATH 里的 ``pg_dump``。
    """
    name = "postgres"
    resolved = dsn or os.environ.get(PG_DSN_ENV)
    if not resolved:
        return skipped_entry(
            name=name,
            reason=(
                f"未给备份库连接串：用 --pg-dsn 或 env {PG_DSN_ENV}；"
                "它必须是 BYPASSRLS 角色（受限账号会因 RLS 直接失败）"
            ),
        )
    if not container and not shutil.which("pg_dump"):
        return skipped_entry(
            name=name,
            reason=(
                "PATH 中无 pg_dump ⇒ 补 --pg-container <容器名>（走 docker exec），"
                "或在目标环境装 postgresql-client"
            ),
        )
    binary = shutil.which("pg_dump")
    host, port, user, password, database = split_pg_dsn(resolved)
    # 容器里跑时 host 写 localhost（容器看到的 PG 就是它自己）
    effective_host = "localhost" if container else host
    argv = [
        "--host",
        effective_host,
        "--port",
        str(port),
        "--username",
        user,
        "--dbname",
        database,
        "--format=custom",
        "--no-owner",
    ]
    #: **刻意不写文件、统一走 stdout**：容器模式不必先落容器内 /tmp 再 ``docker cp``
    #: 出来（多一次拷贝就多一处中间态），本机模式也省掉一道临时文件。
    if container:
        command = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={password}",
            container,
            "pg_dump",
        ]
        env = dict(os.environ)
    else:
        command = [binary or "pg_dump"]
        env = {**os.environ, "PGPASSWORD": password}
    target = out_dir / PG_DUMP_FILE
    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        [*command, *argv],
        capture_output=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()[:300]
        return skipped_entry(
            name=name, reason=f"pg_dump 退出码 {proc.returncode}: {detail}"
        )
    if not proc.stdout:
        return skipped_entry(
            name=name, reason="pg_dump 未产出任何字节（空导出 ⇒ 当作失败，不写空文件）"
        )
    target.write_bytes(proc.stdout)
    return file_entry(name=name, path=target, base_dir=out_dir, method="pg_dump -Fc")


def _neo4j_dump_command(container: str, dump_argv: list[str]) -> list[str]:
    """组装图库 dump 命令：**容器在跑**用 exec；**容器已停**用一次性 `--volumes-from`。

    为什么要第二个分支：F-P6W-2（在线库会被 `The database is in use` 拒掉）
    意味着 dump 前必须先停 DBMS，而停 DBMS 的最省事办法是把整个图容器停掉；
    容器一停 `docker exec` 就用不了了 ⇒ 改用同镜像的一次性容器挂同一份 volume
    只跑 `neo4j-admin`（不动原容器，也不用 `docker cp` 中转）。
    """
    probe = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        ["docker", "inspect", container, "--format", "{{.State.Running}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if probe.stdout.strip().lower() == "true":
        return ["docker", "exec", container, "neo4j-admin", *dump_argv]

    image = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        ["docker", "inspect", container, "--format", "{{.Config.Image}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return [
        "docker",
        "run",
        "--rm",
        "--volumes-from",
        container,
        "--entrypoint",
        "neo4j-admin",
        image.stdout.strip(),
        *dump_argv,
    ]


def collect_neo4j(*, out_dir: Path, container: str | None = None) -> ObjectEntry:
    """§6.1 ② Neo4j —— ``neo4j-admin database dump``（**图容器内的能力**，本机通常没有）。"""
    name = "neo4j"
    if not container and not shutil.which("neo4j-admin"):
        return skipped_entry(
            name=name,
            reason=(
                "PATH 中无 neo4j-admin；图库 dump 只能在图容器内跑 ⇒ "
                "补 --neo4j-container <容器名>，或本机装 neo4j-admin 后复跑"
            ),
        )
    #: **统一走 stdout**：容器里不必先落临时文件再 ``docker cp`` 出来。
    dump_argv = [
        "database",
        "dump",
        get_settings().neo4j_database,
        "--to-stdout",
    ]
    if container:
        command = _neo4j_dump_command(container, dump_argv)
    else:
        command = ["neo4j-admin", *dump_argv]
    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        command, capture_output=True, check=False
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()[:300]
        return skipped_entry(
            name=name,
            reason=(
                f"neo4j-admin dump 失败（退出码 {proc.returncode}）: {detail}"
                " —— F-P6W-2：在线库会被拒（`The database is in use`），"
                "图库备份窗口须停图库"
            ),
        )
    target = out_dir / NEO4J_DUMP_FILE
    target.write_bytes(proc.stdout)
    return file_entry(
        name=name, path=target, base_dir=out_dir, method="neo4j-admin database dump"
    )


def collect_storage(*, out_dir: Path, storage_root: Path) -> ObjectEntry:
    """§6.1 ③ 文件存储 —— `/data/storage`（**stdlib tarfile**，不依赖外部命令）。"""
    name = "storage"
    root = Path(storage_root)
    if not root.is_dir():
        return skipped_entry(name=name, reason=f"文件存储根目录不存在: {root}")
    target = out_dir / STORAGE_TAR_FILE
    with tarfile.open(target, "w") as archive:
        archive.add(root, arcname=root.name)
    return file_entry(name=name, path=target, base_dir=out_dir, method="tarfile")


def collect_license(*, out_dir: Path, license_file: Path) -> ObjectEntry:
    """§6.1 ④ License 文件 —— 复制（恢复后必须能继续启动，ADR-0006 §2.2 第 5 步）。"""
    name = "license"
    source = Path(license_file)
    if not source.is_file():
        return skipped_entry(name=name, reason=f"License 文件不存在: {source}")
    target = out_dir / LICENSE_FILE
    shutil.copy2(source, target)
    return file_entry(name=name, path=target, base_dir=out_dir, method="copy")


def collect_config(*, out_dir: Path, env_file: Path | None) -> ObjectEntry:
    """§6.1 ⑤ 配置 —— `.env` 的**脱敏副本**（去密钥）。"""
    name = "config"
    source = Path(env_file) if env_file else None
    if source is None or not source.is_file():
        return skipped_entry(
            name=name,
            reason="未找到可读的 .env（用 --env-file 指定）⇒ 脱敏副本无从产出",
        )
    target = out_dir / CONFIG_FILE
    keys = redact_env_file(source, target)
    return file_entry(
        name=name,
        path=target,
        base_dir=out_dir,
        method=f"copy+redact（{len(keys)} 项密钥已置 <redacted>）",
    )


def collect_active_kg_version(
    probe: Any | None = None,
) -> ActiveKgVersion:
    """§6.1 ⑥ **记录备份时刻的 active `kg_version`**（写进清单，不是文件）。

    ``probe`` 可注入（签名 ``() -> KgVersionRecord | None``）；不注入时走 PG 真源
    （``KgVersioningService.get_active``，ADR-0002 §3.2）。
    读不到 ⇒ 如实记 ``unavailable`` + 原因（**不许**把"连不上"写成"没有版本"）。
    """
    if probe is None:
        from app.db.session import open_session
        from app.services.kg.versioning import KgVersioningService

        settings = get_settings()

        def probe() -> Any | None:  # pragma: no cover - 极薄适配层
            with open_session(org_id=settings.default_org_id) as session:
                return KgVersioningService(session).get_active(
                    org_id=settings.default_org_id
                )

    try:
        record = probe()
    except Exception as exc:  # noqa: BLE001 - 读不到一律如实登记
        return ActiveKgVersion(
            status=KG_UNAVAILABLE,
            source="pg:kg_versions",
            reason=f"读取 PG active kg_version 失败: {type(exc).__name__}: {exc}",
        )
    if record is None:
        return ActiveKgVersion(
            status=KG_UNAVAILABLE,
            source="pg:kg_versions",
            reason="PG kg_versions 中无 ready 版本（未建图或未激活）",
        )
    ready_at = getattr(record, "ready_at", None)
    return ActiveKgVersion(
        status=KG_RECORDED,
        source="pg:kg_versions",
        version=str(record.version),
        pg_status=str(record.status),
        ready_at=None if ready_at is None else str(ready_at),
    )


# --------------------------------------------------------------------------- #
# 编排
# --------------------------------------------------------------------------- #


def default_out_dir() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("reports") / "backup" / stamp


def run_backup(
    *,
    out_dir: Path,
    pg_dsn: str | None = None,
    env_file: Path | None = None,
    storage_root: Path | None = None,
    license_file: Path | None = None,
    neo4j_container: str | None = None,
    pg_container: str | None = None,
    active_probe: Any | None = None,
) -> tuple[BackupManifest, ManifestVerification]:
    """产出一次全量备份；写完清单**立刻自己重算一遍**（这是第 8 项的第一现场）。"""
    settings = get_settings()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = (
        collect_postgres(out_dir=out_dir, dsn=pg_dsn, container=pg_container),
        collect_neo4j(out_dir=out_dir, container=neo4j_container),
        collect_storage(
            out_dir=out_dir,
            storage_root=Path(storage_root) if storage_root else settings.storage_root,
        ),
        collect_license(
            out_dir=out_dir,
            license_file=Path(license_file)
            if license_file
            else Path(settings.license_file_path),
        ),
        collect_config(out_dir=out_dir, env_file=env_file),
    )

    manifest = BackupManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        generated_at=utc_now_iso(),
        app_version=settings.app_version,
        objects=entries,
        active_kg_version=collect_active_kg_version(active_probe),
    )
    manifest.write(out_dir)
    return manifest, verify_manifest(out_dir)


def write_report(path: Path, verification: ManifestVerification) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "ok": verification.ok,
                "failures": list(verification.failures),
                "passed": list(verification.passed),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"报告已落盘: {target}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out-dir",
        help=f"备份落点目录（默认 {default_out_dir().as_posix()}）",
    )
    parser.add_argument(
        "--verify",
        metavar="DIR",
        help="只校验既有备份集（重算 SHA-256 + 清单完整性 ⇒ §10 第 8 项判据）",
    )
    parser.add_argument(
        "--pg-dsn",
        help=(
            f"备份库连接串（也可走 env {PG_DSN_ENV}）；"
            "**必须 BYPASSRLS 角色**（受限账号会被 FORCE RLS 拦下，见模块 docstring）"
        ),
    )
    parser.add_argument("--env-file", help=".env 路径（据此产出脱敏副本）")
    parser.add_argument(
        "--storage-root", help="文件存储根目录（默认 settings.storage_root）"
    )
    parser.add_argument(
        "--license-file", help="License 文件路径（默认 settings.license_file_path）"
    )
    parser.add_argument(
        "--neo4j-container", help="图容器名（走 docker exec 跑 neo4j-admin）"
    )
    parser.add_argument(
        "--pg-container",
        help="PG 容器名（走 docker exec 跑 pg_dump，本机无 client 时用）",
    )
    parser.add_argument("--out", help="校验报告 JSON 落点（机读产物，可选）")
    args = parser.parse_args(argv)

    if args.verify:
        verification = verify_manifest(Path(args.verify))
        for line in verification.lines():
            print(line)
        if args.out:
            write_report(Path(args.out), verification)
        print(
            f"[{'OK' if verification.ok else 'FAIL'}] "
            f"备份集校验{'通过' if verification.ok else '未通过'}"
        )
        return 0 if verification.ok else 1

    if not args.out_dir:
        parser.error("必须给 --out-dir（或改用 --verify <DIR> 只做校验）")

    out_dir = Path(args.out_dir)
    manifest, verification = run_backup(
        out_dir=out_dir,
        pg_dsn=args.pg_dsn,
        env_file=Path(args.env_file) if args.env_file else None,
        storage_root=Path(args.storage_root) if args.storage_root else None,
        license_file=Path(args.license_file) if args.license_file else None,
        neo4j_container=args.neo4j_container,
        pg_container=args.pg_container,
    )
    print(f"备份目录: {out_dir}")
    print(f"清单: {out_dir / 'backup-manifest.json'}")
    for line in verification.lines():
        print(line)
    if args.out:
        write_report(Path(args.out), verification)

    skipped = [item.name for item in manifest.objects if item.status == "skipped"]
    if skipped:
        print(
            f"\n[WARN] 以下对象未备份到 ⇒ 备份集**不完整**"
            f"（§6.1「缺一不可复现」）: {', '.join(skipped)}"
        )
    print(f"[{'OK' if verification.ok else 'FAIL'}] backup 完成")
    return 0 if verification.ok else 1


if __name__ == "__main__":
    sys.exit(main())
