"""P2-B 收尾探测：**演示库（非测试库）上，dev 主体到底能不能打开受保护端点？**

**为什么要探**：P2-B 给 10 个端点挂上了 RBAC 强制校验，而 conftest 播的那份 admin
**只落在 `graphrag_test`** —— 演示库 `graphrag` 里的 `user_roles` 是空的。
从代码路径推：dev 主体 ⇒ 查不到授权 ⇒ `REASON_NO_ROLE` ⇒ **403**。
但那是**推理**，不是实测；本脚本就是把推理换成实测结论。

**用法**（本机 .env 的 `DATABASE_URL` 指向演示库 `graphrag`）：

    cd backend && uv run python ../changes/P2/probe_rbac_dev_actor.py

⚠️ **只读**：不写任何业务数据。打印 `roles` / `user_roles` 行数 + 三个受保护端点的状态码。
（播种前后的对比由 `scripts/seed_dev_rbac.py` 执行后再跑一次本脚本取得。）
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import create_app  # noqa: E402

PROBES = [
    ("GET", "/api/v1/documents"),
    ("GET", "/api/v1/audit"),
    ("POST", "/api/v1/affiliation/detect"),
]


def main() -> None:
    settings = get_settings()
    print(f"DATABASE_URL        = {settings.database_url}")
    print(f"ALLOW_DEV_ORG_HEADER= {settings.allow_dev_org_header}")

    with SessionLocal() as session:
        roles = session.execute(text("SELECT COUNT(*) FROM roles")).scalar_one()
        grants = session.execute(text("SELECT COUNT(*) FROM user_roles")).scalar_one()
        names = [
            row[0]
            for row in session.execute(text("SELECT name FROM roles ORDER BY name"))
        ]
    print(f"roles 行数          = {roles}  {names}")
    print(f"user_roles 行数     = {grants}")

    headers = {
        "X-Org-Id": str(settings.default_org_id),
        "X-Actor-Id": str(settings.default_actor_id),
    }
    with TestClient(create_app()) as client:
        print("\n--- dev 主体打受保护端点 ---")
        for method, path in PROBES:
            response = client.request(method, path, headers=headers)
            body = response.text[:160].replace("\n", " ")
            print(f"{method} {path:<36} -> {response.status_code}  {body}")


if __name__ == "__main__":
    main()
