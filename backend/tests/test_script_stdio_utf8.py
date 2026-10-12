"""门禁：`scripts/` 下**可直接运行的脚本**必须自带 stdio UTF-8 兜底。

**它防的是什么**
Windows 控制台默认 GBK（cp936）。脚本只要打印一个非 ASCII 字符（`⇒`、中文），
就会抛 ``UnicodeEncodeError: 'gbk' codec can't encode character`` —— 而 CI 跑在
Linux 上**永远不会复现** ⇒ 这个坑只能靠"有人在本机踩到"发现，于是**反复复发**：

- ``changes/P6-D1b/integration-log.md`` 的 ``F-P6D1b-3`` 就是它（当时的处置 =
  给那一个脚本手工加一行）；
- 之后每个新脚本都靠作者**记得**贴一段 ⇒ 漏了 18 个，其中恰好包括
  ``check_startup_readiness.py`` / ``check_seams.py`` / ``check_session_drift.py``
  / ``check_patch_contract_freeze.py`` ——**本机开工自检的四个入口全在漏的名单里**。

**为什么判据是"源码里要有"，而不是"跑一遍看崩不崩"**
跑一遍在 Linux 上恒绿（GBK 不存在）⇒ 那是**恒绿失效**（纪律 **R-9**）。
判据必须能在 Linux 上拦住"漏加"，所以直接扫源码。

**已知技术债（本门禁**不**拦，如实登记）**
既有约 22 个脚本只 reconfigure 了 ``stdout``、**没管 ``stderr``** ⇒ 异常 traceback
里带中文时**仍会崩**。统一它们属另批工作，本门禁只保证"**不能一段都没有**"。

**位置的已知边界**
片段按既有约定放在** import 块之后** ⇒ ``app`` 导入期（loguru 初始化就会打中文
WARNING）的输出**不在保护范围内**。实测那类输出是中文（GBK 可编码）⇒ 只显示乱码、
**不会崩**；真正会崩的 ``⇒`` 等字符不会出现在导入期。要彻底覆盖就得把片段挪到
所有 import 之前（随之要处理 ``import sys`` 的顺序与重复），收益边际小，留另批。
"""

from __future__ import annotations

import pathlib

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"

#: 低于这个数 ⇒ 多半是目录搬走了 / glob 写错了 ⇒ 门禁会**静默恒绿**（R-9）。
EXPECTED_MIN_SCRIPTS = 30


def _runnable_scripts() -> list[pathlib.Path]:
    """``scripts/`` 下带 ``if __name__ == "__main__":`` 的脚本（= 会被直接跑的）。"""
    return sorted(
        path
        for path in SCRIPTS_DIR.glob("*.py")
        if '__name__ == "__main__"' in path.read_text(encoding="utf-8")
    )


def test_gate_is_not_vacuous() -> None:
    """**反向守卫**：目录空了 / 路径错了 ⇒ 下面那条会恒绿，这里先红。"""
    scripts = _runnable_scripts()
    assert len(scripts) >= EXPECTED_MIN_SCRIPTS, (
        f"只找到 {len(scripts)} 个可执行脚本（期望 ≥ {EXPECTED_MIN_SCRIPTS}）"
        f" ⇒ scripts/ 目录或 glob 可能已经变了，门禁正在静默失效"
    )


def test_runnable_scripts_force_utf8_stdio() -> None:
    """每个可直接运行的脚本都必须把 stdio 强制成 UTF-8（**防 Windows GBK 崩**）。

    判据刻意只查**两个字的组合**（``reconfigure`` + ``utf-8``），不规定具体写法：
    现有脚本有的是 ``sys.stdout.reconfigure``、有的是循环两个 stream、有的带
    ``errors="replace"`` —— 统一写法归另批，这里只保证**不能一段都没有**。
    """
    missing = [
        path.name
        for path in _runnable_scripts()
        if not _has_utf8_stdio(path.read_text(encoding="utf-8"))
    ]
    assert not missing, (
        f"以下 {len(missing)} 个脚本打印非 ASCII 时会在 Windows 控制台抛 "
        f"UnicodeEncodeError（GBK），但没有任何 stdio UTF-8 兜底：\n"
        + "\n".join(f"  - scripts/{name}" for name in missing)
        + "\n\n修法（放在 import 块之后、任何打印之前）：\n"
        '  if hasattr(sys.stdout, "reconfigure"):\n'
        '      sys.stdout.reconfigure(encoding="utf-8", errors="replace")\n'
        '      sys.stderr.reconfigure(encoding="utf-8", errors="replace")\n'
        "\n为什么必须内联而不能抽公共模块：部分脚本会被测试**按文件路径 import**\n"
        "（如 tests/test_eval_qset_parity.py），此时 scripts/ 不在 sys.path 上\n"
        "⇒ 公共模块本身会 ImportError，兜底代码反而成了新的崩溃源。"
    )


def _has_utf8_stdio(text: str) -> bool:
    return "reconfigure" in text and "utf-8" in text
