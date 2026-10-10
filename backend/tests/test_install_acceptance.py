"""P6-W（**W-b**）：安装验收脚本的判据。

重点盯三件事（其余闭环完成后自己会说清楚）：

1. **十项逐条都有交代**：每一项都必须给出一个状态（``PASS`` / ``SKIP`` / ``FAIL``）
   并且 ``detail`` 非空 ⇒ 不许出现"没这一项"或"空白原因"（那种留白会被读成漏做）。
2. **第 9 项今天必须是 SKIP 且带 D-1b 证据**，并且这个"来源于**机械查**"：
   `inspect_d1b()` 真的去读 `deploy/docker-compose.yml`、真的去全仓找导出痕迹。
   ⇒ 一旦哪天有人去补 D-1b，这条就不再是这个理由（不会停在"永久 SKIP"上）。
3. **第 8 项建立在真实备份产物上**：给出一套真的备份集 ⇒ PASS；改一个字节 ⇒ FAIL。
   这条是专门堵"只检查文件是否存在"的恒绿实现（**R-9**）。

pytest 委派（第 3 / 7 项）在本文件一律用 ``run_pytest=False`` 关掉：
那两条本身跑的就是别人的用例，在这里再套一层只会把批次拖慢。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.services.backup import (
    FILE_OBJECT_NAMES,
    KG_RECORDED,
    MANIFEST_SCHEMA_VERSION,
    ActiveKgVersion,
    BackupManifest,
    file_entry,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "install_acceptance", BACKEND_ROOT / "scripts" / "install_acceptance.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["install_acceptance"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load()


# --------------------------------------------------------------------------- #
# 1. 十项逐条有交代
# --------------------------------------------------------------------------- #


def test_all_ten_items_report_a_status_and_a_reason(mod) -> None:
    results = mod.run_all(mod.Context(run_pytest=False))
    assert len(results) == 10
    assert [item.item for item in results] == sorted(mod.ITEM_TITLES)
    for result in results:
        assert result.status in {"PASS", "SKIP", "FAIL"}, result
        assert result.detail.strip(), f"第 {result.item} 项没有原因"
        assert result.title == mod.ITEM_TITLES[result.item]
        for sub in result.subs:
            assert sub.status in {"PASS", "SKIP", "FAIL"}
            assert sub.detail.strip(), f"第 {result.item} 项的子项 {sub.label} 没有原因"


def test_render_and_json_are_machine_readable(mod) -> None:
    results = mod.run_all(mod.Context(run_pytest=False))
    rendered = mod.render(results)
    for result in results:
        assert f"{result.item} " in rendered or f"{result.item}  " in rendered
        assert result.title in rendered

    payload = json.loads(json.dumps([item.to_dict() for item in results]))
    assert [row["item"] for row in payload] == list(range(1, 11))
    assert all(row["status"] in {"PASS", "SKIP", "FAIL"} for row in payload)
    assert all(row["subs"] for row in payload)  # 每项至少一个子项 ⇒ 不存在"空项算通过"


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("PASS", "PASS"), "PASS"),
        (("PASS", "SKIP"), "SKIP"),
        (("PASS", "FAIL"), "FAIL"),
        (("SKIP", "FAIL"), "FAIL"),
        (("SKIP", "SKIP"), "SKIP"),
    ],
)
def test_combine_priority_fail_then_skip_then_pass(mod, statuses, expected) -> None:
    subs = tuple(
        mod.SubCheck(label=f"s{i}", status=status, detail="d")
        for i, status in enumerate(statuses)
    )
    assert mod.combine(subs)[0] == expected


def test_combine_of_empty_is_skip_not_pass(mod) -> None:
    assert mod.combine(())[0] == "SKIP"


# --------------------------------------------------------------------------- #
# 2. 第 9 项：今天必须是 SKIP + D-1b 机械证据
# --------------------------------------------------------------------------- #


def test_d1b_inspection_finds_build_in_dev_compose(mod) -> None:
    """**开发** compose 仍带 `build:` ⇒ 拿它当交付物查，结果必须是"不合规"。

    这条不是"D-1b 未落地"的证据（交付 compose 已经落地，见下一条），而是钉死
    「方案 A」的前提：开发那份的 `build:` **必须留住**（G-19 第二条靠它识别自研）。
    """
    ok, problems = mod.inspect_d1b(
        compose_file=REPO_ROOT / "deploy" / "docker-compose.yml", repo_root=REPO_ROOT
    )
    assert ok is False
    joined = " ".join(problems)
    assert "build:" in joined


def test_d1b_inspection_passes_on_the_delivery_compose(mod) -> None:
    """P6-D1b 的闭环：**交付** compose 无 `build:` + `backend/scripts/` 下有出包脚本。

    ⚠️ 第二条能不能查到，取决于 `SCANNED_DELIVERY_PREFIXES` 里有没有
    `("backend", "scripts")` —— 仓库根没有 `scripts/` 目录，漏了它这条会**恒红**。
    """
    ok, problems = mod.inspect_d1b(
        compose_file=REPO_ROOT / "deploy" / "docker-compose.delivery.yml",
        repo_root=REPO_ROOT,
    )
    assert ok, "；".join(problems)
    assert ("backend", "scripts") in mod.SCANNED_DELIVERY_PREFIXES


def test_d1b_inspection_ignores_prose_in_docs(mod, tmp_path: Path) -> None:
    """反向守卫：docs/ 里描述计划的 `docker save` **不算**交付物。

    没有这条，只要有人在文档里写下这个词，查证就会被"伪证"命中
    （本仓库 `docs/deployment-spec.md` 正是在描述 D-1b 这条未做完的计划）。
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text(
        "计划：docker save -o images.tar 后 docker load -i images.tar\n",
        encoding="utf-8",
    )
    ok, problems = mod.inspect_d1b(
        compose_file=tmp_path / "compose.yml", repo_root=tmp_path
    )
    assert ok is False  # compose 不存在 ⇒ 仍有 1 条问题，但不该被 docs 里的词抵消
    assert "docs/ 里的描述不算" in " ".join(problems)


