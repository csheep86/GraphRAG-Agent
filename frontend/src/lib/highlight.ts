export type HighlightSegments = { before: string; hit: string; after: string };

/**
 * 切分高亮区间（Sprint 6 批次 C 实装，Sprint 7.3 批次 C 提取到 `lib/` 供疑点页共用）。
 *
 * **真机教训（2026-09-23 批次 C）**：后端 `_snippet` 是 `text.strip()` 后截断
 * 200 字**再加省略号**（真机 `snippet.length=201`），且 strip 会让摘录相对原文
 * **位移**。所以直接按契约口径「`char_offset` 起点 + `snippet.length` 长度」切，
 * 高亮内容会与摘录对不上（实测 `highlight_match=false`）。
 *
 * 补充（Sprint 7.3）：疑点 `evidence.text` 是片段原文、不带省略号，`indexOf`
 * 命中率高于问答引用的 `_snippet`；但同一套「命中就用、不命中就退回、都不成立
 * 就不高亮」的口径对两者都成立，故共用一份实现——**绝不伪造位置**。
 *
 * **Sprint 10 批次 A（裁决 D-A / D-B）**：契约新增 `char_end`，与 `char_offset`
 * 构成半开区间 `[offset, end)`，由后端按「实体 char_start − chunk char_start」
 * **确定性换算**（偏移**不是**模型编的）。故优先级反转：
 * 1. **先用区间**：`end` 有效（0 ≤ start < end ≤ len）⇒ 直接按区间切——
 *    回退档是 `[0, len(text)]`，即**整段高亮**（"指到哪一段"的诚实表达，不是空白）；
 * 2. 区间不可用（旧契约 / 数据异常）才退回上面的 `indexOf` 摘录定位；
 * 3. 都不成立 → 返回纯文本（**不高亮**，绝不伪造位置）。
 *
 * 疑点页只传前两个参数（无 `end`）⇒ 行为与改造前**完全一致**。
 */
export function splitHighlight(
  text: string,
  offset: number | null | undefined,
  snippet: string,
  end?: number | null,
): HighlightSegments | string {
  const start = offset ?? -1;
  if (
    typeof end === "number" &&
    start >= 0 &&
    end > start &&
    end <= text.length
  ) {
    return {
      before: text.slice(0, start),
      hit: text.slice(start, end),
      after: text.slice(end),
    };
  }

  const base = snippet.endsWith("…") ? snippet.slice(0, -1) : snippet;
  if (base.length === 0) return text;

  const exact = text.indexOf(base);
  const fallbackStart = exact >= 0 ? exact : start;
  if (fallbackStart < 0 || fallbackStart >= text.length) return text;

  const fallbackEnd = Math.min(fallbackStart + base.length, text.length);
  return {
    before: text.slice(0, fallbackStart),
    hit: text.slice(fallbackStart, fallbackEnd),
    after: text.slice(fallbackEnd),
  };
}
