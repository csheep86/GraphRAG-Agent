#!/usr/bin/env python3
"""开发中回切点（drift check）：拿**当前这一批改动**去对照边界。

为什么需要这个脚本
------------------
`check_startup_readiness.py` 管**开工前**（护栏到底有没有在拦），
CI 管**提交后**（ruff / pytest / 契约零漂移）。中间那一段——
**写代码写到一半、开始"顺手"多做的时候**——一直是空的。

而本仓库的历史病例几乎全部集中在这一段：

* `changes/Sprint9/c0-recon.md:72` ——「要让它产生 diff 就得新增端点（**范围蔓延**）」
* `changes/archive/2026-09-24-Sprint8.1/proposal.md:27` ——「不改签名…那是动既有行为，属范围蔓延」
* 同上 `:73` ——「重造要人工下载 + 花钱，且属范围蔓延」
* 同上 `:103` ——「若发现不改签名就落不了审计，**先停下来升级**——那是范围蔓延，不是顺手」
* `tests/README.md:12` ——「提交即真相」陷阱；`changes/Sprint9/integration-log.md`
  §10 / §11 的**两批同型病**

这几处的共同点**不是不知道边界**（Non-goals 早就写在 proposal 模板里了），
而是**写完以后没有人回去对照**。本脚本就是把"回去对照"这个动作自动化。

五条判据，**全部只看本次 diff**（不看全仓库）——这样才不会一上来就红一片，
让报告变成没人看的噪音。**宁可漏报，不可噪音**：噪音多的护栏比没护栏更危险（纪律 R-9）。

| 编号 | 判据 | 防的是什么 |
|---|---|---|
| **S1** | 本批次 proposal 存在，且其 **Non-goals** 非空（并把它打印出来） | **无边界开发** |
| **S2** | 改动量超阈值（文件数 / 新增行）⇒ 提示拆批 | **一次性摊太大** |
| **S3** | `config.py` 里**新增** Settings 字段 ⇒ `.env.example` 是否同步 | 加了开关没留模板 |
| **S4** | 改了 `schemas/` `routes/` ⇒ 该跑 `export_openapi --check`；改了 `contracts/` ⇒ 该跑 `gen:api` | 契约漂移 |
| **S5** | 新增的 `app/**/*.py` **没有任何地方引用** | **过度开发**（提前写了没人要的模块） |

用法
----
    uv run python scripts/check_session_drift.py              # 对照未提交改动
    uv run python scripts/check_session_drift.py --since HEAD~3  # 对照最近 3 个提交
    uv run python scripts/check_session_drift.py --max-files 15

什么时候跑（建议写进批次任务 closing 步骤）
----------------------------------------
1. **每个批次 / 子任务收尾时** —— 在说"做完了"之前；
2. **改完一个模块、正准备改下一个时** —— 中途回切，别攒到最后；
3. **CI 红的时候** —— 先看是不是批次本身摊太大了，而不是先去改测试让它绿。

退出码
------
恒为 **0**。它是**报告**不是门禁——`CI` 才是门禁。
但 **[S1] 没有批次边界** 与 **[S5] 孤儿模块** 两条出现时，
按 `CODEBUDDY.md` 的要求应当**停下来去向用户确认**，而不是继续往下写。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[0]

#: 本批次边界声明的候选**目录**（不含 archive —— 归档批次不再指导当前开发）。
#: 前缀**不写死** `Sprint*`：`changes/P1/` 这类阶段批次（见 `docs/delivery-plan.md` §3）
#: 匹配不到 ⇒ S1 会静默拿**别的**批次的 Non-goals 来对照本批改动——报告看起来正常，
#: 对照的却是错的边界（2026-10-01 实踩：整个 P1 期间 S1 一直在报 Sprint10.5 的 5 条边界）。
_BATCH_DIR_GLOBS = ("changes/Sprint*", "changes/P*")

#: proposal 里声明边界的几种节标题写法，历史上有过两种叫法
_NONGOALS_HEADINGS = ("non-goals", "明确不做", "边界")

#: 这两个从来不参与命令（一个是构建产物目录，一个是包声明）
_SKIP_PY = ("__init__.py", "conftest.py")


# --------------------------------------------------------------------------- #
# 终端编码自适应（Windows PowerShell 默认 GBK，直接 print 会崩掉整份报告）
# --------------------------------------------------------------------------- #
def _sym(name: str) -> str:
    emoji = {
        "warn": "⚠️",
        "ok": "✅",
        "no": "❌",
        "arrow": "↳",
        "imply": "⇒",
        "mine": "💣",
        "note": "📌",
    }
    plain = {
        "warn": "[!!]",
        "ok": "[OK]",
        "no": "[NG]",
        "arrow": "->",
        "imply": "=>",
        "mine": "[!]",
        "note": "[*]",
    }
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        emoji[name].encode(enc)
    except (UnicodeEncodeError, LookupError, AttributeError):
        return plain[name]
    return emoji[name]


def _safe(text: object) -> str:
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    return str(text).encode(enc, errors="replace").decode(enc, errors="replace")


# --------------------------------------------------------------------------- #
# git
# --------------------------------------------------------------------------- #
def _git(*args: str) -> str:
    """在仓库根执行 git；失败一律返回空串（报告脚本不该因为 git 炸掉）。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:  # pragma: no cover - git 不在 PATH
        print(f"{_sym('no')} git 不可用：{exc}")
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout


