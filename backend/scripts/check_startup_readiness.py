#!/usr/bin/env python3
"""开工自检：把护栏的**真实状态**读出来。

为什么需要这个脚本
------------------
需求基线 `docs/delivery-requirements-and-guardrails.md` 里的 G 编号，
**一大半是 `@pytest.mark.xfail` 骨架**——意思是：

    pytest 全绿  ≠  护栏在拦

只看 CI 绿就宣称"做完了"，正是这套体系要防的事。但人工去逐个核对哪些是 `xfail`、
哪些是真的在拦、哪些又因为"校验来源压根不存在"而恒绿，**太容易漏**——
所以把它做成脚本，让**每个阶段的开工第一步**都有同一个机器判据。

本脚本**不跑测试**（只解析源码，秒级完成），把护栏分成四档：

* 🟢 **已生效** —— 无 `xfail`、**也不会被跳过** ⇒ 测试红就是它拦的
* 🔵 **条件跳过** —— 带 `skipif`、或依赖的 fixture 内会 `pytest.skip` ⇒
  **这一条在当前环境里可能压根没跑**，"CI 绿"证明不了它拦住了什么
* 🟡 **挂起** —— 有 `xfail`，CI 绿但它没在拦任何东西
* ⚠️ **恒绿失效** —— 挂起，且**校验来源尚不存在**；即便去掉 `xfail` 也只是一场空跑
  （纪律 **R-9「恒绿即失效」**）

🔵 这一档为什么必须有（**P7-B**，实证见 `changes/P7-A/integration-log.md` §5.2）：
本地不起 Neo4j 时全量 `pytest` 由 **930 passed 掉到 923 passed**，少的 7 条**全绿通过、
无人察觉**，而本脚本两次输出**一模一样** —— 若「以机器输出为准」这句要成立，
机器就必须把"根本没跑"也读出来，而不是把它当成"在拦"。

另外顺带检查几条**开工地雷**（是否切 PG、`plugins/` 是否存在等）。

用法
----
    uv run python scripts/check_startup_readiness.py
    uv run python scripts/check_startup_readiness.py --self-test   # 脚本自带自测

退出码
------
正常报告恒为 **0**（它是**报告**而不是门禁——门禁由 pytest / CI 承担）；
仅 `--self-test` 有失败用例时返回 **1**。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[0]
TESTS_DIR = BACKEND_ROOT / "tests"

#: **一律扫全部 test_*.py**，靠函数名 `test_g<N>_` 认出护栏。
#: 只扫 `test_guardrails_*.py` 会漏掉**已生效**的那批（它们未必住在 guardrails 文件里，
#: 例如 G-11 在 `test_seam_signature_snapshot.py`）——那等于把"已建成"报成"没做"。
#: 本脚本要防的是**两个方向**的错，不只"以没做冒充做了"。
TEST_PATTERN = "test_*.py"

#: `test_g11_xxx` -> G-11
_G_RE = re.compile(r"^test_(g\d+)_", re.IGNORECASE)

#: 静态求值失败时的哨兵（不能用 None——None 本身可能是合法值）
_MISSING = object()

#: `_eval` 允许的 Path 方法：够用即可，不允许就判不出来，绝不猜
_PATH_METHODS = ("exists", "is_dir", "is_file", "resolve")

#: 从 docstring / reason 里揪出这个护栏守的是哪条需求
_DR_RE = re.compile(r"DR-[A-Z]\d+")

#: 从 config.py 抠出 ``database_url`` 的**字段默认值**。
#: ⚠️ **为什么不能用 `"sqlite" not in cfg.lower()` 了**：config.py 里有
#: ``_guard_production_sqlite``——那是 G-21 的**反向守卫本体，永远不许删**，
#: 于是按子串判的话这条地雷会**永久 NG**，把「别信文档、信脚本」这条纪律
#: 反过头来变成误导。要判的是**默认值**，不是文件里有没有这个字样。
_CFG_DB_URL_RE = re.compile(
    r'^\s*database_url\s*:\s*str\s*=\s*["\']([^"\']+)', re.MULTILINE
)

#: `.env.example` 的 ``DATABASE_URL`` **赋值行**（只看赋值行：注释里回顾口径历史
#: 是允许的，把注释也算上会重蹈上面那条同型误报）。
_ENV_DB_URL_RE = re.compile(r"^\s*DATABASE_URL\s*=\s*(\S+)", re.MULTILINE)

#: 「来源是否存在」探测：G 编号 -> 依赖的路径（相对仓库根）。
#: 这些路径不存在时，对应护栏即便转正也只是在做空转。
SOURCE_PATHS: dict[str, str] = {
    "G-12": "deploy/variants",
    "G-14": "plugins",
    "G-22": "plugins",
    "G-23": "backend/app/services/license",
}

#: **范围边界提示**：G 编号 -> 它**不覆盖**的部分。
#: 为什么要有这张表：护栏转绿只代表"它验的那件事成立"，但护栏名字听起来往往
#: 比它实际验的更大——G-18 绿灯会被读成"账号体系做完了"，而它只验"表存在且形状对"。
#: **文档里写了没人翻**，所以把边界塞进这份每次开工都要看的报告里。
SCOPE_CAVEATS: dict[str, str] = {
    "G-18": (
        "⚠️ 只验「users 表存在且形状正确」——它当前 0 消费者；"
        "SSO / RBAC / License 分属 P2-C / P2-B / P4，不得因本条绿灯宣称完成"
    ),
    "G-24": (
        "⚠️ 只验「矩阵存在 + 强制校验入口存在」，**不验具体权限值**（属实现决策）；"
        "且**测试默认主体是 admin** ⇒ 默认路径验不到拒绝分支，"
        "拒绝分支只由 tests/test_rbac.py 用非默认 actor 验；"
        "另：RLS 策略归 P3，本条绿灯**不代表**租户隔离完成"
    ),
}


def _dotted_name(node: ast.expr) -> str:
    """把 `pytest.mark.xfail` 这样的属性链还原成字符串。"""
    if isinstance(node, ast.Attribute):
        return f"{_dotted_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _eval(node: ast.expr, env: dict[str, object]) -> object:
    """尽力静态求值 `xfail` 的条件表达式；判不了返回 `_MISSING`。

    只支持本项目实际用到的形态：常值 / 名字 / `Path` 链式拼路径 /
    `.exists()` `.is_dir()` `.is_file()` `.resolve()` / `not` / `/`。
    **宁可判不出来，也不猜。**
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env.get(node.id, _MISSING)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        val = _eval(node.operand, env)
        return (not val) if isinstance(val, bool) else _MISSING
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, right = _eval(node.left, env), _eval(node.right, env)
        if isinstance(left, Path) and isinstance(right, str):
            return left / right
        return _MISSING
    if isinstance(node, ast.Attribute):
        owner = _eval(node.value, env)
        if isinstance(owner, Path) and node.attr == "parent":
            return owner.parent
        return _MISSING
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "Path" and len(node.args) == 1:
            arg = _eval(node.args[0], env)
            return Path(arg) if isinstance(arg, str) else _MISSING
        if isinstance(fn, ast.Attribute) and not node.args and not node.keywords:
            owner = _eval(fn.value, env)
            if isinstance(owner, Path) and fn.attr in _PATH_METHODS:
                return getattr(owner, fn.attr)()
        return _MISSING
    return _MISSING


