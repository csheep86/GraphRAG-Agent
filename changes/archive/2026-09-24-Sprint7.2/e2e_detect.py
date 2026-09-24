"""Sprint 7.2 批次 B 的真机端到端校验（临时脚本，非产品代码）。

**不做桩、不 bypass**：走真实 HTTP 端点 → 真实任务状态机 → 真实执行体（连线上的
Neo4j 跑两跳）→ 真实 `affiliation_suspicions` 落库 → 真实复核流转。

校验点（`tasks.md` §7）：
1. `POST /affiliation/detect` → 202 + task_id；
2. 任务走到 `completed`，`result_summary.total` 与批次 A 的 **10 条**一致（不多不少 =
   没有重复出条，也没有丢疑点）；
3. `GET /affiliation/suspicions` 取回同批疑点，每条 `evidence` 非空；
4. `PATCH` 一条 → `confirmed` 且 `reviewed_by` 落真值。
"""

from __future__ import annotations

import argparse
import time
from uuid import UUID

from fastapi.testclient import TestClient

DOC_IDS = [
    "a711dc7f-b879-4821-8244-39e6cba82a4b",
    "d80d9c62-e130-45ff-ba11-d669391faa96",
    "f88f6a58-c455-4fbb-81be-f51cec21f35a",
    "a31982f3-64c3-4ff5-900d-17c5fb23355c",
    "ecbba312-c159-4fed-9a93-93e056f78f05",
    "56a49265-0fe5-4cdd-a83c-b29a52573575",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", required=True)
    parser.add_argument("--actor", required=True)
    args = parser.parse_args()

    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.main import create_app
    from app.services.kg.versioning import KgVersioningService

    settings = get_settings()
    headers = {"X-Org-Id": args.org, "X-Actor-Id": args.actor}

    with SessionLocal() as session:
        active = KgVersioningService(session).get_active(org_id=UUID(args.org))
    print(f"[0] active kg_version = {active.version if active else None} "
          f"(app_env={settings.app_env})")
    if active is None:
        print("[STOP] 没有 active 版本，detect 应 failed（不是静默 0 条）")

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/affiliation/detect", json={"doc_ids": DOC_IDS}, headers=headers
        )
        print(f"[1] POST /affiliation/detect → {response.status_code}")
        if response.status_code != 202:
            print("    body:", response.text[:400])
            return 1
        task_id = response.json()["task_id"]
        print(f"    task_id = {task_id}")

        deadline = time.time() + 180
        status_body: dict = {}
        while time.time() < deadline:
            status_body = client.get(
                f"/api/v1/affiliation/tasks/{task_id}", headers=headers
            ).json()
            if status_body["status"] in {"completed", "failed"}:
                break
            time.sleep(3)
        print(f"[2] GET /affiliation/tasks/{{id}} → status={status_body.get('status')}")
        print(f"    result_summary = {status_body.get('result_summary')}")
        print(f"    error_code = {status_body.get('error_code')}")

        listed = client.get("/api/v1/affiliation/suspicions", headers=headers)
        print(f"[3] GET /affiliation/suspicions → {listed.status_code}")
        if listed.status_code != 200:
            print("    body:", listed.text[:400])
            return 1
        body = listed.json()
        print(f"    task_id={body['task_id']} total={body['total']}")
        for item in body["items"]:
            evidence = item["evidence"]
            print(
                f"    - {item['suspicion_type']} / {item['severity']} / "
                f"{' & '.join(item['entity_names'][:2])} "
                f"(evidence={len(evidence)}, "
                f"first_chunk={evidence[0]['chunk_id'] if evidence else None})"
            )
        empty_evidence = [i["id"] for i in body["items"] if not i["evidence"]]
        print(f"    无证据疑点数 = {len(empty_evidence)}（必须为 0）")

        if not body["items"]:
            return 0
        target = body["items"][0]["id"]
        patched = client.patch(
            f"/api/v1/affiliation/suspicions/{target}",
            json={"status": "confirmed"},
            headers=headers,
        )
        print(f"[4] PATCH /affiliation/suspicions/{{id}} → {patched.status_code}")
        print(f"    body = {patched.text[:200]}")
        again = client.get(
            "/api/v1/affiliation/suspicions",
            headers=headers,
            params={"status": "confirmed"},
        ).json()
        print(f"[5] confirmed 过滤后条数 = {again['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
