"""接缝接口签名快照（ADR-0004 §3 第 6 条 / 护栏 **G-11**）。

八个接缝是**客户插件的唯一接入面**（ADR-0007 §3.2）。用户裁决：**付费升
V2.0 时插件才需重新开发** ⇒ 同一大版本内，插件不得因打补丁而失效。

本脚本把「接口长什么样」从人的记忆变成可机械比对的事实：

    uv run python scripts/extract_seam_signatures.py            # 打印当前签名
    uv run python scripts/extract_seam_signatures.py --check     # 与快照逐字比对（CI）
    uv run python scripts/extract_seam_signatures.py --update    # 重写快照（bump MAJOR 时）

**为什么必须机械判**：补丁若改一行 ``AuthProvider.authenticate()`` 的参数，
客户的 LDAP 适配就废了，且**要到补丁后的某次登录才炸**——这是"静默失效"，
人工评审拦不住。

与 ``check_seams.py`` 的分工：后者管「实现类有几个」（集合不多不少），
本脚本管「接口长什么样」（签名不变）。两条互补，缺一则插件可能在客户
现场静默失效。
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

SNAPSHOT_PATH = BACKEND_ROOT / "tests" / "snapshots" / "seam_signatures.json"

#: 冻结的接口（module, class）。
#:
#: **只冻结已存在的接口**——给一个尚不存在的接口冻结签名没有意义：
#: 接缝 2 ``IngestionSource`` 当前 0 实现、接缝 9 ``LicenseProvider`` 尚未落地
#: （ADR-0006）。两者实现后并入本集合；并入本身即 MAJOR 级变更，须注明
#: ``breaking``（ADR-0004 §3 第 6 条）。
FROZEN_CLASSES: tuple[tuple[str, str], ...] = (
    ("app.services.auth.base", "AuthProvider"),
    ("app.services.events.base", "EventSink"),
    ("app.services.export.base", "ExportSink"),
)

SNAPSHOT_VERSION = 1


def _annotation(annotation: object) -> str | None:
    """把注解归一成**稳定**的字符串，避免把内存地址 / 路径写进快照。

    模块普遍带 ``from __future__ import annotations`` ⇒ 注解已是字符串，原样返回；
    否则取 ``__qualname__``（``Settings`` 而非 ``<class 'app.core.config.Settings'>``）。
    """
    if annotation is inspect.Parameter.empty:
        return None
    if isinstance(annotation, str):
        return annotation
    qualname = getattr(annotation, "__qualname__", None)
    return qualname if isinstance(qualname, str) else str(annotation)


def _signature_of(func: object) -> dict[str, Any]:
    """序列化一个方法的签名：参数名 / kind / 注解 / 默认值。"""
    signature = inspect.signature(func)  # type: ignore[arg-type]
    params: list[dict[str, Any]] = []
    for name, param in signature.parameters.items():
        if name in ("self", "cls"):
            continue  # 接收者不是接口契约的一部分
        params.append(
            {
                "name": name,
                "kind": str(param.kind),
                "annotation": _annotation(param.annotation),
                "default": (
                    None
                    if param.default is inspect.Parameter.empty
                    else repr(param.default)
                ),
            }
        )
    return {
        "params": params,
        "return": _annotation(signature.return_annotation),
    }


def collect() -> dict[str, Any]:
    """采集当前代码里全部冻结接口的公开方法签名。"""
    classes: dict[str, Any] = {}
    for module_name, class_name in FROZEN_CLASSES:
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        methods: dict[str, Any] = {}
        for name, member in sorted(vars(cls).items()):
            if name.startswith("_"):
                continue  # 私有 / dunder 不算接入面
            if not callable(member):
                continue
            methods[name] = _signature_of(member)
        classes[f"{module_name}.{class_name}"] = methods
    return {"version": SNAPSHOT_VERSION, "classes": classes}


def load_snapshot() -> dict[str, Any]:
    """读取已提交的快照；不存在则返回空结构（由调用方判定为"待生成"）。"""
    if not SNAPSHOT_PATH.exists():
        return {}
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def diff(current: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    """逐字比对，返回人类可读的差异列表（空列表 = 一致）。"""
    problems: list[str] = []
    old_classes: dict[str, Any] = snapshot.get("classes", {})
    new_classes: dict[str, Any] = current.get("classes", {})

    for key in sorted(set(old_classes) | set(new_classes)):
        if key not in new_classes:
            problems.append(f"接口消失：{key}")
            continue
        if key not in old_classes:
            problems.append(f"接口新增：{key}（须 bump MAJOR 并注明 breaking）")
            continue
        old_methods: dict[str, Any] = old_classes[key]
        new_methods: dict[str, Any] = new_classes[key]
        for method in sorted(set(old_methods) | set(new_methods)):
            if method not in new_methods:
                problems.append(f"{key}.{method} 消失")
            elif method not in old_methods:
                problems.append(f"{key}.{method} 新增（须 bump MAJOR）")
            elif old_methods[method] != new_methods[method]:
                problems.append(
                    f"{key}.{method} 签名变更：\n"
                    f"    快照: {json.dumps(old_methods[method], ensure_ascii=False, sort_keys=True)}\n"
                    f"    当前: {json.dumps(new_methods[method], ensure_ascii=False, sort_keys=True)}"
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="与快照逐字比对；不一致非零退出（CI 用）",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="重写快照文件（仅在 bump MAJOR 并注明 breaking 时使用）",
    )
    args = parser.parse_args()

    current = collect()

    if args.update:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[OK] 快照已更新：{SNAPSHOT_PATH}")
        return 0

    if args.check:
        snapshot = load_snapshot()
        if not snapshot:
            print(f"[FAIL] 快照不存在：{SNAPSHOT_PATH}（先跑 --update 生成）")
            return 1
        problems = diff(current, snapshot)
        if problems:
            print("[FAIL] 接缝接口签名与快照不一致（同大版本内不得变更）：")
            for problem in problems:
                print(f"  - {problem}")
            print(
                "\n若为**有意**的破坏性变更：bump MAJOR 并在提交信息注明 breaking，"
                "然后 uv run python scripts/extract_seam_signatures.py --update"
            )
            return 1
        print("[OK] 接缝接口签名与快照逐字一致")
        return 0

    print(json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
