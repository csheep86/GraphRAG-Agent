"use client";

import { ArrowRight, Database, FileText, Network, SearchX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  entitySystem,
  entityTypeLabel,
  isHopExpired,
  originMeta,
  relationLabel,
  todayISO,
} from "@/lib/reasoning";
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
 *
 * **时效渲染（J3）**：某一跳的 `valid_to` 非空且已到期 ⇒ 该跳画成**虚线置灰**，
 * 与仍然有效的边区分开。判定口径由 `@/lib/reasoning` 的 `isHopExpired` 单点持有，
 * 这里只负责画（ADR-0005 §6：`valid_to = null` 是「未失效」，不是「明天失效」）。
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

  const today = todayISO();

  return (
    <ol className="flex flex-col gap-2">
      {hops.map((hop, index) => {
        const meta = originMeta(hop.origin);
        const Icon = ORIGIN_ICON[hop.origin as keyof typeof ORIGIN_ICON] ?? Database;
        const expired = isHopExpired(hop.valid_to, today);

        return (
          <li key={`${hop.source.id}-${hop.relation}-${hop.target.id}-${index}`}>
            <div
              className={
                expired
                  ? "rounded-lg border border-dashed border-muted-foreground/50 p-3"
                  : "rounded-lg border border-border p-3"
              }
              data-expired={String(expired)}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="muted">{entityTypeLabel(hop.source.entity_type)}</Badge>
                <span
                  className={
                    expired
                      ? "text-[12px] font-medium text-muted-foreground"
                      : "text-[12px] font-medium text-foreground"
                  }
                >
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
                <span
                  className={
                    expired
                      ? "text-[12px] font-medium text-muted-foreground"
                      : "text-[12px] font-medium text-foreground"
                  }
                >
                  {hop.target.name}
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">
                  {hop.target.id}
                </span>

                {expired ? (
                  <Badge variant="outline" className="border-dashed">
                    已于 {hop.valid_to} 失效
                  </Badge>
                ) : null}
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Icon className="size-3" />
                  {meta.label}
                </span>
                <span className="text-[10px] text-muted-foreground/70">
                  {entitySystem(hop.target.entity_type)}
                </span>
                {hop.valid_from || hop.valid_to ? (
                  <span className="font-mono text-[10px] text-muted-foreground/70">
                    有效期 {hop.valid_from ?? "未标施行日"} ~{" "}
                    {hop.valid_to ?? "未标失效日"}
                  </span>
                ) : null}
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