def _module_env(tree: ast.Module, test_path: Path) -> dict[str, object]:
    """收集模块级可静态求值的常量，供 `_eval` 解 `SNAPSHOT.exists()` 这类条件。"""
    env: dict[str, object] = {"__file__": str(test_path)}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                env[target.id] = _eval(node.value, env)
    return env


def _file_level_gid(tree: ast.Module) -> str | None:
    """模块 docstring **首行**里的 `G-<N>`——专项测试文件用它标注整文件的归属。

    例如 `test_seam_signature_snapshot.py` 首行是「G-11：接缝接口签名冻结」。
    """
    matched = re.match(r"G-(\d+)", _first_line(ast.get_docstring(tree) or ""))
    return f"G-{matched.group(1)}" if matched else None


def _xfail_state(node: ast.FunctionDef, env: dict[str, object]) -> tuple[bool, str]:
    """返回 ``(是否真的挂起, reason)``。

    **为什么不能"见 xfail 就判挂起"**：有些护栏的 xfail 是**带条件**的
    （G-11 是 ``xfail(not SNAPSHOT.exists(), ...)``），快照一生成它就自动生效了。
    照"有装饰器即挂起"来判，会把**已建好的护栏报成没做** ——
    那是本脚本同样要防的错：不仅要防"没做冒充做了"，也要防"做完了却以为没做"。
    """
    for deco in node.decorator_list:
        call = deco if isinstance(deco, ast.Call) else None
        target = call.func if call else deco
        if not _dotted_name(target).endswith(".xfail"):
            continue
        reason = ""
        if call:
            for kw in call.keywords:
                if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                    reason = str(kw.value.value)
        suspended = True
        if call and call.args:
            evaluated = _eval(call.args[0], env)
            suspended = evaluated if isinstance(evaluated, bool) else True
        return suspended, reason or "(未写 reason)"
    return False, ""


