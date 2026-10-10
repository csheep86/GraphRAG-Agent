"""``restore`` —— DR-E2（P6-W / W-a）**恢复 + §6.2 版本一致性校验**。

用法::

    uv run python scripts/restore.py --backup-dir <目录>                # 只校验（默认不动数据）
    uv run python scripts/restore.py --backup-dir <目录> --apply        # 真恢复 + 校验
    uv run python scripts/restore.py --backup-dir <目录> --apply \\
        --pg-dsn <BYPASSRLS 连接串> --target-db <目标库名>

退出码
------
``0`` 全部通过；``1`` **清单校验未通过**（⇒ **拒绝恢复**，就此停住）；
``2`` **§6.2 一致性未通过**（幽灵版本 / 图库不可达 / 版本错位 ⇒ **报错，不静默启动**）；
``3`` 参数错误。

**三条刻意的设计约束**：

1. **清单不过 ⇒ 一步都不恢复**。带着坏清单恢复，等于把"不知道恢复到什么程度"
   变成既定事实 —— 那比不恢复更糟（尚可回头错觉没了）。
2. **`.env` 不自动回写**。写回会把客户现场新配的密钥盖掉（决策 **W7**）⇒
   只输出"脱敏副本在哪、密钥须现场重填"。
3. **图库不默认 load**。`neo4j-admin database load` 要求图库**停服**，
   擅自执行的副作用大于收益 ⇒ 只在显式给了 ``--neo4j-container`` 时才做。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

from app.core.config import get_settings  # noqa: E402
from app.services.backup import (  # noqa: E402
    MANIFEST_FILENAME,
    STATUS_PRESENT,
    BackupManifest,
    ObjectEntry,
    evaluate_manifest_vs_pg,
    evaluate_version_consistency,
    split_pg_dsn,
    verify_manifest,
)


class RestoreTarError(RuntimeError):
    """备份归档本身有问题（成员路径越界 / 顶层目录不唯一）。"""


# --------------------------------------------------------------------------- #
# 1. 各对象的恢复（路径一律由参数注入 ⇒ 不依赖 /data 这类固定位置）
# --------------------------------------------------------------------------- #


def _strip_top_level(
    members: list[tarfile.TarInfo],
) -> tuple[str, list[tarfile.TarInfo]]:
    """去掉归档里统一的顶层目录名（备份时以 ``storage_root.name`` 做 arcname）。

    要求**所有成员共享同一个顶层名**：一个正常 tar-stream 只会有一种顶层。
    不唯一 ⇒ 这个包不是本脚本产出的 ⇒ 拒收（不猜它该怎么落）。
    """
    tops = {member.name.split("/", 1)[0] for member in members}
    if len(tops) != 1:
        raise RestoreTarError(
            f"归档顶层目录不唯一: {sorted(tops)} ⇒ 不是本脚本产出的备份"
        )
    top = tops.pop()
    stripped: list[tarfile.TarInfo] = []
    for member in members:
        _, _, rest = member.name.partition("/")
        if rest:
            member.name = rest
            stripped.append(member)
    return top, stripped


def extract_storage_archive(archive: Path, target_root: Path) -> tuple[str, int]:
    """把 `storage.tar` 解开到 ``target_root``；返回 (顶层目录名, 解出的成员数)。

    **tar 是不可信输入**（它可能来自别人的机器）：必须逐成员校验目标路径没跑出
    ``target_root``（``../`` 穿越），否则一次恢复能把任意文件写穿。
    Python 3.11 的 :func:`tarfile.extractall` 没有 ``filter="data"`` 兜底 ⇒ 自己判。
    """
    target_root = Path(target_root).resolve()
    with tarfile.open(Path(archive)) as handle:
        members = list(handle.getmembers())
        top, stripped = _strip_top_level(members)
        for member in stripped:
            member_path = (target_root / member.name).resolve()
            #: 用 `is_relative_to` 而不是拼字符串前缀 —— 后者在 Windows 上会因为
            #: 分隔符不是 "/" 而**把所有成员都判成越界**（本机踩过）。
            if not member_path.is_relative_to(target_root):
                raise RestoreTarError(f"归档成员越界（路径穿越）: {member.name}")
        handle.extractall(path=target_root, members=stripped)
        return top, len(stripped)


def restore_storage(
    *, backup_dir: Path, entry: ObjectEntry, target_root: Path
) -> tuple[str, str]:
    """§6.1 ③ 文件存储 —— 解开 tar（stdlib ⇒ 不依赖外部命令，CI 可跑）。"""
    archive = Path(backup_dir) / str(entry.path)
    target_root = Path(target_root)
    target_root.mkdir(parents=True, exist_ok=True)
    top, count = extract_storage_archive(archive, target_root)
    return (
        "storage",
        f"已解开 {count} 个成员 → {target_root}（归档顶层 “{top}” 已被剥掉）",
    )


def restore_license(
    *, backup_dir: Path, entry: ObjectEntry, target_path: Path
) -> tuple[str, str]:
    """§6.1 ④ License 文件 —— 复制回 ``LICENSE_FILE_PATH``。"""
    source = Path(backup_dir) / str(entry.path)
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target_path)
    return ("license", f"已恢复到 {target_path}")


def restore_postgres(
    *,
    backup_dir: Path,
    entry: ObjectEntry,
    pg_dsn: str | None,
    target_db: str | None,
    container: str | None = None,
) -> tuple[str, str]:
    """§6.1 ① PostgreSQL —— ``pg_restore``（需 BYPASSRLS 连接串 + 已存在的目标库）。

    ``container`` 给了就 ``docker exec``（目标环境常见形态），并把备份文件从
    **stdin** 喂进去 —— 免得先 ``docker cp`` 再 ``exec``（多一处中间态）。
    """
    source = Path(backup_dir) / str(entry.path)
    if not target_db:
        return ("postgres", "SKIP 未给 --target-db：脚本不猜目标库名，恢复错库不可回头")
    if not pg_dsn:
        return (
            "postgres",
            "SKIP 未给 --pg-dsn（须 BYPASSRLS 角色，理由见 backup.py 的 F-P6W-1）",
        )
    if not container and not shutil.which("pg_restore"):
        return (
            "postgres",
            "SKIP PATH 中无 pg_restore ⇒ 补 --pg-container <容器名>（走 docker exec）",
        )
    host, port, user, password, _db = split_pg_dsn(pg_dsn)
    effective_host = "localhost" if container else host
    argv = [
        "--host",
        effective_host,
        "--port",
        str(port),
        "--username",
        user,
        "--dbname",
        target_db,
        "--clean",
        "--if-exists",
        "--no-owner",
    ]
    if container:
        command = [
            "docker",
            "exec",
            "-i",
            "-e",
            f"PGPASSWORD={password}",
            container,
            "pg_restore",
        ]
        env = dict(os.environ)
    else:
        command = [shutil.which("pg_restore") or "pg_restore"]
        env = {**os.environ, "PGPASSWORD": password}
    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        [*command, *argv],
        input=source.read_bytes(),
        capture_output=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()[:300]
        return ("postgres", f"pg_restore 退出码 {proc.returncode}: {detail}")
    return ("postgres", f"已恢复到库 {target_db}")


def restore_neo4j(
    *, backup_dir: Path, entry: ObjectEntry, container: str | None
) -> tuple[str, str]:
    """§6.1 ② Neo4j —— ``neo4j-admin database load``（**要求图库停服** ⇒ 默认不做）。"""
    source = Path(backup_dir) / str(entry.path)
    if not container:
        return (
            "neo4j",
            "SKIP 未给 --neo4j-container：图库 load 要求停服，副作用大于收益 ⇒ 不自动做",
        )
    settings = get_settings()
    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        [
            "docker",
            "exec",
            container,
            "neo4j-admin",
            "database",
            "load",
            settings.neo4j_database,
            f"--from-path={source}",
            "--overwrite-destination=true",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ("neo4j", f"neo4j-admin load 失败（退出码 {proc.returncode}）")
    return ("neo4j", f"已恢复图库 {settings.neo4j_database}")


def config_hint(*, backup_dir: Path, entry: ObjectEntry) -> tuple[str, str]:
    """§6.1 ⑤ 配置 —— **不自动回写**（W7），只告诉人该怎么做。"""
    return (
        "config",
        f"SKIP 不自动回写 .env（会盖掉现场新配的密钥）；脱敏副本在 "
        f"{Path(backup_dir) / str(entry.path)}，密钥须现场重填后另存",
    )


# --------------------------------------------------------------------------- #
# 2. §6.2 一致性（default 探针只有极薄一层；被测的是判定逻辑本身）
# --------------------------------------------------------------------------- #


def default_pg_active_probe() -> Any | None:
    """PG 真源的 active ``kg_version`` record（ADR-0002 §3.2）。"""
    from app.db.session import open_session
    from app.services.kg.versioning import KgVersioningService

    settings = get_settings()
    with open_session(org_id=settings.default_org_id) as session:
        return KgVersioningService(session).get_active(org_id=settings.default_org_id)


def default_neo4j_probe(version: str) -> bool:
    """该版本在图库里**是否存在**（``None`` = 节点不存在 ⇒ 幽灵版本）。"""
    from app.services.graphs import GraphService

    return GraphService.instance().fetch_kg_version_status(version) is not None


# --------------------------------------------------------------------------- #
# 3. 编排
# --------------------------------------------------------------------------- #


def apply_restore(
    *,
    manifest: BackupManifest,
    backup_dir: Path,
    pg_dsn: str | None,
    target_db: str | None,
    storage_root: Path | None,
    license_file: Path | None,
    neo4j_container: str | None,
    pg_container: str | None = None,
) -> tuple[tuple[str, str], ...]:
    """按清单逐个恢复；返回每个对象的 (name, 结果串)——**不做静默跳过**。"""
    settings = get_settings()
    outcomes: list[tuple[str, str]] = []
    by_name = {item.name: item for item in manifest.objects}

    for name in ("postgres", "neo4j", "storage", "license", "config"):
        entry = by_name.get(name)
        if entry is None or entry.status != STATUS_PRESENT:
            outcomes.append((name, f"SKIP 清单里没有 {name} 的可用备份"))
            continue
        if name == "postgres":
            outcomes.append(
                restore_postgres(
                    backup_dir=backup_dir,
                    entry=entry,
                    pg_dsn=pg_dsn,
                    target_db=target_db,
                    container=pg_container,
                )
            )
        elif name == "neo4j":
            outcomes.append(
                restore_neo4j(
                    backup_dir=backup_dir, entry=entry, container=neo4j_container
                )
            )
        elif name == "storage":
            outcomes.append(
                restore_storage(
                    backup_dir=backup_dir,
                    entry=entry,
                    target_root=Path(storage_root)
                    if storage_root
                    else settings.storage_root,
                )
            )
        elif name == "license":
            outcomes.append(
                restore_license(
                    backup_dir=backup_dir,
                    entry=entry,
                    target_path=Path(license_file)
                    if license_file
                    else Path(settings.license_file_path),
                )
            )
        else:
            outcomes.append(config_hint(backup_dir=backup_dir, entry=entry))
    return tuple(outcomes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--backup-dir", required=True, help=f"备份集目录（含 {MANIFEST_FILENAME}）"
    )
    parser.add_argument("--apply", action="store_true", help="真恢复（默认只校验）")
    parser.add_argument("--pg-dsn", help="恢复用的 BYPASSRLS 库连接串")
    parser.add_argument("--target-db", help="恢复目标库名（须已存在，脚本不建库）")
    parser.add_argument(
        "--storage-root", help="文件存储根目录（默认 settings.storage_root）"
    )
    parser.add_argument(
        "--license-file", help="License 落点（默认 settings.license_file_path）"
    )
    parser.add_argument("--neo4j-container", help="图容器名（显式指定才会 load 图库）")
    parser.add_argument(
        "--pg-container",
        help="PG 容器名（走 docker exec 跑 pg_restore，本机无 client 时用）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backup_dir = Path(args.backup_dir)

    # --- ① 清单校验：**不过就一步都不恢复** ------------------------------ #
    verification = verify_manifest(backup_dir)
    for line in verification.lines():
        print(line)
    if not verification.ok:
        print(
            "[FAIL] 清单校验未通过 ⇒ **拒绝恢复**"
            "（带着坏清单恢复 = 把「恢复到什么程度不知道」变成既定事实）"
        )
        return 1

    manifest = BackupManifest.read(backup_dir)

    # --- ② 恢复 ---------------------------------------------------------- #
    if not args.apply:
        print("[INFO] 未给 --apply ⇒ 本轮**未改动任何数据**（只做上面的清单校验）")
    else:
        outcomes = apply_restore(
            manifest=manifest,
            backup_dir=backup_dir,
            pg_dsn=args.pg_dsn,
            target_db=args.target_db,
            storage_root=Path(args.storage_root) if args.storage_root else None,
            license_file=Path(args.license_file) if args.license_file else None,
            neo4j_container=args.neo4j_container,
            pg_container=args.pg_container,
        )
        for name, outcome in outcomes:
            verdict = "SKIP" if outcome.startswith("SKIP") else "DONE"
            print(f"{verdict} {name}: {outcome}")

    # --- ③ §6.2 版本一致性（错位 ⇒ 报错，不静默启动） --------------------- #
    try:
        record = default_pg_active_probe()
    except Exception as exc:  # noqa: BLE001 - PG 不可读 ⇒ 不许当成"没有版本"
        print(f"[FAIL] 读取 PG active kg_version 失败 ⇒ 拒绝判定: {exc}")
        return 2

    active_version = None if record is None else str(record.version)
    consistency = evaluate_version_consistency(
        active_version=active_version,
        neo4j_version_exists=default_neo4j_probe,
    )
    print(consistency.line(label="§6.2 版本一致性"))

    drift = evaluate_manifest_vs_pg(
        manifest_version=manifest.active_kg_version.version,
        active_version=active_version,
    )
    print(drift.line(label="§6.2 清单↔PG"))

    if not (consistency.ok and drift.ok):
        print(
            "\n[FAIL] §6.2 一致性未通过 ⇒ **不许启动**"
            "（ADR-0002 §3.2：幽灵版本必须报错，不得静默降级）"
        )
        return 2

    print("\n[OK] restore 通过（§6.2 一致性已校验）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
