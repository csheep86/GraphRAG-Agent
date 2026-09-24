"use client";

import { FileText, Loader2, TriangleAlert } from "lucide-react";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { splitHighlight } from "@/lib/highlight";
import { useChatStore } from "@/store/use-chat-store";

/**
 * 切分高亮区间原在本文件实装（2026-09-23 批次 C），Sprint 7.3 批次 C 提取到
 * `@/lib/highlight`——疑点证据要用同一套口径，两份实现必然漂移，故合并为一份。
 * 真机教训与降级口径见 `lib/highlight.ts`。
 */

/**
 * 引用溯源抽屉（Sprint 6 批次 C）。
 *
 * 点击引用标注 → `openChunk` 回查 `GET /documents/{id}/chunks/{chunk_id}` →
 * 展示真实原文全文并高亮引用片段。三种非成功态各有明确呈现：
 * 加载骨架 / 错误（保留 HTTP 状态与 `reason`）/ 越界降级为纯文本，
 * **不**用空内容或占位文本冒充原文（§5.3 关 Mock 硬门槛）。
 */
export function ChunkViewer() {
  const citation = useChatStore((state) => state.chunkCitation);
  const chunk = useChatStore((state) => state.chunk);
  const loading = useChatStore((state) => state.chunkLoading);
  const error = useChatStore((state) => state.chunkError);
  const closeChunk = useChatStore((state) => state.closeChunk);

  const segments =
    chunk && citation
      ? splitHighlight(chunk.text, citation.char_offset, citation.snippet)
      : null;

  return (
    <Sheet
      open={citation !== null}
      onOpenChange={(open) => {
        if (!open) closeChunk();
      }}
    >
      <SheetContent aria-describedby={undefined}>
        <header className="border-b border-border px-5 py-4 pr-12">
          <SheetTitle className="flex items-center gap-1.5 text-sm font-medium text-foreground">
            <FileText className="size-3.5 text-[#8ab4ff]" />
            原文片段
          </SheetTitle>
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            {/* 页码失配为 null → 显示「?」，不伪造（批次 B Q1 口径） */}
            {citation
              ? `${citation.doc_id.slice(0, 8)} · 第 ${citation.page ?? "?"} 页 · ${citation.chunk_id}`
              : ""}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto scrollbar-subtle px-5 py-4">
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-[92%]" />
              <Skeleton className="h-3 w-[86%]" />
              <Skeleton className="h-3 w-[64%]" />
            </div>
          ) : error ? (
            <div className="rounded-lg border border-[#f87171]/40 bg-[#f87171]/[0.07] p-3">
              <p className="flex items-center gap-1.5 text-[12px] font-medium text-[#f87171]">
                <TriangleAlert className="size-3.5" />
                原文回查失败
              </p>
              <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/85">
                {error.message}
              </p>
              {error.reason || error.status ? (
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  {error.reason ? `reason: ${error.reason}` : ""}
                  {error.status ? ` · HTTP ${error.status}` : ""}
                </p>
              ) : null}
              <p className="mt-2 text-[11px] text-muted-foreground">
                该引用无法定位到原文，已保留引用标注但**不**展示占位内容。
              </p>
            </div>
          ) : segments !== null ? (
            <article className="whitespace-pre-wrap text-[12px] leading-6 text-foreground/90">
              {typeof segments === "string" ? (
                segments
              ) : (
                <>
                  {segments.before}
                  <mark className="rounded bg-[#7c3aed]/30 px-0.5 text-foreground">
                    {segments.hit}
                  </mark>
                  {segments.after}
                </>
              )}
            </article>
          ) : null}
        </div>

        {chunk ? (
          <footer className="border-t border-border px-5 py-3">
            <p className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground/70">
              {loading ? <Loader2 className="size-3 animate-spin" /> : null}
              char {chunk.char_start}–{chunk.char_end}
            </p>
          </footer>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
