"""DR-E2（P6-W / **W-a**）：备份清单与版本一致性的**唯一换算口**。

本模块落实 `docs/deployment-spec.md` §6.1 / §6.2 / §6.4 里能被机器判的三件事，
供 `scripts/backup.py` 与 `scripts/restore.py` **共用**（不许两处各写一份 ⇒ 漂移）：

1. **§6.1 六类对象**——其中**五类落文件**（PostgreSQL / Neo4j / 文件存储 /
   License 文件 / 配置），**第六类 `active kg_version` 不是文件**，而是清单里的
   `active_kg_version` 字段（§6.1 原文："记录到备份清单"）。
2. **§6.4 的 `backup-manifest.json`**——各文件 **SHA-256 + 大小 + 时刻** + active
   `kg_version`；`verify_manifest()` 是第 8 项「SHA-256 校验通过」的机器判据。
3. **§6.2 一致性**——`evaluate_version_consistency()`：PG 的 active 版本必须能在
   Neo4j 里找到对应节点；找不到（**幽灵版本**）或图库不可达 ⇒ **报错**，
   绝不静默放行。

**两条刻意的设计约束**：

- **校验只认重算出来的哈希**，不认"文件在不在"（R-9 恒绿失效的第一种形态就是
  `if path.exists()` ⇒ 一个字节被改过也照样绿）。
- **探针（probe）一律注入**：本模块不自己连 Neo4j / PG。真实探针只有极薄的一层
  （见两个脚本里的 `default_*`），被测的是**判定逻辑本身**。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MANIFEST_FILENAME = "backup-manifest.json"
MANIFEST_SCHEMA_VERSION = "1.0"

#: §6.1 六类对象里**落文件**的五类（顺序即清单里的顺序）。
FILE_OBJECT_NAMES: tuple[str, ...] = (
    "postgres",
    "neo4j",
    "storage",
    "license",
    "config",
)

STATUS_PRESENT = "present"
STATUS_SKIPPED = "skipped"

#: ``active_kg_version`` 的两个状态
KG_RECORDED = "recorded"
KG_UNAVAILABLE = "unavailable"

REDACTION_PLACEHOLDER = "<redacted>"

#: 判定"这一行要不要遮"主要看 **key 名**（不看值形态）——
#: 短口令 / 数字串 / base64 的**值形态**都猜不准，而 `.env` 的命名是人为约定、命中率高得多。
#: ``salt|signing|hmac`` 也算：**它们不是端点，是密钥材料**（伪匿名 / 签名的salt）。
_SECRET_KEY_RE = re.compile(
    r"(?i)(key|secret|token|password|passwd|pwd|credential|salt|signing|hmac)"
)
#: 第二种形态：**连接串里内嵌凭据**（``postgres://user:pw@host/db``）。
#: 光靠 key 名抓不到它（`DATABASE_URL` 里没有敏感词），但它实实在在带口令 ⇒
#: 只把口令那一段替换掉（主机 / 库名还留着，恢复时还有得看）。
_URL_CREDENTIAL_RE = re.compile(
    r"^(?P<head>[a-zA-Z0-9+.\-]+://[^:/?#@\s]*):[^@/?#\s]*@"
)


class BackupError(RuntimeError):
    """备份 / 恢复过程中的**可预期**失败（区别于未捕获异常）。"""


# --------------------------------------------------------------------------- #
# 1. 哈希与清单条目
# --------------------------------------------------------------------------- #


def sha256_of(path: Path) -> str:
    """流式算 SHA-256（备份文件可能很大，不整读进内存）。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class ObjectEntry:
    """§6.1 的一类对象。

    ``status=present`` 时 ``path`` / ``sha256`` / ``size`` / ``collected_at``
    必须齐全；``status=skipped`` 时必须给 ``reason``（**不许留白** —— 留白会让
    "没备份到" 与 "备份了但清单写漏了" 读起来一样）。
    """

    name: str
    status: str
    path: str | None = None
    sha256: str | None = None
    size: int | None = None
    collected_at: str | None = None
    method: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "status": self.status}
        for name in ("path", "sha256", "size", "collected_at", "method", "reason"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ObjectEntry:
        return cls(
            name=str(payload["name"]),
            status=str(payload["status"]),
            path=payload.get("path"),
            sha256=payload.get("sha256"),
            size=payload.get("size"),
            collected_at=payload.get("collected_at"),
            method=payload.get("method"),
            reason=payload.get("reason"),
        )


def file_entry(*, name: str, path: Path, base_dir: Path, method: str) -> ObjectEntry:
    """把一个**已存在**的备份文件登记成清单条目（当场重算 SHA-256 / 大小 / 时刻）。"""
    stat = Path(path).stat()
    relative = Path(path).resolve().relative_to(Path(base_dir).resolve())
    return ObjectEntry(
        name=name,
        status=STATUS_PRESENT,
        path=str(relative),
        sha256=sha256_of(path),
        size=int(stat.st_size),
        collected_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        method=method,
    )


def skipped_entry(*, name: str, reason: str) -> ObjectEntry:
    return ObjectEntry(name=name, status=STATUS_SKIPPED, reason=reason)


def split_pg_dsn(dsn: str) -> tuple[str, int, str, str, str]:
    """把 SQLAlchemy 风格连接串拆成 ``pg_dump`` / ``pg_restore`` 要的五元组。

    放在这里而不是两个脚本里各写一份，是为了让 ``backup`` 的**导出参数**与
    ``restore`` 的**导入参数**永远按同一把尺子切（两处各写一份迟早漂移）。
    """
    parsed = urlparse(dsn)
    host = parsed.hostname or "localhost"
    port = int(parsed.port or 5432)
    user = parsed.username or ""
    password = parsed.password or ""
    database = parsed.path.lstrip("/") or "graphrag"
    return host, port, user, password, database


@dataclass(frozen=True, slots=True)
class ActiveKgVersion:
    """§6.1 第六类对象：备份时刻的 active `kg_version`（记录到清单里）。"""

    status: str
    source: str
    version: str | None = None
    pg_status: str | None = None
    ready_at: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status, "source": self.source}
        for name in ("version", "pg_status", "ready_at", "reason"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ActiveKgVersion:
        return cls(
            status=str(payload["status"]),
            source=str(payload.get("source", "unknown")),
            version=payload.get("version"),
            pg_status=payload.get("pg_status"),
            ready_at=payload.get("ready_at"),
            reason=payload.get("reason"),
        )


@dataclass(frozen=True, slots=True)
class BackupManifest:
    schema_version: str
    generated_at: str
    app_version: str
    objects: tuple[ObjectEntry, ...]
    active_kg_version: ActiveKgVersion

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "app_version": self.app_version,
            "objects": [item.to_dict() for item in self.objects],
            "active_kg_version": self.active_kg_version.to_dict(),
        }

    def write(self, backup_dir: Path) -> Path:
        target = Path(backup_dir) / MANIFEST_FILENAME
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def read(cls, backup_dir: Path) -> BackupManifest:
        payload = json.loads((Path(backup_dir) / MANIFEST_FILENAME).read_text("utf-8"))
        return cls(
            schema_version=str(payload["schema_version"]),
            generated_at=str(payload["generated_at"]),
            app_version=str(payload.get("app_version", "unknown")),
            objects=tuple(ObjectEntry.from_dict(item) for item in payload["objects"]),
            active_kg_version=ActiveKgVersion.from_dict(payload["active_kg_version"]),
        )


