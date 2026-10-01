"""G-11：接缝接口签名冻结（ADR-0004 §3 第 6 条）。

八个接缝是**客户插件的唯一接入面**（ADR-0007 §3.2）。用户裁决：**付费升 V2.0
时插件才需重新开发** ⇒ 同一大版本内插件不得因打补丁而失效。

**为什么必须机械判**：补丁若改一行 ``AuthProvider.authenticate()`` 的参数，客户的
LDAP 适配就废了，且**要到补丁后的某次登录才炸**——这是"静默失效"，人工评审拦不住。

**为什么走 subprocess**：比对逻辑已在 ``scripts/extract_seam_signatures.py --check``
里，测试复用同一份实现，避免"测试口径与命令口径两套"。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND_ROOT / "scripts" / "extract_seam_signatures.py"
SNAPSHOT = BACKEND_ROOT / "tests" / "snapshots" / "seam_signatures.json"


@pytest.mark.xfail(
    not SNAPSHOT.exists(),
    reason="快照尚未生成；跑 scripts/extract_seam_signatures.py --update",
    strict=False,
)
def test_seam_signatures_match_frozen_snapshot() -> None:
    """PATCH / MINOR 版本内，冻结接口的签名必须与快照**逐字相同**。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=BACKEND_ROOT,
    )
    assert proc.returncode == 0, (
        "接缝接口签名与快照不一致（同大版本内不得变更）。\n"
        f"--- 脚本输出 ---\n{proc.stdout}\n{proc.stderr}"
    )


def test_frozen_snapshot_is_committed() -> None:
    """快照文件必须入库——否则上面那条比对会退化成"从没生效过"。

    这是 G-2 那条教训的同款护栏：门禁脚本本身默认基准取 HEAD 时恒绿，
    等于判据从未在流水线上生效过。
    """
    assert SNAPSHOT.exists(), (
        f"缺少已提交的签名快照 {SNAPSHOT}。"
        "请跑 uv run python scripts/extract_seam_signatures.py --update 并提交生成物。"
    )
