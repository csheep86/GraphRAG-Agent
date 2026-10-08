# P5-E · 任务拆解

> **边界**：[`proposal.md`](./proposal.md) §3（11 条 Non-goals）
> **执行模式**：无人值守，逐任务验证通过即提交

---

## T1 · `mask(field, category)` 工具 + 八类策略

- [x] 新建 `backend/app/core/masking.py`：八类 category 常量 + `CATEGORIES` + `mask()` + 策略分派表
- [x] 哈希类（`tax_no` / `legal_person` / `id_card`）走 `SHA-256 + salt` → **64 字符 hex**，
      复用 `license/fingerprint.py:79` 的加 salt 形态（`f"{salt}|{value}"`）
- [x] 文件名类**直接调用** `documents.hash_filename`（D4，产出逐字节相同）
- [x] 合同金额 / 发票号 / 银行账号 / 电话按 spec §4.5 示例列实现（P5E-1 / P5E-2）
- [x] 短输入 ⇒ 全掩码（P5E-3）；未知 category ⇒ `ValueError`（P5E-4）
- [x] 中文全角数字 / 千分位 / 空格分隔先归一化（陷阱表最后一条）

## T2 · 配置 `mask_salt` + `.env.example` 同步

- [x] `config.py` 新增 `mask_salt: str`（挨着 `license_fp_salt` 落成同款形态）
- [x] `backend/.env.example` 新段（S3 必须不报）
- [x] `check_seams.py` 仍 **ERROR 0 / WARN 0**（新配置有真实消费点）

## T3 · 接线 ① `audit.py::record_audit_entry`

- [x] `record_audit_entry` 在 `session.add` **之前**对 `detail` 脱敏
- [x] 登记表 `SENSITIVE_DETAIL_FIELDS`（detail key → category）⇒ 「自动」来自登记表，**不靠猜值**（Non-goal 10）
- [x] 调用方可经 `sensitive=` 显式增补 / 覆盖
- [x] `audit.py` 文件头注释第 2 条「本批次不引入脱敏器」的口径同步改掉

## T4 · 接线 ② loguru JSON 日志出口

- [x] `core/logging.py::setup_logging` 装 loguru patcher，对 `record["extra"]` 按登记表脱敏
- [x] `middleware.py:106` 那句「本批次无脱敏器」的注释同步改掉
- [x] integration-log 登记「为什么显式调用不够、必须补兜底」

## T5 · 测试（新文件 `tests/test_masking.py`）

- [x] 八类对偶用例（spec §4.5 示例列，逐字）
- [x] 文件名 = `hash_filename` 等式断言
- [x] **落库判据**：`record_audit_entry` 写八类原文 ⇒ 读回 `audit_log.detail` JSON 断言无原文
- [x] **日志判据**：loguru sink 捕获 ⇒ 断言八类原文不出现
- [x] 短输入 / 未知 category / 全角归一化 / salt 读到的值（不只断言"设了"）
- [x] 既有正向守卫（`test_audit.py:103` 等）保持绿且**不改为绿而改断言**

## T6 · 门禁与收口

- [x] `export_openapi.py --check` 零 diff、26 路径不变（D6）
- [x] `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0
- [x] `ruff check` + `ruff format --check`
- [x] `check_session_drift.py` 逐条对照（S1 读到 11 条；S3 必须 OK）
- [x] 矩阵 H5 行 + M5 模块行同步（写明 `alert` 表仍缺 P2）
- [x] integration-log 撰写 + 提交推送 + CI 四 job 全绿
