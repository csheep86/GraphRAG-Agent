# 本地环境就位清单（P5-B 踩完坑后的可执行版本）

> **用途**：本地演示环境被清掉后（换机器 / 重建容器 / 新会话），按本文件从头跑一遍即可复原。
> **为什么单独成文**：`integration-log.md` 讲的是"发生了什么"，本文件讲的是"**照着敲什么**"。
> 下一会话开始写代码前先按 §0 判断缺什么，只补缺的那几条，不必全跑。
>
> **权威原则**：`.env` 里的口令以**容器实际配置**为准（`docker inspect`），不以文档为准 ——
> 本批就是被 `.env` 里一句陈旧的 `NEO4J_PASSWORD=password` 卡住的。

---

## 0. 先判断缺什么（¥0，30 秒）

```powershell
cd d:\AIProject\GraphRAG-Agent
docker ps --format "table {{.Names}}\t{{.Status}}"
cd backend
uv run python scripts/check_startup_readiness.py      # 只看最后三档计数，不必逐条读
```

| 现象 | 缺哪一条 | 跳到 |
|---|---|---|
| `AuthError: authentication failure` / 图谱操作全挂 | ① Neo4j 口令 | [§1](#1-neo4j-口令) |
| `FATAL: database "graphrag" does not exist` | ② PG 库与迁移 | [§2](#2-pg-库迁移rls顺序不能反) |
| 受保护端点全线 **403 `LICENSE_MISSING`** | ③ dev License | [§3](#3-dev-license别用-license_enforcefalse-绕过) |
| C1 的 `awaiting_baseline` 恒为 0 | ④ embedding 服务 | [§4](#4-本地-embedding-服务c1-基线侧) |
| pytest 里 8 条真图判据**静默 skip** | ⑤ 真图环境变量 | [§5](#5-graph_real_neo4j_-补了才不会静默-skip) |
| G-25 两条 fail，报 `affiliation-demo-v2` 无数据 | ⑥ 已知不修 | [§6](#6-affiliation-demo-v2已知不修) |

---

## 1. Neo4j 口令

```powershell
docker inspect graphrag-neo --format "{{range .Config.Env}}{{println .}}{{end}}" | Select-String NEO4J_AUTH
Select-String -Path backend\.env -Pattern '^NEO4J_PASSWORD'
```

两边不一致就把 `.env` 改成容器那个（本批实测为 `ci-graph-pw-2026`）。
`.env` 在 `.gitignore`，**改它不算进提交**。

## 2. PG 库、迁移、RLS（**顺序不能反**）

```powershell
docker exec graphrag-pg psql -U graphrag -d postgres -Atc "select datname from pg_database"
# 没有 graphrag 就建：
docker exec graphrag-pg psql -U graphrag -d postgres -Atc "CREATE DATABASE graphrag"
# ⚠️ PG 15+ 起 public schema 不默认授予 CREATE，少了这步 alembic 必然 permission denied
docker exec graphrag-pg psql -U graphrag -d graphrag -Atc "GRANT ALL ON SCHEMA public TO app_owner; GRANT USAGE ON SCHEMA public TO app_rls"

cd backend
uv run alembic upgrade head
uv run python scripts/init_rls_roles.py --admin-url postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag
```

**不要**用 `alembic stamp head` 跳过迁移 —— 那会让 G-26 的迁移判据变成空跑。
`init_rls_roles.py` 不要加 `--create-tables`（会撞 `DuplicateTable`）。

## 3. dev License（**别用 `LICENSE_ENFORCE=false` 绕过**）

缺它时所有受保护端点返回 `403 LICENSE_MISSING`（不是"全拒答"，别误判成回归）。
按 ADR-0006 §2.3 签一份真 Ed25519 的 dev license，**私钥一次性、不落盘**：

```powershell
# 临时脚本：生成密钥对 → 用私钥签名 → 写 deploy/license/app.lic → 把公钥回填 .env
# 关键字段必须与本机指纹一致：from app.services.license.fingerprint import compute_fingerprint
# 详见 changes/P5-B/integration-log.md §6 第 3 条的当时做法（内含完整可跑脚本）
cd backend
Select-String -Path .env -Pattern '^LICENSE_FILE_PATH|^LICENSE_PUBLIC_KEY'
```

验证（重启后端后）：

```powershell
Invoke-WebRequest http://127.0.0.1:8002/api/v1/license/status `
  -UseBasicParsing -SkipHttpErrorCheck `
  -Headers @{"X-Org-Id"="00000000-0000-4000-8000-000000000001"}
# 期望：states = active（真验签通过）
```

`.lic` 文件含签名与本机机器指纹，已加进 `.gitignore`（`deploy/license/*.lic`）——**不要提交**。

## 4. 本地 embedding 服务（C1 基线侧）

`.env` 里的 `EVAL_EMBEDDING_*` 早已指向它，**缺的是进程没起**：

```powershell
cd backend
Start-Process uv -ArgumentList run,python,scripts/local_embedding_server.py,--port,8009 `
  -RedirectStandardOutput "$env:TEMP\embed.log" -RedirectStandardError "$env:TEMP\embed.err" -WindowStyle Hidden
Start-Sleep -Seconds 45
Get-NetTCPConnection -LocalPort 8009 -State Listen      # 有输出即已监听
```

模型 `BAAI/bge-small-zh-v1.5` 通常在 HF 缓存里，不需要重新下载。

## 5. `GRAPH_REAL_NEO4J_*`（补了才不会静默 skip）

CI 由 job env 注入；本地不设的话，**8 条真图判据会静默 skip**（不是失败，很容易被当成"都跑过了"）：

```powershell
$env:GRAPH_REAL_NEO4J_URI = "bolt://localhost:7687"
$env:GRAPH_REAL_NEO4J_USER = "neo4j"
$env:GRAPH_REAL_NEO4J_PASSWORD = "ci-graph-pw-2026"
cd backend
uv run pytest -q        # 本地口径期望：1006 passed / 4 skipped / 2 failed
```

补了之后 G-9 图谱侧 5 条（含 **ADR-0003 §4.1 图谱侧**）会真跑并通过 —— 这是本地唯一能在 G-9 上不留盲区的方式。

## 6. `affiliation-demo-v2`（**已知不修**）

G-25 两条真图判据在本地 fail，根因是本地没有 `affiliation-demo-v2` 这套语料
（`affiliation_detect_done total=0`），**与 `attendance-demo-v1` 是两套不相干的语料**。
CI 上有该数据所以 CI 通过。**处置：不在本地恢复它**，需要实测 affiliation 时再单独引语料。

---

## 附：演示图谱重建（有 ¥ 支出：MinerU + LLM）

```powershell
cd backend
uv run python scripts/seed_attendance_ontology.py      # 本体真源 = demo/attendance/ontology_schema.json
uv run python scripts/ingest_attendance_csv.py         # 顺序：先 CSV
uv run python scripts/ingest_attendance_policies.py    # 后制度文档（会跑 verify_and_close 四项自检）
```

期望：Entity **2855** / Relation **3643**（原库 3729，差 -86 属抽取非确定性，允许）、
`attendance-demo-v1` = `ready`、`verify_and_close` **四项全 OK**。

---

## 附录 A · dev License 签发脚本（本批实跑通过）

存为临时 py 文件跑一次即可；**私钥只在内存里，不落盘**：

```python
import base64, json, pathlib, sys
sys.path.insert(0, r"d:\AIProject\GraphRAG-Agent\backend")
from cryptography.hazmat.primitives.asymmetric import ed25519
from app.services.license.fingerprint import compute_fingerprint

priv = ed25519.Ed25519PrivateKey.generate()
pub = base64.b64encode(priv.public_key().public_bytes_raw()).decode()
body = {
    "license_id": "00000000-0000-4000-8000-00000000dev1",
    "schema_version": 1,
    "product": "graphrag-agent",
    "customer": "local-dev",
    "fingerprint": compute_fingerprint(),          # ← 必须与本机一致，否则验签不过
    "issued_at": "2026-01-01T00:00:00Z",
    "not_before": "2026-01-01T00:00:00Z",
    "not_after": "2036-12-31T00:00:00Z",
    "grace_days": 30,
    "limits": {"max_orgs": 100, "max_seats": 100},
    "modules": ["m1_ingest", "m2_extract", "m3_graphqa", "m4_affiliation",
                "m5_permission", "m6_ontology", "connectors"],
}
canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
sig = base64.b64encode(priv.sign(canonical.encode("utf-8"))).decode()
payload = dict(body, signature=sig)
p = pathlib.Path(r"d:\AIProject\GraphRAG-Agent\deploy\license\app.lic")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print("PUBKEY=" + pub)                              # ← 把这个值回填 .env 的 LICENSE_PUBLIC_KEY
```

再把两行写进 `backend/.env`（两键缺一都会 403）：

```
LICENSE_FILE_PATH=d:/AIProject/GraphRAG-Agent/deploy/license/app.lic
LICENSE_PUBLIC_KEY=<上面打印的 PUBKEY>
```

> ⚠️ 签名体用的是 `sort_keys` + 紧凑分隔符的规范序，**改字段顺序或加空格都会验签失败**。
> 若日后验签实现变了，以 `app/services/license/provider.py` 的实际读法为准，**别照抄本附录**。
