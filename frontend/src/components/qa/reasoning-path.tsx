"use client";

import { ArrowRight, Database, FileText, Network, SearchX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { entitySystem, entityTypeLabel, originMeta, relationLabel } from "@/lib/reasoning";
import type { components } from "@/types/api";

type ReasoningPathHop = components["schemas"]["ReasoningPathHop"];

const ORIGIN_ICON = {
  document: FileText,
  graph: Network,
  cypher: Database,
} as const;

/**
 * 推理路径链（批次 E2 的核心）。
 *
 * **渲染纪律**：顺序严格照后端给的 `reasoning_path[]`（前端**不**重排、不补跳）。
 * `null`（拒答未产出）与 `[]`（零命中）必须**分开说**——二者语义相反：
 * 前者是「没给你结论所以没给链」，后者是「查过了，图上没连上」。
 */
export function ReasoningPath({ hops }: { hops: ReasoningPathHop[] | null }) {
  if (hops === null) {
    return (
      <div className="rounded-lg border border-dashed border-border p-4 text-[11px] text-muted-foreground">
        拒答分支不返回推理路径（<code>reasoning_path = null</code>）：
        路径是**证据链**，没有结论就不给链，避免读成「有据可依只是没说」。
      </div>
    );
  }

  if (hops.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed border-border p-4 text-[11px] text-muted-foreground">
        <SearchX className="size-3.5 shrink-0" />
        图上没接通（<code>reasoning_path = []</code>）：问句没锚到已知实体，
        或锚点在规定跳数内走不到任何条款 / 事实——**不**补一条示例链充数。
      </div>
    );
  }

  return (
    <ol className="flex flex-col gap-2">
      {hops.map((hop, index) => {
        const meta = originMeta(hop.origin);
        const Icon = ORIGIN_ICON[hop.origin as keyof typeof ORIGIN_ICON] ?? Database;

        return (
          <li key={`${hop.source.id}-${hop.relation}-${hop.target.id}-${index}`}>
            <div className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="muted">{entityTypeLabel(hop.source.entity_type)}</Badge>
                <span className="text-[12px] font-medium text-foreground">
                  {hop.source.name}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {hop.source.id}
                </span>

                <span className="flex items-center gap-1 px-1 text-muted-foreground">
                  <ArrowRight className="size-3" />
                  <span className="text-[11px]">{relationLabel(hop.relation)}</span>
                </span>

                <Badge variant="muted">{entityTypeLabel(hop.target.entity_type)}</Badge>
                <span className="text-[12px] font-medium text-foreground">
                  {hop.target.name}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {hop.target.id}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Icon className="size-3" />
                  {meta.label}
                </span>
                <span className="text-[10px] text-muted-foreground/70">
                  {entitySystem(hop.target.entity_type)}
                </span>
                {hop.evidence ? (
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {hop.evidence}
                  </span>
                ) : null}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
