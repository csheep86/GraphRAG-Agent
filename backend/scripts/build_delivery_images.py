"""P6-D1b：离线镜像包（决策 **Y8**）——构建 / 打包 / 校验的**唯一换算口**。

本脚本落实 `docs/deployment-spec.md` §4（离线安装）与 §6.4①（独立环境 = **从交付物部署**）
里能被机器判的三件事，供**交付**这一条路专用（开发态仍走 `docker compose up` 从源码构建）：

1. **构建**自研镜像（backend / frontend），tag == `app_version`（**不许 `latest`**，D-N）；
2. **打包**成 tar（`docker save`）+ 产出 `delivery-manifest.json`（SHA-256 / 大小 / image id）；
3. **校验**（`--verify`）：重算 tar 的 SHA-256、核对镜像 id、并**机械比对** tar 里的 tag
   与交付 compose 的 `image:` 是否**逐字节相同**。

**三条刻意的设计约束**：

- **入包的 tag 只能从交付 compose 反推**（`image_refs()`），**不在本脚本里写第二份**。
  两处各写一份迟早漂移，而漂移的后果是：客户现场 `docker load` 之后 compose 去找一个
  **不存在**的镜像，`pull` / `up` 那一步直接卡死（判据 ⑦b）。
- **校验只认重算出来的哈希**，不认"文件在不在"（**R-9** 恒绿失效的第一种形态就是
  `if path.exists()` ⇒ 一个字节被改过也照样绿）。
- **体积口径**：镜像的 `size` 是 `docker image inspect .Size`（**展开后**的大小，与
  `docker images` 同口径）；真正要传输的是 **tar 的 `size`**。两个数字**不许互相冒充**
  —— 本仓库曾把展开大小当传输体积，估成 1.9GB（`changes/P6-W/new-session-prompt.md` §11）。

**不含任何 registry 操作**（Y4 + Y8）：本脚本不 `login` / 不 `push` / 不读任何 registry 凭证。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

#: 直接 `python scripts/build_delivery_images.py` 时 sys.path[0] 是 `scripts/`，
#: `app` 不在其中 ⇒ 与 `scripts/backup.py` 同款处理（先补路径，再导入）。
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

#: Windows 控制台默认 GBK，而本脚本的输出里全是 `⇒` / `≈` ⇒ 不设会抛
#: `UnicodeEncodeError`（P6-W 的坑：异常发生在**打印**那一刻，看起来像脚本坏了）。
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 取决于宿主
    sys.stdout.reconfigure(encoding="utf-8")

#: **交付**用编排文件（无 `build:`，是客户现场的唯一安装入口）。
DELIVERY_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.delivery.yml"

MANIFEST_FILENAME = "delivery-manifest.json"
MANIFEST_SCHEMA_VERSION = "1.0"

#: **自研**镜像的识别口径：交付 compose 里**没有** `build:` 可依（这是它与开发 compose
#: 唯一的结构差异），故改用镜像名前缀。第三方（neo4j / postgres）不在此列。
OWN_IMAGE_PREFIX = "graphrag-agent/"

#: `docker save` 产物名的模板
TAR_TEMPLATE = "graphrag-agent-offline-{version}.tar"


class DeliveryError(RuntimeError):
    """离线包过程中的**可预期**失败（区别于未捕获异常）。"""


# --------------------------------------------------------------------------- #
# 1. 构建规格（与开发 compose 的 `build:` 逐项对齐）
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class BuildSpec:
    """一个自研镜像的构建规格。

    字段与 `deploy/docker-compose.yml` 的 `build:` 块**一一对应**——本脚本不用 compose
    去构建，是因为 `--dry-run` 必须把**完整命令**（含 `--build-arg`）打出来供人核对
    （判据 ⑥）；字段对齐就是为了防止两处漂移。
    """

    name: str
    #: 构建上下文（**相对仓库根**）
    context: str
    #: Dockerfile（**相对仓库根**；`docker build -f` 按 cwd 解析）
    dockerfile: str
    build_args: tuple[tuple[str, str], ...] = ()


#: **前端三个 ARG 必须与开发 compose 的 `build.args` 逐项相同**（决策 Y5）。
#: 漏掉 `NEXT_PUBLIC_USE_MOCK=false` ⇒ 容器化前端**静默走 Mock**（R18 红线：
#: 看起来能跑、数据全是假的）。
FRONTEND_BUILD_ARGS: tuple[tuple[str, str], ...] = (
    ("NEXT_PUBLIC_USE_MOCK", "false"),
    ("NEXT_PUBLIC_APP_ENV", "production"),
    ("NEXT_PUBLIC_API_BASE_URL", "http://127.0.0.1:8000"),
)

BUILD_SPECS: tuple[BuildSpec, ...] = (
    # backend 的 context 是**仓库根**（要为 `COPY plugins ./plugins` 提供源，ADR-0007 §3.1）
    BuildSpec(name="backend", context=".", dockerfile="backend/Dockerfile"),
    BuildSpec(
        name="frontend",
        context="frontend",
        dockerfile="frontend/Dockerfile",
        build_args=FRONTEND_BUILD_ARGS,
    ),
)


def current_app_version() -> str:
    """当前 `app_version`（compose 的 tag 必须与它相等，G-19）。"""
    from app.core.config import get_settings

    return get_settings().app_version


# --------------------------------------------------------------------------- #
# 2. 交付 compose 的合规判据（G-19 族；**yaml 解析，不 grep**）
# --------------------------------------------------------------------------- #


def compose_services(compose_path: Path) -> dict[str, dict]:
    """解析 compose 的 `services`（顶层不是映射时返回空 ⇒ 由调用方报错）。"""
    data = yaml.safe_load(Path(compose_path).read_text(encoding="utf-8")) or {}
    services = data.get("services") if isinstance(data, dict) else None
    return services if isinstance(services, dict) else {}


def delivery_compose_problems(*, compose_path: Path, version: str) -> list[str]:
    """交付 compose 的三条判据（判据 ① / ② / ③ 的机器形态）。

    返回**空列表** = 合规。三条分别是：

    1. **全服务无 `build:`** —— §6.4①「从交付物部署」；带 `build:` 意味着客户现场
       还得有源码（客户拿不到源码 ⇒ 那条路根本不通）；
    2. **自研 tag == `app_version`** —— 漂移了就不知道交付的是哪一版（G-19 同源）；
    3. **第三方 tag 固定且非 `latest`** —— `:latest` 是不可复现的同义词（D-N）。

    ⚠️ **不许用 grep 数 `build:` 字样**：本文件里这个词在注释中满地都是。
    """
    problems: list[str] = []
    path = Path(compose_path)
    if not path.is_file():
        return [f"交付 compose 不存在: {path}"]

    services = compose_services(path)
    if not services:
        problems.append(f"{path.name} 无 services ⇒ 本判据失去对象")

    checked_own = 0
    for name, service in sorted(services.items()):
        if not isinstance(service, dict):
            continue
        if "build" in service:
            problems.append(
                f"{name}：仍带 `build:` ⇒ 独立环境无源码可构建（§6.4① 要求从交付物部署）"
            )
        image = service.get("image") or ""
        tag = image.rsplit(":", 1)[-1] if ":" in image else ""
        if image.startswith(OWN_IMAGE_PREFIX):
            checked_own += 1
            if tag != version:
                problems.append(
                    f"{name}：自研镜像 {image or '（无）'} 的 tag 是 {tag or '（缺省）'}，"
                    f"与 app_version={version} 不一致"
                )
        elif not tag or tag == "latest":
            problems.append(
                f"{name}：第三方镜像 {image or '（无）'} 的 tag 为 latest 或缺省；"
                "须固定小版本，`:latest` 是不可复现的同义词"
            )
    if not checked_own:
        problems.append(
            f"{path.name} 里没有任何 {OWN_IMAGE_PREFIX}* 的自研镜像 ⇒ 本判据失去对象"
        )
    return problems


def image_refs(compose_path: Path) -> tuple[str, ...]:
    """按服务名排序去重地取出 compose 里**全部** `image:`（顺序稳定 ⇒ 可比对）。"""
    refs: list[str] = []
    for _name, service in sorted(compose_services(compose_path).items()):
        if not isinstance(service, dict):
            continue
        image = service.get("image")
        if isinstance(image, str) and image and image not in refs:
            refs.append(image)
    return tuple(refs)


def split_refs(refs: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """切成（自研, 第三方）—— 自研按镜像名前缀识别（交付 compose 无 `build:` 可依）。"""
    own = tuple(ref for ref in refs if ref.startswith(OWN_IMAGE_PREFIX))
    third = tuple(ref for ref in refs if not ref.startswith(OWN_IMAGE_PREFIX))
    return own, third


# --------------------------------------------------------------------------- #
# 3. 计划（--dry-run 打的就是它）
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Plan:
    """一次出包的**完整计划**：命令 + 入包清单。

    `commands` 是**逐条 argv**（不是拼好的字符串），`--dry-run` 时才渲染成人能读的一行。
    """

    version: str
    compose_file: Path
    tar: Path
    #: 入包的 ref（**由交付 compose 反推**，不在本脚本里写第二份 ⇒ 不可能漂移）
    refs: tuple[str, ...]
    third_party_included: bool
    commands: tuple[tuple[str, ...], ...]


def build_plan(
    *,
    version: str,
    compose_file: Path,
    out_dir: Path,
    save: bool,
    include_third_party: bool,
    skip_build: bool = False,
) -> Plan:
    """产出计划。**先过合规判据** —— 不合规的 compose 不许出包（否则包出去也装不上）。"""
    problems = delivery_compose_problems(compose_path=compose_file, version=version)
    if problems:
        raise DeliveryError(
            "交付 compose 不合规 ⇒ 不出包：\n  - " + "\n  - ".join(problems)
        )

    refs = image_refs(compose_file)
    own, third = split_refs(refs)
    selected = refs if include_third_party else own

    commands: list[tuple[str, ...]] = []
    if not skip_build:
        for spec in BUILD_SPECS:
            commands.append(build_command(spec=spec, version=version))
    if save:
        tar = Path(out_dir) / TAR_TEMPLATE.format(version=version)
        commands.append(("docker", "save", "-o", str(tar), *selected))
    else:
        tar = Path(out_dir) / TAR_TEMPLATE.format(version=version)

    return Plan(
        version=version,
        compose_file=Path(compose_file),
        tar=tar,
        refs=selected,
        third_party_included=include_third_party,
        commands=tuple(commands),
    )


def build_command(*, spec: BuildSpec, version: str) -> tuple[str, ...]:
    """一条 `docker build`：**必须**带 `-t <自研名>:<app_version>`（不许 `latest`）。"""
    argv: list[str] = ["docker", "build", "-f", spec.dockerfile]
    for key, value in spec.build_args:
        argv += ["--build-arg", f"{key}={value}"]
    argv += ["-t", f"{OWN_IMAGE_PREFIX}{spec.name}:{version}", spec.context]
    return tuple(argv)


def render(command: tuple[str, ...]) -> str:
    """argv → 一行可复制的命令（`--dry-run` 用它打印**完整命令**供人核对）。"""
    return shlex.join(command)


# --------------------------------------------------------------------------- #
# 4. 执行（真跑：build → save → manifest）
# --------------------------------------------------------------------------- #


def run(command: tuple[str, ...], *, dry_run: bool) -> int:
    """跑一条命令；``dry_run`` 时**只打印不执行**（`--dry-run` 不许真的动 docker）。"""
    print(("DRY  " if dry_run else "RUN  ") + render(command))
    if dry_run:
        return 0
    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        list(command),
        cwd=REPO_ROOT,
        check=False,
    )
    return proc.returncode


def inspect_image(ref: str) -> tuple[str, int]:
    """取镜像的 ``(image_id, size)`` —— ``size`` 是**展开后**的大小，不是传输体积。"""
    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        ["docker", "image", "inspect", ref, "--format", "{{.Id}} {{.Size}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        raise DeliveryError(f"镜像不存在或 docker 不可用: {ref}")
    parts = proc.stdout.split()
    if len(parts) != 2:
        raise DeliveryError(
            f"docker image inspect 输出无法解析: {ref} ⇒ {proc.stdout!r}"
        )
    return parts[0], int(parts[1])


def repo_relative(path: Path) -> str:
    """清单里记路径：能相对仓库根就相对（便于搬走后仍可读），否则退回落盘时的原样。

    ⚠️ 不能直接 `resolve().relative_to(REPO_ROOT)`：产物落在仓库外（测试用 `tmp_path`、
    或有人 `--out-dir` 到另一个盘符）时会抛 `ValueError` —— 那是**记账**问题，不该让出包失败。
    """
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def sha256_of(path: Path) -> str:
    """流式算 SHA-256（tar 可能几百 MB，不整读进内存）。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(*, plan: Plan, out_dir: Path) -> Path:
    """产出 `delivery-manifest.json`（风格对齐 P6-W 的 `backup-manifest.json`）。

    缺了它，"客户手上这包是不是当时出的那一包"就无从机械核（§4.1 第 6 条要求
    「SHA-256 与清单一致」）。
    """
    images: list[dict[str, Any]] = []
    for ref in plan.refs:
        image_id, size = inspect_image(ref)
        name, _, tag = ref.rpartition(":")
        images.append(
            {
                "ref": ref,
                "name": name,
                "tag": tag,
                "image_id": image_id,
                "size": size,
                "own": ref.startswith(OWN_IMAGE_PREFIX),
            }
        )
    payload: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "app_version": plan.version,
        "compose_file": repo_relative(plan.compose_file),
        "third_party_included": plan.third_party_included,
        # ⚠️ `images[].size` 是**展开后**的镜像大小（docker inspect .Size）；
        #    真正要传输的体积看 `tar.size` —— 两个数字不许互相冒充。
        "size_basis": "images[].size=docker inspect .Size（展开后）；传输体积=tar.size",
        "tar": {
            "name": plan.tar.name,
            "path": repo_relative(plan.tar),
            "sha256": sha256_of(plan.tar),
            "size": int(Path(plan.tar).stat().st_size),
        },
        "images": images,
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    target = Path(out_dir) / MANIFEST_FILENAME
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


