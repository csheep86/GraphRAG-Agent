# Sprint 7.0 演示素材清单（D6 文档准备）

> **性质**：交接物。本机目前**没有任何真实演示年报**（全仓仅 `mineru_mvp/input/complex_table.pdf`，4KB 测试件；UI 上看到的"上市公司年度报告 xxxx.pdf"是前端 Mock 标题）。
> **用途**：为 D6 的两条结论提供素材——① 能否抽出可用的法人 / 地址；② 文档之间是否**真实存在**可被两跳算法命中的交叉。
> **纪律**：这份清单**不保证**存在交叉。真实情况是"抽出来才知道"，谁都不许预先假定命中。

---

## 1. 为什么是"人工下载"而不是写爬虫

已实测（2026-09-23），自动路线走不通，**不是网络问题**：

| 尝试 | 结果 |
|---|---|
| 本机 → 巨潮 `cninfo.com.cn` / 上交所 `sse.com.cn` / 深交所 `szse.cn` | ✅ 全部 `200`（0.3~0.5s）——国内站点通畅 |
| 巨潮列表 API `hisAnnouncement/query`（3 组参数：不同 stock 格式 / 带 `seDate` / 带 `plate`） | ❌ `totalAnnouncement=0` |
| 上交所 `queryCompanyBulletinNew.do` | ❌ 返回 581 字节空壳，无年报数据 |

结论：巨潮公开列表接口已收紧（需 cookie / 新版 API），继续投入的成本远超收益。**改由人工从官网下载**，一次 5–10 分钟即可拿到 3–4 份，且零合规风险。

未来若要做正规爬虫（低频、限速、遵守 robots），可作为独立小任务；**不属 Sprint 7.0 范围**。

---

## 2. 下载位置（巨潮）

1. 打开 <http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice>
2. 搜索框输入**股票代码**（如 `600036`），选中出现的公司
3. 公告类别选「**年度报告**」
4. 下载**最新一期** PDF（全文版）

## 3. 候选清单（挑一个系，下 3–4 家）

同一集团系的公司，跨公司共享法人 / 地址的概率最高：

| 系别 | 推荐代码 |
|---|---|
| 招商局 | 招商银行 `600036`、招商蛇口 `001979`、招商轮船 `601872`、招商公路 `001965` |
| 华润 | 华润三九 `000999`、华润双鹤 `600062`、华润微 `688396` |
| 中粮 | 中粮糖业 `600737`、大悦城 `000031`、酒鬼酒 `000799` |
| 中信 | 中信证券 `600030`、中信银行 `601998`、中信重工 `601608` |

> 只下一个系即可，混合不同系反而降低命中概率。

## 4. 落盘路径（**不要改 .gitignore**）

```
backend/storage/demo-docs/
```

该路径已被 `.gitignore` 第 41 行的 `backend/storage/` 覆盖 —— 几十 MB 的 PDF 不会进仓库。

**体积建议**：年报正文常 100+ 页，MinerU 全文解析慢、token 贵。演示可只取**前 15~20 页**（封面 + 第二节「公司简介和主要财务指标」就含**法定代表人 / 注册地址 / 办公地址**），真实性不受影响。

文件命名建议带上股票代码，便于后续对照：

```
backend/storage/demo-docs/600036_招商银行_2024年年报.pdf
backend/storage/demo-docs/001979_招商蛇口_2024年年报.pdf
```

## 5. 交叉性预检（下载完立刻做，别等到跑管线）

先肉眼确认这批文档到底有没有交叉——**这比跑完整管线快得多**，且能提前阻止"白跑一趟"。

用 `uv` 临时挂载 `pypdf`（不污染项目依赖）提取前 20 页文本并抓关键字段：

```powershell
cd D:\AIProject\GraphRAG-Agent
uv run --with pypdf python -c "
import glob, re
from pypdf import PdfReader
pat = re.compile(r'(法定代表人|注册地址|办公地址|注册地|公司住所)')
for f in sorted(glob.glob('backend/storage/demo-docs/*.pdf')):
    txt = '\n'.join((p.extract_text() or '') for p in PdfReader(f).pages[:20])
    print('=' * 60); print(f)
    for line in txt.splitlines():
        if pat.search(line): print('   ', line.strip()[:120])
"
```

把输出粘进 `changes/Sprint7.0/integration-log.md`，然后肉眼比对：

- [ ] **同名法定代表人**出现在 ≥2 家 → `shared_legal_rep` 有戏
- [ ] **相同注册地址字符串**出现在 ≥2 家 → `shared_address` 有戏
- [ ] 两项都无 → **零交叉**：换一个系重下，或按 plan §6.4 调整演示口径，**严禁调阈值 / 编数据凑疑点**

## 6. 与 tasks.md 的衔接

本清单是 `tasks.md` §0 最后一条「D6 演示数据集到位」的执行细则。完成 §5 预检后：

1. 把**原始输出**（不是转述）贴进 `changes/Sprint7.0/integration-log.md` 的「前置核实」段；
2. 再按 `tasks.md` §4 跑 mock vs llm 对照，产出 **D6 两条正式结论**；
3. 结论回写 `changes/Sprint7.1/proposal.md` 决策点 **D6**，作为批次 A 的开工依据。

## 7. 合规提醒

- 三座站点均为**公开信息披露**来源，取用合规；
- 仅用于本地技术演示，**不外部分发/转售**；
- 若手工下载时也遇到验证码或访问限制，**不要绕过**（换时段或换交易所官网即可）。
