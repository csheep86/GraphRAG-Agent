"use client";

import { FileText, Scale } from "lucide-react";
import { useEffect, useState } from "react";

import { getEntityDetail } from "@/api/graph";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { COMPLIANCE_LEVEL_META, COMPLIANCE_RULE_META } from "@/lib/compliance";
import { useComplianceStore } from "@/store/use-compliance-store";

/** `graph:clause:ent_<hex>` → 提取实体 id；其余引用形态（`document:doc:…`）本就可读 */
const CLAUSE_REF = /^graph:clause:(.+)$/;

/**
 * 条款引用可读化（Sprint 9.6 G3，截图点验暴露的演示观感问题）：
 * `graph:clause:ent_c974307a4bd5` 这种裸哈希 id 客户看不懂——
 * 回查契约内现成的 `GET /entities/{id}` 拿 `canonical_name` 做标题，
 * 原 ref 降级为副标题。**回查失败/加载中都降级显示原 ref**（不伪造标题）；
 * `document:doc:…` 形态本就可读，不回查。
 */
function useClauseTitles(refs: string[]): Record<string, string> {
  const [titles, setTitles] = useState<Record<string, string>>({});

  useEffect(() => {
    const clauseIds = [
      ...new Set(
        refs
          .map((ref) => CLAUSE_REF.exec(ref)?.[1])
          .filter((id): id is string => Boolean(id)),
      ),
    ];
    if (clauseIds.length === 0) {
      return;
    }
    let cancelled = false;
    Promise.all(
      clauseIds.map((id) =>
        getEntityDetail(id)
          .then((d) => [id, d.canonical_name || ""] as const)
          .catch(() => [id, ""] as const),
      ),
    ).then((pairs) => {
      if (!cancelled) {
        setTitles((prev) => ({ ...prev, ...Object.fromEntries(pairs.filter(([, title]) => title)) }));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [refs]);

  return titles;
}

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
  const clauseTitles = useClauseTitles(detail?.policy_refs ?? []);

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
                  {detail.policy_refs.map((ref) => {
                    const clauseId = CLAUSE_REF.exec(ref)?.[1];
                    const title = clauseId ? clauseTitles[clauseId] : undefined;
                    return (
                      <li
                        key={ref}
                        className="rounded-lg border border-border px-3 py-2"
                      >
                        {title ? (
                          <>
                            <p className="text-[12px] leading-5 text-foreground/90">
                              {title}
                            </p>
                            <p className="mt-0.5 font-mono text-[10px] break-all text-muted-foreground">
                              {ref}
                            </p>
                          </>
                        ) : (
                          <span className="font-mono text-[11px] break-all text-foreground/85">
                            {ref}
                          </span>
                        )}
                      </li>
                    );
                  })}
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