# --------------------------------------------------------------------------- #
# 2. 第 8 项的机器判据：清单完整性 + SHA-256 重算
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ManifestVerification:
    """清单校验结果与**三态机读输出**。

    ``failures`` 非空 ⇒ ``ok=False``；``passed`` 只记录**确实重算过**的条目，
    让"过了几条 / 没过几条"一眼对得上账（不会有人把空现状读成"全部通过"）。
    """

    failures: tuple[str, ...] = ()
    passed: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.failures

    def lines(self) -> tuple[str, ...]:
        return tuple(
            [f"FAIL {item}" for item in self.failures]
            + [f"PASS {item}" for item in self.passed]
        )


def missing_file_objects(manifest: BackupManifest) -> tuple[str, ...]:
    """§6.1 要求的五类文件对象里，**清单根本没提**的（缺 ⇒ 备份集不完整）。"""
    seen = {item.name for item in manifest.objects}
    return tuple(name for name in FILE_OBJECT_NAMES if name not in seen)


def verify_manifest(backup_dir: Path) -> ManifestVerification:
    """**重算**每个备份文件的 SHA-256 并与清单比对（第 8 项的核心判据）。

    失败形态分三类分别登记（不许混成一团 ⇒ "缺文件"不会被读成"哈希不符"）：

    - 清单缺失 / 解析失败 / schema 版本不认；
    - 清单里有 ``present`` 条目、但文件不在 / 哈希对不上 / 大小对不上 / 字段不全；
    - 清单里有 ``skipped`` 条目 ⇒ **备份集不完整**（§6.1「缺一不可复现」）。
    """
    failures: list[str] = []
    passed: list[str] = []

    try:
        manifest = BackupManifest.read(backup_dir)
    except FileNotFoundError:
        return ManifestVerification(
            failures=(f"备份目录下无 {MANIFEST_FILENAME}：这不是一个备份集",)
        )
    except (json.JSONDecodeError, KeyError) as exc:
        return ManifestVerification(failures=(f"{MANIFEST_FILENAME} 无法解析: {exc}",))

    if manifest.schema_version != MANIFEST_SCHEMA_VERSION:
        failures.append(
            f"清单 schema_version={manifest.schema_version}，"
            f"本脚本只认 {MANIFEST_SCHEMA_VERSION}"
        )
    else:
        passed.append(f"{MANIFEST_FILENAME} 可解析且 schema_version 匹配")

    missing = missing_file_objects(manifest)
    if missing:
        failures.append(f"§6.1 对象在清单中缺失: {', '.join(missing)}")
    else:
        passed.append("§6.1 五类文件对象均在清单中有条目")

    for item in manifest.objects:
        if item.status == STATUS_SKIPPED:
            failures.append(
                f"{item.name}: 备份时被跳过 ⇒ 备份集不完整（原因: {item.reason}）"
            )
            continue
        if item.status != STATUS_PRESENT:
            failures.append(f"{item.name}: 未知 status={item.status}")
            continue
        if not item.path or not item.sha256 or item.size is None:
            failures.append(f"{item.name}: present 但缺 path/sha256/size 字段")
            continue
        target = Path(backup_dir) / item.path
        if not target.is_file():
            failures.append(f"{item.name}: 清单登记的文件不存在: {item.path}")
            continue
        actual = sha256_of(target)
        if actual != item.sha256:
            failures.append(
                f"{item.name}: SHA-256 不符（清单 {item.sha256[:12]}… / "
                f"实际 {actual[:12]}…）⇒ 备份已损坏或已被改动"
            )
            continue
        if int(target.stat().st_size) != int(item.size):
            failures.append(
                f"{item.name}: 大小不符（清单 {item.size} / "
                f"实际 {target.stat().st_size}）"
            )
            continue
        passed.append(
            f"{item.name}: SHA-256 校验通过（{item.size} 字节, {item.method or 'n/a'}）"
        )

    if manifest.active_kg_version.status != KG_RECORDED:
        failures.append(
            "未记录 backup 时刻的 active kg_version"
            f"（原因: {manifest.active_kg_version.reason}）⇒ §6.2 无法回头校验"
        )
    else:
        passed.append(
            "active kg_version 已记录: "
            f"{manifest.active_kg_version.version}（{manifest.active_kg_version.source}）"
        )

    return ManifestVerification(failures=tuple(failures), passed=tuple(passed))


