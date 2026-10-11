# P7-B：`check_startup_readiness.py` 补 `skipif` / fixture-skip 档位 + 自带反向自测

> **来源**：[`changes/P7-A/integration-log.md`](../P7-A/integration-log.md) §5.1 / §5.2 / §6（P1 项）。
> P7-A 当初**刻意没在本批修**，理由写在 `P7-A/proposal.md` §3 第 6 条：改脚本会改 CI 报告口径、且须连带给脚本加自测 ⇒ 独立成批。
> **队列**：`docs/delivery-plan.md` §9.2 序 9。

## 1. 要解决什么（**P7-A 已实证，此处不重述证据**）

> 本地不起 Neo4j 时，全量 `pytest` 由 **930 passed → 923 passed**，少的 **7 条全绿通过、无人察觉**；
> 而 `check_startup_readiness.py` **两次输出一模一样**（都报 `[OK]`）。

⇒ 这违反本项目 §0.1 那句「以机器输出为准」—— 因为**在这个格子机器上，机器输出本身失真了**。
失真原因是结构性的：脚本的三分类全靠 `_xfail_state()` 一个布尔，`skipif` 与 fixture 内 `pytest.skip`
**完全不参与判定** ⇒ 带这两种标记的护栏一律落进 🟢「已生效」。

**全仓弱化形态普查（本批开工复核，非抽样）**：

| 形态 | 命中 | 脚本改动前 |
|---|---|---|
| `xfail(strict=True)` | 3（G-12 ×1、G-23 ×2） | ✅ 判 `[--]` 挂起，识别正确 |
| `xfail(条件, strict=False)` | 1（G-11） | ✅ 条件为假时不判挂起，正确 |
| `@pytest.mark.skipif(...)` | 4 | ❌ 判 `[OK]`，**不识别** |
| fixture 内 `pytest.skip(...)` | 17 | ❌ 判 `[OK]`，**不识别** |
| `local_only` | 3 | 见 Non-goals 第 3 条 |

（P7-A §5.2 说的"差值 7 条"是**有无 Neo4j** 导致的横跨差值；本批要覆盖的是**全部可跳过形态**，不止那 7 条。）

## 2. 不做什么（Non-goals）

1. **不改任何测试文件的实际行为** —— 不删 `skipif`、不改 fixture。本批改的是脚本的**读法**，不是测试的跑法。
2. **不改 CI** —— `.github/workflows/ci.yml` 零 diff。（已核实：第 258-259 步调本脚本时明示「**仅报告、非门禁**」，且脚本退出码恒 0 ⇒ 改动不会断流水线。）
3. **不接 `local_only`** —— P7-A §5.1 已判：由 `test_local_only_boundary.py` 独立登记 + CI 单列一步打印 ⇒ **不在本脚本职责内**，本批保持该结论。
4. **不动既有三档的语义** —— 🟢 / 🟠 / 🟡 的定义与「P8 零缺口只认全 🟢」的要求都不放宽。
5. **不动产品代码** —— `backend/app/**` 零改动。
6. **不追求静态求值全准** —— 判不出来的条件一律按**保守**处理（记"可能跳过"），
   **宁可多报一行待确认，也不许把"会跳过"误报成"在拦"**。

## 3. 设计

### 3.1 新增第四档 🔵 **条件跳过**

不是把它塞进既有任何一档 —— 三档语义分别是「在拦 / 一半在拦 / 完全挂起」，
而"环境不满足时整条不执行"是**第四种性质**，混进去会让"该怎么转正"这件事说不清楚。

| 档 | 记号 | 含义 | 转正动作 |
|---|---|---|---|
| 🟢 已生效 | `[OK]` | 真在拦 | — |
| 🔵 **条件跳过** | `[SKIP]` | **可能在本次环境里根本没跑** | 把 skip 条件满足起来（起图库 / 设 env），或拆出必跑子集 |
| 🟠 部分生效 | `[~~]` | 一半在拦、一半挂起 | 摘掉那条 xfail |
| 🟡 挂起 | `[--]` | CI 绿，没在拦 | 让测试真通过再摘 xfail |

### 3.2 归属优先级

```
suspended(xfail 生效) > skipped(可跳过) > active
```

理由：一条同时带 xfail 与 skip 的用例，先按"一定没拦"记，避免把更严重的状态被较轻的状态盖住。

### 3.3 识别办法（静态，`ast`）

- **装饰器 `skipif`**：沿用 `_xfail_state()` 那套静态求值（含 `_eval` 的条件折叠）；
  多iline 的 `@pytest.mark.skipif(` 同样按 `ast` 取 ⇒ 不受换行影响。
- **fixture 内 `pytest.skip`**：先扫模块内的 `@pytest.fixture` 建名表，
  再取测试函数的**参数名**当它所依赖的 fixture ⇒ 若 fixture 体内有 `pytest.skip(...)` 即记命中；
  **fixture 依赖 fixture 时递归**，避免"中间跳一级就漏"。
- **fixture 借@pytest.fixture 装饰 或以 conftest 提供**：conftest 提供的 fixture 本批也扫（`tests/conftest.py`）。

### 3.4 `--self-test`（**含反向验证**）

给脚本自身加内联自测：在临时目录写最小源码 → 走同一套 `collect_guardrails()` → 断言档位。

必须同时有**两个方向**的用例，这是本脚本一贯的戒律（docstring 原话：「本脚本要防的是**两个方向**的错」）：

