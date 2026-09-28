"use client";

import { Check, FileText, Scale, ShieldQuestion, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CONFIDENCE_TONE_CLASS,
  CONFIDENCE_TONE_TEXT,
  anomalyStatusLabel,
  causeLabel,
  causeSystem,
  confidenceTone,
} from "@/lib/attribution";
import { useAttributionStore } from "@/store/use-attribution-store";

/**
 * 归因结论面板（批次 E3 的核心）。
 *
 * 三件事，按演示话术排：
 * 1. **置信度条**——`Σ命中权重 / Σ全部权重`，把算式写在下面，可手工核对；
 * 2. **原因排序**——后端给的 `causes[]` 顺序照渲染（前端**不**重排），
 *    每条标出来自哪个系统，凑成"跨四系统取证"这件事；
 * 3. **结论与制度出处**——`policy_refs` 为空时明确说「没有制度依据」，
 *    不把结论包装成有据可依。
 */
export function AttributionPanel() {
  const selected = useAttributionStore((state) => state.selected);
  const explain = useAttributionStore((state) => state.explain);
  const loading = useAttributionStore((state) => state.explainLoading);
  const error = useAttributionStore((state) => state.explainError);

  if (!selected) {
    return (
      <Card className="flex-1 px-5 py-10 text-center text-[13px] text-muted-foreground">
        左侧选一条异常，系统开始跨系统取证。
      </Card>
    );
  }

  return (
    <Card className="min-w-0 flex-1">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">
            {selected.employee_name}
          </span>
          <span className="font-mono text-[10px] text-muted-foreground">
            {selected.employee_id} · {selected.date}
          </span>
          <Badge variant="outline">{anomalyStatusLabel(selected.status)}</Badge>
        </div>
        {explain ? (
          <span className="font-mono text-[10px] text-muted-foreground">
            {explain.anomaly_type}
          </span>
        ) : null}
      </div>

      {loading ? (
        <div className="space-y-3 px-5 py-5">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-2 w-full rounded-full" />
          <Skeleton className="h-3 w-64" />
          <Skeleton className="h-3 w-56" />
        </div>
      ) : error ? (
        <div className="px-5 py-5">
          <div className="rounded-lg border border-[#f87171]/40 bg-[#f87171]/[0.07] p-3">
            <p className="flex items-center gap-1.5 text-[12px] font-medium text-[#f87171]">
              <ShieldQuestion className="size-3.5" />
              归因未完成
            </p>
            <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/85">
              {error}
            </p>
          </div>
        </div>
      ) : explain ? (
        <div className="px-5 py-5">
          <section>
            <div className="flex items-baseline justify-between">
              <h3 className="text-[12px] font-medium text-muted-foreground">
                置信度（Σ命中权重 / Σ全部权重）
              </h3>
              <span
                className={`text-[18px] font-semibold ${CONFIDENCE_TONE_TEXT[confidenceTone(explain.confidence)]}`}
              >
                {Math.round(explain.confidence * 100)}%
              </span>
            </div>

            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className={`h-full rounded-full ${CONFIDENCE_TONE_CLASS[confidenceTone(explain.confidence)]}`}
                style={{ width: `${Math.round(explain.confidence * 100)}%` }}
              />
            </div>

            <p className="mt-2 text-[11px] text-muted-foreground">
              确定性加权，非模型评分：
              {explain.causes
                .filter((cause) => cause.matched)
                .map((cause) => cause.weight)
                .reduce((sum, weight) => sum + weight, 0)
                .toFixed(2)}{" "}
              /{" "}
              {explain.causes
                .map((cause) => cause.weight)
                .reduce((sum, weight) => sum + weight, 0)
                .toFixed(2)}
            </p>
          </section>

          <section className="mt-5">
            <h3 className="text-[12px] font-medium text-muted-foreground">
              原因排序（{explain.causes.length} 项，含未命中）
            </h3>

            <ul className="mt-2 space-y-2">
              {explain.causes.map((cause) => (
                <li
                  key={cause.code}
                  className="rounded-lg border border-border p-3"
                >
                  <div className="flex items-center gap-2">
                    {cause.matched ? (
                      <Check className="size-3.5 text-status-completed" />
                    ) : (
                      <X className="size-3.5 text-muted-foreground/60" />
                    )}
                    <span className="text-[12px] font-medium text-foreground">
                      {causeLabel(cause.code)}
                    </span>
                    <Badge variant="muted">{causeSystem(cause.code)}</Badge>
                    <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                      权重 {cause.weight.toFixed(2)}
                    </span>
                  </div>

                  <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/80">
                    {cause.reason}
                  </p>

                  {cause.evidence.length > 0 ? (
                    <p className="mt-1.5 font-mono text-[10px] break-all text-muted-foreground">
                      {cause.evidence.join(" · ")}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>

          <section className="mt-5">
            <h3 className="flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
              <Scale className="size-3.5" />
              结论与建议动作
            </h3>
            <p className="mt-2 rounded-lg bg-white/[0.04] p-3 text-[12px] text-foreground/90">
              {explain.conclusion} ⇒ {explain.action}
            </p>
          </section>

          <section className="mt-5">
            <h3 className="flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
              <FileText className="size-3.5" />
              制度出处（{explain.policy_refs.length} 条）
            </h3>
            {explain.policy_refs.length > 0 ? (
              <ul className="mt-2 space-y-1.5">
                {explain.policy_refs.map((ref) => (
                  <li
                    key={ref}
                    className="rounded-lg border border-border px-3 py-2 font-mono text-[11px] break-all text-foreground/85"
                  >
                    {ref}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 rounded-lg border border-dashed border-border p-3 text-[11px] text-muted-foreground">
                未取到制度出处 —— 此时结论里的制度话术不得声称有依据。
              </p>
            )}
          </section>
        </div>
      ) : null}
    </Card>
  );
}