# --------------------------------------------------------------------------- #
# 3. §6.2 一致性：active 版本 vs 图库里该版本的节点
# --------------------------------------------------------------------------- #

CODE_CONSISTENT = "pg_graph_consistent"
CODE_GHOST_VERSION = "ghost_version"
CODE_GRAPH_UNREACHABLE = "graph_unreachable"
CODE_NO_ACTIVE_VERSION = "no_active_version"
CODE_ACTIVE_VERSION_DRIFT = "active_version_mismatch"


@dataclass(frozen=True, slots=True)
class VersionConsistency:
    code: str
    ok: bool
    message: str

    def line(self, *, label: str) -> str:
        return f"{'PASS' if self.ok else 'FAIL'} {label} [{self.code}] {self.message}"


def evaluate_version_consistency(
    *,
    active_version: str | None,
    neo4j_version_exists: Callable[[str], bool],
) -> VersionConsistency:
    """§6.2 第 2 条：**PG 的 active 版本 == Neo4j 中该版本的节点存在**。

    - 两侧都在 ⇒ ``pg_graph_consistent``；
    - PG 有版本、图库里没有 ⇒ ``ghost_version``（**幽灵版本，必须报错**，
      ADR-0002 §3.2 明令禁止）；
    - 图库连不上 ⇒ ``graph_unreachable``，**同样判失败**："测不出来"不能当成"一致"
      （否则客户现场图库一挂，恢复后照样静默起来一个错版本的系统）；
    - PG 没有 active 版本 ⇒ ``no_active_version``：无版本可错位 ⇒ 判**通过**，
      但 message 里**写明它什么都没证明**（不许被读成"一致性已验证"）。
    """
    if not active_version:
        return VersionConsistency(
            code=CODE_NO_ACTIVE_VERSION,
            ok=True,
            message=(
                "PG 中无 active kg_version ⇒ 无版本可错位；"
                "本条**未做任何一致性验证**（新环境属正常，但不等于已验证）"
            ),
        )
    try:
        exists = neo4j_version_exists(active_version)
    except Exception as exc:  # noqa: BLE001 - 探针异常一律视作不可判定
        return VersionConsistency(
            code=CODE_GRAPH_UNREACHABLE,
            ok=False,
            message=(
                f"PG active 版本 = {active_version}，但读取图库失败 ⇒ "
                f"无法判定该版本节点是否存在（{type(exc).__name__}: {exc}）"
            ),
        )
    if not exists:
        return VersionConsistency(
            code=CODE_GHOST_VERSION,
            ok=False,
            message=(
                f"PG active 版本 = {active_version}，但 Neo4j 中该版本节点不存在 ⇒ "
                "幽灵版本（ADR-0002 §3.2 禁止），不许静默启动"
            ),
        )
    return VersionConsistency(
        code=CODE_CONSISTENT,
        ok=True,
        message=f"PG active 版本 = Neo4j 该版本节点存在（{active_version}）",
    )


