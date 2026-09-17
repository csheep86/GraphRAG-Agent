"use client";

import { CornerDownRight } from "lucide-react";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { selectEvidenceMessage, useChatStore } from "@/store/use-chat-store";

export function EvidencePanel() {
  const message = useChatStore(selectEvidenceMessage);

  const paths = message?.graph_paths ?? [];
  const citations = message?.citations ?? [];
  const relatedCount = message?.node_count ?? 0;

  // 「相关实体」由关系路径两端去重得到
  const relatedEntities = Array.from(
    new Set(paths.flatMap((path) => [path.source, path.target])),
  );

  return (
    <Card className="flex h-full min-h-0 flex-col gap-0 overflow-hidden">
      <CardHeader className="px-4 pt-4 pb-3">
        <div className="space-y-1">
          <CardTitle>引用证据</CardTitle>
          <p className="text-[11px] text-muted-foreground">
            回答中的图谱节点与关系
          </p>
        </div>
      </CardHeader>

      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-subtle px-4 pb-4">
        <p className="text-[11px] font-medium text-[#a78bfa]">关系路径</p>

        <div className="mt-2.5 rounded-lg border border-[#7c3aed]/40 bg-[#7c3aed]/[0.07] p-3">
          {paths.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">
              当前回答没有可用的图谱关系路径。
            </p>
          ) : (
            <div className="space-y-3">
              {paths.map((path) => (
                <div key={`${path.source}-${path.relation}-${path.target}`}>
                  <p className="truncate text-[11px] text-foreground">
                    {path.source}
                  </p>
                  <p className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                    <CornerDownRight className="size-3 shrink-0" />
                    <span className="truncate">{path.relation}</span>
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-foreground/85">
                    {path.target}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {citations.length > 0 ? (
          <>
            <Separator className="my-4" />
            <p className="text-[11px] font-medium text-muted-foreground">
              原文证据
            </p>
            <div className="mt-2.5 space-y-2.5">
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
                      第 {citation.page} 页 · {citation.chunk_id}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : null}

        <Separator className="my-4" />

        <div className="flex items-center justify-between">
          <span className="text-[11px] text-muted-foreground">相关实体</span>
          <span className="text-sm font-semibold text-foreground tabular-nums">
            {relatedCount}
          </span>
        </div>

        <div className="mt-2.5 rounded-lg border border-border bg-white/[0.02] p-2.5">
          {relatedEntities.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">暂无实体</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {relatedEntities.map((entity) => (
                <span
                  key={entity}
                  className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-foreground/90"
                >
                  {entity}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
