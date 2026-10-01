"""A 组（交付形态）护栏：**G-12** / **G-14**。

对应 ``docs/delivery-requirements-and-guardrails.md`` §2.2，依据 `ADR-0007` 与 PRD H15。

机制说明（与 ``test_guardrails.py`` 同源）见需求基线 §2.2 开头：未完成的需求
一律用 ``xfail(strict=True)`` 骨架就位——现在 XFAIL（CI 绿、原因进日志），
需求达成后 XPASS ⇒ strict 判红 ⇒ 强制摘标记转常驻门禁。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "G-14 前置：deploy/variants/ 尚不存在 ⇒ 客户标识黑名单为空 ⇒ "
        "上面那条**恒绿**，没有在拦任何东西"
    ),
)
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
        "G-12 / DR-A1 / DR-A3：deploy/variants/ 当前 **0 个**变体。"
        "1 个客户时无矩阵可言；启用条件写死为 **variant ≥ 2**"
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "G-19 / DR-A6：deploy/docker-compose.yml 的 backend / frontend 仍是 "
        "`build:` 且**无 `image:`** ⇒ 没有版本化镜像 ⇒ 补丁包无从谈起"
    ),
)
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


@pytest.mark.xfail(
    strict=True,
    reason="G-22 前置：plugins/ 目录不存在 ⇒ 上面那条**恒绿**，没有在拦任何东西",
)
def test_g22_plugin_source_exists() -> None:
    """守卫（纪律 **R-9「恒绿即失效」**）：必须**至少有一个**插件可校验。"""
    assert PLUGIN_ROOT.is_dir(), (
        f"{PLUGIN_ROOT} 不存在 ⇒ 提取不到任何插件清单 ⇒ "
        "test_g22_plugin_manifests_are_valid 只是恒绿，没在拦东西"
    )
    assert _plugins(), f"{PLUGIN_ROOT} 存在但没有 */plugin.yaml"
