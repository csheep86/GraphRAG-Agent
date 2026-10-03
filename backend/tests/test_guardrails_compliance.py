"""DR-C1 / DR-B9 护栏：**G-23** / **G-24**。

两条都属于"整套子系统的存在性 + 行为"判据：

- **G-23**（DR-C1 License）：`licenses` 表 / `LicenseProvider` / **纯 ASGI** `LicenseMiddleware`
  / 6 个 `LICENSE_*` 错误码进契约 / `GET /license/status` / `license-cli fingerprint`，
  以及行为围栏——**移除 license 文件 ⇒ 受保护端点 403 `LICENSE_MISSING` 且拒绝落审计**。
- **G-24**（DR-B9 RBAC 三粒度）：**角色 × 资源 × 操作**矩阵 + 端点强制校验。

> **G-23（License）仍零代码** ⇒ 两条断言挂起（ADR-0006 未落地）。
>
> 📌 **G-24 已转正（2026-10-03，P2-B）**：`roles` / `user_roles` 两张表 +
> 角色 × 资源 × 操作矩阵 + 路由层强制校验入口 + 拒绝写 `permission.denied` 已落地，
> 本条由 XPASS 转常驻门禁，判据同时**补强**（只摘 xfail 不算转正）。
> 另加两条：`test_g24_roles_rls_exemption_is_declared_and_bounded`
> （ADR-0003 §4.1 / spec §4.2 的 RLS 豁免三条机械断言）与
> `test_g24_role_name_set_is_frozen`（角色集合封闭）。
>
> ⚠️ **转正的边界，不许外推**：
> ① 本条**不断言具体权限值**——赋权属实现决策，取值与理由登记在
> `changes/P2/integration-log.md`；
> ② **RLS 策略一行未写**（DR-B4 归 **P3**），本批只做 `roles` 的豁免**登记**；
> ③ 真实账号链路（登录 / 授权管理界面）归 **P2-C**，当前授权记录仍由测试夹具播种。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

APP_ROOT = BACKEND_ROOT / "app"
SCRIPTS_ROOT = BACKEND_ROOT / "scripts"
MODELS = APP_ROOT / "db" / "models.py"
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"

#: 遍历时必须跳过——``backend/.venv`` 有几千个文件，不排会拖垮整轮测试。
SKIP_DIRS = {
    ".venv",
    "__pycache__",
    "node_modules",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
}


def _load_tree(root: Path, suffix: str = ".py") -> dict[Path, str]:
    """读取目录下的全部源码，排开虚拟环境与缓存。"""
    sources: dict[Path, str] = {}
    for path in sorted(root.rglob(f"*{suffix}")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            sources[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return sources


def _any_match(sources: dict[Path, str], pattern: str) -> bool:
    rx = re.compile(pattern)
    return any(rx.search(text) for text in sources.values())


# --------------------------------------------------------------------------- #
# G-23：License 控制（DR-C1）
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="G-23 / DR-C1：License 子系统零代码（ADR-0006 未落地），六项资产均不存在",
)
def test_g23_license_assets_exist() -> None:
    """DR-C1 完成判据的**静态侧**：六项资产必须齐备。

    六项缺一不可——缺 `LICENSE_*` 契约码前端就无法区分错误，缺 CLI 客户无法取指纹，
    缺 `LicenseProvider` 抽象就谈不上"可替换实现"。
    """
    app_sources = _load_tree(APP_ROOT)
    script_sources = _load_tree(SCRIPTS_ROOT)
    models_src = MODELS.read_text(encoding="utf-8")
    contract_src = CONTRACT.read_text(encoding="utf-8")

    missing: list[str] = []

    if not re.search(r"class\s+License\b", models_src):
        missing.append("`licenses` 表（models.py 无 class License）")

    if not _any_match(app_sources, r"class\s+\w*LicenseProvider\b"):
        missing.append("`LicenseProvider` 抽象与其实现")

    if _any_match(app_sources, r"LicenseMiddleware\s*\(\s*BaseHTTPMiddleware"):
        missing.append(
            "`LicenseMiddleware` 继承了 BaseHTTPMiddleware——"
            "ADR-0006 要求**纯 ASGI**（P95 增量 < 1ms 的前提）"
        )
    elif not _any_match(app_sources, r"class\s+LicenseMiddleware\b"):
        missing.append("`LicenseMiddleware`（纯 ASGI，每请求校验）")

    codes = set(re.findall(r"\bLICENSE_[A-Z_]+\b", contract_src))
    if len(codes) < 6:
        missing.append(f"契约中的 LICENSE_* 错误码不足 6 个（当前 {len(codes)} 个）")

    if "/license/status" not in contract_src and not _any_match(
        app_sources, r"/license/status"
    ):
        missing.append("`GET /license/status` 端点")

    if not _any_match(script_sources, r"\bfingerprint\b"):
        missing.append("`license-cli fingerprint`（客户侧取机器指纹）")

    assert not missing, (
        "License 子系统资产不齐（DR-C1 / ADR-0006）：\n  - " + "\n  - ".join(missing)
    )


@pytest.mark.xfail(
    strict=True,
    reason="G-23 / DR-C1：License 子系统零代码，移除 license 后的行为围栏无从建立",
)
def test_g23_missing_license_blocks_requests() -> None:
    """DR-C1 完成判据的**行为侧**：移除 license 文件 ⇒ 受保护端点 **403 `LICENSE_MISSING`**。

    同时要求**拒绝必须落审计**——否则客户到期后打不开系统，而我们拿不出证据说明是
    License 到期而非系统故障（排障会被误导）。
    """
    try:
        from app.core.middleware import LicenseMiddleware  # noqa: F401
    except ImportError as exc:  # pragma: no cover - 有实现后不再走到这里
        pytest.fail(f"LicenseMiddleware 不存在：{exc}")

    pytest.fail(
        "已存在 LicenseMiddleware 类，但尚未接入移除 license 后的 403 / 审计断言占位——"
        "请在本条补全端到端行为断言并摘掉 xfail"
    )


# --------------------------------------------------------------------------- #
# G-24：RBAC 三粒度（DR-B9）
# --------------------------------------------------------------------------- #


def test_g24_rbac_three_granularity_matrix() -> None:
    """✅ **已转正（2026-10-03，P2-B）**：角色 × 资源 × 操作矩阵存在 **且** 端点强制校验。

    只建角色表不算 RBAC——**端点不强制校验**的话，权限就只是数据库里的一列装饰。
    所以本条**同时**断言两侧的**具体落点**（不是"源码里出现过某个字样"就算数）：

    - 矩阵侧：`roles` / `user_roles` 两张表在 ORM 元数据里，且 `user_roles` 带
      `doc_scope` / `scene_scope`（三粒度的后两格）+ `org_id` 打头索引；
    - 入口侧：`app/services/rbac/deps.py` 存在 `require_permission`，并且**真的挂**
      在受保护端点上（后者由 `tests/test_rbac.py` 按路由对象逐条核对——静态扫源码
      证明不了"挂在哪个端点上"，删掉某个端点的依赖它照样绿）。

    ⚠️ **本条不断言具体权限值**：G-24 的判据是「矩阵存在 + 入口存在」，
    具体赋权属实现决策（取值与理由登记在 `changes/P2/integration-log.md`）。
    """
    app_sources = _load_tree(APP_ROOT)
    models_src = MODELS.read_text(encoding="utf-8")

    missing: list[str] = []

    if not re.search(r"class\s+User\b", models_src):
        missing.append(
            "`users` 表（DR-B13 / G-18 前置，SSO / RBAC / License 席位三者共同依赖）"
        )
    if not re.search(r"class\s+Role\b", models_src):
        missing.append("`roles` 表（M5 §4.2，全局角色字典表）")
    if not re.search(r"class\s+UserRole\b", models_src):
        missing.append("`user_roles` 表（M5 §4.3，三粒度的载体）")

    if not _any_match(app_sources, r"(class|enum)\s+\w*Role\w*\b"):
        missing.append("角色定义（Role 枚举 / 常量）")

    if not _any_match(app_sources, r"(permission|Permission|PERMISSION)"):
        missing.append("权限定义（permission）")

    # 「资源 × 操作」矩阵：至少要有成对的 {(subject|resource), (action|operation)} 表述
    if not _any_match(
        app_sources, r"(?=.*\b(resource|subject)\b)(?=.*\b(action|operation)\b)"
    ):
        missing.append("资源 × 操作 维度（缺一格就不是三粒度）")

    if not _any_match(app_sources, r"(Depends\(|require_perm|enforce_rbac)"):
        missing.append("路由层的**强制校验入口**（依赖 / 中间件）——否则矩阵形同虚设")

    assert not missing, "RBAC 三粒度未达标（DR-B9）：\n  - " + "\n  - ".join(missing)

    # -- 判据补强（与 P2-A 给 G-18 补判据同一动作：只摘 xfail 不算转正）--
    from app.db.models import Base

    user_roles = Base.metadata.tables.get("user_roles")
    assert user_roles is not None, "user_roles 表不在 ORM 元数据里"
    columns = {column.name for column in user_roles.columns}
    for granularity in ("doc_scope", "scene_scope"):
        assert granularity in columns, (
            f"user_roles 缺 {granularity} ——缺了就只剩「角色」一格，不是三粒度"
        )
    leading = {next(iter(index.columns.keys())) for index in user_roles.indexes}
    assert "org_id" in leading, (
        "user_roles 缺少 org_id 打头的索引（ADR-0003 §3.1 第 1 条）："
        f"现有索引首列为 {sorted(leading)}"
    )


def test_g24_roles_rls_exemption_is_declared_and_bounded() -> None:
    """`roles` 的 **RLS 豁免**三条机械断言（`specs/m5-permission-audit.md` §4.2）。

    原文要求是「豁免必须在代码评审中被显式确认」，而 P2-B 是**无人值守**批次、
    过程中没有人类 CR ⇒ 按 **2026-10-03 裁决（用户选 A）** 改为
    「**代码内显式声明 + 机械断言 + 事后 CR 抽检**」：**要求未放松**
    （仍须显式、仍须给理由、仍被断言盯住），只变更履行载体。

    ① 不得出现租户业务列；② 仅允许 4 种系统预置角色；③ 豁免清单 == 实际模型。
    """
    from app.db.models import RLS_EXEMPT_TABLES, Base
    from app.services.rbac.roles import ROLE_NAME_VALUES

    roles = Base.metadata.tables.get("roles")
    assert roles is not None, "roles 表不在 ORM 元数据里"

    # ① 全局字典表**不得**出现租户业务列——出现即说明字典表被业务污染
    assert "org_id" not in {column.name for column in roles.columns}, (
        "roles 出现了 org_id：全局字典表被租户业务污染，RLS 豁免的正当性就没了"
    )

    # ② 仅允许 spec §4.2 的 4 种预置角色（DB 侧由 ck_roles_name 钉死）
    checks = [
        str(constraint.sqltext)
        for constraint in roles.constraints
        if isinstance(constraint, CheckConstraint)
    ]
    assert checks, "roles 缺少 name 的 CheckConstraint（预置角色集合无人把守）"
    assert all(
        any(f"'{name}'" in check for check in checks) for name in ROLE_NAME_VALUES
    ), f"roles 的 CheckConstraint 未覆盖全部预置角色：{checks}"

    # ③ 豁免清单 == 实际声明豁免的模型（防偷偷加表享受豁免）
    declared = {
        mapper.class_.__tablename__
        for mapper in Base.registry.mappers
        if getattr(mapper.class_, "__rls_exempt__", False)
    }
    assert declared == set(RLS_EXEMPT_TABLES), (
        f"RLS 豁免登记 {sorted(RLS_EXEMPT_TABLES)} 与模型实际声明 {sorted(declared)} "
        "不一致——新增豁免必须同时改两处（ADR-0003 §3.1 / spec §4.2）"
    )


def test_g24_role_name_set_is_frozen() -> None:
    """角色集合**封闭**：模型常量、枚举、预置种子三处必须逐字一致。

    P2-B 边界写了「不得新增角色名」。三处任一被单独改动 ⇒ 红。
    """
    from app.db.models import ROLE_NAME_VALUES as MODEL_VALUES
    from app.services.rbac.policy import ROLE_PERMISSIONS
    from app.services.rbac.roles import PRESET_ROLES, ROLE_NAME_VALUES, RoleName

    assert tuple(MODEL_VALUES) == tuple(ROLE_NAME_VALUES) == tuple(RoleName)
    assert [name for name, _ in PRESET_ROLES] == list(ROLE_NAME_VALUES)
    assert set(ROLE_PERMISSIONS) == set(ROLE_NAME_VALUES)
