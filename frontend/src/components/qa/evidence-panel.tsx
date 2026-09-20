"use client";

import { CornerDownRight } from "lucide-react";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { selectEvidenceMessage, useChatStore } from "@/store/use-chat-store";
import type { GraphEdge, GraphNode } from "@/types/mock";

/** 节点显示名：优先消解后的标准名 canonical_name，回退原始 label */
function nodeName(node: GraphNode): string {
  return node.canonical_name || node.label;
}

/**
 * 关系显示名：后端受控投影把桥梁专有类型统一投影为 MENTIONS，
 * 真实关系名保留在 `properties.relation_name`（批次 B 枚举扩展后部分类型将直通）。
 */
function relationLabel(edge: GraphEdge): string {
  const name = edge.properties?.["relation_name"];
  return typeof name === "string" && name.length > 0 ? name : edge.type;
}

export function EvidencePanel() {
  const message = useChatStore(selectEvidenceMessage);

  // 批次 A：直接消费契约字段 kg_nodes / kg_relations（原 graph_paths 降级退役）
  const nodes = message?.kg_nodes ?? [];
  const relations = message?.kg_relations ?? [];
  const citations = message?.citations ?? [];

  // 关系端点 id → 节点显示名（节点缺失时回退显示 id，不隐藏关系）
  const nameById = new Map(nodes.map((node) => [node.id, nodeName(node)]));
  const endpointName = (id: string) => nameById.get(id) ?? id;

  const hasAnyEvidence =
    nodes.length > 0 || relations.length > 0 || citations.length > 0;

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
        {!hasAnyEvidence ? (
          // 拒答 / 图谱为空 / 尚无回答：统一占位（契约保证空列表而非缺字段）
          <div className="mt-2 rounded-lg border border-dashed border-border p-4 text-center">
            <p className="text-[11px] text-muted-foreground">暂无引用证据</p>
          </div>
        ) : (
          <>
            <p className="text-[11px] font-medium text-[#a78bfa]">关系路径</p>

            <div className="mt-2.5 rounded-lg border border-[#7c3aed]/40 bg-[#7c3aed]/[0.07] p-3">
              {relations.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">
                  当前回答没有可用的图谱关系路径。
                </p>
              ) : (
                <div className="space-y-3">
                  {relations.map((edge) => (
                    <div key={edge.id}>
                      <p className="truncate text-[11px] text-foreground">
                        {endpointName(edge.source)}
                      </p>
                      <p className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                        <CornerDownRight className="size-3 shrink-0" />
                        <span className="truncate">{relationLabel(edge)}</span>
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-foreground/85">
                        {endpointName(edge.target)}
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
                {nodes.length}
              </span>
            </div>

            <div className="mt-2.5 rounded-lg border border-border bg-white/[0.02] p-2.5">
              {nodes.length === 0 ? (
                <p className="text-[11px] text-muted-foreground">暂无实体</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {nodes.map((node) => (
                    <span
                      key={node.id}
                      className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-foreground/90"
                    >
                      {nodeName(node)}
                      {/* 实体类型标签：帮助区分同名不同类的实体 */}
                      <span className="ml-1 text-[10px] text-muted-foreground">
                        {node.entity_type}
                      </span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {/* LLM token 用量（契约 token_usage；拒答 / 未返回时为 null 不展示） */}
        {message?.token_usage ? (
          <p className="mt-3 font-mono text-[10px] text-muted-foreground/70">
            Token：输入 {message.token_usage.prompt_tokens} · 输出{" "}
            {message.token_usage.completion_tokens} · 共{" "}
            {message.token_usage.total_tokens}
          </p>
        ) : null}
      </div>
    </Card>
  );
}
