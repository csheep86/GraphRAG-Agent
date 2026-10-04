"""A 组（交付形态）护栏：**G-12** / **G-14**。

对应 ``docs/delivery-requirements-and-guardrails.md`` §2.2，依据 `ADR-0007` 与 PRD H15。

机制说明（与 ``test_guardrails.py`` 同源）见需求基线 §2.2 开头：未完成的需求
一律用 ``xfail(strict=True)`` 骨架就位——现在 XFAIL（CI 绿、原因进日志），
需求达成后 XPASS ⇒ strict 判红 ⇒ 强制摘标记转常驻门禁。
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest
import yaml

from app.core.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"
VARIANT_DIR = REPO_ROOT / "deploy" / "variants"
COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
PLUGIN_ROOT = REPO_ROOT / "plugins"

#: DR-A2 裁剪后的插件最小字段集（`config_schema` / `openapi_fragment` 随 DR-A4 / A5 降级，
#: 在出现 **B 类插件**前不得提前要求）。
REQUIRED_PLUGIN_FIELDS = ("id", "version", "entry_point", "seam", "base_version")


def _customer_tokens() -> dict[str, str]:
    """从 ``deploy/variants/<客户>.yaml`` 提取**客户专属标识**。

    返回 ``{token: 来源}``，报错时能直接指出是哪个变体把它引进来的。
    目录不存在时返回空——因此 :func:`test_g14_customer_token_source_exists`
    专门守"来源为空"这种情况，防止本判据退化成恒绿。
    """
    tokens: dict[str, str] = {}
    if not VARIANT_DIR.is_dir():
        return tokens
    for path in sorted(VARIANT_DIR.glob("*.yaml")):
        tokens[path.stem] = f"变体文件名 {path.name}"
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue  # 语法错误由 G-12 那条管，这里只管"提取标识"
        if not isinstance(data, dict):
            continue
        for key in ("customer", "customer_id", "name", "id"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                tokens.setdefault(value.strip(), f"{path.name} 的 {key} 字段")
    return tokens


# --------------------------------------------------------------------------- #
# G-14：基座契约纯净性（PRD H15）
# --------------------------------------------------------------------------- #


def test_g14_base_contract_has_no_customer_specific_fields() -> None:
    """基座契约不得出现**任何客户专属**标识（客户名 / 插件 id / 客户定制端点）。

    基座契约被**所有**客户共用；一旦混入某个客户的字段，就等于把定制写进了公共面，
    后面每加一个客户都要回头拆。
    """
    tokens = _customer_tokens()
    text = CONTRACT.read_text(encoding="utf-8")
    hits = {token: src for token, src in tokens.items() if token and token in text}
    assert not hits, (
        f"基座契约 {CONTRACT.name} 出现客户专属标识 {hits}。"
        "客户专属内容必须留在变体 / 插件侧，不得污染基座契约（PRD H15）。"
    )


# ✅ **已转正（2026-10-04，P2.5）**：`deploy/variants/baseline.yaml` 已落 ⇒ 黑名单非空。
#    **转正流程**：先让本条**真通过**（strict xfail 下 XPASS ⇒ FAILED，实测到过），
#    **再**摘 `@pytest.mark.xfail`——只删标记不算转正。
def test_g14_customer_token_source_exists() -> None:
    """守卫：黑名单**必须有来源**——否则上一条会退化成"从没生效过"。

    与 G-2 同款教训：门禁若以空集合作基准则恒绿，等于这条判据从未生效过。
    因此把"来源是否可读"单列成一条，且让它**先红着**。
    """
    assert VARIANT_DIR.is_dir(), (
        f"{VARIANT_DIR} 不存在 ⇒ 提取不到任何客户标识 ⇒ "
        "test_g14_base_contract_has_no_customer_specific_fields 只是恒绿，没在拦东西"
    )
    assert _customer_tokens(), (
        f"{VARIANT_DIR} 存在但提取不到客户标识（既无变体文件、也无可识别字段）"
    )


# --------------------------------------------------------------------------- #
# G-12：variant 矩阵构建
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason=(
        "G-12 / DR-A1 / DR-A3：deploy/variants/ 当前 **1 个**变体"
        "（`baseline`，2026-10-04 P2.5 落）。启用条件写死为 **variant ≥ 2**，"
        "本批**不凑第二个**（需求基线 §300：不许捏造客户、不许放宽成 ≥1）"
    ),
)
def test_g12_variant_matrix_builds() -> None:
    """一次基座改动 ⇒ **全部** variant 都必须构建成功。

    **骨架阶段的判据范围**：只做「yaml 可解析 + 是映射」。真实镜像构建依赖
    deploy 侧的构建流程（ADR-0007 §3.2 变体镜像），待该流程落地后升级本条——
    在那之前，本条**不得**宣称已验证"构建成功"。
    """
    variants = sorted(VARIANT_DIR.glob("*.yaml"))
    assert len(variants) >= 2, (
        f"{VARIANT_DIR} 下只有 {len(variants)} 个变体。"
        "少于 2 个时无矩阵可言；一旦 ≥2，本条必须转常驻门禁。"
    )
    for path in variants:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path.name} 的顶层不是映射，无法作为变体配置"


# --------------------------------------------------------------------------- #
# G-19：compose 版本化镜像（DR-A6 —— 补丁流程的**唯一前提**）
# --------------------------------------------------------------------------- #


# ✅ **已转正（2026-10-01）**：三个服务均已声明固定 tag 的 `image:`，摘 `xfail` 转为常驻门禁。
# ✅ **tag 漂移缺口已补（2026-10-01，决策点 1 采纳 (a)）**：原判据管不到
#    「app_version bump 而 compose 忘了改」，由下一条 `test_g19_own_image_tags_track_app_version`
#    接管——已做负向验证（把 tag 改错则该用例 FAIL）。
def test_g19_compose_uses_versioned_images() -> None:
    """每个服务都必须声明**固定 tag 的镜像**——否则"出补丁 / 回滚"两件事都不存在。

    DR-A6 是 DR-A7（离线包）与 DR-C2（补丁流程）的**前置**（需求基线 §5 依赖 1）：
    没有版本化镜像，"补丁包"这回事根本不存在。

    判据两条：
      1. 服务必须声明 ``image:``（只写 ``build:`` 的版本无法被 pull / 也无法回滚）；
      2. tag **不得**为 ``latest`` 或缺省——``:latest`` 是不可复现的同义词（D-N）。
    """
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    services = compose.get("services")
    assert isinstance(services, dict) and services, f"{COMPOSE.name} 无 services"

    problems: list[str] = []
    for name, service in sorted(services.items()):
        if not isinstance(service, dict):
            continue
        image = service.get("image")
        if not image:
            problems.append(
                f"{name}：无 image: 字段（当前只有 build:）⇒ 现场无法 pull 升级、"
                "也无法改 tag 回滚"
            )
            continue
        tag = image.rsplit(":", 1)[-1] if ":" in image else ""
        if not tag or tag == "latest":
            problems.append(
                f"{name}：image 的 tag 为 latest 或缺省（{image}）；"
                "须固定小版本，`:latest` 是不可复现的同义词"
            )

    assert not problems, (
        f"{COMPOSE.name} 尚未满足版本化镜像要求（DR-A6，补丁流程的唯一前提）：\n  - "
        + "\n  - ".join(problems)
    )


def test_g19_own_image_tags_track_app_version() -> None:
    """自研服务的 ``image`` tag 必须等于 **当前** ``app_version``（决策点 1 采纳 (a)）。

    上一条只校验「有 image: 且 tag 不是 latest」⇒ **管不住漂移**：
    ``app_version`` bump 到 1.7.0 而 compose 忘了改时它照样绿——护栏会在最该响的
    那一刻沉默（`changes/P1/proposal.md` §6 决策点 1 就是这个缺口）。

    判定范围收紧到**本仓库构建**的服务：以是否声明 ``build:`` 为准。
    ``neo4j`` / ``postgres`` 这类第三方镜像没有 ``build:``，它们的 tag 跟
    ``app_version`` 无关，强制相等反而会逼出一个每次都要改的假约束。
    """
    version = get_settings().app_version
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) or {}
    services = compose.get("services") or {}

    problems: list[str] = []
    checked = 0
    for name, service in sorted(services.items()):
        if not isinstance(service, dict) or "build" not in service:
            continue
        checked += 1
        image = service.get("image") or ""
        tag = image.rsplit(":", 1)[-1] if ":" in image else ""
        if tag != version:
            problems.append(
                f"{name}：image={image or '（无）'} 的 tag 是 {tag or '（缺省）'}，"
                f"与 app_version={version} 不一致"
            )

    assert checked, (
        f"{COMPOSE.name} 里没有任何带 build: 的服务 ⇒ 本判据失去对象。"
        "自研镜像必须同时声明 build: 与 image:（DR-A6）"
    )
    assert not problems, (
        f"compose 的镜像 tag 与 app_version={version} 脱钩（发版 bump 时必须同步改）：\n  - "
        + "\n  - ".join(problems)
    )


# --------------------------------------------------------------------------- #
# G-22：插件规范（DR-A2）
# --------------------------------------------------------------------------- #


def _plugins() -> list[tuple[Path, dict]]:
    """读取 ``plugins/<id>/plugin.yaml``；目录不存在时返回空（由守卫那条管）。"""
    if not PLUGIN_ROOT.is_dir():
        return []
    manifests: list[tuple[Path, dict]] = []
    for path in sorted(PLUGIN_ROOT.glob("*/plugin.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            manifests.append((path, {"__error__": str(exc)}))
            continue
        manifests.append((path, data if isinstance(data, dict) else {}))
    return manifests


def test_g22_plugin_manifests_are_valid() -> None:
    """每个插件清单必须含 DR-A2 的**最小字段集**。

    ``seam`` 是否属于 ADR-0004 八个接缝，由 **R-1 / `check_seams.py`** 把关，
    此处不重复判定——避免同一判据两处实现、日后走偏。
    """
    problems: list[str] = []
    for path, data in _plugins():
        error = data.get("__error__")
        if error:
            problems.append(f"{path}：YAML 解析失败 —— {error}")
            continue
        for field in REQUIRED_PLUGIN_FIELDS:
            value = data.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{path}：缺字段或值为空 —— {field}")

    assert not problems, "插件清单不合规（DR-A2）：\n  - " + "\n  - ".join(problems)


# ✅ **已转正（2026-10-04，P2.5）**：`plugins/json-csv-export/plugin.yaml` 已落 ⇒ 有插件可校验。
#    **转正流程**：先真通过（strict xfail 下 XPASS ⇒ FAILED，实测到过），再摘 xfail。
def test_g22_plugin_source_exists() -> None:
    """守卫（纪律 **R-9「恒绿即失效」**）：必须**至少有一个**插件可校验。"""
    assert PLUGIN_ROOT.is_dir(), (
        f"{PLUGIN_ROOT} 不存在 ⇒ 提取不到任何插件清单 ⇒ "
        "test_g22_plugin_manifests_are_valid 只是恒绿，没在拦东西"
    )
    assert _plugins(), f"{PLUGIN_ROOT} 存在但没有 */plugin.yaml"


def test_g22_plugin_entry_points_are_importable() -> None:
    """`entry_point` 必须**真的指向存在的类**（GA 硬门槛「不许造空壳」的机械保证）。

    **为什么必须另立这一条**：G-22 的主断言只验 5 个字段**非空** ⇒
    写一句 `entry_point: nonexistent.module:Whatever` 也能**全绿**——
    那是标准的空壳假绿，恰好是需求基线 §300 明令禁止的「为转护栏而造空壳插件」。

    ⚠️ **不是**要求实现代码搬到 `plugins/` 下：ADR-0007 §3.6 的示例本身就是
    `app.services.auth.ldap:LdapAuthProvider` ⇒ 实现类住在 `app/` 里是 ADR 本意，
    `plugins/` 只放清单。这里验的是「清单指的那个人**真的存在**」。
    """
    problems: list[str] = []
    for path, data in _plugins():
        if data.get("__error__"):
            continue
        spec = data.get("entry_point")
        # 缺字段 / 非字符串由 test_g22_plugin_manifests_are_valid 管，此处不重复报
        if not isinstance(spec, str) or not spec.strip():
            continue
        module_name, _, attr = spec.partition(":")
        if not module_name or not attr:
            problems.append(f"{path}：entry_point 不是 `模块:类名` 形式 —— {spec}")
            continue
        try:
            target = getattr(importlib.import_module(module_name), attr)
        except Exception as exc:  # 导入失败 / 类不存在，都要说清是哪个插件
            problems.append(f"{path}：entry_point 无法解析 —— {spec}（{exc!r}）")
            continue
        if not inspect.isclass(target):
            problems.append(f"{path}：entry_point 指向的不是类 —— {spec}")

    assert not problems, (
        "插件清单的 entry_point 指向了不存在的目标（空壳插件）：\n  - "
        + "\n  - ".join(problems)
    )
