"""DR-B1 / DR-B3 护栏：**G-20** / **G-21**。

ADR-0003 §3.6.2 把这两件事连在一起：**切 PG**（B1）+ **清除旧 SQLite 兜底**（B3）＝「附加偿还」。
只**切**不**清**会留下方言特判，日后在客户现场以"SQLite 上明明没事"的形式复发——
所以拆成两条各自可机械判：

- **G-20**：PG **就位**（默认配置 + compose 含固定 tag 的 PG 服务）
- **G-21**：SQLite **已清除**（无方言特判 / 无 sqlite 默认值 / 无"兜底"口径）

机制说明见需求基线 §2.2 开头：未完成的需求用 ``xfail(strict=True)`` 骨架就位，
需求达成后 XPASS ⇒ strict 判红 ⇒ 强制摘标记转常驻门禁。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.core.config import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
ENV_EXAMPLE = BACKEND_ROOT / ".env.example"
SESSION = BACKEND_ROOT / "app" / "db" / "session.py"
DB_INIT = BACKEND_ROOT / "app" / "db" / "__init__.py"


def _default_database_url() -> str:
    """取 ``database_url`` 的**字段默认值**——不受测试环境变量污染。"""
    return str(Settings.model_fields["database_url"].default)


def _compose_services() -> dict[str, dict]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    services = data.get("services") or {}
    return {k: v for k, v in services.items() if isinstance(v, dict)}


def _postgres_service() -> tuple[str, dict] | None:
    """找出 compose 里的 PostgreSQL 服务（按镜像名判定）。"""
    for name, service in _compose_services().items():
        image = str(service.get("image", ""))
        if re.search(r"\b(postgres|postgis)\b", image):
            return name, service
    return None


# --------------------------------------------------------------------------- #
# G-20：PG 就位（DR-B1）
# --------------------------------------------------------------------------- #


# ✅ **已转正（2026-10-01）**：默认库已为 PG，compose 已有固定 tag 的 `postgres:16-alpine`。
def test_g20_postgres_is_in_place() -> None:
    """PG 必须**就位**：默认持久化是 PG，且 compose 起固定 tag 的 PG 服务。

    三条判据缺一不可：默认配置（漏了 ⇒ 起装还是 SQLite）、compose 有 PG 服务
    （漏了 ⇒ 现场无人负责起库）、tag 固定（``:latest`` 是不可复现的同义词）。
    """
    problems: list[str] = []

    default_url = _default_database_url()
    if not default_url.startswith("postgresql"):
        problems.append(
            f"config.py 的 database_url 默认值为 {default_url!r}，应当为 postgresql://…"
        )

    pg = _postgres_service()
    if pg is None:
        problems.append(
            f"{COMPOSE.name} 无 PostgreSQL 服务（生产/交付实际没有 PG 可用）"
        )
    else:
        name, service = pg
        image = str(service.get("image", ""))
        tag = image.rsplit(":", 1)[-1] if ":" in image else ""
        if not tag or tag == "latest":
            problems.append(
                f"compose 的 {name} 镜像 tag 为 latest 或缺省（{image}），须固定小版本"
            )

    assert not problems, "PostgreSQL 尚未就位（DR-B1）：\n  - " + "\n  - ".join(
        problems
    )


# --------------------------------------------------------------------------- #
# G-21：清除 SQLite 兜底（DR-B3）
# --------------------------------------------------------------------------- #


# ✅ **已转正（2026-10-01）**：方言特判 / 默认值 / .env.example / 口径注释四类痕迹均已清除。
#    ⚠️ 本文件（含注释）此后**禁止**再出现那几个被清列名开关的**字面名**——
#       G-21 按字样扫描，写「已删除 xxx」同样判命中（本批次实踩两次）。
#    ⚠️ 下方 `test_g21_production_sqlite_guard_still_present` 是**反向守卫**，必须保留
#       且始终通过 —— 删它等于以后有人再悄悄加回 SQLite 也无人拦。
def test_g21_no_sqlite_fallback_in_code() -> None:
    """不得再有任何"SQLite 兜底"痕迹——方言特判尤其必须清干净。

    **为什么单列一条**：``connect_args["check_same_thread"] = False`` 这类方言特判留着，
    就永远有人在"SQLite 上明明跑得好好的"这条路上多走一段；而 ADR-0003 §3.6.2
    已明确它是**待偿还的附加债务**。
    """
    problems: list[str] = []

    session_src = SESSION.read_text(encoding="utf-8")
    if "check_same_thread" in session_src:
        problems.append(
            f"{SESSION.name} 仍有 SQLite 方言特判 check_same_thread（ADR-0003 §3.6.2 明列待清理）"
        )
    if re.search(r'startswith\(\s*["\']sqlite', session_src + _default_database_url()):
        problems.append("代码里仍存在 sqlite 方言分支")

    if _default_database_url().startswith("sqlite"):
        problems.append(
            f"config.py 的 database_url 默认仍是 SQLite（{_default_database_url()!r}）"
        )

    env_src = ENV_EXAMPLE.read_text(encoding="utf-8")
    if re.search(r"^\s*DATABASE_URL\s*=\s*sqlite", env_src, re.MULTILINE):
        problems.append(f"{ENV_EXAMPLE.name} 的 DATABASE_URL 示例仍指向 sqlite")

    init_doc = DB_INIT.read_text(encoding="utf-8")
    if re.search(r"SQLite.{0,10}(临时)?兜底", init_doc):
        problems.append(
            f"{DB_INIT.name} 的模块文档仍宣称「SQLite 临时兜底」——口径未随 ADR-0003 更新"
        )

    assert not problems, (
        "仍存在 SQLite 兜底痕迹（DR-B3，须按 ADR-0003 §3.6.2 偿还）：\n  - "
        + "\n  - ".join(problems)
    )


def test_g21_production_sqlite_guard_still_present() -> None:
    """**反向守卫**：清理 SQLite 的同时，生产禁 SQLite 的围栏**不得被一并删掉**。

    这条**必须始终通过**——它守的是另外一个方向：B3 的清理很容易顺手把
    ``_guard_production_sqlite`` 也当成"SQLite 残留"误删，那就等于把最后的底线拆了。
    """
    source = (BACKEND_ROOT / "app" / "core" / "config.py").read_text(encoding="utf-8")
    assert "_guard_production_sqlite" in source, (
        "config.py 缺少 _guard_production_sqlite ——"
        "清理 SQLite 兜底时不得把这个生产围栏一并删掉（G-7 / DR-B3）"
    )