def evaluate_manifest_vs_pg(
    *, manifest_version: str | None, active_version: str | None
) -> VersionConsistency:
    """备份清单记的版本 vs 恢复后 PG 的 active 版本 —— 错位同样要报错。

    只在两侧**都有值**时判 ``active_version_mismatch``；任一侧缺失交给
    :func:`evaluate_version_consistency` 负责（避免同一个缺口被算两遍 ⇒
    报告里出现两倍的失败项，读起来像是两个不同的问题）。
    """
    if manifest_version and active_version and manifest_version != active_version:
        return VersionConsistency(
            code=CODE_ACTIVE_VERSION_DRIFT,
            ok=False,
            message=(
                f"备份清单记的 active 版本 = {manifest_version}，"
                f"恢复后 PG 的 active 版本 = {active_version} ⇒ 版本错位"
            ),
        )
    if manifest_version or active_version:
        return VersionConsistency(
            code=CODE_CONSISTENT,
            ok=True,
            message=(
                f"备份清单与 PG active 版本一致（{manifest_version or active_version}）"
            ),
        )
    return VersionConsistency(
        code=CODE_CONSISTENT,
        ok=True,
        message="两侧均无版本可比对（未做 drift 判定）",
    )


# --------------------------------------------------------------------------- #
# 4. 配置对象（§6.1「配置：.env **脱敏副本**（去密钥）」）
# --------------------------------------------------------------------------- #


def redact_env_text(text: str) -> tuple[str, tuple[str, ...]]:
    """按 **key 名**把密钥值换成 ``<redacted>``，返回 (脱敏文本, 被脱敏的 key 名)。

    返回 key 名是为了让调用方能**机械断言"该遮的都遮了"**——否则这条判据只能靠肉眼。
    """
    out: list[str] = []
    redacted: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(raw_line)
            continue
        key, _, value = stripped.partition("=")
        if _SECRET_KEY_RE.search(key.strip()):
            out.append(f"{key}={REDACTION_PLACEHOLDER}")
            redacted.append(key.strip())
            continue
        inline = _URL_CREDENTIAL_RE.match(value.strip())
        if inline:
            masked = _URL_CREDENTIAL_RE.sub(
                rf"\g<head>:{REDACTION_PLACEHOLDER}@", value.strip(), count=1
            )
            out.append(f"{key}={masked}")
            redacted.append(key.strip())
            continue
        out.append(raw_line)
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out) + trailing, tuple(redacted)


def redact_env_file(src: Path, dst: Path) -> tuple[str, ...]:
    """写脱敏副本；返回被脱敏的 key 名序列。"""
    text = Path(src).read_text(encoding="utf-8")
    payload, keys = redact_env_text(text)
    Path(dst).write_text(payload, encoding="utf-8")
    return keys


__all__ = [
    "CODE_ACTIVE_VERSION_DRIFT",
    "CODE_CONSISTENT",
    "CODE_GHOST_VERSION",
    "CODE_GRAPH_UNREACHABLE",
    "CODE_NO_ACTIVE_VERSION",
    "FILE_OBJECT_NAMES",
    "KG_RECORDED",
    "KG_UNAVAILABLE",
    "MANIFEST_FILENAME",
    "MANIFEST_SCHEMA_VERSION",
    "REDACTION_PLACEHOLDER",
    "STATUS_PRESENT",
    "STATUS_SKIPPED",
    "ActiveKgVersion",
    "BackupError",
    "BackupManifest",
    "ManifestVerification",
    "ObjectEntry",
    "VersionConsistency",
    "evaluate_manifest_vs_pg",
    "evaluate_version_consistency",
    "file_entry",
    "missing_file_objects",
    "redact_env_file",
    "redact_env_text",
    "sha256_of",
    "skipped_entry",
    "split_pg_dsn",
    "utc_now_iso",
    "verify_manifest",
]