def _changed_files(since: str) -> dict[str, str]:
    """返回 ``{路径: 状态}``，状态取 name-status 的首字母（A/M/D/…）。"""
    out = _git("diff", "--name-status", since)
    result: dict[str, str] = {}
    for line in out.splitlines():
        if "\t" not in line:
            continue
        status, _, path = line.partition("\t")
        # 重命名跑一趟会给出两条（R 旧 -> 新），只关心新路径
        result[path.strip()] = status.strip()[:1]
    return result


def _diff_text(since: str, path: str) -> str:
    return _git("diff", since, "--", path)


def _added_lines(diff_text: str) -> list[str]:
    return [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


# --------------------------------------------------------------------------- #
# S1：批次边界
# --------------------------------------------------------------------------- #
def _batch_recency(batch: Path) -> float:
    """批次目录的「最近活跃度」：取其自身与目录下 md 的最大 mtime。

    两条理由：目录 mtime 只在文件**增删**时变（改既有 md 不变），光看它会把
    一直在推进的批次判成"不活跃"；而 md 之外的内容（子目录里的 py / png）
    不该影响"边界声明文档"的新旧判断。读不到就退回 0.0，不让它炸掉整份报告。
    """
    try:
        stamps = [batch.stat().st_mtime]
    except OSError:  # pragma: no cover - 目录被并发删除
        return 0.0
    try:
        stamps.extend(doc.stat().st_mtime for doc in batch.glob("*.md"))
    except OSError:  # pragma: no cover - 同上
        pass
    return max(stamps)


def _latest_proposal() -> Path | None:
    """找**处于进行中**（未归档）的最新批次文档。

    为什么排除 archive/：归档批次描述的是历史工作，拿它的 Non-goals 来对照
    今天这批改动，会得出完全跑偏的结论。
    """
    candidates: list[Path] = []
    for pattern in _BATCH_DIR_GLOBS:
        candidates.extend(
            path
            for path in REPO_ROOT.glob(pattern)
            if path.is_dir() and "archive" not in path.parts
        )
    if not candidates:
        return None
    # 按「批次内文档的最近改动时间」取正在推进的那一个。
    # 只看目录 mtime 会漏判：目录 mtime **只**随文件增删而变，改既有 md 不变
    # （⇒ 一直在推进的批次可能永远排不到最前）。
    batch = max(candidates, key=_batch_recency)
    docs = sorted(batch.glob("*.md"))
    # `proposal.md` 优先：S1 的定义就是「本批次 proposal 的 Non-goals」。
    # 批次里还有别的 md（如 integration-log.md）也写了边界节，纯按文件名排序会先命中它
    # ⇒ 对照的仍是"第二手"边界。把它排到最前，它没写边界时再退而求其次。
    docs.sort(key=lambda path: (path.name != "proposal.md", path.name))
    for doc in docs:
        if _nongoals_of(doc):
            return doc
    # 该批次没有任何文档写了边界节 —— 取 proposal 让它挨骂
    proposal = batch / "proposal.md"
    return proposal if proposal.exists() else None


def _nongoals_of(doc: Path) -> list[str]:
    """抽出文档里的 Non-goals 条目；标题底下到下一个二级标题之间的 `- ` 行。"""
    try:
        lines = doc.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    capture = False
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            capture = any(h in title.lower() for h in _NONGOALS_HEADINGS)
            continue
        # 三种项目符号都得认：**数字列表是最常见的写法**——Sprint10.5/proposal.md
        # 的「明确不做」就是 `1. 2. 3.`，只认 `-`/`*` 会把有边界的批次报成没边界，
        # 那是**误报**；而误报比没报告更有害（R-9 的同款教训）。
        if capture and re.match(r"^([-*]|\d+[.)])\s", stripped):
            body = re.sub(r"^([-*]|\d+[.)])\s*", "", stripped).strip()
            if body:
                items.append(body)
    return items


def check_batch_boundary() -> tuple[bool, str]:
    doc = _latest_proposal()
    if doc is None:
        return False, "找不到进行中的批次文档（changes/Sprint*/proposal.md）"
    items = _nongoals_of(doc)
    if not items:
        return False, f"{doc.relative_to(REPO_ROOT)} 没有 Non-goals / 「明确不做」节"
    return True, str(doc.relative_to(REPO_ROOT))


# --------------------------------------------------------------------------- #
# S2：批规模
# --------------------------------------------------------------------------- #
def count_added_lines(since: str, files: dict[str, str]) -> int:
    total = 0
    for path, status in files.items():
        if status == "D":
            continue
        if not path.endswith((".py", ".ts", ".tsx", ".yaml", ".yml", ".md")):
            continue
        total += len(_added_lines(_diff_text(since, path)))
    return total


# --------------------------------------------------------------------------- #
# S3：新增 Settings 字段 vs .env.example
# --------------------------------------------------------------------------- #
def check_settings_sync(since: str) -> list[str]:
    """本批在 ``config.py`` 里**新增**的 Settings 字段，是否同步进了 ``.env.example``。

    只做**增量**：全量比对会一次性红掉 4 条（`app_name` / `api_prefix` 本来就不该
    出现在 .env；`task_retry_multiplier` 是 R-7 已登记的无消费者配置）——那等于
    一上来就喊狼来了。**增量比对保证了每一条都确实是本批次的账。**
    """
    rel = "backend/app/core/config.py"
    if rel not in _changed_files(since):
        return []

    added_defs = set()
    for line in _added_lines(_diff_text(since, rel)):
        # 只认 Settings 类里的字段赋值（`name: type = ...`）
        match = re.match(r"^\s{4}([a-z][a-z0-9_]*)\s*:\s*[A-Za-z_\[]", line)
        if match:
            added_defs.add(match.group(1))

    if not added_defs:
        return []

    example_rel = "backend/.env.example"
    try:
        example = (REPO_ROOT / example_rel).read_text(encoding="utf-8")
    except OSError:
        return [f"{example_rel} 读不到，无法核对"]

    accepted = {
        k.split("=")[0].strip()
        for k in re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=", example, re.M)
    }
    documented = {
        k.strip() for k in re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\b", example, re.M)
    }

    problems = []
    for field in sorted(added_defs):
        key = field.upper()
        if key in accepted or key in documented:
            continue
        problems.append(
            f"config.py 新增 `{field}` => .env.example 未同步 "
            f"（期望出现 {key}=）；没有模板，下一个部署的人无从知道它存在"
        )
    return problems


# --------------------------------------------------------------------------- #
# S4：契约联动
# --------------------------------------------------------------------------- #
#: 改这些 ⇒ 契约可能漂移
_CONTRACT_TRIGGERS = (
    "backend/app/schemas/",
    "backend/app/api/v1/routes/",
)


def check_contract_duty(files: dict[str, str]) -> list[str]:
    duties: list[str] = []
    if any(p.startswith(_CONTRACT_TRIGGERS) for p in files):
        duties.append(
            "改了 schemas/ 或 routes/ => 跑 "
            "`uv run python scripts/export_openapi.py --check` 确认契约零漂移"
        )
    if any(p.startswith("contracts/") for p in files):
        duties.append(
            "改了 contracts/openapi.yaml => 前端跑 `npm run gen:api`，"
            "并按「契约同步铁律」四步核对 TS 类型与 Mock"
        )
    return duties


# --------------------------------------------------------------------------- #
# S5：孤儿模块（过度开发的典型形态）
# --------------------------------------------------------------------------- #
def check_orphan_modules(files: dict[str, str]) -> list[str]:
    """本批**新增**的 ``backend/app/**/*.py``，有没有被任何已跟踪源码引用。

    提前写"以后大概会用"的模块，是本项目反复出现的过度开发形态
    （对照组：`ADR-0003 §3.7` 要求的效果正好相反——东西要少而有用）。
    注意：接口 / 实现类的**注册**常常靠字符串或装饰器路由，所以本判据
    只做**文本出现与否**的粗筛，命中的**自己去确认**，脚本不替你判断。
    """
    new_files = [
        p
        for p, status in files.items()
        if status == "A"
        and p.startswith("backend/app/")
        and p.endswith(".py")
        and Path(p).name not in _SKIP_PY
    ]
    if not new_files:
        return []

    sources: list[str] = []
    for tracked in _git("ls-files", "backend").splitlines():
        if tracked.endswith(".py"):
            sources.append(tracked)

    problems: list[str] = []
    for f in new_files:
        stem = Path(f).stem
        referenced = False
        for src in sources:
            if src == f:
                continue
            try:
                text = (REPO_ROOT / src).read_text(encoding="utf-8")
            except OSError:
                continue
            if re.search(rf"\b{re.escape(stem)}\b", text):
                referenced = True
                break
        if not referenced:
            problems.append(
                f"{f}：全仓库没有任何 .py 提到 `{stem}` => "
                "如果它是本批次要用的，接线是不是漏了？如果以后才用，那是提前开发"
            )
    return problems


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="开发中回切点：本批改动 vs 批次边界")
    parser.add_argument(
        "--since",
        default="HEAD",
        help="对照的基线（默认 HEAD = 所有未提交改动；可用 HEAD~3 看最近几个提交）",
    )
    parser.add_argument("--max-files", type=int, default=25, help="改动文件数告警阈值")
    parser.add_argument("--max-lines", type=int, default=600, help="新增行数告警阈值")
    args = parser.parse_args()

    files = _changed_files(args.since)
    if not files:
        print(f"{_sym('ok')} 与 {args.since} 之间没有改动 —— 无需回切")
        return 0

    warn_ = _sym("warn")
    ok_ = _sym("ok")
    no_ = _sym("no")
    arrow_ = _sym("arrow")
    imply_ = _sym("imply")
    mine_ = _sym("mine")
    note_ = _sym("note")

    print("=" * 78)
    print(f"开发中回切点 —— 本批改动 vs 批次边界（基线 {args.since}）")
    print("=" * 78)

    blockers = 0

    # -- S1 批次边界 ------------------------------------------------------- #
    print(f"\n{mine_} S1 批次边界（防无边界开发）")
    has_boundary, where = check_batch_boundary()
    if has_boundary:
        doc = _nongoals_of(REPO_ROOT / where)
        print(f"   {ok_} {_safe(where)} 声明了 {len(doc)} 条边界")
        print(f"   {arrow_} 逐条对照下面这些，确认本批改动**没有越过**：")
        for item in doc:
            print(f"      - {_safe(item)[:70]}")
    else:
        blockers += 1
        print(f"   {no_} {_safe(where)}")
        print(f"   {arrow_} 没有边界 {imply_} 任何改动都合法 {imply_} 范围必然蔓延。")
        print("      先补 Non-goals 再往下写（模板见 specs/_template/proposal.md）。")

    # -- S2 批规模 --------------------------------------------------------- #
    print(f"\n{mine_} S2 批规模（防一次性摊太大）")
    added = count_added_lines(args.since, files)
    oversize = []
    if len(files) > args.max_files:
        oversize.append(f"改动 {len(files)} 个文件 > 阈值 {args.max_files}")
    if added > args.max_lines:
        oversize.append(f"新增 {added} 行 > 阈值 {args.max_lines}")
    if oversize:
        blockers += 1
        print(f"   {warn_} {'；'.join(oversize)}")
        print(f"   {arrow_} 摊太大是范围蔓延最常见的入口：先是「顺手改一个」,")
        print("      然后失败时找不到是哪一处。**建议拆批再提交**。")
    else:
        print(f"   {ok_} {len(files)} 个文件 / 新增 {added} 行 —— 在阈值内")

    # -- S3 配置同步 ------------------------------------------------------- #
    print(f"\n{mine_} S3 配置同步（加了开关要留模板）")
    sync_problems = check_settings_sync(args.since)
    if sync_problems:
        blockers += 1
        for item in sync_problems:
            print(f"   {no_} {_safe(item)}")
    else:
        print(f"   {ok_} 本批新增的 Settings 字段均已在 .env.example 就位")

    # -- S4 契约联动 ------------------------------------------------------- #
    print(f"\n{mine_} S4 契约联动（改了 schemas / routes 就该复核契约）")
    duties = check_contract_duty(files)
    if duties:
        for item in duties:
            print(f"   {note_} {_safe(item)}")
        print(f"   {arrow_} 这几步不是「提交后再说」——契约漂移正是外人看不见的那种债。")
    else:
        print("   " + f"{ok_} 本批未触及契约相关路径")

    # -- S5 孤儿模块 ------------------------------------------------------- #
    print(f"\n{mine_} S5 孤儿模块（防过度开发）")
    orphans = check_orphan_modules(files)
    if orphans:
        blockers += 1
        for item in orphans:
            print(f"   {warn_} {_safe(item)}")
        print(f"   {arrow_} 命中只代表「没被提到」，**不等于**该删。")
        print("      但必须先回答：它属于本批次的哪一条需求？")
    else:
        print(f"   {ok_} 本批新增的 app 模块均已被引用（或本批无新增）")

    # -- 收尾 -------------------------------------------------------------- #
    print("\n" + "=" * 78)
    if blockers:
        print(f"{warn_} 本次回切发现 {blockers} 类需要处理的项")
        print(f"{imply_} 出口纪律：在声称「做完了」之前发现的，都是**还算便宜**的——")
        print("   该补边界的先停下来补；属于重构的，挪出本批次，不许混进来。")
    else:
        print(f"{ok_} 本次回切未发现漂移 —— 可以进入下一子任务")
    print("   三条自检问句（脚本拦不住，必须自己答）：")
    print("   1) 这批改动里，有没有一样东西是「顺便做的」？它属于哪条 DR/G？")
    print("   2) 有没有为了躲一个坑而绕路的实现？（绕出来的简化，日后都会回来收费）")
    print("   3) 验收判据是真跑出来的，还是读代码得出的？")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
