"""初始化 ``relation_expiry_policies``（ADR-0005 §6 L1 的策略表）。

为什么要有这个脚本
------------------
策略表是 :func:`app.services.kg.policies.load_expiry_policies` 的**唯一数据源**，
而后者决定 L1 仲裁要不要封旧边。表为**空**时，判定函数走保守默认
``append_only``（多值并存、不封任何边）——于是「法定代表人换了人，旧边被封」
这条能力**在真实租户下根本不会发生**，而且**没有任何报错**：图照建、接口照返回，
只是永远查不到 ``valid_to``。

实测（2026-09-28，dev 库）：策略表 0 行。PoC 与正式测试之所以 3/3，是因为它们
**自己插了策略行**。⇒ 缺的不是逻辑，是**把逻辑接上的那一步初始化**。

本脚本就是那一步。默认按 ADR-0005 §6 L1 的定义落两类：

- ``LEGAL_REP`` / ``REGISTERED_AT`` = ``single_current``（一人 / 一址，新事实封旧）；
- ``'*'`` = ``append_only``（兜底行；与代码的保守默认同值，写出来是为了让运维
  **看得见**这个兜底，而不是以为"没配就是没配"）。

幂等：**已存在的行不覆盖**（运维可能手工调过策略，脚本不该悄悄改回去）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/seed_expiry_policies.py                 # 默认租户
    uv run python scripts/seed_expiry_policies.py --org <uuid>    # 指定租户
    uv run python scripts/seed_expiry_policies.py --single HAS_FINANCIAL_INDICATOR
    uv run python scripts/seed_expiry_policies.py --dry-run       # 只看会写什么
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.models import RelationExpiryPolicy  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.kg.policies import (  # noqa: E402 - 常量复用，不另起一套字面量
    FALLBACK_RELATION_TYPE,
    POLICY_SINGLE_CURRENT,
)

#: 追加多值策略（与 ``single_current`` 相对）的类型常量；代码里未定义，故在此声明
POLICY_APPEND_ONLY = "append_only"

#: ADR-0005 §6 L1 明确点名的两类「只允许一个当前值」的关系。
#: 不在表里的类型 ⇒ 查不到具体行 ⇒ 落到兜底行 ``'*'`` ⇒ 并存（不封边）。
DEFAULT_SINGLE_CURRENT: tuple[str, ...] = ("LEGAL_REP", "REGISTERED_AT")


def force_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None)
        if stream and enc and enc.lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def seed(
    *,
    org_id: UUID,
    extra_single: tuple[str, ...],
    dry_run: bool,
) -> int:
    """写入（或预览）策略行；已存在的类型**跳过**。返回退出码。"""
    planned: list[tuple[str, str]] = [
        (relation_type, POLICY_SINGLE_CURRENT)
        for relation_type in (*DEFAULT_SINGLE_CURRENT, *extra_single)
    ]
    planned.append((FALLBACK_RELATION_TYPE, POLICY_APPEND_ONLY))

    db = SessionLocal()
    try:
        existing = {
            str(row[0]): str(row[1])
            for row in db.execute(
                select(
                    RelationExpiryPolicy.relation_type, RelationExpiryPolicy.policy
                ).where(RelationExpiryPolicy.org_id == org_id)
            ).all()
        }
        created = 0
        for relation_type, policy in planned:
            if relation_type in existing:
                print(
                    f"  [SKIP] {relation_type:<28} 已存在 = {existing[relation_type]}"
                    "（不覆盖：运维可能手工调过）"
                )
                continue
            print(f"  [{'DRY' if dry_run else 'NEW'}] {relation_type:<28} -> {policy}")
            if not dry_run:
                db.add(
                    RelationExpiryPolicy(
                        org_id=org_id, relation_type=relation_type, policy=policy
                    )
                )
                created += 1
        if not dry_run:
            db.commit()
        print(
            f"\n  租户 {org_id}：新增 {created} 行 / 计划 {len(planned)} 行"
            + ("（dry-run，未写库）" if dry_run else "")
        )
    finally:
        db.close()
    return 0


def main() -> int:
    force_utf8_console()
    parser = argparse.ArgumentParser(description="初始化 relation_expiry_policies")
    parser.add_argument("--org", help="租户 id（默认取 settings.default_org_id）")
    parser.add_argument(
        "--single",
        action="append",
        default=[],
        metavar="RELATION_TYPE",
        help="追加一个 single_current 类型（可重复）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写库")
    args = parser.parse_args()

    org_id = UUID(args.org) if args.org else get_settings().default_org_id
    print(f"租户 org_id = {org_id}")
    return seed(org_id=org_id, extra_single=tuple(args.single), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
