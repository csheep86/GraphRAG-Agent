"""考勤域演示语料生成器（**可复现**，零第三方依赖）。

用法::

    uv run python demo/attendance/generate_corpus.py

产物::

    corpus/*.csv       9 张业务数据表（确定性，seed 固定）
    corpus/*.docx      4 份考勤制度文档（由 policies/*.md 转换）

**纪律**：

1. 全部为**仿真生成**语料，用于演示与链路验证，**不是**任何真实客户数据；
2. 制度数值一律取**法定合规值**（周 40h / 月加班 36h / 月计薪 21.75 天 → 174h）；
3. 固定 ``SEED``，同一环境重复执行产物逐字节一致。
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import random
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
POLICIES_DIR = ROOT / "policies"
OUT_DIR = ROOT / "corpus"

SEED = 20261001

# -- 制度常量（与 policies/ 一致，改制度必须同步改这里）------------------------
MONTH_STANDARD_HOURS = 174.0  # 21.75 天 × 8h（制度二第六条）
WEEK_STANDARD_HOURS = 40.0  # 制度二第三条
MONTH_OVERTIME_CAP = 36.0  # 劳动法第 41 条
CORE_START, CORE_END = "10:00", "16:00"  # 制度二第十二条

YEAR, MONTH = 2026, 10
DAYS: list[dt.date] = [dt.date(YEAR, MONTH, d) for d in range(1, 32)]
REST_WEEKDAYS = {5, 6}  # 周六 / 周日

#: 综合计算工时制**背景**员工的轮休星期（做五休二：周三 + 周日）。
#:
#: 改前为「周一至周六全排 + 周日 35% 出勤」⇒ 月排班 ≈27 天 / ≈216h，
#: 21/22 名综合制员工**全员**触发月加班超限，演示页被背景噪音淹没（登记为 L11）。
#: 做五休二 ⇒ 月排班 ≈22 天 / ≈176h，低于「174h 标准 + 36h 上限 = 210h」的触发线；
#: 综合制按**月**核算（制度二第七条），跨周排班本来就合规，改的是排班强度而非口径。
COMP_REST_WEEKDAYS = {2, 6}  # 周三 / 周日

#: 背景员工月内 12h 连班**最多 3 天**（否则随机叠加会把月度工时顶过 210h，
#: 重新引入 L11 的"全员超限"）。演示用例 E002 不受此限（其排班为精确构造）。
BACKGROUND_LONG_SHIFT_CAP = 3


def is_rest(day: dt.date) -> bool:
    return day.weekday() in REST_WEEKDAYS


# -- 组织架构 ----------------------------------------------------------------
# 部门 → (岗位, 工时制, 人数)
DEPT_SPEC: dict[str, tuple[str, str, int]] = {
    "生产部": ("产线操作工", "综合计算工时制", 14),
    "售后部": ("售后工程师", "综合计算工时制", 8),
    "研发部": ("研发工程师", "标准工时制", 7),
    "客服部": ("客服专员", "标准工时制", 6),
    "行政部": ("行政专员", "标准工时制", 3),
    "销售部": ("销售经理", "不定时工作制", 2),
}

#: 5 个演示用例固定占用前 5 个工号，数据由本脚本**精确构造**（非随机）
DEMO_CASES: list[tuple[str, str, str, str, str]] = [
    ("E001", "张伟", "售后部", "售后工程师", "综合计算工时制"),
    ("E002", "李静", "生产部", "产线操作工", "综合计算工时制"),
    ("E003", "王强", "研发部", "研发工程师", "标准工时制"),
    ("E004", "陈敏", "客服部", "客服专员", "标准工时制"),
    ("E005", "刘洋", "研发部", "研发工程师", "标准工时制"),
]

#: 背景员工姓名池（虚构）
NAME_POOL = [
    "杨帆",
    "赵磊",
    "孙悦",
    "周涛",
    "吴敏",
    "徐强",
    "朱琳",
    "马超",
    "胡静",
    "郭鹏",
    "何静",
    "高翔",
    "林芳",
    "罗伟",
    "郑爽",
    "梁静",
    "谢军",
    "宋佳",
    "唐勇",
    "许静",
    "韩磊",
    "冯敏",
    "邓超",
    "曹静",
    "彭勇",
    "曾静",
    "萧然",
    "田静",
    "董强",
    "潘婷",
    "蒋涛",
    "蔡静",
    "余波",
    "于静",
    "杜鹃",
]

#: 出差目的地（虚构客户现场）
SITES = ["武汉光谷", "长沙梅溪湖", "南昌红谷滩", "合肥滨湖", "郑州郑东", "西安高新"]

# 演示用例的关键日期（**已核对星期**）
#   10-16 = 周五（工作日）：应出勤却无打卡 → **真正的缺卡**，用于「异常归因」
#   10-17 = 周六（休息日）：休息日出勤处理工单 → 用于「政策问答：算不算加班」
#   注：缺卡不能设在休息日——休息日本无打卡义务，不会生成缺卡记录。
TRIP_START = dt.date(2026, 10, 16)
TRIP_ABSENT_DAY = dt.date(2026, 10, 16)  # 周五，缺卡日
TRIP_REST_DAY = dt.date(2026, 10, 17)  # 周六，休息日出勤
TRIP_END = dt.date(2026, 10, 18)
TRIP_DAYS = (TRIP_START, TRIP_REST_DAY, TRIP_END)
#: 李静连续出勤区间（10-01 周四 ~ 10-22 周三，共 22 天）
LI_WORK_START, LI_WORK_END = dt.date(2026, 10, 1), dt.date(2026, 10, 22)
#: 李静连班（12h）日期，共 10 天；其余 12 天为 8h → 合计 216h
LI_LONG_SHIFTS = {dt.date(2026, 10, d) for d in (3, 4, 9, 10, 14, 15, 16, 17, 21, 22)}
#: 王强核心时段未在岗日期，共 7 次（> 制度二第十三条的 5 次阈值）
WANG_CORE_ABSENT = {dt.date(2026, 10, d) for d in (5, 8, 12, 15, 19, 22, 26)}
#: 刘洋周工时超限周：**第 42 周**（10-12 周一 ~ 10-17 周六）连上 6 天 × 8h = 48h。
#:
#: 标准工时制背景员工恒为「周一至周五 5 × 8h = 40h」，**不**大于制度上限 40h，
#: 故「周工时超限」在改语料前**零命中**（登记为 L10）——必须显式埋设，不能靠随机。
LIU_WEEK_OVERTIME_DAYS = frozenset(dt.date(2026, 10, d) for d in range(12, 18))


def build_employees() -> list[dict[str, str]]:
    """40 名员工：前 4 名为演示用例，其余按部门配额填充。"""
    rows: list[dict[str, str]] = []
    for eid, name, dept, pos, wts in DEMO_CASES:
        rows.append(
            {
                "employee_id": eid,
                "name": name,
                "department": dept,
                "position": pos,
                "work_time_system": wts,
                "hire_date": "2023-03-01",
                "status": "active",
            }
        )
    pool = iter(NAME_POOL)
    idx = len(DEMO_CASES) + 1
    for dept, (pos, wts, quota) in DEPT_SPEC.items():
        taken = sum(1 for r in rows if r["department"] == dept)
        for _ in range(quota - taken):
            rows.append(
                {
                    "employee_id": f"E{idx:03d}",
                    "name": next(pool),
                    "department": dept,
                    "position": pos,
                    "work_time_system": wts,
                    "hire_date": f"20{random.randint(21, 25)}-{random.randint(1, 12):02d}-01",
                    "status": "active",
                }
            )
            idx += 1
    return rows


def _shift_row(seq: int, eid: str, day: dt.date, hours: float) -> dict[str, object]:
    if hours >= 12:
        start, end, stype = "08:00", "21:00", "连班"
    elif day.weekday() in REST_WEEKDAYS:
        start, end, stype = "09:00", "18:00", "周末班"
    else:
        start, end, stype = "09:00", "18:00", "正常班"
    return {
        "shift_id": f"S{seq:05d}",
        "employee_id": eid,
        "date": day.isoformat(),
        "shift_type": stype,
        "start_time": start,
        "end_time": end,
        "planned_hours": hours,
        "is_rest_day": 1 if is_rest(day) else 0,
    }


def build_shifts(employees: list[dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seq = 1

    def push(eid: str, day: dt.date, hours: float) -> None:
        nonlocal seq
        rows.append(_shift_row(seq, eid, day, hours))
        seq += 1

    for emp in employees:
        eid, dept, wts = emp["employee_id"], emp["department"], emp["work_time_system"]

        # -- 演示用例 E002 李静：连续出勤 22 天，10 天连班 → 月累计 216h ----
        if eid == "E002":
            for day in DAYS:
                if LI_WORK_START <= day <= LI_WORK_END:
                    push(eid, day, 12.0 if day in LI_LONG_SHIFTS else 8.0)
            continue

        # -- 演示用例 E001 张伟：工作日正常排班（含 10-16 出差缺卡日）------
        #    休息日不排班；10-17 的出勤由工单 + 定位证明，不体现在排班里。
        if eid == "E001":
            for day in DAYS:
                if is_rest(day):
                    continue  # 售后外勤，休息日不排班
                push(eid, day, 8.0)
            continue

        # -- 演示用例 E003 王强：核心越界日**必须出勤**，否则用例不成立 ----
        if eid == "E003":
            for day in DAYS:
                if is_rest(day):
                    continue
                if day in WANG_CORE_ABSENT or random.random() < 0.90:
                    push(eid, day, 8.0)
            continue

        # -- 演示用例 E005 刘洋：第 42 周连上 6 天 → 周工时 48h > 40h ----
        if eid == "E005":
            for day in DAYS:
                if day in LIU_WEEK_OVERTIME_DAYS:
                    push(eid, day, 8.0)  # 含 10-17 周六，冲刺周排满 6 天
                elif not is_rest(day) and random.random() < 0.95:
                    push(eid, day, 8.0)
            continue

        # -- 其余员工：按工时制生成背景排班 -------------------------------
        if wts == "不定时工作制":
            continue  # 不定时工作制不排班
        if wts == "综合计算工时制":
            # 做五休二（周三 + 周日轮休，见 COMP_REST_WEEKDAYS 注释）
            workdays = [
                d
                for d in DAYS
                if d.weekday() not in COMP_REST_WEEKDAYS and random.random() < 0.95
            ]
        else:  # 标准工时制
            workdays = [d for d in DAYS if not is_rest(d) and random.random() < 0.95]
        long_left = BACKGROUND_LONG_SHIFT_CAP if dept == "生产部" else 0
        for day in workdays:
            hours = 8.0
            if long_left and random.random() < 0.20:
                hours = 12.0
                long_left -= 1
            push(eid, day, hours)
    return rows


def build_attendance(
    employees: list[dict[str, str]], shifts: list[dict[str, object]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seq = 1
    by_emp: dict[str, list[dict[str, object]]] = {}
    for s in shifts:
        by_emp.setdefault(str(s["employee_id"]), []).append(s)

    for emp in employees:
        eid = emp["employee_id"]
        for s in by_emp.get(eid, []):
            day = dt.date.fromisoformat(str(s["date"]))
            hours = float(s["planned_hours"])

            # -- 演示用例 E001 张伟 10-16：出差在外，无打卡 → 缺卡 ---------
            if eid == "E001" and day == TRIP_ABSENT_DAY:
                rows.append(
                    {
                        "record_id": f"A{seq:05d}",
                        "employee_id": eid,
                        "date": day.isoformat(),
                        "check_in": "",
                        "check_out": "",
                        "actual_hours": 0.0,
                        "core_hours_present": 0.0,
                        "status": "absent",
                        "is_rest_day": 1,
                    }
                )
                seq += 1
                continue

            # -- 演示用例 E003 王强：7 次核心时段未在岗 -------------------
            if eid == "E003" and day in WANG_CORE_ABSENT:
                check_in, check_out, core = "15:30", "23:00", 0.5
                status = "normal"
            else:
                late = random.random() < 0.08
                check_in = (
                    f"09:{random.randint(25, 45)}"
                    if late
                    else f"08:{random.randint(35, 58)}"
                )
                end_hour = int(8 + hours + (1 if hours >= 12 else 0))
                check_out = f"{end_hour:02d}:{random.randint(0, 59):02d}"
                core = 6.0
                status = "late" if late else "normal"
                # 小概率缺卡（下班未打卡），制造背景异常
                if random.random() < 0.03:
                    check_out, status = "", "missing_check_out"

            rows.append(
                {
                    "record_id": f"A{seq:05d}",
                    "employee_id": eid,
                    "date": day.isoformat(),
                    "check_in": check_in,
                    "check_out": check_out,
                    "actual_hours": round(
                        hours - (1 if status == "missing_check_out" else 0), 1
                    ),
                    "core_hours_present": core,
                    "status": status,
                    "is_rest_day": 1 if is_rest(day) else 0,
                }
            )
            seq += 1
    return rows


def build_business_trips(employees: list[dict[str, str]]) -> list[dict[str, object]]:
    """出差审批单。E001 张伟 10-16~10-18 武汉为**演示用例**，精确构造。"""
    rows: list[dict[str, object]] = [
        {
            "trip_id": "BT-2026-0017",
            "employee_id": "E001",
            "destination": "武汉",
            "site": "武汉光谷",
            "start_date": TRIP_START.isoformat(),
            "end_date": TRIP_END.isoformat(),
            "purpose": "客户现场设备故障排查与售后工单处理",
            "status": "approved",
        }
    ]
    seq = 2
    peers = [
        e
        for e in employees
        if e["position"] == "售后工程师" and e["employee_id"] != "E001"
    ]
    for emp in peers:
        for _ in range(random.randint(1, 3)):
            start = dt.date(2026, 10, random.randint(1, 26))
            end = start + dt.timedelta(days=random.randint(1, 3))
            if end > dt.date(2026, 10, 31):
                end = dt.date(2026, 10, 31)
            site = random.choice(SITES)
            rows.append(
                {
                    "trip_id": f"BT-2026-{seq:04d}",
                    "employee_id": emp["employee_id"],
                    "destination": site[:2],
                    "site": site,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "purpose": "客户现场巡检与工单处理",
                    "status": "approved",
                }
            )
            seq += 1
    return rows


def build_work_orders(employees: list[dict[str, str]]) -> list[dict[str, object]]:
    """售后工单。两张为**演示用例**：

    - ``SO-2026-0912``（10-16 周五）→ 支撑「异常归因」：缺卡日当天有到场闭环；
    - ``SO-2026-0913``（10-17 周六）→ 支撑「政策问答」：休息日实际提供了劳动。
    """
    rows: list[dict[str, object]] = [
        {
            "order_id": "SO-2026-0912",
            "employee_id": "E001",
            "customer": "武汉光谷希尔顿酒店",
            "site": "武汉光谷",
            "dispatched_at": "2026-10-16 09:40",
            "closed_at": "2026-10-16 10:22",
            "status": "closed",
            "fault_type": "智能马桶盖板无法启动",
        },
        {
            "order_id": "SO-2026-0913",
            "employee_id": "E001",
            "customer": "武汉光谷希尔顿酒店",
            "site": "武汉光谷",
            "dispatched_at": "2026-10-17 09:15",
            "closed_at": "2026-10-17 11:40",
            "status": "closed",
            "fault_type": "同批次设备复检",
        },
    ]
    seq = 913
    peers = [e for e in employees if e["position"] == "售后工程师"]
    for emp in peers:
        for _ in range(random.randint(8, 14)):
            day = dt.date(2026, 10, random.randint(1, 30))
            # 演示用例日期不接受随机工单污染（否则归因/问答的证据集不可控）
            if emp["employee_id"] == "E001" and day in TRIP_DAYS:
                continue
            site = random.choice(SITES)
            rows.append(
                {
                    "order_id": f"SO-2026-{seq}",
                    "employee_id": emp["employee_id"],
                    "customer": f"{site}客户{random.randint(1, 40):02d}号",
                    "site": site,
                    "dispatched_at": f"{day.isoformat()} {random.randint(9, 16):02d}:{random.randint(0, 59):02d}",
                    "closed_at": f"{day.isoformat()} {random.randint(10, 19):02d}:{random.randint(0, 59):02d}",
                    "status": random.choice(
                        ["closed", "closed", "closed", "processing"]
                    ),
                    "fault_type": random.choice(
                        [
                            "龙头漏水",
                            "花洒出水异常",
                            "马桶冲水不畅",
                            "浴柜门板变形",
                            "淋浴房渗水",
                        ]
                    ),
                }
            )
            seq += 1
    return rows


def build_locations(employees: list[dict[str, str]]) -> list[dict[str, object]]:
    """移动定位轨迹。**仅外勤岗（售后工程师）产生**；E001 出差三日为演示用例。"""
    rows: list[dict[str, object]] = [
        {
            "loc_id": "L00001",
            "employee_id": "E001",
            "date": TRIP_ABSENT_DAY.isoformat(),
            "time": "09:58",
            "site": "武汉光谷",
            "latitude": "30.5067",
            "longitude": "114.4056",
        },
        {
            "loc_id": "L00002",
            "employee_id": "E001",
            "date": TRIP_ABSENT_DAY.isoformat(),
            "time": "13:20",
            "site": "武汉光谷",
            "latitude": "30.5102",
            "longitude": "114.3989",
        },
        {
            "loc_id": "L00003",
            "employee_id": "E001",
            "date": TRIP_REST_DAY.isoformat(),
            "time": "09:30",
            "site": "武汉光谷",
            "latitude": "30.5071",
            "longitude": "114.4042",
        },
    ]
    seq = 4
    for emp in employees:
        if emp["position"] != "售后工程师":
            continue
        for day in DAYS:
            if random.random() < 0.45:
                site = random.choice(SITES)
                rows.append(
                    {
                        "loc_id": f"L{seq:05d}",
                        "employee_id": emp["employee_id"],
                        "date": day.isoformat(),
                        "time": f"{random.randint(8, 18):02d}:{random.randint(0, 59):02d}",
                        "site": site,
                        "latitude": f"{30.40 + random.random() * 0.30:.4f}",
                        "longitude": f"{114.20 + random.random() * 0.40:.4f}",
                    }
                )
                seq += 1
    return rows


def build_access(
    employees: list[dict[str, str]], shifts: list[dict[str, object]]
) -> list[dict[str, object]]:
    """门禁刷卡记录。**关键**：E001 张伟 10-17 **故意无记录**（外勤，无门禁设备）。

    这条"缺失"正是归因演示的核心——门禁缺失不能否定出勤（制度四第三条）。
    """
    seq = 1
    rows: list[dict[str, object]] = []
    for s in shifts:
        eid = str(s["employee_id"])
        emp = next(e for e in employees if e["employee_id"] == eid)
        day = dt.date.fromisoformat(str(s["date"]))
        if emp["position"] == "售后工程师":
            # 售后以外勤为主，原则上不刷门禁。
            # **例外**：E001 在总部办公日刷门禁，出差日不刷——
            # 这样「10-16 门禁缺失」才是有效对比证据，而非"他本来就没有"。
            if eid != "E001" or day in TRIP_DAYS:
                continue
        rows.append(
            {
                "access_id": f"AC{seq:06d}",
                "employee_id": eid,
                "date": day.isoformat(),
                "in_time": f"08:{random.randint(20, 58):02d}",
                "out_time": f"{random.randint(17, 22):02d}:{random.randint(0, 59):02d}",
                "gate": "厂区东门",
            }
        )
        seq += 1
    return rows


def build_leaves(employees: list[dict[str, str]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seq = 1
    for _ in range(14):
        emp = random.choice([e for e in employees if e["employee_id"] != "E002"])
        start = dt.date(2026, 10, random.randint(1, 27))
        days = random.randint(1, 3)
        rows.append(
            {
                "leave_id": f"LV{seq:04d}",
                "employee_id": emp["employee_id"],
                "leave_type": random.choice(["年休假", "病假", "事假"]),
                "start_date": start.isoformat(),
                "end_date": (start + dt.timedelta(days=days - 1)).isoformat(),
                "days": days,
                "status": "approved",
            }
        )
        seq += 1
    return rows


def build_overtime(employees: list[dict[str, str]]) -> list[dict[str, object]]:
    """加班单。**演示用例 E004 陈敏**：月累计 22h，已调休 0h → 触发「季度调休未消化」。"""
    rows: list[dict[str, object]] = []
    seq = 1
    for date_str, hours in [
        ("2026-10-11", 6.0),
        ("2026-10-18", 6.0),
        ("2026-10-25", 5.0),
        ("2026-10-31", 5.0),
    ]:
        rows.append(
            {
                "overtime_id": f"OT{seq:04d}",
                "employee_id": "E004",
                "date": date_str,
                "hours": hours,
                "overtime_type": "rest_day",  # 休息日加班 → 优先安排调休（制度三第八条）
                "approved": 1,
                "comp_off_hours": hours,
                "comp_off_used_hours": 0.0,  # 全部未调休
            }
        )
        seq += 1
    for emp in employees:
        if emp["work_time_system"] != "标准工时制" or emp["employee_id"] in (
            # E004 的加班单由上面**精确构造**（22h 全未调休），不接受随机单污染；
            # E003 王强是「弹性时段越界」用例、E005 刘洋是「周工时超限」用例，
            # 随机加班单会让他们**额外**命中「调休未消化」，演示时同一员工出现
            # 两条风险、用例不再干净 —— 演示用例只保留自己那条。（E002 除外：
            # 她**故意**同时命中月加班与连续出勤，用于演示一因多果。）
            "E003",
            "E004",
            "E005",
        ):
            continue
        for _ in range(random.randint(0, 3)):
            day = dt.date(2026, 10, random.randint(1, 30))
            hours = float(random.choice([2, 3, 4]))
            used = hours if random.random() < 0.5 else 0.0
            rows.append(
                {
                    "overtime_id": f"OT{seq:04d}",
                    "employee_id": emp["employee_id"],
                    "date": day.isoformat(),
                    "hours": hours,
                    "overtime_type": random.choice(["workday", "rest_day"]),
                    "approved": 1,
                    "comp_off_hours": hours,
                    "comp_off_used_hours": used,
                }
            )
            seq += 1
    return rows


# -- Markdown → DOCX（标准库 zipfile 手写 OOXML，零依赖）----------------------
_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_HEAD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:document xmlns:w="{_NS}"><w:body>'
)
_DOC_TAIL = "<w:sectPr/></w:body></w:document>"


def _run(text: str, *, bold: bool = False, size: int | None = None) -> str:
    rpr = ""
    if bold or size:
        parts = ["<w:rPr>"]
        if bold:
            parts.append("<w:b/>")
        if size:
            parts.append(f'<w:sz w:val="{size}"/>')
        parts.append("</w:rPr>")
        rpr = "".join(parts)
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _para(text: str, *, bold: bool = False, size: int | None = None) -> str:
    return f"<w:p>{_run(text, bold=bold, size=size)}</w:p>"


def _table(rows: list[list[str]]) -> str:
    out = [
        '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>',
        '<w:tblW w:w="0" w:type="auto"/></w:tblPr>',
    ]
    for r_i, row in enumerate(rows):
        out.append("<w:tr>")
        for cell in row:
            out.append(
                '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>'
                f"{_para(cell, bold=(r_i == 0))}</w:tc>"
            )
        out.append("</w:tr>")
    out.append("</w:tbl>")
    out.append("<w:p/>")
    return "".join(out)


def md_to_docx(md_text: str) -> bytes:
    """把受限 Markdown（标题 / 段落 / 列表 / 表格）转成最小合法 DOCX。"""
    body: list[str] = []
    pending_table: list[list[str]] = []

    def flush_table() -> None:
        nonlocal pending_table
        if pending_table:
            body.append(_table(pending_table))
            pending_table = []

    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_table()
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") and c for c in cells):
                continue  # 分隔行
            pending_table.append(cells)
            continue
        flush_table()
        if line.startswith("### "):
            body.append(_para(line[4:].replace("**", ""), bold=True, size=28))
        elif line.startswith("## "):
            body.append(_para(line[3:].replace("**", ""), bold=True, size=32))
        elif line.startswith("# "):
            body.append(_para(line[2:].replace("**", ""), bold=True, size=40))
        elif line.startswith("---"):
            continue
        else:
            text = line.lstrip("- ").replace("**", "")
            body.append(_para(text))
    flush_table()

    document = _DOC_HEAD + "".join(body) + _DOC_TAIL

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("word/document.xml", document)
    return bio.getvalue()


def write_csv(name: str, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path = OUT_DIR / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name:<28} {len(rows):>5} 行")


def _read_csv(name: str) -> list[dict[str, str]]:
    """回读已落盘的 CSV（自检用，避免重复解析字符串）。"""
    with (OUT_DIR / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    random.seed(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("生成制度文档（DOCX）:")
    for md in sorted(POLICIES_DIR.glob("*.md")):
        docx = md_to_docx(md.read_text(encoding="utf-8"))
        out = OUT_DIR / f"{md.stem}.docx"
        out.write_bytes(docx)
        print(f"  {out.name:<28} {len(docx):>5} 字节")

    print("\n生成业务数据（CSV）:")
    employees = build_employees()
    shifts = build_shifts(employees)
    write_csv("employees.csv", employees)
    write_csv("shifts.csv", shifts)
    write_csv("attendance_records.csv", build_attendance(employees, shifts))
    write_csv("business_trips.csv", build_business_trips(employees))
    write_csv("work_orders.csv", build_work_orders(employees))
    write_csv("location_records.csv", build_locations(employees))
    write_csv("access_records.csv", build_access(employees, shifts))
    write_csv("leave_requests.csv", build_leaves(employees))
    write_csv("overtime_records.csv", build_overtime(employees))

    self_check(shifts)


def self_check(shifts: list[dict[str, object]]) -> None:
    """校验四个演示用例的数据**确实成立**——不成立则演示无法跑通。"""
    print("\n自检（演示用例是否成立）:")

    # E002 李静：月累计工时
    li = [float(s["planned_hours"]) for s in shifts if s["employee_id"] == "E002"]
    li_total = sum(li)
    li_ot = li_total - MONTH_STANDARD_HOURS
    ok = li_ot > MONTH_OVERTIME_CAP
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E002 李静 月累计 {li_total:.0f}h，"
        f"标准 {MONTH_STANDARD_HOURS:.0f}h → 加班 {li_ot:.0f}h "
        f"{'>' if ok else '<='} 上限 {MONTH_OVERTIME_CAP:.0f}h"
    )

    # E002 连续出勤
    li_days = sorted(
        dt.date.fromisoformat(str(s["date"]))
        for s in shifts
        if s["employee_id"] == "E002"
    )
    streak = best = 1
    for a, b in zip(li_days, li_days[1:], strict=False):
        streak = streak + 1 if (b - a).days == 1 else 1
        best = max(best, streak)
    ok = best >= 12
    print(f"  [{'OK ' if ok else 'FAIL'}] E002 李静 最长连续出勤 {best} 天（阈值 12）")

    att_rows = _read_csv("attendance_records.csv")
    acc_rows = _read_csv("access_records.csv")
    ot_rows = _read_csv("overtime_records.csv")

    # E001 张伟 10-16：工作日缺卡 + 无门禁（由出差审批 / 工单 / 定位补证）
    zhang = [
        r
        for r in att_rows
        if r["employee_id"] == "E001" and r["date"] == TRIP_ABSENT_DAY.isoformat()
    ]
    gate = [
        r
        for r in acc_rows
        if r["employee_id"] == "E001" and r["date"] == TRIP_ABSENT_DAY.isoformat()
    ]
    gate_near = [
        r for r in acc_rows if r["employee_id"] == "E001" and r["date"] == "2026-10-15"
    ]
    ok = (
        len(zhang) == 1
        and zhang[0]["status"] == "absent"
        and not zhang[0]["check_in"]
        and not gate
        and len(gate_near) == 1  # 前一日有门禁 → 缺卡日的缺失才构成证据
    )
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E001 张伟 10-16 工作日缺卡"
        f"（{zhang[0]['status'] if zhang else '无记录'}）、当日门禁 {len(gate)} 条、"
        f"前一日门禁 {len(gate_near)} 条 → 出差审批 + 工单 + 定位应能补证"
    )

    # E001 张伟 10-17：休息日出勤（政策问答「算不算加班」的数据前提）
    wo = _read_csv("work_orders.csv")
    rest_wo = [
        r
        for r in wo
        if r["employee_id"] == "E001"
        and r["closed_at"].startswith(TRIP_REST_DAY.isoformat())
    ]
    ok = len(rest_wo) == 1
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E001 张伟 10-17（周六）有已闭环工单 "
        f"{rest_wo[0]['order_id'] if rest_wo else '无'} → 休息日出勤事实成立"
    )

    # E003 王强：核心时段（10:00-16:00）未在岗次数
    wang = sum(
        1
        for r in att_rows
        if r["employee_id"] == "E003" and float(r["core_hours_present"]) < 6.0
    )
    ok = wang > 5
    print(f"  [{'OK ' if ok else 'FAIL'}] E003 王强 核心时段未在岗 {wang} 次（阈值 5）")

    # E004 陈敏：加班已产生调休额度但全部未调休
    chen = [r for r in ot_rows if r["employee_id"] == "E004"]
    ot_hours = sum(float(r["hours"]) for r in chen)
    used = sum(float(r["comp_off_used_hours"]) for r in chen)
    ok = ot_hours > 0 and used == 0
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E004 陈敏 月加班 {ot_hours:.0f}h，"
        f"已调休 {used:.0f}h → 调休未消化"
    )

    # E005 刘洋：**周**工时超限（ISO 周聚合，与规则引擎 engine._rule_weekly_hours 同口径）
    liu_by_week: dict[tuple[int, int], float] = {}
    for r in att_rows:
        if r["employee_id"] != "E005":
            continue
        key = dt.date.fromisoformat(r["date"]).isocalendar()[:2]
        liu_by_week[key] = liu_by_week.get(key, 0.0) + float(r["actual_hours"])
    worst_week, worst_hours = max(liu_by_week.items(), key=lambda kv: kv[1])
    ok = worst_hours > WEEK_STANDARD_HOURS
    print(
        f"  [{'OK ' if ok else 'FAIL'}] E005 刘洋 {worst_week[0]} 年第 "
        f"{worst_week[1]} 周实际工时 {worst_hours:g}h > 周上限 "
        f"{WEEK_STANDARD_HOURS:g}h（阈值严格大于，背景员工恒为 40h ⇒ 不触发）"
    )

    # L11 回归护栏：背景综合制员工**不得**成片触发月加班超限
    emp_rows = _read_csv("employees.csv")
    comp_ids = {
        r["employee_id"]
        for r in emp_rows
        if r["work_time_system"] == "综合计算工时制" and r["employee_id"] != "E002"
    }
    breach = sorted(
        eid
        for eid in comp_ids
        if sum(float(s["planned_hours"]) for s in shifts if s["employee_id"] == eid)
        - MONTH_STANDARD_HOURS
        > MONTH_OVERTIME_CAP
    )
    peak = max(
        (
            sum(float(s["planned_hours"]) for s in shifts if s["employee_id"] == eid)
            for eid in comp_ids
        ),
        default=0.0,
    )
    ok = not breach
    print(
        f"  [{'OK ' if ok else 'FAIL'}] 背景综合制员工 {len(comp_ids)} 人："
        f"月最高 {peak:.0f}h（触发线 {MONTH_STANDARD_HOURS + MONTH_OVERTIME_CAP:.0f}h），"
        f"超限 {len(breach)} 人{'' if ok else ' → ' + ', '.join(breach)}"
    )


if __name__ == "__main__":
    main()
