"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { RULE_VALUE_SOURCE_META } from "@/lib/compliance";
import { useComplianceStore } from "@/store/use-compliance-store";

/**
 * 规则值面板（本页**可核查性**的核心）。
 *
 * 五个规则值全部**解析自制度文本**，不是硬编码：每个都带 `source` / `reference` /
 * `evidence`，能点回图谱条款节点或 M1 产物 `full.md` 的对应行。
 * 制度改了，这里的数字跟着变——所以「为什么是 36h」这个问题有答案。
 *
 * `evidence` 里可能带 `</td><td>` 这类残留：那是 MinerU 把表格渲染成 HTML 的
 * 产物，**原样展示不清洗**——清洗过就看不出它出自表格，也就无从复核了。
 */
export function RuleValuePanel() {
  const data = useComplianceStore((state) => state.data);
  const [open, setOpen] = useState(true);

  if (!data) return null;

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-5 py-4 text-left"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="size-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 text-muted-foreground" />
        )}
        <span className="text-sm font-medium text-foreground">
          规则值（{data.rule_values.length} 个）
        </span>
        <span className="text-[11px] text-muted-foreground">
          全部解析自制度文档，每个都带出处
        </span>
      </button>

      {open ? (
        <div className="grid gap-2 px-5 pb-5 sm:grid-cols-2">
          {data.rule_values.map((item) => {
            const source = RULE_VALUE_SOURCE_META[item.source];

            return (
              <article
                key={item.key}
                className="rounded-lg border border-border p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-medium text-foreground">
                    {item.label}
                  </span>
                  <Badge variant="outline" title={source.hint}>
                    {source.label}
                  </Badge>
                </div>

                <p className="mt-1.5 text-[18px] leading-none font-semibold text-foreground">
                  {item.value}
                  <span className="ml-1 text-[11px] font-normal text-muted-foreground">
                    {item.unit}
                  </span>
                </p>

                <p className="mt-2 font-mono text-[10px] break-all text-muted-foreground">
                  {item.reference}
                </p>

                <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/75">
                  {item.evidence}
                </p>
              </article>
            );
          })}
        </div>
      ) : null}
    </Card>
  );
}