def test_item9_is_skipped_because_no_drill_is_filed_yet(mod) -> None:
    """第 9 项**仍必须是 SKIP**，但理由从"D-1b 未落地"变成"**演练未做**"。

    本批（P6-D1b）只解前置；翻 PASS 要等 P6-X 的**双人演练留证**。
    ⇒ 断言同时盯两头：不许再拿 D-1b 当借口，也不许偷偷变 PASS。
    """
    subs = mod.check_9(mod.Context(run_pytest=False))
    status, detail = mod.combine(subs)
    assert status == "SKIP"
    assert "P6-X" in detail
    assert "D-1b 前置已满足" in detail
    assert "未落地" not in detail


def test_item9_would_flip_once_a_drill_is_filed(
    mod, tmp_path: Path, monkeypatch
) -> None:
    """反向守卫：留证真出现了，脚本**必须**认；不许永远停在 SKIP。

    用临时目录冒充 `docs/drills/`（monkeypatch），不往真仓库里落 —— 免得测试自己
    造出一份"演练留证"，反倒把第 9 项弄成假的 PASS。
    """
    drills = tmp_path / "drills"
    drills.mkdir()
    (drills / "restore-drill-2099-01-01.md").write_text("# 占位\n", encoding="utf-8")
    monkeypatch.setattr(mod, "DEFAULT_DRILL_DIR", drills)

    status, detail = mod.combine(mod.check_9(mod.Context(run_pytest=False)))
    assert status == "PASS", "有留证却不认 ⇒ 这条验收项会永远停在 SKIP"
    assert "restore-drill-2099-01-01.md" in detail


# --------------------------------------------------------------------------- #
# 3. 第 8 项：建立在真实备份产物上
# --------------------------------------------------------------------------- #


