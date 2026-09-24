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
 * 故本处两步走：
 * 1. 去掉尾部省略号，用 `indexOf` 在全文里定位摘录**实际位置**——命中即用它；
 * 2. 找不到（摘录被 LLM 改写等）才回退到契约口径 `char_offset` 起点；
 * 3. 两者都不成立 → 返回纯文本（**不高亮**，绝不伪造位置）。
 */
export function splitHighlight(
  text: string,
  offset: number | null | undefined,
  snippet: string,
): HighlightSegments | string {
  const base = snippet.endsWith("…") ? snippet.slice(0, -1) : snippet;
  if (base.length === 0) return text;

  const exact = text.indexOf(base);
  const start = exact >= 0 ? exact : (offset ?? -1);
  if (start < 0 || start >= text.length) return text;

  const end = Math.min(start + base.length, text.length);
  return {
    before: text.slice(0, start),
    hit: text.slice(start, end),
    after: text.slice(end),
  };
}
