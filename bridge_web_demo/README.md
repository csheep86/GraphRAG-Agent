# Bridge Web Demo · MinerU → LangExtract 桥接与可视化

独立 MVP：把 `mineru_mvp/output/` 的解析产物送入 LangExtract（DeepSeek），输出实体关系 JSON，
并提供一个单页面可视化工具（上传 PDF、实时流程状态、结果列表、知识图谱）。

> 严格遵循 `docs/bridge-pipeline-specification-v1.0.md`。
> 上游规范：`docs/mineru_cloud_api_spec.md`、`docs/langextract_spec.md`。
> 本目录**不依赖也不修改** `backend/`、`frontend/`、`contracts/`。

---

## 1. 目录结构

```
bridge_web_demo/
├── bridge_pipeline.py     # 核心管线：定位 full.md -> 清洗 -> LangExtract -> output.json
├── mineru_client.py       # MinerU 云解析客户端（上传 PDF 时使用）
├── server.py              # 极简 FastAPI：上传 / 后台任务 / 状态轮询 / 结果接口
├── index.html             # 单页面可视化（零依赖 Canvas 力导向图谱）
├── output.json            # 运行产物（实体关系 JSON）
├── output/.gitkeep        # 占位文件，强制入库
├── uploads/               # 上传的 PDF（被 .gitignore 忽略）
├── .env.example           # 配置模板
└── pyproject.toml / uv.lock
```

## 2. 安装

```bash
cd bridge_web_demo
cp .env.example .env      # 填入 DEEPSEEK_API_KEY / MINERU_TOKEN
uv sync
```

## 3. 命令行运行管线（复制 MinerU 输出 → output.json）

```bash
uv run python bridge_pipeline.py
# 或指定 MinerU 输出根目录
uv run python bridge_pipeline.py --mineru-output-dir ../mineru_mvp/output
```

管线会：
1. 遍历 `../mineru_mvp/output/*/`，取**最新** `full.md`（不存在则回退 `*_content_list_v2.json`）；
2. 清洗文本（去 HTML、页眉页脚、多余空白）；
3. 调用 LangExtract（`provider=openai`、`use_schema_constraints=False`、`fence_output=False`、
   `tokenizer=UnicodeTokenizer()`）；
4. 落盘 `output.json`（实体 + 关系 + 统计 + 溯源偏移）。

## 4. 启动可视化 Web

```bash
uv run uvicorn server:app --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000
```

- **上传 PDF** → 后台先调 MinerU 云解析，再跑 Bridge Pipeline，前端 1s 轮询步骤级状态；
- **勾选「跳过 MinerU」** → 离线演示，直接消费已有 `mineru_mvp/output/` 产物；
- **读取最近结果** → 直接加载 `output.json` 展示。

## 5. 接口

| Method | Path | 说明 |
|---|---|---|
| `POST` | `/api/jobs` | `multipart`：`file`(可选) / `skip_mineru` → `202 {job_id, trace_id}` |
| `GET` | `/api/jobs/{job_id}` | 步骤级状态 |
| `GET` | `/api/jobs/{job_id}/result` | 结果 JSON（未完成 409） |
| `GET` | `/api/result/latest` | 最近一次 `output.json` |
| `GET` | `/api/health` | 环境自检 |

## 6. 实测约束（详见两份 spec）

- MinerU 输出在 `output/<任务子目录>/`，必须遍历子目录；
- `*_content_list_v2.json` 为「页列表嵌套」，比 v1 多一层；表格 HTML 在 `content["html"]`；
- LangExtract 调用 DeepSeek 必须满足六条铁律，否则中文实体拿不到 `char_interval`（溯源失败）。

## 7. 安全

- `.env` 被根 `.gitignore` 忽略；仅提交 `.env.example`；
- 上传限制 100MB、仅允许 `.pdf`；
- 日志不输出密钥。
