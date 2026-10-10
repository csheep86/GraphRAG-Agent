"""P6-D1b：离线镜像包（决策 Y8）与**交付 compose** 的判据。

盯四件事（其余闭环完成后自己会说清楚）：

1. **交付 compose 合规**（G-19 族）：yaml 解析后**全服务无 `build:`**、自研
   tag == `app_version`、第三方 tag 固定非 `latest`；**不许 grep 数 `build:` 字样**
   （注释里全是这个词）。配**反向用例**：把 `build:` 加回去 / 把 tag 改成 `latest`
   / 抽掉自研镜像 ⇒ 必须 FAIL（否则这条护栏会退化成恒绿，**R-9**）。
2. **开发 compose 不许被顺手改坏**：它的 `build:` 是 G-19 第二条识别"自研"的唯一
   依据（决策 Y1 = 方案 A）⇒ 单独钉一条，防止有人为了让第 9 项翻绿去删它。
3. **入包 tag 与交付 compose 逐字节相同**（判据 ⑦b）：保存清单**由 compose 反推**，
   且每个 ref 都能在 compose 原文里找到 `image: <ref>` 这一整行。
4. **`--verify` 只认重算出来的哈希**：改一个字节必须 FAIL（同 R-9）。

另有一条 **Y8 红线**：脚本源码与 CI 工作流里**不许出现** registry 操作
（`docker login` / `docker push`）—— 见到即越界。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from fnmatch import fnmatch
from pathlib import Path

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
DELIVERY_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.delivery.yml"
DEV_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
SCRIPT = BACKEND_ROOT / "scripts" / "build_delivery_images.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_delivery_images", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_delivery_images"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load()


@pytest.fixture(scope="module")
def version(mod):
    return mod.current_app_version()


def _mutated_compose(tmp_path: Path, mutate) -> Path:
    """把**真实**交付 compose 解析后改动再落盘（改结构，不是改字符串 ⇒ 不会误伤注释）。"""
    data = yaml.safe_load(DELIVERY_COMPOSE.read_text(encoding="utf-8"))
    mutate(data)
    target = tmp_path / "compose.yml"
    target.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# 1. G-19 族：交付 compose 合规（含反向用例）
# --------------------------------------------------------------------------- #


def test_g19_delivery_compose_has_no_build(mod, version) -> None:
    """§6.4①：交付给客户的编排文件**不许**带 `build:`（客户拿不到源码）。"""
    problems = mod.delivery_compose_problems(
        compose_path=DELIVERY_COMPOSE, version=version
    )
    assert problems == [], "\n  - ".join(problems)


def test_g19_dev_compose_keeps_its_build(mod) -> None:
    """反向守卫：**开发** compose 的 `build:` **不许**被删。

    G-19 第二条（`test_g19_own_image_tags_track_app_version`）靠 `build:` 识别"自研"，
    且断言 `checked`（"没有任何带 build: 的服务 ⇒ 本判据失去对象"）。
    谁为了让第 9 项翻绿去删它，那条护栏会当场 FAIL，且失败原因看起来像"护栏错了"。
    """
    services = mod.compose_services(DEV_COMPOSE)
    builders = sorted(name for name, svc in services.items() if "build" in (svc or {}))
    assert builders == ["backend", "db-init", "frontend"], builders


def test_g19_delivery_compose_rejects_a_reintroduced_build(
    mod, version, tmp_path
) -> None:
    """反向用例：把 `build:` 加回去 ⇒ 必须 FAIL。"""

    def add_build(data):
        data["services"]["backend"]["build"] = {"context": ".."}

    path = _mutated_compose(tmp_path, add_build)
    problems = mod.delivery_compose_problems(compose_path=path, version=version)
    assert any("build:" in item for item in problems), problems


def test_g19_delivery_compose_rejects_latest_tag(mod, version, tmp_path) -> None:
    """反向用例：自研 tag 改 `latest`（或漂移）⇒ 必须 FAIL。"""

    def to_latest(data):
        data["services"]["frontend"]["image"] = "graphrag-agent/frontend:latest"

    path = _mutated_compose(tmp_path, to_latest)
    problems = mod.delivery_compose_problems(compose_path=path, version=version)
    assert any("frontend" in item and "latest" in item for item in problems), problems


def test_g19_delivery_compose_rejects_missing_own_images(
    mod, version, tmp_path
) -> None:
    """反向用例：**没有**自研镜像 ⇒ 必须 FAIL（否则本判据恒绿 = 失效，R-9）。"""

    def drop_own(data):
        for name in list(data["services"]):
            if str(data["services"][name].get("image", "")).startswith(
                mod.OWN_IMAGE_PREFIX
            ):
                del data["services"][name]

    path = _mutated_compose(tmp_path, drop_own)
    problems = mod.delivery_compose_problems(compose_path=path, version=version)
    assert any("失去对象" in item for item in problems), problems


def test_g19_delivery_compose_rejects_unpinned_third_party(
    mod, version, tmp_path
) -> None:
    """反向用例：第三方 tag 不固定（`:latest`）⇒ 必须 FAIL（D-N）。"""

    def unpin(data):
        data["services"]["neo4j"]["image"] = "neo4j:latest"

    path = _mutated_compose(tmp_path, unpin)
    problems = mod.delivery_compose_problems(compose_path=path, version=version)
    assert any("neo4j" in item for item in problems), problems


def test_g19_delivery_compose_rejects_a_missing_file(mod, version, tmp_path) -> None:
    """文件不存在 ⇒ 必须报错，不许静默判"合规"。"""
    problems = mod.delivery_compose_problems(
        compose_path=tmp_path / "nope.yml", version=version
    )
    assert any("不存在" in item for item in problems), problems


# --------------------------------------------------------------------------- #
# 2. 计划：--dry-run 的完整命令与入包清单
# --------------------------------------------------------------------------- #


def test_dry_run_prints_the_frontend_build_args(mod, version, capsys) -> None:
    """判据 ⑥：`--dry-run` 必须打出**完整命令**，含 `NEXT_PUBLIC_USE_MOCK=false`。

    漏了这个 build-arg，容器化前端会**静默走 Mock**（R18：看起来能跑、数据全是假的）。
    """
    code = mod.main(["--dry-run", "--save"])
    out = capsys.readouterr().out
    assert code == 0
    assert "--build-arg NEXT_PUBLIC_USE_MOCK=false" in out
    assert f"-t graphrag-agent/frontend:{version}" in out
    assert f"-t graphrag-agent/backend:{version}" in out
    assert "docker save -o" in out


def test_dry_run_never_calls_docker(mod, monkeypatch) -> None:
    """`--dry-run` 只打印 ⇒ **真的不许**调用 docker（不然"预览"就成了"出包"）。"""
    calls: list[tuple] = []

    def boom(*args, **kwargs):  # pragma: no cover - 被调用即失败
        calls.append(args)
        raise AssertionError("--dry-run 调用了 subprocess")

    monkeypatch.setattr(mod.subprocess, "run", boom)
    assert mod.main(["--dry-run", "--save"]) == 0
    assert calls == []


def test_save_defaults_to_own_images_only(mod, version, tmp_path) -> None:
    """Y9：默认**只打自研**（≈456 MB）；第三方由客户现场联网自拉。"""
    plan = mod.build_plan(
        version=version,
        compose_file=DELIVERY_COMPOSE,
        out_dir=tmp_path,
        save=True,
        include_third_party=False,
    )
    assert plan.refs == (
        f"graphrag-agent/backend:{version}",
        f"graphrag-agent/frontend:{version}",
    )
    assert plan.third_party_included is False


def test_include_third_party_adds_all_four(mod, version, tmp_path) -> None:
    """断网现场的后路（Y9 / `--include-third-party`）：四个全打 ⇒ **不许砍掉**这条。"""
    plan = mod.build_plan(
        version=version,
        compose_file=DELIVERY_COMPOSE,
        out_dir=tmp_path,
        save=True,
        include_third_party=True,
    )
    assert plan.refs == (
        f"graphrag-agent/backend:{version}",
        f"graphrag-agent/frontend:{version}",
        "neo4j:5.26-community",
        "postgres:16-alpine",
    )


def test_saved_refs_match_the_compose_byte_for_byte(mod, version, tmp_path) -> None:
    """判据 ⑦b：tar 里的 tag 与交付 compose 的 `image:` **逐字节相同**。

    差一个字符，客户现场 `docker load` 之后 compose 就会去找一个不存在的镜像。
    """
    plan = mod.build_plan(
        version=version,
        compose_file=DELIVERY_COMPOSE,
        out_dir=tmp_path,
        save=True,
        include_third_party=False,
    )
    save_command = next(cmd for cmd in plan.commands if cmd[:2] == ("docker", "save"))
    assert list(save_command[4:]) == list(plan.refs)

    text = DELIVERY_COMPOSE.read_text(encoding="utf-8")
    for ref in plan.refs:
        assert f"image: {ref}" in text, f"交付 compose 里没有 `image: {ref}` 这一行"


def test_plan_refuses_a_non_compliant_compose(mod, version, tmp_path) -> None:
    """不合规的 compose **不许出包**（包出去也装不上）。"""

    def to_latest(data):
        data["services"]["backend"]["image"] = "graphrag-agent/backend:latest"

    path = _mutated_compose(tmp_path, to_latest)
    with pytest.raises(mod.DeliveryError) as exc:
        mod.build_plan(
            version=version,
            compose_file=path,
            out_dir=tmp_path,
            save=True,
            include_third_party=False,
        )
    assert "latest" in str(exc.value)


# --------------------------------------------------------------------------- #
# 3. --verify：重算 SHA-256 + 机械比对（改一个字节必须 FAIL）
# --------------------------------------------------------------------------- #


def _fake_docker(mod, monkeypatch) -> None:
    """把"问 docker"的两处钉死（CI 上没有 docker daemon）。"""
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(
        mod, "inspect_image", lambda ref: (f"sha256:{'0' * 12}{ref}", 123456)
    )


def _produce(mod, version, out_dir: Path, *, third_party: bool = False) -> Path:
    """造一套**真实文件**（小 tar 代替真镜像，判的是清单逻辑不是镜像本身）。"""
    plan = mod.build_plan(
        version=version,
        compose_file=DELIVERY_COMPOSE,
        out_dir=out_dir,
        save=True,
        include_third_party=third_party,
    )
    plan.tar.parent.mkdir(parents=True, exist_ok=True)
    plan.tar.write_bytes(b"fake-tar-payload")
    return mod.write_manifest(plan=plan, out_dir=out_dir)


def test_verify_passes_on_an_intact_bundle(mod, version, tmp_path, monkeypatch) -> None:
    _fake_docker(mod, monkeypatch)
    _produce(mod, version, tmp_path)
    result = mod.verify(
        out_dir=tmp_path, compose_file=DELIVERY_COMPOSE, version=version
    )
    assert result.ok, "\n".join(result.lines())
    joined = " ".join(result.lines())
    assert "SHA-256 校验通过" in joined
    assert "逐字节一致" in joined


def test_verify_detects_a_single_flipped_byte(
    mod, version, tmp_path, monkeypatch
) -> None:
    """**R-9 头号判据**：改一个字节 ⇒ 必须 FAIL（只查"文件在不在"的实现会照样绿）。"""
    _fake_docker(mod, monkeypatch)
    _produce(mod, version, tmp_path)
    tar = tmp_path / mod.TAR_TEMPLATE.format(version=version)
    payload = bytearray(tar.read_bytes())
    payload[0] ^= 0x01
    tar.write_bytes(bytes(payload))

    result = mod.verify(
        out_dir=tmp_path, compose_file=DELIVERY_COMPOSE, version=version
    )
    assert not result.ok
    assert any("SHA-256 不符" in item for item in result.failures), result.failures


def test_verify_detects_a_tag_mismatch(mod, version, tmp_path, monkeypatch) -> None:
    """清单里的 tag 与交付 compose 对不上 ⇒ 必须 FAIL（客户现场会卡在 pull）。"""
    _fake_docker(mod, monkeypatch)
    manifest_path = _produce(mod, version, tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["images"][0]["ref"] = f"graphrag-agent/backend:{version}-oops"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = mod.verify(
        out_dir=tmp_path, compose_file=DELIVERY_COMPOSE, version=version
    )
    assert not result.ok
    assert any("不一致" in item for item in result.failures), result.failures


def test_verify_dry_run_does_not_call_docker(
    mod, version, tmp_path, monkeypatch
) -> None:
    """`--verify --dry-run`：清单 / 哈希 / tag 都照核，**只是不碰 docker**。"""
    _fake_docker(mod, monkeypatch)
    _produce(mod, version, tmp_path)

    def boom(_ref):  # pragma: no cover - 被调用即失败
        raise AssertionError("--verify --dry-run 调用了 docker")

    monkeypatch.setattr(mod, "inspect_image", boom)
    result = mod.verify(
        out_dir=tmp_path,
        compose_file=DELIVERY_COMPOSE,
        version=version,
        dry_run=True,
    )
    assert result.ok, "\n".join(result.lines())
    assert any("未核 image id" in item for item in result.passed)


def test_verify_on_a_directory_without_manifest(mod, version, tmp_path) -> None:
    result = mod.verify(
        out_dir=tmp_path, compose_file=DELIVERY_COMPOSE, version=version
    )
    assert not result.ok
    assert any("这不是一个交付包" in item for item in result.failures)


def test_verify_rejects_a_foreign_schema_version(
    mod, version, tmp_path, monkeypatch
) -> None:
    _fake_docker(mod, monkeypatch)
    manifest_path = _produce(mod, version, tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "9.9"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = mod.verify(
        out_dir=tmp_path, compose_file=DELIVERY_COMPOSE, version=version
    )
    assert not result.ok
    assert any("schema_version" in item for item in result.failures)


def test_verify_rejects_app_version_drift(mod, version, tmp_path, monkeypatch) -> None:
    _fake_docker(mod, monkeypatch)
    _produce(mod, version, tmp_path)
    result = mod.verify(
        out_dir=tmp_path, compose_file=DELIVERY_COMPOSE, version=f"{version}-next"
    )
    assert not result.ok
    assert any("app_version" in item for item in result.failures)


# --------------------------------------------------------------------------- #
# 4. Y8 红线：不许出现 registry 操作
# --------------------------------------------------------------------------- #


def test_dockerignore_does_not_exclude_the_scripts_the_dockerfile_copies() -> None:
    """**F-P6D1b-2**（本机实测）：`.dockerignore` 里一条 `**/scripts/` 会让 backend
    镜像**构建失败** —— 而 Docker 只报 `CopyIgnoredFile` **warning**，真正的报错是
    `failed to calculate checksum of ref ... "/backend/scripts": not found`，看着像
    Docker 的问题，其实是自己把要 COPY 的目录排掉了。

    `backend/Dockerfile:39` 需要 `backend/scripts`（镜像里要跑 `init_rls_roles.py`
    建 RLS；没有它 backend 照常起来、库里一个策略都没有，**症状为零**）。
    ⇒ 不许再用通配把这份打掉。
    """
    dockerfile = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY backend/scripts" in dockerfile, (
        "Dockerfile 不再 COPY scripts ⇒ 本判据过时"
    )

    patterns = [
        line.strip()
        for line in (REPO_ROOT / ".dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.strip().startswith(("#", "!"))
    ]
    offenders = [
        pattern
        for pattern in patterns
        if fnmatch("backend/scripts", pattern.rstrip("/"))
        or fnmatch("backend/scripts/init_rls_roles.py", pattern)
    ]
    assert offenders == [], offenders


@pytest.mark.parametrize("needle", ["docker push", "docker login", "docker tag "])
def test_no_registry_operations_in_the_script(needle) -> None:
    """Y8：离线包是**唯一主通道** ⇒ 出包脚本里不许有推镜像的任何一步。"""
    assert needle not in SCRIPT.read_text(encoding="utf-8")


def test_no_registry_steps_in_ci() -> None:
    """判据 ⑩：CI 工作流里不许有 `docker login` / `docker push` / registry 登录动作。"""
    workflows = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows, "没有工作流文件 ⇒ 本判据失去对象"
    offenders = []
    for path in workflows:
        body = path.read_text(encoding="utf-8").lower()
        for needle in ("docker/login-action", "docker push", "docker logout"):
            if needle in body:
                offenders.append(f"{path.name}: {needle}")
    assert offenders == [], offenders
