"""外部数据手工导入 CLI（接缝 8 的写入点；plan §6.2 批次 B）。

用法::

    uv run python -m app.services.external_data.cli --org-id <uuid> --file refs.json
    uv run python -m app.services.external_data.cli --org-id <uuid> --file refs.csv --apply

纪律：

- **默认 dry-run**：先让人看见要写多少条、有多少坏行；加 ``--apply`` 才落库；
- 写入目标只有 ``external_refs``（接缝 7），**不**为某个数据源单建表；
- ``local_id`` 不做存在性校验（本系统 ID 可能来自图谱而非 PG，校验它等于要求
  两种存储必须同事实同步，那是 S9 实体消解的题目）。
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy.exc import IntegrityError

from app.db.models import ExternalRef
from app.db.session import SessionLocal, init_db
from app.services.external_data.schema import load_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="external-data-import",
        description="手工导入外部 ID 映射文件（JSON / CSV）到 external_refs",
    )
    parser.add_argument("--org-id", required=True, help="租户 UUID（`X-Org-Id` 同义）")
    parser.add_argument("--file", required=True, help="导入文件路径（.json / .csv）")
    parser.add_argument(
        "--fmt",
        choices=("auto", "json", "csv"),
        default="auto",
        help="文件格式，默认按扩展名判断",
    )
    parser.add_argument(
        "--apply", action="store_true", help="真正写库；不加则只打印计划"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        org_id = uuid.UUID(args.org_id)
    except ValueError:
        print(f"[ERROR] --org-id 不是合法 UUID: {args.org_id!r}")
        return 2

    result = load_file(args.file, fmt=args.fmt)
    for line in result.errors:
        print(f"[BAD ] {line}")
    print(f"[INFO] 可导入 {len(result.records)} 条，坏行 {len(result.errors)} 条")

    if not result.records:
        print("[STOP] 没有可导入的记录")
        return 1
    if not args.apply:
        for record in result.records[:10]:
            print(
                f"       {record.object_type}:{record.local_id} "
                f"← {record.external_system}:{record.external_id}"
            )
        if len(result.records) > 10:
            print(f"       …… 其余 {len(result.records) - 10} 条省略")
        print("[DRY-RUN] 未写库；加 --apply 才落 external_refs")
        return 0

    init_db()
    written = 0
    skipped = 0
    with SessionLocal() as session:
        for record in result.records:
            # 同一 (org, 外部系统, 外部 ID) 已存在 → 幂等跳过（**不**静默覆盖：外来 ID
            # 指向变了是数据事故，得让人显式处理）
            exists = (
                session.query(ExternalRef.id)
                .filter(
                    ExternalRef.org_id == org_id,
                    ExternalRef.external_system == record.external_system,
                    ExternalRef.external_id == record.external_id,
                )
                .first()
            )
            if exists is not None:
                skipped += 1
                continue
            session.add(
                ExternalRef(
                    org_id=org_id,
                    object_type=record.object_type,
                    local_id=record.local_id,
                    external_system=record.external_system,
                    external_id=record.external_id,
                )
            )
            written += 1
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            print(f"[ERROR] 写库失败（唯一约束冲突？）: {exc}")
            return 1

    print(f"[ OK ] 写入 {written} 条，跳过已存在 {skipped} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
