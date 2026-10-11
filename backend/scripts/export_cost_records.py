"""从 ``cost_metrics`` 导出 ``--calibrate`` 能吃的 cost-records JSON（P6-V4 · V4-b）。

用法::

    uv run python scripts/export_cost_records.py --out data/eval/cost-records.json
    uv run python scripts/export_cost_records.py --stage answer --out answer.json
    uv run python scripts/export_cost_records.py --org-id <uuid> --date-from 2026-10-01

导出后交给校准（**只输出建议值，不改配置**）::

    uv run python scripts/eval_acceptance.py --calibrate --cost-records <上面的文件>

**为什么要有它（它闭掉的是一个死循环）**：``--calibrate`` 需要 ``--cost-records``，
而那份文件此前只能靠人手编 ⇒ 「没校准 ⇒ 不会去攒数据；没数据 ⇒ 没法校准」，
TBD-7 就一直停在 provisional。本脚本让「库里跑出来的真实数据」能直接进校准。

**⚠️ 读导出值的人必须知道的限制（不掩饰）**：``cost_metrics`` 的行粒度是
「一天 × 一个 stage」，**表里没有逐文档的 token 明细**（要明细 = 新表 + 迁移 +
ADR-0004 登记，属另批）。故每条记录的 ``token_usage_total`` 是**当日均值**
（见 :func:`app.services.cost_metrics.to_cost_records`）⇒ 喂进 ``--calibrate`` 后
**P50 == P90 == 均值**，分位数退化。⇒ 建议值只是**量级参考**，不是分布上界，
**不能**被读成「已校准」。

**退出码**：0 = 已写出记录；1 = 库里没有可导出的行（**不是**失败，但也不许
被当成"导出成功"——那会让下游拿着空文件去校准）。
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Windows 控制台默认 GBK，中文结果会 UnicodeEncodeError —— 强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select  # noqa: E402

from app.db.models import COST_STAGE_EXTRACTION, CostMetric  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.services.cost_metrics import to_cost_records  # noqa: E402

#: 与 ``app.evaluation.runner.ORG_ID`` 同值：单机演示的默认租户。
DEFAULT_ORG_ID = "00000000-0000-4000-8000-000000000001"


def _parse_day(raw: str | None) -> date | None:
    if raw is None or not raw.strip():
        return None
    return date.fromisoformat(raw.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--org-id",
        default=DEFAULT_ORG_ID,
        help=f"租户 id（默认 {DEFAULT_ORG_ID}；RLS 下**只**看得到本租户的行）",
    )
    parser.add_argument(
        "--stage",
        default=COST_STAGE_EXTRACTION,
        help=("成本口径（默认 %(default)s = M2 抽取，C3-a 的口径）；问答口径填 answer"),
    )
    parser.add_argument("--date-from", help="起始日（YYYY-MM-DD，含）")
    parser.add_argument("--date-to", help="结束日（YYYY-MM-DD，含）")
    parser.add_argument(
        "--out", required=True, type=Path, help="输出 JSON 路径（--calibrate 直接吃）"
    )
    args = parser.parse_args()

    try:
        org_id = uuid.UUID(str(args.org_id).strip())
    except (TypeError, ValueError):
        print(f"--org-id 不是合法 UUID：{args.org_id!r}")
        return 2

    try:
        date_from, date_to = _parse_day(args.date_from), _parse_day(args.date_to)
    except ValueError as exc:
        print(f"--date-from / --date-to 必须是 YYYY-MM-DD：{exc}")
        return 2

    conditions = [CostMetric.org_id == org_id, CostMetric.stage == args.stage]
    if date_from is not None:
        conditions.append(CostMetric.metric_date >= date_from)
    if date_to is not None:
        conditions.append(CostMetric.metric_date <= date_to)

    with session_scope(org_id=org_id) as db:
        rows = db.scalars(select(CostMetric).where(*conditions)).all()
        records = to_cost_records(rows)
        days = sorted({row.metric_date for row in rows})
        total_tokens = sum(int(row.token_usage_total or 0) for row in rows)

    if not records:
        print(
            f"cost_metrics 没有可导出的行（org_id={org_id}, stage={args.stage}"
            f"{f', {date_from}..{date_to}' if date_from or date_to else ''}）⇒ "
            "未写出文件。\n"
            "要么这段真的没跑过 LLM 调用，要么落点坏了——先跑一轮真实抽取再导出。"
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已写出 {len(records)} 条记录 ⇒ {args.out}")
    print(f"来源：{len(rows)} 行 / {len(days)} 天 / 累计 {total_tokens} token")
    print(
        "⚠️ cost_metrics 是**日聚合**（无逐文档明细）⇒ 同一天的记录拿到**同一个均值**，"
        "\n   --calibrate 的 P50 == P90 == 均值 ⇒ 建议值只是**量级参考**，不是分布上界。"
    )
    print(
        f"\n下一步：uv run python scripts/eval_acceptance.py --calibrate "
        f"--cost-records {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