@pytest.fixture
def real_backup_set(tmp_path: Path) -> Path:
    """五类文件齐全 + 真哈希（与 `test_backup_restore.py` 同款，不依赖外部工具）。"""
    backup = _load_module("backup", BACKEND_ROOT / "scripts" / "backup.py")
    out_dir = tmp_path / "set"
    out_dir.mkdir()

    storage_root = tmp_path / "storage"
    (storage_root / "org-a").mkdir(parents=True)
    (storage_root / "org-a" / "a.txt").write_text("原件", encoding="utf-8")
    env_file = tmp_path / "env.txt"
    env_file.write_text(
        "APP_ENV=production\nNEO4J_PASSWORD=pw123456\n", encoding="utf-8"
    )
    license_file = tmp_path / "app.lic"
    license_file.write_text("lic-body", encoding="utf-8")

    (out_dir / "postgres.dump").write_bytes(b"pgdump")
    (out_dir / "neo4j.dump").write_bytes(b"neo4jbytes")
    objects = (
        file_entry(
            name="postgres",
            path=out_dir / "postgres.dump",
            base_dir=out_dir,
            method="pg_dump -Fc",
        ),
        file_entry(
            name="neo4j",
            path=out_dir / "neo4j.dump",
            base_dir=out_dir,
            method="neo4j-admin database dump",
        ),
        backup.collect_storage(out_dir=out_dir, storage_root=storage_root),
        backup.collect_license(out_dir=out_dir, license_file=license_file),
        backup.collect_config(out_dir=out_dir, env_file=env_file),
    )
    assert {item.name for item in objects} == set(FILE_OBJECT_NAMES)
    BackupManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        generated_at="2099-01-01T00:00:00+00:00",
        app_version="1.6.0",
        objects=objects,
        active_kg_version=ActiveKgVersion(
            status=KG_RECORDED, source="pg:kg_versions", version="v-p6w-1"
        ),
    ).write(out_dir)
    return out_dir


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_item8_passes_on_a_real_backup_set(mod, real_backup_set: Path) -> None:
    status, detail = mod.combine(mod.check_8(mod.Context(backup_dir=real_backup_set)))
    assert status == "PASS", detail


def test_item8_fails_after_one_byte_is_changed(mod, real_backup_set: Path) -> None:
    """**本批最要紧的一条**：清单写着原哈希，实际改了一个字节 ⇒ 第 8 项必须红。"""
    (real_backup_set / "license.lic").write_bytes(b"tampered")
    status, detail = mod.combine(mod.check_8(mod.Context(backup_dir=real_backup_set)))
    assert status == "FAIL"
    assert "SHA-256 不符" in detail


def test_item8_without_backup_dir_is_skipped_not_pass(mod) -> None:
    status, detail = mod.combine(mod.check_8(mod.Context()))
    assert status == "SKIP"
    assert "scripts/backup.py" in detail


def test_item8_fails_when_backup_dir_does_not_exist(mod, tmp_path: Path) -> None:
    status, detail = mod.combine(mod.check_8(mod.Context(backup_dir=tmp_path / "nope")))
    assert status == "FAIL"
    assert "不存在" in detail


# --------------------------------------------------------------------------- #
# 4. 目标环境项：没给 --base-url 时必须是 SKIP（不许读成"这项过了"）
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("number", [1, 2, 4, 5, 6])
def test_target_env_items_skip_without_base_url(mod, number: int) -> None:
    check = mod.CHECKS[number]
    subs = check(mod.Context(run_pytest=False))
    assert subs
    assert any(sub.status == "SKIP" for sub in subs)
    assert "base-url" in " ".join(sub.detail for sub in subs)


def test_item10_needs_an_env_file_and_a_real_log(mod, tmp_path: Path) -> None:
    """第 10 项两个子项都得有出处：`.env` 与**目标环境的真实日志**。"""
    subs = mod.check_10(mod.Context())
    assert len(subs) == 2
    assert {sub.status for sub in subs} == {"SKIP"}

    env_file = tmp_path / "prod.env"
    env_file.write_text(
        "PRIVATE_DEPLOY_ENABLED=true\nNEO4J_PASSWORD=prod-pw-abcdef\n", encoding="utf-8"
    )
    clean_log = tmp_path / "app.log"
    clean_log.write_text('{"event": "boot", "k": "v"}\n', encoding="utf-8")
    subs = mod.check_10(mod.Context(env_file=env_file, log_files=(clean_log,)))
    assert {sub.status for sub in subs} == {"PASS"}

    dirty_log = tmp_path / "leak.log"
    dirty_log.write_text(
        '{"event": "boot", "pwd": "prod-pw-abcdef"}\n', encoding="utf-8"
    )
    subs = mod.check_10(mod.Context(env_file=env_file, log_files=(dirty_log,)))
    leaking = [sub for sub in subs if sub.label == "无密钥进日志"]
    assert leaking and leaking[0].status == "FAIL"
