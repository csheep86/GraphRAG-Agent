"use client";

import { Check, FileText, TriangleAlert, X } from "lucide-react";

import {
  SuspicionSeverityBadge,
  SuspicionStatusBadge,
  SuspicionTypeBadge,
} from "@/components/common/suspicion-badges";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDateTime } from "@/lib/format";
import { splitHighlight } from "@/lib/highlight";
import { useAffiliationStore } from "@/store/use-affiliation-store";

/**
 * 疑点证据抽屉（Sprint 7.3 批次 C）。
 *
 * 打开一条疑点 → store 并发回查它**每条证据**的 chunk 原文 → 全文展示并高亮
 * 证据片段。三种非成功态各有明确呈现：加载骨架 / 单条失败 / 越界降级为纯文本，
 * **不**用空内容或占位文本冒充原文（§6.3 关 Mock 硬门槛）。
 */
export function SuspicionDetailSheet() {
  const detail = useAffiliationStore((state) => state.detail);
  const loading = useAffiliationStore((state) => state.detailLoading);
  const chunks = useAffiliationStore((state) => state.detailChunks);
  const errors = useAffiliationStore((state) => state.detailErrors);
  const closeDetail = useAffiliationStore((state) => state.closeDetail);
  const review = useAffiliationStore((state) => state.review);

  const reviewed = detail ? detail.status !== "open" : false;

  return (
    <Sheet
      open={detail !== null}
      onOpenChange={(open) => {
        if (!open) closeDetail();
      }}
    >
      <SheetContent aria-describedby={undefined}>
        {detail ? (
          <>
            <header className="border-b border-border px-5 py-4 pr-12">
              <SheetTitle className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
                <SuspicionTypeBadge type={detail.suspicion_type} />
                <SuspicionSeverityBadge severity={detail.severity} />
                <SuspicionStatusBadge status={detail.status} />
              </SheetTitle>
              <p className="mt-1.5 font-mono text-[10px] text-muted-foreground">
                {detail.kg_version}
                {detail.reviewed_by
                  ? ` · 复核人 ${detail.reviewed_by.slice(0, 8)}`
                  : ""}
                {detail.reviewed_at
                  ? ` · ${formatDateTime(detail.reviewed_at)}`
                  : ""}
              </p>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto scrollbar-subtle px-5 py-4">
              <section>
                <h3 className="text-[12px] font-medium text-muted-foreground">
                  涉及主体
                </h3>
                <ul className="mt-2 space-y-1">
                  {detail.entity_names.map((name, index) => (
                    <li
                      key={`${name}-${index}`}
                      className="text-[13px] text-foreground"
                    >
                      {name}
                      <span className="ml-1.5 font-mono text-[10px] text-muted-foreground">
                        {detail.entities[index] ?? ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="mt-5">
                <h3 className="text-[12px] font-medium text-muted-foreground">
                  原文证据（{detail.evidence.length} 条）
                </h3>

                <div className="mt-2 space-y-3">
                  {detail.evidence.map((evidence, index) => {
                    const chunk = chunks[index];
                    const error = errors[index];

                    return (
                      <article
                        key={`${evidence.node_id}-${index}`}
                        className="rounded-lg border border-border p-3"
                      >
                        <p className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
                          <FileText className="size-3 text-[#8ab4ff]" />
                          {`第 ${index + 1} 条 · 第 ${evidence.page ?? "?"} 页 · ${evidence.chunk_id}`}
                        </p>

                        <div className="mt-2">
                          {loading ? (
                            <div className="space-y-2">
                              <Skeleton className="h-3 w-full" />
                              <Skeleton className="h-3 w-[90%]" />
                              <Skeleton className="h-3 w-[64%]" />
                            </div>
                          ) : error ? (
                            <div className="rounded-lg border border-[#f87171]/40 bg-[#f87171]/[0.07] p-2.5">
                              <p className="flex items-center gap-1.5 text-[12px] font-medium text-[#f87171]">
                                <TriangleAlert className="size-3.5" />
                                原文回查失败
                              </p>
                              <p className="mt-1 text-[11px] leading-relaxed text-foreground/85">
                                {error}
                              </p>
                            </div>
                          ) : chunk ? (
                            <EvidenceText
                              text={chunk.text}
                              offset={evidence.char_start}
                              snippet={evidence.text}
                            />
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            </div>

            <footer className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
              <span className="font-mono text-[10px] text-muted-foreground/70">
                trace {detail.trace_id.slice(0, 8)}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="xs"
                  disabled={reviewed}
                  title={
                    reviewed
                      ? "已复核的疑点不可改回待复核（契约限定）"
                      : undefined
                  }
                  onClick={() => void review(detail.id, "confirmed")}
                >
                  <Check className="size-3.5" />
                  确认
                </Button>
                <Button
                  variant="outline"
                  size="xs"
                  disabled={reviewed}
                  title={
                    reviewed
                      ? "已复核的疑点不可改回待复核（契约限定）"
                      : undefined
                  }
                  onClick={() => void review(detail.id, "dismissed")}
                >
                  <X className="size-3.5" />
                  驳回
                </Button>
              </div>
            </footer>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

/**
 * 原文 + 高亮。
 *
 * 高亮口径与 Sprint 6 溯源**同一份实现**（`lib/highlight.ts`）：疑点
 * `evidence.text` 是片段原文，`indexOf` 命中即用；命中不了就退回
 * `char_start`；都不成立则**整段纯文本不高亮**——不伪造位置。
 */
function EvidenceText({
  text,
  offset,
  snippet,
}: {
  text: string;
  offset: number;
  snippet: string;
}) {
  /**
   * **真机实测（2026-09-24，10/10 条疑点）**：`evidence.text` 与 chunk 全文
   * **等长**——证据粒度是 **chunk 级**（`:Subject`/`:Address` → `:Entity` →
   * `(:Chunk)-[:MENTIONS]->` 取的是整段），不是实体提及级。此时整段 `<mark>`
   * 等于"高亮了几千字"，视觉上就是没高亮且**误导**，故整段场景改淡底 +
   * 标注；只有当片段是全文**真子集**时才做 `<mark>` 高亮。
   *
   * 片段级定位（`char_offset` 恒 0）属 Sprint 10（`plan.md:619`），本批次不做，
   * 也不宣称做到——见 `integration-log.md` §7 缺口登记。
   */
  const coversWholeChunk = snippet.length >= text.length;
  const segments = coversWholeChunk
    ? null
    : splitHighlight(text, offset, snippet);

  return (
    <div className="space-y-1.5">
      {coversWholeChunk ? (
        <>
          <article className="whitespace-pre-wrap rounded bg-[#7c3aed]/[0.10] p-2 text-[12px] leading-6 text-foreground/90">
            {text}
          </article>
          <p className="text-[10px] text-muted-foreground">
            证据粒度为原文片段（chunk 级）；实体提及级定位待 Sprint 10。
          </p>
        </>
      ) : (
        <article className="whitespace-pre-wrap text-[12px] leading-6 text-foreground/90">
          {typeof segments === "string" ? (
            segments
          ) : (
            <>
              {segments?.before}
              <mark className="rounded bg-[#7c3aed]/30 px-0.5 text-foreground">
                {segments?.hit}
              </mark>
              {segments?.after}
            </>
          )}
        </article>
      )}

      {!coversWholeChunk && typeof segments === "string" ? (
        <p className="text-[10px] text-muted-foreground">
          证据片段未在该原文中定位到，已展示片段全文但不高亮。
        </p>
      ) : null}

      <p className="font-mono text-[10px] text-muted-foreground/70">
        char {offset}–{offset + snippet.length}
      </p>
    </div>
  );
}
