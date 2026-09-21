"""接缝纪律门禁：把 ADR-0004 §3 的"边界判据"变成可机械执行的门禁。

用法（工作目录 = `backend/`）：

    uv run python scripts/check_seams.py             # 报告（未到期项记 WARN，不阻塞）—— 每 Sprint 收尾用这个
    uv run python scripts/check_seams.py --strict     # WARN 亦判失败 —— 只适用于 Demo-MVP 完成点（v1.4.0，接缝全部到期）
    uv run python scripts/check_seams.py --json       # 机器可读输出

四类判据（依据 ADR-0004 §3 第 4、5 条 + 计划文档 §4.3 / §6.3 / §7.2 / §12 R9）：

1. **接口实现集合 = 登记集合**（ADR-0004 §2.1）——同时拦"多做"（登记外实现，如 `LdapAuthProvider`）
   与"少做"（到期仍无实现）。注意接缝 5 事件出口登记的就是 `db` + `log` **两个**实现，
   所以判据是"集合相等"而不是"数量等于 1"。
2. **`settings.*` 必须有消费者**（ADR-0004 §3 第 5 条）——拦"假做"：配置声明了但代码从不读。
   经 `@property` 间接读取也算消费（如 `settings.max_upload_size_bytes` ⇒ 其引用的
   `max_upload_size_mb`）。**盲区**：本判据只拦"完全无消费者"；B4 `task_retry_multiplier`
   属"读它的地方不全"（`app/services/agents.py` 以 `exp_base` 读它，而任务退避路径没读），
   拦不到，需靠验收项兜底（计划文档附录 T11）。
3. **预留字段双向判据**——`documents` 的 8 个预留字段必须在 ORM 模型存在且可空，
   且**不得出现在 `contracts/openapi.yaml`**。只验一侧会被两种方式绕过：
   只加 3 个字段照样过（`--check` 只看"没多出来"）、或字段泄进契约后 `--check` 反而不报。
4. **登记表一致**（代码 → 文档，单向）——门禁里的登记集合必须能在 ADR-0004 §2.1 的
   第 N 行里逐字找到。缺了就是"改了门禁没改登记表"（否则该改动是静默的）；而反向
   "只改登记表"会由判据 1 报"登记外实现"。两个方向都红 ⇒ 不存在"只改一侧还能过"的漏口。

**版本闸门**：每条判据带 `required_from`。`settings.app_version` 低于该值时，"尚未到位"记 WARN
（不阻塞开发）；达到即自动转 ERROR——**打 tag 那一刻门禁上闸，无需改脚本**。

扫描范围：`app/`（实现与模型）+ `scripts/`（脚本也消费配置）；
**不含 `tests/`**——测试读取配置不构成"生产消费"。
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
CONTRACT_FILE = REPO_ROOT / "contracts" / "openapi.yaml"
CONFIG_FILE = BACKEND_DIR / "app" / "core" / "config.py"
ADR_FILE = REPO_ROOT / "docs" / "adr" / "0004-integration-seams.md"

SCAN_DIRS: tuple[Path, ...] = (BACKEND_DIR / "app", BACKEND_DIR / "scripts")
SKIP_FILES: frozenset[Path] = frozenset(
    {CONFIG_FILE.resolve(), Path(__file__).resolve()}
)

#: 规则生效点：配置消费者判据自 Sprint 5 动工前生效（计划文档 §8.4）
SETTINGS_CONSUMER_FROM = "1.1.0"


@dataclass(frozen=True)
class InterfaceRule:
    """接口的实现集合约束（登记集合出自 ADR-0004 §2.1）。"""

    seam: str
    interface: str
    required_from: str | None
    min_impls: int
    max_impls: int
    allowed: tuple[str, ...] | None = None
    #: 必须在 ADR-0004 §2.1 第 N 行里逐字出现的登记字样；留空则取 `allowed`
    adr_tokens: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class PresenceRule:
    """表 / 目录 / 配置项的到位约束。"""

    seam: str
    kind: str  # table | path | setting
    target: str
    required_from: str | None
    note: str = ""


@dataclass(frozen=True)
class Finding:
    level: str  # ERROR | WARN | OK
    check: str
    message: str


@dataclass
class ClassIndex:
    """按基类名索引的类定义 + 全部类名（用于区分"接口未定义"与"接口无实现"）。"""

    by_base: dict[str, list[tuple[str, str, int]]] = field(default_factory=dict)
    names: set[str] = field(default_factory=set)


# ------------------------------------------------------------------------------
# 判据表：唯一真源在 ADR-0004 §2.1 / §2.2，此处只做"可执行投影"
# ------------------------------------------------------------------------------

INTERFACE_RULES: tuple[InterfaceRule, ...] = (
    InterfaceRule(
        "接缝 1 身份",
        "AuthProvider",
        "1.1.0",
        1,
        1,
        allowed=("LocalAuthProvider",),
    ),
    InterfaceRule(
        "接缝 2 数据接入",
        "IngestionSource",
        None,  # Demo-MVP 不要求：批次 A2 的 0.5 天已用于 8 个预留字段
        0,
        1,
        note="接口收口随 Pro 首个真实数据源落地（计划文档附录 T10）",
    ),
    InterfaceRule(
        "接缝 5 事件出口",
        "EventSink",
        "1.3.0",
        2,
        2,
        adr_tokens=("db", "log"),
        note="登记的就是本地 db + log 两个实现，不是 1 个",
    ),
    InterfaceRule(
        "接缝 6 数据输出",
        "ExportSink",
        "1.4.0",
        1,
        1,
        adr_tokens=("JSON/CSV 实现",),
    ),
)

PRESENCE_RULES: tuple[PresenceRule, ...] = (
    PresenceRule("接缝 1 身份", "path", "app/services/auth", "1.1.0"),
    PresenceRule("接缝 3 模型", "setting", "llm_provider", "1.1.0"),
    PresenceRule("接缝 3 模型", "setting", "parser_provider", "1.1.0"),
    PresenceRule("接缝 4 流水线", "setting", "pipeline_stages", "1.1.0"),
    PresenceRule("接缝 5 事件出口", "table", "domain_events", "1.3.0"),
    PresenceRule("接缝 7 实体映射", "table", "external_refs", "1.3.0"),
    PresenceRule("接缝 8 外部数据导入", "path", "app/services/external_data", "1.3.0"),
    PresenceRule("接缝 6 数据输出", "path", "app/services/export", "1.4.0"),
)

RESERVED_TABLE = "documents"
RESERVED_FIELDS: tuple[str, ...] = (
    "source_type",
    "source_ref",
    "document_key",
    "content_hash",
    "source_version",
    "acl_scope",
    "acl_owner_ref",
    "deleted_at",
)
RESERVED_REQUIRED_FROM = "1.1.0"


# ------------------------------------------------------------------------------
# AST 工具
# ------------------------------------------------------------------------------


def _iter_py_files(roots: tuple[Path, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or path.resolve() in SKIP_FILES:
                continue
            files.append(path)
    return files


def _parse(path: Path) -> ast.Module | None:
    """解析失败（语法错误）返回 None——那是 Ruff 的职责，本门禁不重复报。"""
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _base_name(node: ast.expr) -> str:
    """取基类的末级名字：`auth.AuthProvider` / `AuthProvider[T]` → `AuthProvider`。"""
    text = ast.unparse(node)
    return text.split("[")[0].split(".")[-1].strip()


def _call_has_kw(node: ast.expr | None, name: str, expected: bool) -> bool:
    if not isinstance(node, ast.Call):
        return False
    for keyword in node.keywords:
        if keyword.arg != name:
            continue
        if isinstance(keyword.value, ast.Constant) and keyword.value.value is expected:
            return True
    return False


def _collect_classes() -> ClassIndex:
    index = ClassIndex()
    for path in _iter_py_files((BACKEND_DIR / "app",)):
        module = _parse(path)
        if module is None:
            continue
        rel = path.relative_to(BACKEND_DIR).as_posix()
        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef):
                continue
            index.names.add(node.name)
            for base in node.bases:
                index.by_base.setdefault(_base_name(base), []).append(
                    (node.name, rel, node.lineno)
                )
    return index


def _class_table_name(node: ast.ClassDef) -> str | None:
    for stmt in node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        value = stmt.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == "__tablename__":
                return value.value
    return None


def _collect_tables() -> dict[str, str]:
    tables: dict[str, str] = {}
    for path in _iter_py_files((BACKEND_DIR / "app",)):
        module = _parse(path)
        if module is None:
            continue
        rel = path.relative_to(BACKEND_DIR).as_posix()
        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef):
                continue
            table = _class_table_name(node)
            if table is not None:
                tables[table] = f"{rel}:{node.lineno}"
    return tables


def _collect_table_columns(table: str) -> dict[str, tuple[bool, str]]:
    """返回 {列名: (是否可空, 定义位置)}。"""
    columns: dict[str, tuple[bool, str]] = {}
    for path in _iter_py_files((BACKEND_DIR / "app",)):
        module = _parse(path)
        if module is None:
            continue
        rel = path.relative_to(BACKEND_DIR).as_posix()
        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef) or _class_table_name(node) != table:
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign):
                    continue
                if not isinstance(stmt.target, ast.Name):
                    continue
                nullable = "None" in ast.unparse(stmt.annotation)
                if _call_has_kw(stmt.value, "nullable", True):
                    nullable = True
                if _call_has_kw(stmt.value, "nullable", False):
                    nullable = False
                columns[stmt.target.id] = (nullable, f"{rel}:{stmt.lineno}")
    return columns


def _collect_settings() -> tuple[dict[str, str], dict[str, set[str]]]:
    """返回 (字段名 -> 定义位置, 属性名 -> 其体内引用的 `self.<名>` 集合)。"""
    fields: dict[str, str] = {}
    properties: dict[str, set[str]] = {}
    module = _parse(CONFIG_FILE)
    if module is None:
        return fields, properties
    rel = CONFIG_FILE.relative_to(BACKEND_DIR).as_posix()

    for node in ast.walk(module):
        if not isinstance(node, ast.ClassDef) or node.name != "Settings":
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fields[stmt.target.id] = f"{rel}:{stmt.lineno}"
            if not isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            is_property = any(
                (isinstance(d, ast.Name) and d.id == "property")
                or (isinstance(d, ast.Attribute) and d.attr == "property")
                for d in stmt.decorator_list
            )
            if not is_property:
                continue
            referenced: set[str] = set()
            for inner in ast.walk(stmt):
                if (
                    isinstance(inner, ast.Attribute)
                    and isinstance(inner.value, ast.Name)
                    and inner.value.id == "self"
                ):
                    referenced.add(inner.attr)
            properties[stmt.name] = referenced
    return fields, properties


def _collect_setting_consumers() -> dict[str, set[str]]:
    """返回 {被读取的配置名: {读取它的文件, ...}}——只统计"设置对象上的属性访问"。"""
    consumers: dict[str, set[str]] = {}
    for path in _iter_py_files(SCAN_DIRS):
        module = _parse(path)
        if module is None:
            continue
        rel = path.relative_to(BACKEND_DIR).as_posix()
        for node in ast.walk(module):
            if not isinstance(node, ast.Attribute):
                continue
            try:
                base = ast.unparse(node.value)
            except (AttributeError, ValueError):  # pragma: no cover - 极旧语法兜底
                continue
            # `settings.x` / `get_settings().x` / `self.settings.x` 都算；
            # 无关对象上的同名属性不会命中（要求表达式里出现 settings 字样）
            if "settings" in base.lower():
                consumers.setdefault(node.attr, set()).add(rel)
    return consumers


def _expand_indirect(consumed: set[str], properties: dict[str, set[str]]) -> set[str]:
    """属性间接消费：`settings.dev_org_header_enabled` 被读 ⇒ 其引用的字段也算被消费。"""
    queue = list(consumed)
    while queue:
        name = queue.pop()
        for referenced in properties.get(name, ()):
            if referenced not in consumed:
                consumed.add(referenced)
                queue.append(referenced)
    return consumed


# ------------------------------------------------------------------------------
# 四类判据
# ------------------------------------------------------------------------------


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in re.split(r"[.+\-]", value.strip()):
        if not chunk.isdigit():
            break
        parts.append(int(chunk))
    return tuple(parts) or (0,)


def _is_due(required_from: str | None, current: str) -> bool:
    return required_from is not None and _version_tuple(current) >= _version_tuple(
        required_from
    )


def _gate(required_from: str | None) -> str:
    """未到期判据的统一后缀：方括号形式，接在任何句尾都读得通。"""
    if required_from is None:
        return "［Demo-MVP 阶段不要求，暂记 WARN］"
    return f"［未到期：{required_from} 起要求，暂记 WARN］"


def _check_interfaces(index: ClassIndex, version: str, findings: list[Finding]) -> None:
    check = "接口实现集合"
    for rule in INTERFACE_RULES:
        impls = [
            item
            for item in index.by_base.get(rule.interface, [])
            if item[0] != rule.interface
        ]
        names = sorted({name for name, _, _ in impls})
        where = (
            "、".join(f"{name}({rel}:{line})" for name, rel, line in sorted(impls))
            or "无"
        )
        defined = rule.interface in index.names
        due = _is_due(rule.required_from, version)
        tail = "" if due else f" {_gate(rule.required_from)}"
        note = f"；{rule.note}" if rule.note else ""

        if rule.allowed is not None:
            expected = set(rule.allowed)
            extra = sorted(set(names) - expected)
            missing = sorted(expected - set(names))
            if extra:
                findings.append(
                    Finding(
                        "ERROR",
                        check,
                        f"{rule.seam} {rule.interface}：出现登记外实现 {extra}"
                        f"——超出 ADR-0004 §2.1 登记集合 {sorted(expected)}，"
                        f"属越界集成（Pro / Enterprise 范围）。现有实现：{where}。"
                        f"若这是有意新增的正式实现：先扩写 ADR-0004 §2.1 第 "
                        f"{_seam_number(rule.seam)} 行登记，再改本脚本的 allowed，"
                        f"两处一致后本判据才会转 OK",
                    )
                )
            if missing:
                findings.append(
                    Finding(
                        "ERROR" if due else "WARN",
                        check,
                        f"{rule.seam} {rule.interface}：缺少登记实现 {missing}"
                        f"（登记集合 {sorted(expected)}；"
                        f"{'接口已定义' if defined else '接口尚未定义'}）{note}{tail}",
                    )
                )
            if not extra and not missing:
                findings.append(
                    Finding(
                        "OK",
                        check,
                        f"{rule.seam} {rule.interface}：实现集合 = {sorted(expected)}"
                        f"，无登记外实现",
                    )
                )
        else:
            count = len(names)
            if count > rule.max_impls:
                findings.append(
                    Finding(
                        "ERROR",
                        check,
                        f"{rule.seam} {rule.interface}：实现数 {count} 超过登记上限 "
                        f"{rule.max_impls}——疑似越界集成。现有实现：{where}",
                    )
                )
            elif count < rule.min_impls:
                findings.append(
                    Finding(
                        "ERROR" if due else "WARN",
                        check,
                        f"{rule.seam} {rule.interface}：实现数 {count} < 登记下限 "
                        f"{rule.min_impls}"
                        f"（{'接口已定义' if defined else '接口尚未定义'}）{note}{tail}",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "OK",
                        check,
                        f"{rule.seam} {rule.interface}：实现数 {count} 在登记区间 "
                        f"[{rule.min_impls}, {rule.max_impls}]，现有实现：{where}",
                    )
                )


def _adr_seam_rows(text: str) -> dict[str, str]:
    """取 ADR-0004 §2.1 的表格行：{接缝号: 行原文}（先出现的优先，§4 的同号行不覆盖）。"""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"\|\s*(\d+)\s*\|", line)
        if match:
            rows.setdefault(match.group(1), line)
    return rows


def _seam_number(seam: str) -> str:
    """`接缝 5 事件出口` → `5`（缺号返回空串，随后按"登记行缺失"报 ERROR）。"""
    match = re.search(r"(\d+)", seam)
    return match.group(1) if match else ""


def _check_adr_registry(findings: list[Finding]) -> None:
    """判据 4：门禁登记集合必须能在 ADR-0004 §2.1 的第 N 行里逐字找到。

    方向是 **代码 → 文档**：门禁认账的实现类，登记表必须写；反之（只改文档）
    由判据 1 报"登记外实现"。因此"只改一侧还能过"的漏口被两侧夹死。
    文档 §4「未来如何扩展」列的是**尚未**实现的类，故意不参与核对（不做反向判据）。
    """
    check = "登记表一致"
    if not ADR_FILE.is_file():
        findings.append(
            Finding(
                "ERROR",
                check,
                f"登记真源不存在：{ADR_FILE.as_posix()}——登记集合无从核对，禁止静默放行",
            )
        )
        return
    rows = _adr_seam_rows(ADR_FILE.read_text(encoding="utf-8"))
    for rule in INTERFACE_RULES:
        expected = rule.adr_tokens or rule.allowed or ()
        if not expected:
            continue  # 无登记实现（如接缝 2）无需核对
        number = _seam_number(rule.seam)
        row = rows.get(number)
        if row is None:
            findings.append(
                Finding(
                    "ERROR",
                    check,
                    f"{rule.seam}：ADR-0004 §2.1 里找不到第 {number} 行登记"
                    f"——登记集合 {list(expected)} 无处可查",
                )
            )
            continue
        missing = [token for token in expected if token not in row]
        if missing:
            findings.append(
                Finding(
                    "ERROR",
                    check,
                    f"{rule.seam} {rule.interface}：登记集合 {list(expected)} 中的 "
                    f"{missing} 未出现在 ADR-0004 §2.1 第 {number} 行——"
                    f"先扩写登记行、再改门禁，两处必须一致（ADR-0004 §3 第 4 条）",
                )
            )
        else:
            findings.append(
                Finding(
                    "OK",
                    check,
                    f"{rule.seam} {rule.interface}：登记集合 {list(expected)} "
                    f"与 ADR-0004 §2.1 第 {number} 行一致",
                )
            )


def _check_presence(
    tables: dict[str, str],
    version: str,
    consumed: set[str],
    findings: list[Finding],
) -> None:
    check = "接缝落点到位"
    for rule in PRESENCE_RULES:
        due = _is_due(rule.required_from, version)
        level = "ERROR" if due else "WARN"
        tail = "" if due else f" {_gate(rule.required_from)}"

        if rule.kind == "path":
            exists = (BACKEND_DIR / rule.target).is_dir()
            if not exists:
                findings.append(
                    Finding(
                        level,
                        check,
                        f"{rule.seam}：{rule.target}/ 不存在（接口收口落点）{tail}",
                    )
                )
        elif rule.kind == "table":
            if rule.target not in tables:
                findings.append(
                    Finding(
                        level,
                        check,
                        f"{rule.seam}：表 {rule.target} 未在 ORM 模型声明{tail}",
                    )
                )
        elif rule.kind == "setting":
            if rule.target not in consumed:
                findings.append(
                    Finding(
                        level,
                        check,
                        f"{rule.seam}：settings.{rule.target} 未定义或无人读取"
                        f"（配置项必须有消费者）{tail}",
                    )
                )


def _check_settings_consumers(
    fields: dict[str, str],
    properties: dict[str, set[str]],
    consumers: dict[str, set[str]],
    version: str,
    findings: list[Finding],
) -> None:
    check = "配置消费者"
    consumed = _expand_indirect(set(consumers), properties)
    due = _is_due(SETTINGS_CONSUMER_FROM, version)
    unconsumed = [name for name in sorted(fields) if name not in consumed]

    if not unconsumed:
        findings.append(
            Finding("OK", check, f"Settings 全部 {len(fields)} 个字段均有消费者代码行")
        )
        return
    for name in unconsumed:
        findings.append(
            Finding(
                "ERROR" if due else "WARN",
                check,
                f"settings.{name} 无消费者（定义于 {fields[name]}）"
                f"——无消费者的配置不得提交（ADR-0004 §3 第 5 条；"
                f"此类配置改与不改都不生效）"
                + ("" if due else f" {_gate(SETTINGS_CONSUMER_FROM)}"),
            )
        )


def _check_reserved_fields(
    columns: dict[str, tuple[bool, str]],
    contract_text: str,
    version: str,
    findings: list[Finding],
) -> None:
    check = "预留字段双向判据"
    due = _is_due(RESERVED_REQUIRED_FROM, version)
    leaked = 0
    missing: list[str] = []

    for name in RESERVED_FIELDS:
        if re.search(rf"^\s*{name}\s*:", contract_text, flags=re.MULTILINE):
            leaked += 1
            findings.append(
                Finding(
                    "ERROR",
                    check,
                    f"{name} 出现在 contracts/openapi.yaml——预留字段不得进 API 契约"
                    f"（ADR-0004 §3 第 1 条）：请从 Pydantic schema 移除后重新导出",
                )
            )
        info = columns.get(name)
        if info is None:
            missing.append(name)
            continue
        nullable, location = info
        if not nullable:
            findings.append(
                Finding(
                    "ERROR",
                    check,
                    f"{RESERVED_TABLE}.{name} 非 nullable（{location}）"
                    f"——预留字段必须可空",
                )
            )
    if missing:
        findings.append(
            Finding(
                "ERROR" if due else "WARN",
                check,
                f"{RESERVED_TABLE} 缺少 {len(missing)}/{len(RESERVED_FIELDS)} 个预留字段："
                f"{missing}" + ("" if due else f" {_gate(RESERVED_REQUIRED_FROM)}"),
            )
        )
    if not missing and not leaked:
        findings.append(
            Finding(
                "OK",
                check,
                f"{RESERVED_TABLE} 的 {len(RESERVED_FIELDS)} 个预留字段齐全且可空，"
                f"且均未出现在契约中",
            )
        )


# ------------------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------------------


def _current_version() -> str:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from app.core.config import get_settings

    return get_settings().app_version


def main(argv: list[str]) -> int:
    strict = "--strict" in argv[1:]
    as_json = "--json" in argv[1:]

    version = _current_version()
    index = _collect_classes()
    fields, properties = _collect_settings()
    consumers = _collect_setting_consumers()
    consumed = _expand_indirect(set(consumers), properties)
    columns = _collect_table_columns(RESERVED_TABLE)
    contract_text = (
        CONTRACT_FILE.read_text(encoding="utf-8") if CONTRACT_FILE.is_file() else ""
    )

    findings: list[Finding] = []
    _check_interfaces(index, version, findings)
    _check_adr_registry(findings)
    _check_presence(_collect_tables(), version, consumed, findings)
    _check_settings_consumers(fields, properties, consumers, version, findings)
    _check_reserved_fields(columns, contract_text, version, findings)

    errors = [f for f in findings if f.level == "ERROR"]
    warnings = [f for f in findings if f.level == "WARN"]

    if as_json:
        print(
            json.dumps(
                {
                    "app_version": version,
                    "strict": strict,
                    "findings": [
                        {"level": f.level, "check": f.check, "message": f.message}
                        for f in findings
                    ],
                    "summary": {
                        "error": len(errors),
                        "warn": len(warnings),
                        "ok": sum(1 for f in findings if f.level == "OK"),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("=== 接缝纪律门禁（ADR-0004 §3）===")
        print(f"应用版本：{version}（各判据按 required_from 自动上闸）")
        print(
            "模式："
            + ("--strict（WARN 亦判失败）" if strict else "默认（未到期项记 WARN）")
        )
        current = ""
        for finding in findings:
            if finding.check != current:
                current = finding.check
                print(f"\n--- {current} ---")
            icon = {"ERROR": "[FAIL]", "WARN": "[WARN]", "OK": "[OK]"}[finding.level]
            print(f"  {icon} {finding.message}")
        print(
            f"\n汇总：ERROR {len(errors)} / WARN {len(warnings)} / "
            f"OK {sum(1 for f in findings if f.level == 'OK')}"
        )

    if errors:
        if not as_json:
            print(
                "\n[FAIL] 存在越界或未到位的接缝项，详见上方 [FAIL]",
                file=sys.stderr,
            )
        return 1
    if strict and warnings:
        if not as_json:
            print(
                "\n[FAIL] --strict：仍有未到期项（WARN）——--strict 只适用于 "
                "Demo-MVP 完成点（v1.4.0，接缝全部到期）；"
                "Sprint 收尾请用默认档并要求 ERROR = 0",
                file=sys.stderr,
            )
        return 1
    if not as_json:
        print("[OK] 接缝纪律检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
