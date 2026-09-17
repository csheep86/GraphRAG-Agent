"use client";

import { useState } from "react";
import { ChevronDown, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/mock";

type ChatMessageItemProps = {
  message: ChatMessage;
  onSelectEvidence: (messageId: string) => void;
};

export function ChatMessageItem({
  message,
  onSelectEvidence,
}: ChatMessageItemProps) {
  const [expanded, setExpanded] = useState(false);

  if (message.role === "user") {
    return (
      <div className="rounded-xl bg-bubble-user px-4 py-3">
        <p className="text-[11px] text-muted-foreground">你</p>
        <p className="mt-1.5 text-[13px] leading-relaxed whitespace-pre-wrap text-foreground">
          {message.content}
        </p>
      </div>
    );
  }

  const citations = message.citations ?? [];
  const nodeCount = message.node_count ?? 0;
  const relationCount = message.relation_count ?? 0;
  const hasEvidence = citations.length > 0 || nodeCount > 0;

  return (
    <div className="rounded-xl border border-border bg-white/[0.02] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#6d8dff] to-[#8b5cf6]">
          <Sparkles className="size-3 text-white" />
        </span>
        <span className="text-xs font-medium text-[#8ab4ff]">GraphRAG AI</span>

        {message.refused ? <Badge variant="muted">未给出结论</Badge> : null}
        {!message.refused && message.confidence === "low" ? (
          <Badge variant="muted">低置信度</Badge>
        ) : null}
      </div>

      <p className="mt-3 text-[13px] leading-relaxed whitespace-pre-wrap text-foreground">
        {message.content}
      </p>

      {hasEvidence ? (
        <div className="mt-3.5 rounded-lg border border-border">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronDown
              className={cn(
                "size-3.5 transition-transform",
                expanded && "rotate-180",
              )}
            />
            <span>
              引用来源：{nodeCount} 个节点 / {relationCount} 条关系
            </span>
          </button>

          {expanded ? (
            <div className="space-y-3 border-t border-border px-3 py-3">
              {citations.map((citation, index) => (
                <div key={citation.chunk_id} className="flex gap-2">
                  <span className="mt-px shrink-0 text-[11px] text-muted-foreground tabular-nums">
                    [{index + 1}]
                  </span>
                  <div className="min-w-0">
                    <p className="text-[11px] leading-relaxed text-foreground/90">
                      {citation.snippet}
                    </p>
                    <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                      {citation.doc_id.slice(0, 8)} · 第 {citation.page} 页 ·{" "}
                      {citation.chunk_id}
                    </p>
                  </div>
                </div>
              ))}

              {citations.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">
                  暂无原文片段，仅返回图谱节点统计。
                </p>
              ) : null}

              <button
                type="button"
                onClick={() => onSelectEvidence(message.id)}
                className="text-[11px] text-primary transition-opacity hover:opacity-80"
              >
                在右侧查看图谱证据 →
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
