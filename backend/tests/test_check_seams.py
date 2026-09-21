"""接缝纪律门禁自身的测试。

**为什么门禁需要测试**：一个从不报错的检查项等于没有检查项。本文件逐个证明
`scripts/check_seams.py` 的四类失败模式**真的会拦人**：

1. 登记外实现（"多做"）→ ERROR；
2. 到期仍无实现 / 配置无消费者（"少做 / 假做"）→ ERROR，**未到期**时降级为 WARN（版本闸门）；
3. 预留字段泄进 `contracts/openapi.yaml` → ERROR；
4. 预留字段在 ORM 侧非 nullable → ERROR。

判据出处：ADR-0004 §3 第 4、5 条 / 计划文档 §4.3、§6.3、§7.2、§12 R9。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_seams.py"
_spec = importlib.util.spec_from_file_location("check_seams", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None  # noqa: S101 - 测试自身的加载前置条件
gate = importlib.util.module_from_spec(_spec)
# 必须先登记进 `sys.modules`：脚本内用了 `@dataclass`，而 dataclasses 处理 KW_ONLY 时
# 会按 `cls.__module__` 反查 `sys.modules`，未登记会抛 AttributeError。
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)

#: 到期版本（接缝 1 / 预留字段的 required_from）
DUE = "1.1.0"
#: 未到期版本
NOT_DUE = "1.0.0"


def _levels(findings: list) -> list[str]:
    return [finding.level for finding in findings]


def _messages(findings: list) -> str:
    return " | ".join(finding.message for finding in findings)


# --------------------------------------------------------------------------- #
# 判据 1：接口实现集合 = 登记集合
# --------------------------------------------------------------------------- #


def test_extra_implementation_is_error_without_version_gate() -> None:
    """登记外实现任何时候都拦——越界集成不该等到到期才报。"""
    index = gate.ClassIndex()
    index.names.add("AuthProvider")
    index.by_base["AuthProvider"] = [
        ("LocalAuthProvider", "app/services/auth/local.py", 1),
        ("LdapAuthProvider", "app/services/auth/ldap.py", 2),
    ]
    findings: list = []
    gate._check_interfaces(index, DUE, findings)

    assert "ERROR" in _levels(findings)
    assert "登记外实现" in _messages(findings)
    assert "LdapAuthProvider" in _messages(findings)


def test_missing_implementation_errors_only_when_due() -> None:
    """版本闸门：未到期记 WARN（不阻塞开发），到期转 ERROR（自动上闸）。"""
    empty = gate.ClassIndex()

    before: list = []
    gate._check_interfaces(empty, NOT_DUE, before)
    auth_before = [f for f in before if "AuthProvider" in f.message]
    assert _levels(auth_before) == ["WARN"]
    assert "ERROR" not in _levels(before)

    after: list = []
    gate._check_interfaces(empty, DUE, after)
    auth_after = [f for f in after if "AuthProvider" in f.message]
    assert _levels(auth_after) == ["ERROR"]
    assert "缺少登记实现" in _messages(auth_after)


def test_event_sink_registers_two_local_impls() -> None:
    """接缝 5 登记的**就是** db + log 两个实现——两个不算越界（这是 v2.2 修正的规则）。"""
    index = gate.ClassIndex()
    index.names.add("EventSink")
    index.by_base["EventSink"] = [
        ("DbEventSink", "app/services/events/db.py", 1),
        ("LogEventSink", "app/services/events/log.py", 2),
    ]
    findings: list = []
    gate._check_interfaces(index, "1.3.0", findings)
    sink = [finding for finding in findings if "EventSink" in finding.message]
    assert _levels(sink) == ["OK"]


def test_event_sink_third_impl_is_error() -> None:
    """但第三个（如对接 OA 的 sink）就是越界。"""
    index = gate.ClassIndex()
    index.names.add("EventSink")
    index.by_base["EventSink"] = [
        ("DbEventSink", "app/services/events/db.py", 1),
        ("LogEventSink", "app/services/events/log.py", 2),
        ("OaEventSink", "app/services/events/oa.py", 3),
    ]
    findings: list = []
    gate._check_interfaces(index, "1.3.0", findings)
    sink = [finding for finding in findings if "EventSink" in finding.message]
    assert _levels(sink) == ["ERROR"]
    assert "超过登记上限" in _messages(sink)


def test_ingestion_source_is_optional_in_demo_mvp() -> None:
    """接缝 2 在 Demo-MVP 不要求接口（0.5 天已用于 8 字段），缺失不得报 ERROR。"""
    findings: list = []
    gate._check_interfaces(gate.ClassIndex(), "1.4.0", findings)
    ingestion = [
        finding for finding in findings if "IngestionSource" in finding.message
    ]
    assert _levels(ingestion) == ["OK"]
    assert "实现数 0 在登记区间" in _messages(ingestion)


# --------------------------------------------------------------------------- #
# 判据 2：配置必须有消费者
# --------------------------------------------------------------------------- #


def test_unconsumed_setting_is_gated() -> None:
    fields = {"task_retry_multiplier": "app/core/config.py:57"}

    before: list = []
    gate._check_settings_consumers(fields, {}, {}, NOT_DUE, before)
    assert _levels(before) == ["WARN"]

    after: list = []
    gate._check_settings_consumers(fields, {}, {}, DUE, after)
    assert _levels(after) == ["ERROR"]
    assert "无消费者" in _messages(after)


def test_property_indirection_counts_as_consumption() -> None:
    """`settings.max_upload_size_bytes` 被读 ⇒ 其引用的 `max_upload_size_mb` 也算被消费。"""
    fields = {"max_upload_size_mb": "app/core/config.py:1"}
    properties = {"max_upload_size_bytes": {"max_upload_size_mb"}}
    consumers = {"max_upload_size_bytes": {"app/api/documents.py"}}

    findings: list = []
    gate._check_settings_consumers(fields, properties, consumers, DUE, findings)
    assert _levels(findings) == ["OK"]


def test_presence_rule_catches_declared_but_unread_setting() -> None:
    """`llm_provider` 存在但无人读——接了配置不通链路，同样算未到位。"""
    findings: list = []
    gate._check_presence({}, DUE, consumed=set(), findings=findings)
    llm = [finding for finding in findings if "llm_provider" in finding.message]
    assert _levels(llm) == ["ERROR"]

    early: list = []
    gate._check_presence({}, NOT_DUE, consumed=set(), findings=early)
    assert "ERROR" not in _levels(early)


# --------------------------------------------------------------------------- #
# 判据 3：预留字段双向判据
# --------------------------------------------------------------------------- #


def test_reserved_field_in_contract_is_error() -> None:
    """预留字段一旦进契约就是对外承诺——必须拦。"""
    contract = "components:\n  schemas:\n    DocumentRead:\n      properties:\n        content_hash:\n          type: string\n"
    findings: list = []
    gate._check_reserved_fields({}, contract, NOT_DUE, findings)

    assert "ERROR" in _levels(findings)
    assert "不得进 API 契约" in _messages(findings)


def test_reserved_field_must_be_nullable() -> None:
    findings: list = []
    gate._check_reserved_fields(
        {"source_type": (False, "app/db/models.py:1")}, "", NOT_DUE, findings
    )
    assert "ERROR" in _levels(findings)
    assert "非 nullable" in _messages(findings)


def test_missing_reserved_fields_are_gated() -> None:
    """未到期只报 WARN（S5 才建 8 列），到期必须齐全。"""
    before: list = []
    gate._check_reserved_fields({}, "", NOT_DUE, before)
    assert _levels(before) == ["WARN"]
    assert "缺少 8/8 个预留字段" in _messages(before)

    after: list = []
    gate._check_reserved_fields({}, "", DUE, after)
    assert _levels(after) == ["ERROR"]


# --------------------------------------------------------------------------- #
# 在当前仓库基线上必须恒成立的不变量（与 Sprint 进度无关）
# --------------------------------------------------------------------------- #


def test_settings_fields_are_discovered() -> None:
    fields, properties = gate._collect_settings()
    assert "task_retry_multiplier" in fields
    assert "max_upload_size_mb" in fields
    assert "max_upload_size_bytes" in properties


def test_known_consumed_fields_are_not_false_positive() -> None:
    """B4 的真实措辞是"任务退避路径未读取"——`agents.py` 以 `exp_base` 读它，故本判据不应报它。"""
    fields, properties = gate._collect_settings()
    consumers = gate._collect_setting_consumers()
    consumed = gate._expand_indirect(set(consumers), properties)
    assert "task_retry_multiplier" in fields
    assert "task_retry_multiplier" in consumed


def test_reserved_fields_absent_from_contract() -> None:
    """恒成立的不变量：8 个预留字段在任何版本都不得出现在契约中。"""
    contract = (SCRIPT_PATH.parents[2] / "contracts" / "openapi.yaml").read_text(
        encoding="utf-8"
    )
    findings: list = []
    gate._check_reserved_fields({}, contract, NOT_DUE, findings)
    leaked = [finding for finding in findings if "不得进 API 契约" in finding.message]
    assert leaked == []


# --------------------------------------------------------------------------- #
# 判据 4：登记集合与 ADR-0004 §2.1 一致（防"只改一侧还能过"）
# --------------------------------------------------------------------------- #


def test_adr_registry_matches_current_doc() -> None:
    """恒成立的不变量：门禁登记集合必须都能在 ADR-0004 §2.1 找到。"""
    findings: list = []
    gate._check_adr_registry(findings)
    assert findings, "登记表判据未产出任何结果"
    assert "ERROR" not in _levels(findings)


def test_registry_changed_but_adr_not_updated_is_error(tmp_path, monkeypatch) -> None:
    """改了门禁、忘了改登记表 → 必须红：这是"容易漏的联锁点"的拦截口。"""
    adr = tmp_path / "0004-integration-seams.md"
    adr.write_text(
        "| 1 | 身份接缝 `AuthProvider` | 对接方 | 收口到 services/auth/ | S5 |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "ADR_FILE", adr)

    findings: list = []
    gate._check_adr_registry(findings)

    assert "ERROR" in _levels(findings)
    assert "LocalAuthProvider" in _messages(findings)
    assert "未出现在 ADR-0004 §2.1" in _messages(findings)


def test_missing_adr_file_is_error_never_silent(tmp_path, monkeypatch) -> None:
    """登记真源缺失必须报错——否则判据会退化成"永远通过"。"""
    monkeypatch.setattr(gate, "ADR_FILE", tmp_path / "absent.md")

    findings: list = []
    gate._check_adr_registry(findings)

    assert _levels(findings) == ["ERROR"]
    assert "禁止静默放行" in _messages(findings)