def _first_line(text: str) -> str:
    return next((ln.strip() for ln in text.splitlines() if ln.strip()), "")


# ---------------------------------------------------------------------------
# 「可能被跳过」的识别（P7-B）——第三种弱化形态，此前完全不参与判定
# ---------------------------------------------------------------------------


def _is_fixture(node: ast.FunctionDef) -> bool:
    """``@pytest.fixture`` / ``@pytest.fixture(...)`` 都算。"""
    for deco in node.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        if _dotted_name(target) == "pytest.fixture":
            return True
    return False


def _calls_skip(node: ast.AST) -> str | None:
    """返回函数体内第一处 ``pytest.skip(...)`` 的 reason 表达式；没有则 ``None``。"""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call) or not sub.args:
            continue
        if _dotted_name(sub.func) in ("pytest.skip", "pytest.mark.skip"):
            try:
                return ast.unparse(sub.args[0])
            except Exception:  # noqa: BLE001 —— 个别版本 unparse 会抛，退回常值
                if isinstance(sub.args[0], ast.Constant):
                    return str(sub.args[0].value)
                return "(动态 reason)"
    return None


def _fixture_index(trees: dict[Path, ast.Module]) -> dict[str, ast.FunctionDef]:
    """``{fixture 名: 定义节点}``；同名以最后一个为准（pytest 本身的遮蔽规则亦然）。"""
    index: dict[str, ast.FunctionDef] = {}
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and _is_fixture(node):
                index[node.name] = node
    return index


