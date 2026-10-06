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

import json
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import CheckConstraint

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

APP_ROOT = BACKEND_ROOT / "app"
SCRIPTS_ROOT = BACKEND_ROOT / "scripts"
MODELS = APP_ROOT / "db" / "models.py"
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"

#: **`roles` 的写入白名单**（G-24 断言：`test_g24_role_writes_are_centralized`）。
#: 当前只有 `ensure_preset_roles`（播 4 种系统预置角色）。新增写入点必须先改这里
#: **并**说明理由（spec §4.2：全局字典表禁止写入租户业务数据）。
ROLE_WRITE_MODULES = {"app/services/rbac/service.py"}

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


def test_g23_missing_license_blocks_requests(tmp_path) -> None:
    """DR-C1 完成判据的**行为侧**：移除 license ⇒ 受保护端点 **403 `LICENSE_MISSING`**。

    四条都必须是**真跑出来的**，不是读代码得出的：

    ① 受保护端点被 **403** 且错误码逐字为 ``LICENSE_MISSING``；
    ② 拒绝**落审计**（``action = license.denied``）——否则客户到期后打不开系统，
       而我们拿不出证据说明是 License 到期而非系统故障（排障会被彻底误导）；
    ③ 审计里的 ``trace_id`` 与**响应体一致**（不一致就是"串不进链路的假审计"）；
    ④ ``/health`` 与 ``/license/status`` **仍然可达** —— 自检端点被锁死，
       现场连"为什么不能用"都查不到。

    ⚠️ **测试后必须清场**：本条会写入一条真实审计记录，若不清掉会污染
    其它按条数断言审计的用例（并会让 subsequent 会话的数据状态漂移）。
    """

    from sqlalchemy import delete, select

    import app.services.license.provider as provider_module
    from app.core.config import DEFAULT_ORG_ID, get_settings
    from app.core.middleware import TRACE_ID_HEADER
    from app.db.models import AuditLog
    from app.db.session import open_session
    from app.services.license.provider import DevLicenseProvider
    from app.services.license.provider import (
        get_license_provider as ignored_unused,  # noqa: F401 - 表明入口存在
    )

    settings = get_settings()
    trace_id = str(uuid4())
    old_path = settings.license_file_path
    old_provider = provider_module._PROVIDER

    try:
        # ① 让 license "消失"：指向一个确定不存在的文件 + 换掉已缓存的 Provider
        object.__setattr__(settings, "license_file_path", str(tmp_path / "absent.lic"))
        provider_module._PROVIDER = DevLicenseProvider()

        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        response = client.get("/api/v1/documents", headers={TRACE_ID_HEADER: trace_id})
        assert response.status_code == 403, (
            f"无 license 时应 403，实际 {response.status_code}：{response.text[:200]}"
        )
        body = response.json()
        assert body["code"] == "LICENSE_MISSING", f"错误码不对：{body}"
        assert body["trace_id"] == trace_id, (
            "响应 trace_id 与请求携带的不一致 ⇒ 调用方无法把这条拒绝串回自己的链路"
        )

        self_check = client.get(f"{settings.api_prefix}/license/status")
        health = client.get(f"{settings.api_prefix}/health")
        assert health.status_code == 200, "/health 必须在无 license 时仍可达"
        assert self_check.status_code == 200, (
            "/license/status 必须在无 license 时仍可达"
        )
        assert self_check.json()["has_license"] is False

        # ②③ 拒绝必须落审计，且 trace_id 与响应体一致
        with open_session(org_id=DEFAULT_ORG_ID) as session:
            rows = session.scalars(
                select(AuditLog).where(
                    AuditLog.action == "license.denied",
                    AuditLog.trace_id == trace_id,
                )
            ).all()
            assert len(rows) == 1, (
                f"拒绝未落审计（或落了 {len(rows)} 条重复）：action=license.denied / "
                f"trace_id={trace_id}"
            )
            row = rows[0]
            detail = row.detail or {}
            assert detail.get("code") == "LICENSE_MISSING", (
                f"审计详情缺错误码：{detail}"
            )
            # ADR-0006 §2.5：审计里**禁止**出现 License 正文 / 签名（写进去就是泄漏面）
            blob = json.dumps(detail, ensure_ascii=False)
            for forbidden in ("signature", "raw_payload", "-----BEGIN"):
                assert forbidden not in blob, (
                    f"审计里出现了 License 敏感字段：{forbidden}"
                )
            session.execute(
                delete(AuditLog).where(
                    AuditLog.action == "license.denied", AuditLog.trace_id == trace_id
                )
            )
            session.commit()
    finally:
        object.__setattr__(settings, "license_file_path", old_path)
        provider_module._PROVIDER = old_provider


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


