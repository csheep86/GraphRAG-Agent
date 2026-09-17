import type { GraphCategory } from "@/types/mock";

export const CATEGORY_COLOR_VAR: Record<GraphCategory, string> = {
  topic: "var(--node-topic)",
  norm: "var(--node-norm)",
  org: "var(--node-org)",
  system: "var(--node-system)",
};

/** 图例文案对齐 p04：「主题 / 规范·数据 / 组织·人员 / 制度」 */
const LEGEND: { label: string; category: GraphCategory }[] = [
  { label: "主题", category: "topic" },
  { label: "规范/数据", category: "norm" },
  { label: "组织/人员", category: "org" },
  { label: "制度", category: "system" },
];

export function GraphLegend() {
  return (
    <div className="pointer-events-none absolute bottom-4 left-4 flex items-center gap-3.5 rounded-lg border border-border bg-[#14141a]/85 px-3 py-2 backdrop-blur">
      {LEGEND.map((item) => (
        <span
          key={item.category}
          className="flex items-center gap-1.5 text-[11px] whitespace-nowrap text-muted-foreground"
        >
          <span
            className="size-2 shrink-0 rounded-full"
            style={{ backgroundColor: CATEGORY_COLOR_VAR[item.category] }}
          />
          {item.label}
        </span>
      ))}
    </div>
  );
}
