"use client";

import { FileText, Scale } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { COMPLIANCE_LEVEL_META, COMPLIANCE_RULE_META } from "@/lib/compliance";
import { useComplianceStore } from "@/store/use-compliance-store";

/**
 * 一条风险的详情抽屉。
 *
 * 三块内容对应三条演示话术：
 * 1. **计算过程**——能手工核算（`216 − 174 = 42 > 36`），不是模型给的结论；
 * 2. **制度依据**——`policy_refs[]` 每个引用都能点回条款 / 文档行；
 * 3. **证据节点**——图谱节点 id，可用 `GET /entities/{id}` 回查详情。
 *
 * 「建议动作」单独标注为**前端建议**：契约没有该字段，不能让它看起来像
 * 制度原文（否则就是假借制度权威给处置意见）。
 */
export function FindingDetailSheet() {
  const detail = useComplianceStore((state) => state.detail);
  const closeDetail = useComplianceStore((state) => state.closeDetail);
  const data = useComplianceStore((state) => state.data);

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
                <Badge variant={COMPLIANCE_LEVEL_META[detail.level].variant}>
                  {COMPLIANCE_LEVEL_META[detail.level].label}
                </Badge>
                <span>{detail.rule_label}</span>
                <span className="text-muted-foreground">
                  {detail.employee_name}
                  <span className="ml-1 font-mono text-[10px]">
                    {detail.employee_id}
                  </span>
                </span>
              </SheetTitle>
              <p className="mt-1.5 font-mono text-[10px] text-muted-foreground">
                {data?.kg_version} · 观察日 {data?.as_of} ·{" "}
                {detail.work_time_system}
              </p>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto scrollbar-subtle px-5 py-4">
              <section>
                <h3 className="flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
                  <Scale className="size-3.5" />
                  计算过程（可手工核算）
                </h3>
                <p className="mt-2 rounded-lg bg-white/[0.04] p-3 text-[12px] leading-6 text-foreground/90">
                  {detail.calculation}
                </p>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  实测 {detail.observed} {detail.unit} · 阈值{" "}
                  {detail.threshold} {detail.unit}
                </p>
              </section>

              <section className="mt-5">
                <h3 className="text-[12px] font-medium text-muted-foreground">
                  制度依据（{detail.policy_refs.length} 条）
                </h3>
                <ul className="mt-2 space-y-1.5">
                  {detail.policy_refs.map((ref) => (
                    <li
                      key={ref}
                      className="rounded-lg border border-border px-3 py-2 font-mono text-[11px] break-all text-foreground/85"
                    >
                      {ref}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="mt-5">
                <h3 className="flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
                  <FileText className="size-3.5" />
                  证据节点（{detail.evidence.length} 条）
                </h3>
                <ul className="mt-2 space-y-1.5">
                  {detail.evidence.map((nodeId) => (
                    <li
                      key={nodeId}
                      className="rounded-lg border border-border px-3 py-2 font-mono text-[11px] break-all text-foreground/85"
                    >
                      {nodeId}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[10px] text-muted-foreground">
                  节点 id 可用实体详情接口回查；本页不另造证据文案。
                </p>
              </section>

              <section className="mt-5">
                <h3 className="text-[12px] font-medium text-muted-foreground">
                  建议动作
                </h3>
                <p className="mt-2 rounded-lg border border-dashed border-border p-3 text-[12px] leading-6 text-foreground/85">
                  {COMPLIANCE_RULE_META[detail.rule].action}
                </p>
                <p className="mt-1.5 text-[10px] text-muted-foreground">
                  前端给出的处置建议，**不是制度条款**；实际处置以制度原文与 HR
                  确认为准。
                </p>
              </section>
            </div>

            <footer className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
              <span className="font-mono text-[10px] text-muted-foreground/70">
                trace {data?.trace_id.slice(0, 8)}
              </span>
            </footer>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
