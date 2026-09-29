"use client";

import { CircleSlash, FileText, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  confidenceLabel,
  refusalReasonLabel,
} from "@/lib/reasoning";
import type { components } from "@/types/api";

type AgentQueryResponse = components["schemas"]["AgentQueryResponse"];

/**
 * 判定结论条（批次 E2）：一句话给出「能不能答、依据几跳、置信度几何」。
 *
 * **三类状态必须分开呈现**（混为一谈就会失真）：
 * - 拒答（`refused=true`）：正常业务判定，200，**不是**故障；
 * - 有结论无路径（`reasoning_path=[]`）：结论缺少可核查的图证据，要让人看见；
 * - 有结论且有路径：理想态。
 */
export function VerdictBar({ result }: { result: AgentQueryResponse }) {
  const hopCount = result.reasoning_path?.length ?? 0;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-foreground/[0.03] px-3 py-2.5">
      {result.refused ? (
        <>
          <CircleSlash className="size-4 shrink-0 text-status-failed" />
          <span className="text-[13px] font-medium text-foreground">拒答</span>
          <span className="text-[11px] text-muted-foreground">
            {refusalReasonLabel(result.refusal_reason)}
          </span>
        </>
      ) : (
        <>
          <ShieldCheck className="size-4 shrink-0 text-status-completed" />
          <span className="text-[13px] font-medium text-foreground">已答</span>
          <Badge variant="outline">{confidenceLabel(result.confidence)}</Badge>
        </>
      )}

      <span className="ml-auto flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <FileText className="size-3" />
        引用 {result.citations.length} 条
      </span>

      <span className="text-[11px] text-muted-foreground">
        推理路径{" "}
        {result.reasoning_path === null
          ? "未产出（拒答）"
          : `${hopCount} 跳${hopCount === 0 ? "（图上未接通）" : ""}`}
      </span>

      <span className="font-mono text-[10px] text-muted-foreground">
        {result.kg_version}
      </span>
    </div>
  );
}