def _skip_via_fixture(
    fn: ast.FunctionDef,
    fixtures: dict[str, ast.FunctionDef],
    _seen: set[str] | None = None,
) -> str | None:
    """测试所依赖的 fixture（**含递归依赖**）里有没有会 skip 的。

    为什么要递归：fixture 常常再依赖 fixture，只看直接一层会**隔一级就漏**，
    而漏掉的后果正是把它们判成"在拦"——即本脚本要防的头号错误。
    """
    seen = _seen if _seen is not None else set()
    args = [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
    for arg in args:
        name = arg.arg
        if name in seen or name not in fixtures:
            continue
        seen.add(name)
        fix = fixtures[name]
        reason = _calls_skip(fix)
        if reason:
            return f"依赖的 fixture `{name}` 会 skip：{reason[:48]}"
        deeper = _skip_via_fixture(fix, fixtures, seen)
        if deeper:
            return deeper
    return None


def _skip_state(
    node: ast.FunctionDef,
    env: dict[str, object],
    fixtures: dict[str, ast.FunctionDef],
) -> tuple[bool, str]:
    """返回 ``(是否可能被跳过, 原因)``。

    **保守原则：判不出来就当"会跳过"。** 宁可多报一行待确认，也不许把"根本没跑"
    误报成"在拦" —— 后者正是 P7-A §5.2 那个盲区。
    """
    for deco in node.decorator_list:
        call = deco if isinstance(deco, ast.Call) else None
        target = call.func if call else deco
        if not _dotted_name(target).endswith(".skipif"):
            continue
        reason = ""
        if call:
            for kw in call.keywords:
                if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                    reason = str(kw.value.value)
        if not call or not call.args:
            return True, reason or "skipif（无条件）"
        evaluated = _eval(call.args[0], env)
        # 非 bool（静态判不出来）或求得为 True ⇒ 都按"会跳"记
        if not isinstance(evaluated, bool) or evaluated:
            return True, reason or "skipif 条件为真 / 无法静态求值"
    via = _skip_via_fixture(node, fixtures)
    if via:
        return True, via
    return False, ""


def collect_guardrails(
    tests_dir: Path | None = None,
) -> dict[str, list[dict[str, object]]]:
    """返回 ``{G 编号: [该编号下的测试, ...]}``。

    一个 G 编号**可能对应多条测试**（例如 G-21 既有挂起的主断言、又有必须始终通过的
    反向守卫），所以这里按编号归成列表——早先用单一 dict 会把前一条覆盖掉。

    G 编号的来源，按优先级：

      1. 函数名 ``test_g11_xxx`` —— guardrails 系列用这个
      2. 模块 docstring **首行**的 ``G-<N>`` —— 专项文件（如 G-11 的
         ``test_seam_signature_snapshot.py``）整文件归属同一编号

    ⚠️ **连 `conftest.py` 一起扫**（P7-B）：fixture 常常住在 conftest 里，
    不扫它就认不出「这条用例依赖的 fixture 会 skip」——那正是本批要补的盲区。
    """
    root = tests_dir or TESTS_DIR
    trees: dict[Path, ast.Module] = {}
    for pattern in (TEST_PATTERN, "conftest.py"):
        for path in sorted(root.rglob(pattern)):
            trees[path] = ast.parse(path.read_text(encoding="utf-8"))
    fixtures = _fixture_index(trees)

    found: dict[str, list[dict[str, object]]] = {}
    for path, tree in trees.items():
        env = _module_env(tree, path)
        file_gid = _file_level_gid(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if _is_fixture(node):
                continue  # fixture 是装置，不是测试用例
            matched = _G_RE.match(node.name)
            if matched:
                gid = "G-" + matched.group(1)[1:]
            elif file_gid and node.name.startswith("test_"):
                # 专项文件里也住着辅助函数（如 `_load_module`），只收真正的测试。
                gid = file_gid
            else:
                continue
            suspended, reason = _xfail_state(node, env)
            skipped, skip_reason = _skip_state(node, env, fixtures)
            doc = ast.get_docstring(node) or ""
            blob = f"{doc} {reason} {skip_reason}"
            found.setdefault(gid, []).append(
                {
                    "file": path.stem,
                    "name": node.name,
                    "suspended": suspended,
                    "reason": _first_line(reason),
                    "skipped": skipped,
                    "skip_reason": _first_line(skip_reason),
                    "summary": _first_line(doc),
                    "drs": sorted(set(_DR_RE.findall(blob))),
                }
            )
    return found


def _exists(relpath: str) -> bool:
    return (REPO_ROOT / relpath).exists()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def reality_checks() -> list[tuple[str, bool, str]]:
    """开工地雷：返回 ``(检查项, 是否通过, 未通过时的说明)``。"""
    cfg = _read(BACKEND_ROOT / "app" / "core" / "config.py")
    env = _read(BACKEND_ROOT / ".env.example")
    compose = _read(REPO_ROOT / "deploy" / "docker-compose.yml")
    models = _read(BACKEND_ROOT / "app" / "db" / "models.py")
    cfg_match = _CFG_DB_URL_RE.search(cfg)
    default_url = cfg_match.group(1) if cfg_match else ""
    env_match = _ENV_DB_URL_RE.search(env)
    env_url = env_match.group(1) if env_match else ""
    return [
        (
            "已切 PostgreSQL（DR-B1）",
            default_url.startswith("postgresql"),
            f"config.py 的 database_url 默认值为 {default_url or '（未找到）'}",
        ),
        (
            "compose 含 PG 服务（DR-B1 / G-20）",
            "postgres" in compose.lower(),
            "deploy/docker-compose.yml 无 PG 服务",
        ),
        (
            ".env.example 非 SQLite（DR-B3 / G-21）",
            env_url.startswith("postgresql"),
            f".env.example 的 DATABASE_URL 为 {env_url or '（未找到）'}",
        ),
        (
            "plugins/ 已建（DR-A2）",
            _exists("plugins"),
            "G-14 / G-22 目前没有可校验的对象",
        ),
        (
            "deploy/variants/ 已建（DR-A1 / A3）",
            _exists("deploy/variants"),
            "G-12 目前没有可校验的对象",
        ),
        (
            "License 子系统已建（DR-C1）",
            _exists("backend/app/services/license"),
            "G-23 目前没有可校验的对象",
        ),
        (
            "users 表已建（DR-B13，P2 第一步）",
            bool(re.search(r"^class\s+User\b", models, re.MULTILINE)),
            "SSO / RBAC / License 席位三者都依赖它",
        ),
    ]


def _sym(name: str) -> str:
    """取记号；终端编码不支持时自动降级成 ASCII。

    为什么要写这一段：Windows PowerShell 的默认编码是 GBK，**打不出 emoji**，
    直接 print 会抛 ``UnicodeEncodeError`` 把整份报告崩掉——而报告崩掉恰恰发生在
    最需要读它的时候（开工第一步）。与其让使用者手动 ``chcp 65001``，不如自适应。
    """
    emoji = {
        "active": "\U0001f7e2",
        "conditional": "\U0001f535",
        "partial": "\U0001f7e0",
        "suspended": "\U0001f7e1",
        "warn": "⚠️",
        "shield": "\U0001f6e1",
        "mine": "\U0001f4a3",
        "ok": "✅",
        "no": "❌",
        "arrow": "↳",
        "imply": "⇒",
    }
    ascii_only = {
        "active": "[OK]",
        "conditional": "[SK]",
        "partial": "[~~]",
        "suspended": "[--]",
        "warn": "[!!]",
        "shield": "[SG]",
        "mine": "[!!]",
        "ok": "[OK]",
        "no": "[NG]",
        "arrow": "->",
        "imply": "=>",
    }
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        emoji[name].encode(enc)
    except (UnicodeEncodeError, LookupError, AttributeError):
        return ascii_only[name]
    return emoji[name]


def _safe(text: object) -> str:
    """压到当前 stdout 能打印的范围。

    reason / 说明文字是从**测试源码**里抽出来的，将来谁在里面写个箭头符号，
    报告就会在终端编码不支持时崩掉——所以统一在这里兜一层。
    """
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    return str(text).encode(enc, errors="replace").decode(enc, errors="replace")


def main() -> int:
    guardrails = collect_guardrails()

    def _all_susp(items: list[dict[str, object]]) -> bool:
        return all(bool(i["suspended"]) for i in items)

    def _any_susp(items: list[dict[str, object]]) -> bool:
        return any(bool(i["suspended"]) for i in items)

    ok_ = _sym("active")
    skip_ = _sym("conditional")
    part_ = _sym("partial")
    susp_ = _sym("suspended")
    warn_ = _sym("warn")
    shield_ = _sym("shield")
    mine_ = _sym("mine")
    yes_ = _sym("ok")
    no_ = _sym("no")
    arrow_ = _sym("arrow")
    imply_ = _sym("imply")

    def _any(items: list[dict[str, object]], key: str) -> bool:
        return any(bool(i[key]) for i in items)

    # 归属优先级：**xfail 挂起 > 可跳过 > 在拦**。
    # 理由：一条同时带 xfail 与 skip 的用例，要按「一定没拦」记 ——
    # 不许让较轻的状态把较重的状态盖住。
    suspended = {g: i for g, i in guardrails.items() if _all_susp(i)}
    partial = {g: i for g, i in guardrails.items() if _any_susp(i) and not _all_susp(i)}
    rest = {g: i for g, i in guardrails.items() if not _any_susp(i)}
    conditional = {g: i for g, i in rest.items() if _any(i, "skipped")}
    active = {g: i for g, i in rest.items() if not _any(i, "skipped")}

    def _show(sym: str, title: str, group: dict[str, list], note: str = "") -> None:
        print(f"\n{sym} {title}：{len(group)} 条")
        if note:
            print(f"   {note}")
        for gid, items in sorted(group.items()):
            drs = sorted({str(d) for i in items for d in i["drs"]})  # type: ignore[misc]
            dr = " ".join(f"[{d}]" for d in drs)
            print(f"   {gid:<6}{dr:<20}{len(items)} 项")
            missing = SOURCE_PATHS.get(gid)
            if missing and not _exists(missing):
                tip = f"{warn_} 恒绿失效：{missing}/ 不存在 {imply_} 转正前先看这里"
                print(f"          {_safe(tip)}")
            caveat = SCOPE_CAVEATS.get(gid)
            if caveat:
                print(f"          {_safe(caveat)}")
            for item in items:
                # 逐条标状态——「部分生效」那组必须看得出到底哪条在拦、哪条躺平
                if item["suspended"]:
                    mark = susp_
                elif item["skipped"]:
                    mark = skip_
                else:
                    mark = ok_
                print(f"          {mark} {item['name']}")
                if item["suspended"] and item["reason"]:
                    print(f"             {arrow_} {_safe(item['reason'])[:64]}")
                elif item["skipped"] and item["skip_reason"]:
                    print(f"             {arrow_} {_safe(item['skip_reason'])[:64]}")

    print("=" * 78)
    print("开工自检 —— 护栏真实状态（解析测试源码得出，不跑测试）")
    print("=" * 78)

    _show(ok_, "已生效（真在拦，测试红就是它拦的）", active)
    _show(
        skip_,
        "条件跳过（**这次可能压根没跑** ⇒ 「CI 绿」证明不了它拦住任何东西）",
        conditional,
        f"{imply_} 想把它管的需求算完成，先让这些用例**真的跑起来**（补环境 / 拆必跑子集）",
    )
    _show(
        part_,
        "部分生效（一半在拦、一半挂起）",
        partial,
        f"{imply_} 挂在其中的那一条所管的需求，仍**不得**宣称完成",
    )
    _show(
        susp_,
        "挂起（CI 绿，但没在拦任何东西）",
        suspended,
        f"{imply_} 对应需求一律**不得宣称完成**",
    )

    print(f"\n{shield_} 反向守卫（必须**始终通过**，删了等于拆护栏）")
    for gid, items in sorted(guardrails.items()):
        for item in items:
            if "guard_still" in str(item["name"]):
                print(f"   {gid:<6}{item['name']}")

    print(f"\n{mine_} 开工地雷")
    failures = 0
    for label, ok, hint in reality_checks():
        if ok:
            print(f"   {yes_} {_safe(label)}")
        else:
            failures += 1
            print(f"   {no_} {_safe(label)} -- {_safe(hint)}")

    print("\n" + "=" * 78)
    print("行动指引")
    print("-" * 78)
    print(
        f"1. 要动某条 DR 前：先看它的 G 编号在哪个区；"
        f"{ok_} 才叫真的拦住，{skip_} / {part_} / {susp_} 都不算"
        f"（P8「零缺口」要的是全 {ok_}）。"
    )
    print(
        f"2. 想让 {susp_} 转正：让对应测试**真的通过**，再删掉它的 @pytest.mark.xfail。"
    )
    print("   只是往测试里加断言、却留着 xfail —— 不算转正。")
    print(
        f"3. {warn_} 恒绿失效的：先让校验对象**真的存在**，转正才有意义（纪律 R-9）。"
    )
    print(f"4. 本次地雷 {failures} 项 {imply_} 开工前先看一遍 {mine_} 区。")
    print("=" * 78)
    return 0


#: `--self-test` 的固定用例。每条 = ``(标题, 方向, 源码, 期望)``。
#:
#: ⚠️ **两个方向都不可少**：只测"弱化形态被认出来"会奖励一个**把所有东西都判成
#: 没在拦**的实现（那样当然全绿）；反向用例专门盯着这种溃败。
_SELFTEST_CASES: list[tuple[str, str, str, dict[str, bool]]] = [
    (
        "skipif 条件为真 ⇒ 不得算「在拦」（模拟本地无图：`skipif(not _REAL)`）",
        "正向",
        """
import pytest

_REAL = False

@pytest.mark.skipif(not _REAL, reason="need real graph")
def test_g97_decorator_skip():
    assert False
""",
        {"suspended": False, "skipped": True},
    ),
    (
        "条件无法静态求值 ⇒ **保守**判「会跳过」",
        "正向",
        """
import os

import pytest

@pytest.mark.skipif(os.environ.get("GRAPH_REAL"), reason="only when set")
def test_g96_unknown_condition():
    assert True
""",
        {"suspended": False, "skipped": True},
    ),
    (
        "fixture 内 pytest.skip ⇒ 不得算「在拦」",
        "正向",
        """
import pytest

@pytest.fixture
def real_driver():
    pytest.skip("local no neo4j")

def test_g95_fixture_skip(real_driver):
    assert False
""",
        {"suspended": False, "skipped": True},
    ),
    (
        "fixture 依赖 fixture（**隔一级**）⇒ 仍须认出来",
        "正向",
        """
import pytest

@pytest.fixture
def driver():
    pytest.skip("local no neo4j")

@pytest.fixture
def real_graph(driver):
    return driver

def test_g94_nested_fixture_skip(real_graph):
    assert False
""",
        {"suspended": False, "skipped": True},
    ),
    (
        "skipif 条件为假 ⇒ **仍须**算「在拦」（不许把好护栏降级）",
        "反向",
        """
import pytest

_REAL = False

@pytest.mark.skipif(_REAL, reason="need real graph")
def test_g93_condition_false():
    assert True
""",
        {"suspended": False, "skipped": False},
    ),
    (
        "无任何弱化标记 ⇒ **仍须**算「在拦」",
        "反向",
        """
def test_g92_plain_guard():
    assert True
""",
        {"suspended": False, "skipped": False},
    ),
    (
        "xfail 仍须判为**挂起**（不许被新逻辑吃成 skip）",
        "反向",
        """
import pytest

@pytest.mark.xfail(strict=True, reason="需求未完成")
def test_g91_xfail_still_suspended():
    assert False
""",
        {"suspended": True, "skipped": False},
    ),
]


def _self_test() -> int:
    """脚本自带自测：写最小源码 → 走**同一套** ``collect_guardrails()`` → 断言档位。

    为什么必须有它（P7-A 把本事项单独立批就是因为这个原因）：
    本脚本存在的意义是「别信文档、信机器」。那么判定逻辑本身一旦改动，
    **它自己就得有证据** —— 否则「机器说它在拦」这句话又是无根的。
    """
    import tempfile

    failures: list[str] = []
    for idx, (title, _direction, src, expect) in enumerate(_SELFTEST_CASES):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / f"test_selftest_{idx}.py").write_text(src, encoding="utf-8")
            found = collect_guardrails(root)
            items = [i for group in found.values() for i in group]
            if len(items) != 1:
                failures.append(f"{title}：期望收集到 1 条用例，实测 {len(items)} 条")
                continue
            item = items[0]
            for key, want in expect.items():
                got = bool(item.get(key))
                if got != want:
                    failures.append(f"{title}：`{key}` 期望 {want}，实测 {got}")

    forward = sum(1 for c in _SELFTEST_CASES if c[1] == "正向")
    backward = sum(1 for c in _SELFTEST_CASES if c[1] == "反向")
    print("=" * 78)
    print("check_startup_readiness 自检（--self-test）")
    print("=" * 78)
    print(
        f"用例 {len(_SELFTEST_CASES)} 条：正向 {forward}（别漏报）/ 反向 {backward}（别误报）"
    )
    if failures:
        for line in failures:
            print(f"   {_sym('no')} {_safe(line)}")
        print(f"\n{_sym('no')} {len(failures)} 条未通过 ⇒ 退出码 1")
        return 1
    print(f"   {_sym('ok')} 全部通过：弱化形态被认出，且好护栏没有被降级")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    sys.exit(main())