# --------------------------------------------------------------------------- #
# 5. 校验（--verify：重算 + 机械比对 tag）
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Verification:
    """校验结果与**机读输出**（与 `app.services.backup` 的 `ManifestVerification` 同款）。"""

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


def read_manifest(out_dir: Path) -> dict[str, Any]:
    payload = json.loads(
        (Path(out_dir) / MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    if not isinstance(payload, dict):
        raise DeliveryError(f"{MANIFEST_FILENAME} 顶层不是对象")
    return payload


def verify(
    *, out_dir: Path, compose_file: Path, version: str, dry_run: bool = False
) -> Verification:
    """**重算** tar 的 SHA-256 + 核镜像 id + **机械比对** tag（判据 ④ / ⑦b）。

    失败形态分四类分别登记（不许混成一团 ⇒ "缺文件"不会被读成"哈希不符"）。

    ``dry_run=True`` 时**不调用 docker**（image id 那一段改为明写"未核"），
    让"这套包对不对"能在没有 docker daemon 的机器上先过一遍。
    """
    failures: list[str] = []
    passed: list[str] = []

    try:
        manifest = read_manifest(out_dir)
    except FileNotFoundError:
        return Verification(
            failures=(f"{out_dir} 下无 {MANIFEST_FILENAME}：这不是一个交付包",)
        )
    except (json.JSONDecodeError, DeliveryError) as exc:
        return Verification(failures=(f"{MANIFEST_FILENAME} 无法解析: {exc}",))

    if str(manifest.get("schema_version")) != MANIFEST_SCHEMA_VERSION:
        failures.append(
            f"清单 schema_version={manifest.get('schema_version')}，"
            f"本脚本只认 {MANIFEST_SCHEMA_VERSION}"
        )
    else:
        passed.append(f"{MANIFEST_FILENAME} 可解析且 schema_version 匹配")

    if str(manifest.get("app_version")) != version:
        failures.append(
            f"清单 app_version={manifest.get('app_version')} 与当前 {version} 不一致"
        )
    else:
        passed.append(f"app_version 一致（{version}）")

    # ① tar 的 SHA-256 / 大小（**重算**，不认"文件在不在"）
    tar_info = manifest.get("tar")
    tar_path = Path(out_dir) / str(
        tar_info.get("name") if isinstance(tar_info, dict) else ""
    )
    if not isinstance(tar_info, dict) or not tar_info.get("name"):
        failures.append("清单缺 tar 条目 ⇒ 无法核交付物")
    elif not tar_path.is_file():
        failures.append(f"tar 不在清单所述位置: {tar_path}")
    else:
        actual = sha256_of(tar_path)
        actual_size = int(tar_path.stat().st_size)
        if actual != tar_info.get("sha256"):
            failures.append(
                f"{tar_path.name}: SHA-256 不符（清单 {tar_info.get('sha256')} / 实测 {actual}）"
            )
        elif int(tar_info.get("size", -1)) != actual_size:
            failures.append(
                f"{tar_path.name}: 大小不符（清单 {tar_info.get('size')} / 实测 {actual_size}）"
            )
        else:
            passed.append(f"tar: SHA-256 校验通过（{actual_size} 字节）")

    # ② **机械比对**：清单里的 tag 与交付 compose 的 `image:` 逐字节相同（判据 ⑦b）
    compose = delivery_compose_problems(compose_path=compose_file, version=version)
    if compose:
        failures.append("交付 compose 不合规 ⇒ tag 比对无从谈起：" + "；".join(compose))
    else:
        expected = image_refs(compose_file)
        own, third = split_refs(expected)
        want = expected if manifest.get("third_party_included") else own
        got = tuple(
            str(item.get("ref"))
            for item in manifest.get("images", [])
            if isinstance(item, dict) and item.get("ref")
        )
        if sorted(got) != sorted(want):
            failures.append(
                "清单里的镜像与交付 compose 不一致（差一个字符客户现场就会卡在 pull）："
                f"compose={sorted(want)} / 清单={sorted(got)}"
            )
        else:
            passed.append(f"tag 与交付 compose 逐字节一致（{len(got)} 个镜像）")
            if not manifest.get("third_party_included"):
                passed.append(
                    f"第三方不入包（Y9）：{', '.join(third)} 由客户现场联网自拉"
                )

    # ③ 镜像 id（本机 docker 可用时才核；**核不了就是没验过**，不静默放过）
    if dry_run:
        passed.append("--dry-run ⇒ 未核 image id（那一步需要 docker）")
    elif shutil.which("docker") is None:
        failures.append(
            "本机无 docker ⇒ 镜像 id 无法核对（换一台装了 docker 的机器再验）"
        )
    else:
        for item in manifest.get("images", []):
            if not isinstance(item, dict) or not item.get("ref"):
                continue
            ref = str(item["ref"])
            try:
                image_id, _size = inspect_image(ref)
            except DeliveryError:
                failures.append(f"{ref}: 本机没有这个镜像 ⇒ 交付包不完整")
                continue
            if image_id != item.get("image_id"):
                failures.append(
                    f"{ref}: image id 不符（清单 {item.get('image_id')} / 实测 {image_id}）"
                )
            else:
                passed.append(f"{ref}: image id 一致（{image_id[:19]}）")

    return Verification(failures=tuple(failures), passed=tuple(passed))


# --------------------------------------------------------------------------- #
# 6. CLI
# --------------------------------------------------------------------------- #


def default_out_dir() -> Path:
    """默认落点（`backend/reports/` 已被 gitignore ⇒ 产物不会误入库）。"""
    return REPO_ROOT / "backend" / "reports" / "delivery"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out-dir", help=f"产物落点目录（默认 {default_out_dir().as_posix()}）"
    )
    parser.add_argument(
        "--compose-file",
        help=f"交付 compose（默认 {DELIVERY_COMPOSE.as_posix()}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="**只打印**将要执行的完整命令（含 --build-arg），不调用 docker",
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="不构建，只打包既有镜像"
    )
    parser.add_argument(
        "--save", action="store_true", help="执行 docker save 打 tar + 写清单"
    )
    parser.add_argument(
        "--include-third-party",
        action="store_true",
        help="把 neo4j / postgres **一并**打进包（Y9 默认只打自研；断网现场用）",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="只校验既有交付包（重算 SHA-256 + 核 image id + 比对 tag）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir()
    compose_file = Path(args.compose_file) if args.compose_file else DELIVERY_COMPOSE
    version = current_app_version()

    if args.verify:
        result = verify(
            out_dir=out_dir,
            compose_file=compose_file,
            version=version,
            dry_run=args.dry_run,
        )
        for line in result.lines():
            print(line)
        print("[OK] 校验通过" if result.ok else "[FAIL] 校验未通过")
        return 0 if result.ok else 1

    try:
        plan = build_plan(
            version=version,
            compose_file=compose_file,
            out_dir=out_dir,
            save=args.save,
            include_third_party=args.include_third_party,
            skip_build=args.skip_build,
        )
    except DeliveryError as exc:
        print(f"[FAIL] {exc}")
        return 1

    print(f"app_version={plan.version}  交付 compose={compose_file.name}")
    print(f"入包镜像（{len(plan.refs)}）: {', '.join(plan.refs)}")
    if not args.include_third_party:
        print(
            "第三方不入包（Y9）⇒ 客户现场联网自拉；断网现场改用 --include-third-party"
        )
    if not args.dry_run:
        # `docker save -o` **不会**自己建目录（实测：目录不存在 ⇒ `invalid output path`）
        out_dir.mkdir(parents=True, exist_ok=True)
    for command in plan.commands:
        code = run(command, dry_run=args.dry_run)
        if code != 0:
            print(f"[FAIL] 命令退出码 {code}: {render(command)}")
            return 1

    if args.dry_run:
        print("[DRY] 以上为将要执行的命令；未调用 docker、未产出产物")
        return 0

    if not args.save:
        print("[OK] 构建完成（未 --save ⇒ 没出包）")
        return 0

    manifest = write_manifest(plan=plan, out_dir=out_dir)
    print(f"清单已落盘: {manifest}")
    print(f"[OK] 离线包已产出: {plan.tar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