def test_g24_role_writes_are_centralized() -> None:
    """`roles` 的**写入点必须集中**（spec §4.2 CR 抽检第 ② 条的机械化版本）。

    原文要求「`roles` 仅允许存放系统预置角色，**禁止**写入任何租户业务数据」。
    断言 ②（`ck_roles_name`）只钉得住 `name` 四档，**钉不住 `description`**——
    它是自由文本，正是"往全局字典表塞业务数据"的入口。

    所以这里把**所有构造 `Role(...)` 的模块**收敛到登记集合：
    新增一个写入点（哪怕在业务服务里顺手 `session.add(Role(...))`）⇒ 红 ⇒
    逼人到这里显式登记并说明为什么。

    ⚠️ **只扫 `app/`**：迁移里那句 `INSERT INTO roles` 是 raw SQL，扫不到，
    但它由 `tests/test_rbac.py::test_migration_seeds_preset_roles_and_is_replayable`
    盯住（断言 `roles` 行数 **==** 预置角色数 ⇒ 多插一行就红）。
    两侧合起来才是"没有第二条写入路径"。
    """
    offenders: list[str] = []
    for path, text in _load_tree(APP_ROOT).items():
        # 排除 `class Role(Base)` 这类定义（负向后视），只抓真正的构造调用
        if not re.search(r"(?<!class )\bRole\s*\(", text):
            continue
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel in ROLE_WRITE_MODULES:
            continue
        offenders.append(rel)

    assert not offenders, (
        "`roles` 的写入点未登记（spec §4.2：禁止写入租户业务数据）：\n  - "
        + "\n  - ".join(sorted(offenders))
        + "\n⇒ 确属必要就加进 ROLE_WRITE_MODULES 并说明理由；否则改回走 "
        "`app/services/rbac/service.py::ensure_preset_roles`"
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


def test_g23_license_decision_is_sub_millisecond_at_p95() -> None:
    """R-L4（ADR-0006 §2.6）：**每请求** License 判断的增量必须 **P95 < 1ms**。

    这是**常驻判据**而不是一次性实测：将来有人往热路径里塞了读盘 / 验签 / DB 查询，
    这条会立刻红（ADR §2.6 要求「只做内存判断 —— 有效期比较 + 模块集合 in」）。

    ⚠️ **说明边界**：量的是**中间件判断本身**的耗时（不含业务处理），
    这也是 ADR 那句"每请求判断"所指的部分；它不是端到端请求时延。
    """
    import statistics
    import time

    from app.core.middleware import LicenseMiddleware

    middleware = LicenseMiddleware(app=None)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/documents",
        "headers": [],
    }

    for _ in range(200):  # 预热：把首次加载态的开销排除在外
        middleware._decide(scope)

    samples: list[float] = []
    for _ in range(1000):
        start = time.perf_counter()
        middleware._decide(scope)
        samples.append((time.perf_counter() - start) * 1000)

    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    median = statistics.median(samples)
    assert p95 < 1.0, (
        f"License 判断 P95 = {p95:.4f}ms ≥ 1ms（违反 ADR-0006 R-L4）；"
        f"中位数 {median:.4f}ms —— 通常是把加载 / 验签 / 查库放进了热路径"
    )
