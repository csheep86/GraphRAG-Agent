"use client";

import { useState } from "react";
import { ChevronDown, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ChatMessage, Citation } from "@/types/mock";

type ChatMessageItemProps = {
  message: ChatMessage;
  onSelectEvidence: (messageId: string) => void;
  /** 批次 C：点击引用条目 → 回查原文全文并高亮（与右侧面板共用同一抽屉） */
  onOpenChunk: (citation: Citation) => void;
};

export function ChatMessageItem({
  message,
  onSelectEvidence,
  onOpenChunk,
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
  // 计数由契约字段 kg_nodes / kg_relations 派生（批次 A：原 node_count 占位退役）
  const nodeCount = message.kg_nodes?.length ?? 0;
  const relationCount = message.kg_relations?.length ?? 0;
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
                <button
                  key={citation.chunk_id}
                  type="button"
                  onClick={() => onOpenChunk(citation)}
                  title="查看原文片段"
                  className="-mx-1.5 flex w-[calc(100%+0.75rem)] gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-white/[0.05]"
                >
                  <span className="mt-px shrink-0 text-[11px] text-muted-foreground tabular-nums">
                    [{index + 1}]
                  </span>
                  <div className="min-w-0">
                    <p className="text-[11px] leading-relaxed text-foreground/90">
                      {citation.snippet}
                    </p>
                    <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                      {/* Sprint 6 批次 B（Q1）：页码失配为 null，显示「页码未知」而非空白 */}
                      {citation.doc_id.slice(0, 8)} · 第 {citation.page ?? "?"}{" "}
                      页 · {citation.chunk_id}
                    </p>
                    {/* 批次 C：溯源入口 */}
                    <p className="mt-0.5 text-[10px] text-primary">
                      查看原文 →
                    </p>
                  </div>
                </button>
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

      {/* LLM token 用量（契约 token_usage；拒答 / 未返回时为 null 不展示） */}
      {message.token_usage ? (
        <p className="mt-2 font-mono text-[10px] text-muted-foreground/70">
          Token：输入 {message.token_usage.prompt_tokens} · 输出{" "}
          {message.token_usage.completion_tokens} · 共{" "}
          {message.token_usage.total_tokens}
        </p>
      ) : null}
    </div>
  );
}