| 方向 | 用例 |
|---|---|
| 正向（别漏报） | `skipif(True)` 不得判 active；fixture skip 不得判 active；嵌套 fixture 不得判 active |
| **反向（别误报）** | `skipif(False)` **仍须** active；无任何标记仍须 active；既有 `xfail` 仍须 `[--]`（不得被新逻辑吃成 skip） |

## 4. 出口判据（每条都贴机器输出）

| # | 判据 | 期望 |
|---|---|---|
| **J1** | 4 处装饰器 `skipif` 被识别 | 对应 G 编号从 🟢 转 🔵（或 🟠，若同编号下还有 xfail 成员） |
| **J2** | 17 处 fixture 内 skip 被识别 | 同上；**含 conftest 提供、经一跳 fixture 依赖的情况** |
| **J3** | **不倒退**：改动前判定为 🟢、且不依赖任何可跳过 fixture 的用例 | 改后**仍为 🟢**（基线快照逐行比对，我只许新增档位、不许把"在拦"改写成"没在拦"） |
| **J4** | `--self-test` 全绿 | 正向 + 反向用例全部通过 |
| **J5** | 回归 | `pytest` passed 不降、`ruff` 绿、`check_seams.py` 不倒退 |

## 5. 升级路径

出现下列任一情形 ⇒ 停下找用户：

1. 发现某条 skip 其实**应当变成必跑**（那是产品/测试取舍，不该在改判读脚本时顺手决定）；
2. `--self-test` 出现需要"放宽才绿"的诱惑；
3. 想顺手把 `local_only` 也接管过来（跨出 P7-A 已划的职责边界）；
4. 想把 CI 那一步从"仅报告"升成门禁（会改变全项目的红线口径）。

---

## 6. 实现记录（2026-10-11）

### 6.1 改动清单

| 文件 / 位置 | 改动 |
|---|---|
| `scripts/check_startup_readiness.py` | 新增第四档 🔵 **条件跳过**；新增 `_is_fixture` / `_calls_skip` / `_fixture_index` / `_skip_via_fixture`（**递归**）/ `_skip_state`；`collect_guardrails()` 增加 `tests_dir` 参数并**连 `conftest.py` 一起扫**；每条记录新增 `skipped` / `skip_reason` |
| `_sym()` | 新增 `conditional`（🔵，ASCII 降级 `[SK]`） |
| 报告输出 | 新增 🔵 区块；逐条三态标记（🟢 / 🔵 / 🟡）+ reason；行动指引第 1 条纳入 🔵 |
| `--self-test` | 7 条固定用例（正向 4 / 反向 3），失败时退出码 **1** |

**零改动**：`.github/workflows/ci.yml`、`backend/app/**`、**任何测试文件里的 skip 标记** ——
本批改的是脚本的**读法**，不是测试的跑法。

### 6.2 判据读数

| # | 判据 | 读数 |
|---|---|---|
| **J1** | 装饰器 `skipif` 被识别 | ✅ G-25 的 2 条（`skipif(not _REAL_GRAPH)`）由 🟢 转 🔵，reason 逐条打印 |
| **J2** | fixture 内 skip 被识别 | ✅ G-9 的 5 条（走 `real_driver`）由 🟢 转 🔵，reason 打出 `f'连不上 Neo4j（{uri}）：{exc}'` |
| **J2b** | **交叉印证** | ✅ 2 + 5 = **7 条** —— 与 P7-A §5.2 实测「930 → 923，**少 7 条**」**逐条吻合** |
| **J3** | 不倒退 | ✅ 🟢 17 → **15**，减少的**正好**是这两个 G；其余 15 个 G 档位未变；🟠 / 🟡 仍为 0 |
| **J4** | `--self-test` | ✅ 7 条全过（正向 4 / 反向 3），退出码 0 |
| **J5** | 回归 | ✅ `ruff check` + `ruff format --check` 绿；`check_seams.py` **OK 12 / ERROR 0 / WARN 0**；`pytest -k "guardrail or g25 or g9"` **69 passed / 7 skipped** |

### 6.3 ⚠️ 一个必须说清的口径：**21 处弱化形态里只有 7 处在本脚本职责内**

全仓普查得 `@pytest.mark.skipif` **4 处** + fixture 内 `pytest.skip` **17 处** = **21 处**，
但 `check_startup_readiness.py` **只判带 G 编号的护栏**（函数名 `test_g<N>_`，或专项文件首行标注 `G-<N>`）。

⇒ 落在 G 编号上的恰好是 **7 处**（G-25 ×2、G-9 ×5）；其余 **14 处属于不带 G 编号的普通测试**，
不在本脚本职权内 —— 它们的"悄悄跳过"由 pytest 计数与 CI 日志承载。

**所以报告里 🔵 只有 2 个 G：这是职责边界，不是漏报。**

### 6.4 遗留（登记，不自行处置）

1. **CI 未加 `--self-test` 步骤** —— Non-goals 第 2 条写明本批不动 `ci.yml`。
   ⚠️ 但这意味着判定逻辑将来被改坏时**没有东西会叫** ⇒ 建议下一批把它加进流水线
   （那个 Step 本来就明示「仅报告、非门禁」，加一条自测不会改变门禁强度）。
2. 🔵 里那 7 条**要不要变成必跑**（补环境 / 拆必跑子集），属产品与测试取舍，本批不定。
3. `local_only` 3 处维持 P7-A §5.1 的结论：由 `test_local_only_boundary.py` + CI 单列一步守，不在本脚本职责。
