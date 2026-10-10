"""``install_acceptance`` —— DR-E4：`docs/deployment-spec.md` §10 **安装验收清单**脚本化。

用法::

    uv run python scripts/install_acceptance.py                       # 只跑不依赖目标环境的项
    uv run python scripts/install_acceptance.py --base-url http://localhost:8000
    uv run python scripts/install_acceptance.py --backup-dir reports/backup/<...>
    uv run python scripts/install_acceptance.py --skip-pytest --out reports/acceptance.json

输出：十项**各一行** ``{PASS|SKIP|FAIL}`` + 原因，外加每条**子项**的明细行；
``--out`` 另落一份 JSON（可机读优先于好看）。

退出码
------
``0`` 无 FAIL；``1`` 有 FAIL。**SKIP 不算通过**——它是"本环境这条判据没跑到"，
必须在 ``detail`` 里写明"补什么才能跑"（§10 的判据大多是目标环境 / 双人见证的口径，
把它读成 PASS 就是典型的外推）。

**三条纪律**：

1. **不重抄第 2 / 3 / 7 项的断言**——它们已有 G-23 / G-9 / G-26；本脚本**委托 pytest
   跑既有用例**并要求"真的跑了 N 条且绿"（重复实现迟早漂移）。
2. **不为了让十项全绿去改 §10 的表**（那属 §11 第 2 类升级，不是打磨脚本）。
3. **第 9 项永远走"机械查前置 + 查留证文件"**：只有 `docs/drills/restore-drill-*.md`
   真的存在时才 PASS；否则按 D-1b 的**实际查证结果**给出 SKIP 原因（不留白，
   避免被读成漏做）。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

import httpx  # noqa: E402

from app.services.backup import verify_manifest  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

#: §10 十项的标题（**逐字照抄** `deployment-spec.md` §10 的「项」列）
ITEM_TITLES: dict[int, str] = {
    1: "全部容器健康",
    2: "License 生效",
    3: "License 拒绝可达",
    4: "上传 → 解析 → 建图",
    5: "问答可溯源",
    6: "审计留痕",
    7: "租户隔离",
    8: "备份成功",
    9: "恢复演练",
    10: "生产配置",
}

#: **交付**形态的编排文件（P6-D1b / 决策 **Y1 = 方案 A**）。
#: §6.4① 把「独立环境」定义为**从交付物部署** ⇒ 要查的是**交付给客户的那一份**
#: （`docker-compose.delivery.yml`，全服务无 `build:`），**不是**开发用的那一份
#: （`docker-compose.yml` 保留 `build:` 是**故意**的——G-19 第二条靠它识别自研镜像）。
DEFAULT_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.delivery.yml"
DEFAULT_DRILL_DIR = REPO_ROOT / "docs" / "drills"
DEFAULT_TIMEOUT = 20.0

#: `inspect_d1b` 第 ② 条只扫这些目录（**能真正产出交付物**的地方）。
#: 元组写法是为了容纳 `backend/scripts` 这种**两级**前缀（见该函数内的说明）。
SCANNED_DELIVERY_PREFIXES: tuple[tuple[str, ...], ...] = (
    (".github",),
    ("deploy",),
    ("scripts",),
    ("backend", "scripts"),
)

_SECRET_KEY_RE = re.compile(r"(?i)(key|secret|token|password|passwd|pwd|credential)")
#: 参与"是否泄漏"比对的最短密钥值（太短会满屏误报，反而没人再看这份报告）
_MIN_SECRET_LEN = 6


# --------------------------------------------------------------------------- #
# 骨架
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SubCheck:
    label: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class ItemResult:
    item: int
    title: str
    status: str
    detail: str
    subs: tuple[SubCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "subs": [
                {"label": sub.label, "status": sub.status, "detail": sub.detail}
                for sub in self.subs
            ],
        }


def combine(subs: tuple[SubCheck, ...]) -> tuple[str, str]:
    """三态汇总：**FAIL 优先，其次 SKIP，只有全 PASS 才 PASS**。

    为什么"有一票 SKIP 就整体 SKIP"：§10 每项是**复合判据**（例如第 1 项 =
    「容器 healthy」**且**「/health = 200」），只验一半就给 PASS，
    等于让人以为整条过了。SKIP 的是哪一个子项，明细行里写得清清楚楚。
    """
    if not subs:
        return SKIP, "无任何子项可执行"
    failures = [sub for sub in subs if sub.status == FAIL]
    if failures:
        return FAIL, "；".join(f"{sub.label}: {sub.detail}" for sub in failures)
    skips = [sub for sub in subs if sub.status == SKIP]
    if skips:
        listed = "；".join(f"{sub.label}（{sub.detail}）" for sub in skips)
        return SKIP, f"未覆盖: {listed} ⇒ 已过的子项不顶替没跑的子项"
    return PASS, "；".join(f"{sub.label}: {sub.detail}" for sub in subs)


@dataclass(frozen=True, slots=True)
class Context:
    base_url: str | None = None
    compose_file: Path = DEFAULT_COMPOSE
    backup_dir: Path | None = None
    env_file: Path | None = None
    log_files: tuple[Path, ...] = ()
    org_a: str | None = None
    org_b: str | None = None
    actor_a: str | None = None
    actor_b: str | None = None
    pipeline_sample: Path | None = None
    ask_question: str | None = None
    wait_seconds: float = 60.0
    run_pytest: bool = True


def _tenant_headers(ctx: Context, *, which: str) -> dict[str, str]:
    org, actor = (ctx.org_a, ctx.actor_a) if which == "a" else (ctx.org_b, ctx.actor_b)
    headers: dict[str, str] = {}
    if org:
        headers["X-Org-Id"] = str(org)
    if actor:
        headers["X-Actor-Id"] = str(actor)
    return headers


# --------------------------------------------------------------------------- #
# 工具：HTTP / pytest 委派
# --------------------------------------------------------------------------- #


def _call(
    ctx: Context,
    path: str,
    *,
    method: str = "GET",
    which: str = "a",
    json_body: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, Any]:
    """返回 ``(状态码, 解析后的 JSON)``；连不上时状态码为 ``0``，body 是原因串。"""
    try:
        response = httpx.request(
            method,
            f"{ctx.base_url}{path}",
            headers=_tenant_headers(ctx, which=which),
            json=json_body,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return 0, f"不可达: {type(exc).__name__}: {exc}"
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text[:200]
    return int(response.status_code), body


def pytest_subcheck(
    *, ctx: Context, label: str, target: str, selector: str, note: str
) -> SubCheck:
    """**委托 pytest 跑既有用例**（不是重抄断言），并断言"真的跑了 N 条且绿"。"""
    if not ctx.run_pytest:
        return SubCheck(
            label, SKIP, f"已禁用 pytest 委派（--skip-pytest）；原应跑: {selector}"
        )
    proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
        [sys.executable, "-m", "pytest", target, "-k", selector, "-q", "--no-header"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    tail = lines[-1] if lines else ""
    match = re.search(r"(\d+) passed", tail)
    ran = int(match.group(1)) if match else 0
    if proc.returncode != 0:
        return SubCheck(
            label, FAIL, f"既有护栏未通过（退出码 {proc.returncode}）: {tail[:200]}"
        )
    if ran == 0:
        return SubCheck(
            label,
            FAIL,
            f"选择器 `{selector}` 在 {target} 里没跑到任何用例 ⇒ "
            "护栏可能被改名或误删（**空跑不许算通过**）",
        )
    suffix = f"；{note}" if note else ""
    return SubCheck(label, PASS, f"复用 {target}::{selector} ⇒ {ran} passed{suffix}")


# --------------------------------------------------------------------------- #
# §10 十项
# --------------------------------------------------------------------------- #


def check_1(ctx: Context) -> tuple[SubCheck, ...]:
    """第 1 项：`docker compose ps` 全 healthy **且** `GET /health` = 200。"""
    subs: list[SubCheck] = []

    if ctx.compose_file.is_file() and shutil.which("docker"):
        proc = subprocess.run(  # noqa: S603 - 固定 argv，无 shell
            [
                "docker",
                "compose",
                "-f",
                str(ctx.compose_file),
                "ps",
                "--format",
                "json",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            # Windows 上 docker 的输出是 UTF-8，而本机默认 GBK ⇒ 不显式指定会
            # 在 reader 线程里抛 UnicodeDecodeError（且看不见——它不在主线程）
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode != 0:
            #: compose **命令本身**失败（缺 .env / docker 不在）⇒ 判 SKIP：那是"验不到"，
            #: 不是"观测到不健康"。真观测到 unhealthy（下面的分支）才判 FAIL。
            subs.append(
                SubCheck(
                    "compose healthy",
                    SKIP,
                    f"compose ps 未能执行（看不出来是否健康）: "
                    f"{proc.stderr.strip()[:160]}",
                )
            )
        else:
            rows = [
                json.loads(line) for line in proc.stdout.splitlines() if line.strip()
            ]
            if not rows:
                subs.append(
                    SubCheck("compose healthy", FAIL, "compose ps 返回 0 个服务")
                )
            else:
                bad: list[str] = []
                for row in rows:
                    service = str(row.get("Service", "?"))
                    health = str(row.get("Health", "") or "")
                    state = str(row.get("State", "") or "")
                    if health not in ("", "healthy") or state not in ("", "running"):
                        bad.append(
                            f"{service}(health={health or '-'},state={state or '-'})"
                        )
                if bad:
                    subs.append(
                        SubCheck(
                            "compose healthy",
                            FAIL,
                            f"非 healthy/running: {', '.join(bad)}",
                        )
                    )
                else:
                    subs.append(
                        SubCheck(
                            "compose healthy", PASS, f"{len(rows)} 个服务全 healthy"
                        )
                    )
    else:
        subs.append(
            SubCheck(
                "compose healthy",
                SKIP,
                f"缺 compose 文件（{ctx.compose_file}）或本机无 docker",
            )
        )

    if ctx.base_url:
        code, body = _call(ctx, "/api/v1/health")
        if code == 200 and isinstance(body, dict):
            subs.append(
                SubCheck(
                    "/health 200",
                    PASS,
                    f"status={body.get('status')} version={body.get('version')}",
                )
            )
        else:
            subs.append(SubCheck("/health 200", FAIL, f"HTTP {code}: {body}"))
    else:
        subs.append(SubCheck("/health 200", SKIP, "缺 --base-url（目标环境才验得到）"))
    return tuple(subs)


def check_2(ctx: Context) -> tuple[SubCheck, ...]:
    """第 2 项：`GET /license/status` 显示 `active` + 四维度值。"""
    if not ctx.base_url:
        return (
            SubCheck(
                "license status",
                SKIP,
                "缺 --base-url ⇒ 目标环境上的 /license/status 无从读取；"
                "本地护栏（G-23）由第 3 项复用，两者不是同一场景",
            ),
        )
    code, body = _call(ctx, "/api/v1/license/status")
    if code != 200 or not isinstance(body, dict):
        return (SubCheck("license status", FAIL, f"HTTP {code}: {body}"),)
    if body.get("status") != "active":
        return (SubCheck("license status", FAIL, f"status={body.get('status')}"),)
    limits = body.get("limits")
    if not isinstance(limits, dict) or not limits:
        return (SubCheck("license status", FAIL, "limits 缺失 ⇒ 四维度值无从核对"),)
    modules = body.get("modules") or []
    return (
        SubCheck(
            "license status",
            PASS,
            f"status=active limits={limits} modules={len(modules)}",
        ),
    )


def check_3(ctx: Context) -> tuple[SubCheck, ...]:
    """第 3 项：临时移除 license 文件 → 受保护端点 403 `LICENSE_MISSING`。

    **复用 G-23**（不重抄断言）。目标环境那一遍要在现场拔掉 license 文件再验同一语义，
    属 P6-X 的人工环节 ⇒ 本脚本给出的永远是"护栏已 green"这一档，标题写明"复用"。
    """
    return (
        pytest_subcheck(
            ctx=ctx,
            label="G-23 复用",
            target="tests/test_guardrails_compliance.py",
            selector="g23_missing_license_blocks_requests",
            note="目标环境同语义口径需现场移除 license 文件重验（人工，属 P6-X）",
        ),
    )


def check_4(ctx: Context) -> tuple[SubCheck, ...]:
    """第 4 项：样例文档走完 `pending → completed`，且 active `kg_version` 可读。"""
    if not ctx.base_url:
        return (SubCheck("上传链路", SKIP, "缺 --base-url（需已部署的后端）"),)
    sample = ctx.pipeline_sample
    if sample is None or not Path(sample).is_file():
        return (
            SubCheck(
                "上传链路",
                SKIP,
                "缺 --pipeline-sample <样例文件>：本批默认**不**碰真解析器 / LLM（决策 W3）",
            ),
        )

    path = Path(sample)
    code, body = _post_upload(ctx, path)
    if code != 200 or not isinstance(body, dict):
        return (SubCheck("上传链路", FAIL, f"upload HTTP {code}: {body}"),)
    doc_id = str(body.get("task_id") or "")
    if not doc_id:
        return (SubCheck("上传链路", FAIL, f"upload 响应无 task_id: {body}"),)

    deadline = time.monotonic() + ctx.wait_seconds
    last = "unknown"
    while time.monotonic() < deadline:
        code, body = _call(ctx, f"/api/v1/documents/{doc_id}/status", timeout=30.0)
        if code != 200 or not isinstance(body, dict):
            return (SubCheck("上传链路", FAIL, f"status HTTP {code}: {body}"),)
        last = str(body.get("status"))
        if last in ("completed", "failed"):
            break
        time.sleep(2.0)
    if last != "completed":
        return (SubCheck("上传链路", FAIL, f"状态停在 {last}（未走到 completed）"),)

    code, body = _call(ctx, "/api/v1/graph/overview", timeout=30.0)
    if code != 200 or not isinstance(body, dict):
        return (
            SubCheck(
                "上传链路",
                FAIL,
                f"走到 completed，但 /graph/overview HTTP {code}: {body}",
            ),
        )
    return (
        SubCheck(
            "上传链路",
            PASS,
            f"doc={doc_id[:8]} 走到 completed；active kg_version="
            f"{body.get('kg_version')}（entity_count={body.get('entity_count')}）",
        ),
    )


def _post_upload(ctx: Context, path: Path) -> tuple[int, Any]:
    try:
        response = httpx.post(
            f"{ctx.base_url}/api/v1/documents/upload",
            headers=_tenant_headers(ctx, which="a"),
            files={"file": (path.name, path.read_bytes())},
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        return 0, f"不可达: {type(exc).__name__}: {exc}"
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text[:200]
    return int(response.status_code), body


def check_5(ctx: Context) -> tuple[SubCheck, ...]:
    """第 5 项：1 次提问返回引用 ≥ 1 且可回查原文。"""
    if not ctx.base_url:
        return (SubCheck("问答可溯源", SKIP, "缺 --base-url（需已部署的后端）"),)
    if not ctx.ask_question:
        return (
            SubCheck(
                "问答可溯源",
                SKIP,
                "缺 --ask-question：真 LLM 不进 CI（决策 W3 / D6），本项默认不跑",
            ),
        )
    code, body = _call(
        ctx,
        "/api/v1/agent/query",
        method="POST",
        json_body={"question": ctx.ask_question},
        timeout=60.0,
    )
    if code != 200 or not isinstance(body, dict):
        return (SubCheck("问答可溯源", FAIL, f"HTTP {code}: {body}"),)
    citations = body.get("citations") or []
    if not citations:
        return (
            SubCheck(
                "问答可溯源",
                SKIP if body.get("refused") else FAIL,
                f"refused={body.get('refused')} citations=0"
                + ("（合法拒答 ⇒ 本用例不构成判据）" if body.get("refused") else ""),
            ),
        )
    return (SubCheck("问答可溯源", PASS, f"citations={len(citations)}"),)


def check_6(ctx: Context) -> tuple[SubCheck, ...]:
    """第 6 项：`audit_log` 新增 ≥ 7 条且 `trace_id` 可聚合。"""
    if not ctx.base_url:
        return (SubCheck("审计留痕", SKIP, "缺 --base-url（需已部署的后端）"),)
    code, body = _call(ctx, "/api/v1/audit?page_size=100", timeout=30.0)
    if code != 200 or not isinstance(body, dict):
        return (SubCheck("审计留痕", FAIL, f"HTTP {code}: {body}"),)
    items = body.get("items") or []
    if len(items) < 7:
        return (SubCheck("审计留痕", FAIL, f"审计条数 {len(items)} < 7"),)
    missing = [row for row in items if not row.get("trace_id")]
    if missing:
        return (SubCheck("审计留痕", FAIL, f"{len(missing)} 条缺 trace_id ⇒ 不可聚合"),)
    traces = {str(row.get("trace_id")) for row in items}
    return (
        SubCheck("审计留痕", PASS, f"{len(items)} 条 / {len(traces)} 个 trace 可聚合"),
    )


def check_7(ctx: Context) -> tuple[SubCheck, ...]:
    """第 7 项：跨 org 访问被 RLS 拦截（列表空 / 直取 403）。"""
    subs = [
        pytest_subcheck(
            ctx=ctx,
            label="G-9 复用",
            target="tests/test_guardrails_graph.py",
            selector="g9",
            note="",
        ),
        pytest_subcheck(
            ctx=ctx,
            label="G-26 复用",
            target="tests/test_guardrails_rls.py",
            selector="g26",
            note="",
        ),
    ]
    if not ctx.base_url or not ctx.org_b:
        subs.append(
            SubCheck(
                "目标环境跨 org",
                SKIP,
                "缺 --base-url / --org-b：只有打到目标环境（列表 / 直取）才等同 §10 的场景",
            )
        )
        return tuple(subs)

    code, body = _call(ctx, "/api/v1/documents?page_size=100", which="b", timeout=30.0)
    if code != 200 or not isinstance(body, dict):
        #: **被 RBAC 挡在门外 ≠ 隔离生效**：那只说明 org B 的主体还没授权
        #: （仓库的 dev 播种脚本刻意**只播默认 org**，见 `scripts/seed_dev_rbac.py`）
        #: ⇒ 环境没备好、探针取不到数 ⇒ 记 SKIP 并写出 API 给的原因。
        if code in (401, 403) and isinstance(body, dict):
            reason = str(body.get("message") or body.get("code") or "")
            raw_detail = body.get("detail")
            detail = raw_detail if isinstance(raw_detail, dict) else {}
            inner = str(detail.get("reason") or "")
            subs.append(
                SubCheck(
                    "目标环境跨 org",
                    SKIP,
                    f"org B 主体未获授权（HTTP {code} {reason}"
                    f"{(' / ' + inner) if inner else ''}）"
                    " ⇒ 这**证明不了隔离生效**，只是环境没备好",
                )
            )
            return tuple(subs)
        subs.append(SubCheck("目标环境跨 org", FAIL, f"HTTP {code}: {body}"))
        return tuple(subs)
    rows = body.get("items") or []
    leaked = [row for row in rows if str(row.get("org_id", "")) == str(ctx.org_a)]
    if leaked:
        subs.append(
            SubCheck(
                "目标环境跨 org", FAIL, f"org B 列表里出现 {len(leaked)} 条 org A 记录"
            )
        )
    else:
        subs.append(
            SubCheck(
                "目标环境跨 org",
                PASS,
                f"org B 列表 {len(rows)} 条，无一条带 org A 标记",
            )
        )
    return tuple(subs)


def check_8(ctx: Context) -> tuple[SubCheck, ...]:
    """第 8 项：`backup-manifest.json` 完整 + SHA-256 校验通过。

    判据建立在**真实备份产物**上（`scripts/backup.py` 跑出来的目录）：重算哈希，
    不是只看文件在不在。
    """
    if ctx.backup_dir is None:
        return (
            SubCheck(
                "manifest 校验",
                SKIP,
                "缺 --backup-dir ⇒ 无真实备份产物可验"
                "（先跑 `uv run python scripts/backup.py --out-dir <目录>`）",
            ),
        )
    if not Path(ctx.backup_dir).is_dir():
        return (SubCheck("manifest 校验", FAIL, f"备份目录不存在: {ctx.backup_dir}"),)
    verification = verify_manifest(Path(ctx.backup_dir))
    return tuple(
        SubCheck("manifest 校验", FAIL if line.startswith("FAIL") else PASS, line[5:])
        for line in verification.lines()
    )


#: ② 的匹配式。**两条形态都认**：
#:   a) shell 形态 `docker save` / `docker load` / `docker push`；
#:   b) **argv 形态** `("docker", "save", ...)` —— P6-D1b 的出包脚本是 Python，
#:      命令以 argv 元组出现，只认 (a) 的话**永远**看不见它（那才是真·假阴性）。
#: ⚠️ 目录范围（见 `SCANNED_DELIVERY_PREFIXES`）才是防"文档里的计划冒充交付物"的那一道
#:    （F-P6W-4）；本式只负责认出"真的有这一步"。
_DOCKER_SAVE_RE = re.compile(
    r"docker\s+(save|load)|\bdocker\s+push\b"
    r"|['\"]docker['\"]\s*,\s*['\"](save|load|push)['\"]"
)


def inspect_d1b(*, compose_file: Path, repo_root: Path) -> tuple[bool, tuple[str, ...]]:
    """**机械查** D-1b（离线镜像包 / 私有 registry）是否落地。

    §6.4① 把「独立环境」定义为**从交付物部署**：部署命令里**无 `build:`**，
    只有 `image: <固定 tag>` ⇒ 两条查证：
      ① compose 的服务里还有没有 `build:`；
      ② 全仓有没有 `docker save` / `docker load` / push 到 registry 的痕迹。
    """
    problems: list[str] = []
    if not compose_file.is_file():
        problems.append(f"compose 文件不存在: {compose_file}")
    else:
        builders: list[str] = []
        current: str | None = None
        for line in compose_file.read_text(encoding="utf-8").splitlines():
            if re.match(r"^  \S+:\s*$", line):
                current = line.strip().rstrip(":")
            elif current and re.match(r"^\s+build:", line):
                builders.append(current)
        if builders:
            problems.append(
                f"compose 仍带 build:（{', '.join(sorted(set(builders)))}）"
                " ⇒ tag 只能本机构建，独立环境拿不到"
            )

    #: **只看"能真正产出交付物"的地方**：CI 工作流与可执行脚本。
    #: `docs/` 里当然满地都是 `docker save` / `docker load` —— 那是在**描述计划**，
    #: 不是交付物；把它们算进去的话这条查证会永远命中、永远假阳性。
    #: ⚠️ **`backend/scripts/` 必须算进来**（P6-D1b 决策 D3）：离线包脚本就住在那里，
    #: 而仓库根**没有** `scripts/` 目录 ⇒ 只写 `"scripts"` 等于永远命中不到任何东西，
    #: 本条查证会**恒红**（"未发现导出痕迹"）却查不出原因。
    hits: list[str] = []
    for pattern in ("*.yml", "*.yaml", "*.sh", "*.ps1", "*.py"):
        for path in sorted(repo_root.rglob(pattern)):
            rel = path.relative_to(repo_root)
            if rel.parts[0] in {".git", "changes", "node_modules", ".venv", "docs"}:
                continue
            if not any(
                rel.parts[: len(prefix)] == prefix
                for prefix in SCANNED_DELIVERY_PREFIXES
            ):
                continue
            try:
                body = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if _DOCKER_SAVE_RE.search(body):
                hits.append(str(rel).replace("\\", "/"))
                if len(hits) >= 5:
                    break
        if len(hits) >= 5:
            break
    if not hits:
        problems.append(
            "CI 工作流 / deploy / scripts 下未发现 docker save / load / push registry"
            " 的步骤或产物（docs/ 里的描述不算——那是计划不是交付物）"
            " ⇒ 交付形态仍只能从源码起"
        )
    return (not problems), tuple(problems)


def check_9(ctx: Context) -> tuple[SubCheck, ...]:
    """第 9 项：恢复演练（**人工 + 双人**，§6.4）。

    本脚本**不宣称能替人做演练**：只有 `docs/drills/restore-drill-*.md` 真的存在时才 PASS
    （留证是人操出来的，不是算出来的）；否则输出**机械查得出来**的 SKIP 原因
    （D-1b 前置是否成立），不许留白让人读成漏做。
    """
    drills = (
        sorted(DEFAULT_DRILL_DIR.glob("restore-drill-*.md"))
        if DEFAULT_DRILL_DIR.is_dir()
        else []
    )
    if drills:
        names = ", ".join(path.name for path in drills)
        return (SubCheck("演练留证", PASS, f"{len(drills)} 份留证: {names}"),)

    _ok, problems = inspect_d1b(compose_file=ctx.compose_file, repo_root=REPO_ROOT)
    reason = (
        "**顺延 P6-X；且当前因 D-1b 未落地不可执行**：" + "；".join(problems)
        if problems
        else "D-1b 前置已满足 ⇒ 可做，但本项**仍为人工双人**（执行者 ≠ 见证者），"
        "AI 不得单独收口 ⇒ **顺延 P6-X**"
    )
    return (SubCheck("演练留证", SKIP, reason),)


def _parse_env_pairs(path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        pairs[key.strip()] = value.strip().strip('"').strip("'")
    return pairs


def check_10(ctx: Context) -> tuple[SubCheck, ...]:
    """第 10 项：`PRIVATE_DEPLOY_ENABLED=true` **且** 无密钥进日志。"""
    subs: list[SubCheck] = []

    env_file = ctx.env_file
    if env_file and Path(env_file).is_file():
        pairs = _parse_env_pairs(Path(env_file))
        raw = pairs.get("PRIVATE_DEPLOY_ENABLED")
        if raw is None:
            subs.append(
                SubCheck("PRIVATE_DEPLOY_ENABLED", FAIL, f"{env_file} 里没有这一项")
            )
        elif raw.lower() != "true":
            subs.append(
                SubCheck("PRIVATE_DEPLOY_ENABLED", FAIL, f"= {raw}，生产必须 true")
            )
        else:
            subs.append(SubCheck("PRIVATE_DEPLOY_ENABLED", PASS, "= true"))
    else:
        subs.append(
            SubCheck(
                "PRIVATE_DEPLOY_ENABLED",
                SKIP,
                "缺 --env-file：刻意不读脚本进程的 settings（那是脚本自己的环境，"
                "代表不了目标的 .env）",
            )
        )

    if not ctx.log_files:
        subs.append(
            SubCheck(
                "无密钥进日志",
                SKIP,
                "缺 --log-file：要用**目标环境真实日志**比对"
                "（本机 grep 到一行不算，证明不了生产日志也干净）",
            )
        )
        return tuple(subs)

    secrets: dict[str, str] = {}
    if env_file and Path(env_file).is_file():
        for key, value in _parse_env_pairs(Path(env_file)).items():
            if _SECRET_KEY_RE.search(key) and len(value) >= _MIN_SECRET_LEN:
                secrets[key] = value
    if not secrets:
        subs.append(
            SubCheck("无密钥进日志", SKIP, f"{env_file} 里没有可比的密钥值 ⇒ 无从判定")
        )
        return tuple(subs)

    leaked: list[str] = []
    scanned = 0
    for log in ctx.log_files:
        if not Path(log).is_file():
            leaked.append(f"{log} 不存在")
            continue
        scanned += 1
        body = Path(log).read_text(encoding="utf-8", errors="replace")
        for key, value in secrets.items():
            if value in body:
                leaked.append(f"{key} 的明文出现在 {Path(log).name}")
    if leaked:
        subs.append(SubCheck("无密钥进日志", FAIL, "；".join(leaked[:5])))
    else:
        subs.append(
            SubCheck(
                "无密钥进日志",
                PASS,
                f"{len(secrets)} 个密钥值在 {scanned} 份日志里均未出现",
            )
        )
    return tuple(subs)


CHECKS = {
    1: check_1,
    2: check_2,
    3: check_3,
    4: check_4,
    5: check_5,
    6: check_6,
    7: check_7,
    8: check_8,
    9: check_9,
    10: check_10,
}


def run_all(ctx: Context) -> tuple[ItemResult, ...]:
    results: list[ItemResult] = []
    for number in sorted(CHECKS):
        subs = CHECKS[number](ctx)
        status, detail = combine(subs)
        results.append(
            ItemResult(
                item=number,
                title=ITEM_TITLES[number],
                status=status,
                detail=detail,
                subs=subs,
            )
        )
    return tuple(results)


def render(results: tuple[ItemResult, ...]) -> str:
    lines: list[str] = []
    for result in results:
        lines.append(
            f"{result.item:>2} {result.status:<4} {result.title} | {result.detail}"
        )
        for sub in result.subs:
            lines.append(f"     - [{sub.status}] {sub.label}: {sub.detail}")
    counts = {PASS: 0, SKIP: 0, FAIL: 0}
    for result in results:
        counts[result.status] += 1
    lines.append("")
    lines.append(
        f"汇总: PASS {counts[PASS]} / SKIP {counts[SKIP]} / FAIL {counts[FAIL]}"
        "（SKIP **不是**通过：它是本环境没跑到，明细里写了补什么才能跑）"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base-url", help="目标环境后端地址（如 http://localhost:8000）"
    )
    parser.add_argument(
        "--compose-file", help="compose 文件（默认 deploy/docker-compose.yml）"
    )
    parser.add_argument("--backup-dir", help="真实备份集目录（第 8 项用）")
    parser.add_argument("--env-file", help="目标环境的 .env（第 10 项用）")
    parser.add_argument(
        "--log-file", action="append", default=[], help="目标环境日志文件（可重复）"
    )
    parser.add_argument("--org-a", help="租户 A 的 org_id")
    parser.add_argument("--org-b", help="租户 B 的 org_id（跨租户验证用）")
    parser.add_argument("--actor-a", help="租户 A 的 actor_id")
    parser.add_argument("--actor-b", help="租户 B 的 actor_id")
    parser.add_argument("--pipeline-sample", help="第 4 项用的样例文档")
    parser.add_argument("--ask-question", help="第 5 项用的提问原文")
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=60.0,
        help="第 4 项轮询 completed 的上限秒数",
    )
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="不跑 pytest 委派（第 3 / 7 项的复用子项随之 SKIP）",
    )
    parser.add_argument("--out", help="报告 JSON 落点")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = Context(
        base_url=args.base_url,
        compose_file=Path(args.compose_file) if args.compose_file else DEFAULT_COMPOSE,
        backup_dir=Path(args.backup_dir) if args.backup_dir else None,
        env_file=Path(args.env_file) if args.env_file else None,
        log_files=tuple(Path(item) for item in args.log_file),
        org_a=args.org_a,
        org_b=args.org_b,
        actor_a=args.actor_a,
        actor_b=args.actor_b,
        pipeline_sample=Path(args.pipeline_sample) if args.pipeline_sample else None,
        ask_question=args.ask_question,
        wait_seconds=args.wait_seconds,
        run_pytest=not args.skip_pytest,
    )
    results = run_all(ctx)
    print(render(results))
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                [item.to_dict() for item in results], ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\n报告已落盘: {target}")
    return 1 if any(item.status == FAIL for item in results) else 0


if __name__ == "__main__":
    sys.exit(main())
