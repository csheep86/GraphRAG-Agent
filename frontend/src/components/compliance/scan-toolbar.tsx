"use client";

import { CalendarClock, RefreshCw } from "lucide-react";

import {
  COMPLIANCE_LEVEL_OPTIONS,
  COMPLIANCE_RULE_OPTIONS,
  type ComplianceLevelFilter,
  type ComplianceRuleFilter,
} from "@/lib/compliance";
import { useComplianceStore } from "@/store/use-compliance-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";

/**
 * 观察日快捷按钮。
 *
 * **2026-12-15 是刻意选的**：那天距季末只剩 16 天 < 制度阈值 30 天，
 * 同一条「调休未消化」会从 **medium 升到 high**（临期判据）。
 * 演示时两个观察日各扫一次，正好展示"同一事实随时间自动升级"——
 * 这是规则引擎最不像关键词检索的一处。
 */
const AS_OF_PRESETS: { value: string; label: string }[] = [
  { value: "", label: "数据窗口末日" },
  { value: "2026-12-15", label: "临期 12-15" },
];

export function ScanToolbar() {
  const asOf = useComplianceStore((state) => state.asOf);
  const setAsOf = useComplianceStore((state) => state.setAsOf);
  const ruleFilter = useComplianceStore((state) => state.ruleFilter);
  const setRuleFilter = useComplianceStore((state) => state.setRuleFilter);
  const levelFilter = useComplianceStore((state) => state.levelFilter);
  const setLevelFilter = useComplianceStore((state) => state.setLevelFilter);
  const load = useComplianceStore((state) => state.load);
  const loading = useComplianceStore((state) => state.loading);
  const data = useComplianceStore((state) => state.data);

  const high = data?.findings.filter((f) => f.level === "high").length ?? 0;
  const medium = data?.findings.filter((f) => f.level === "medium").length ?? 0;

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        <CalendarClock className="size-4 text-muted-foreground" />
        <Input
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="w-[148px]"
          aria-label="观察日"
          // 空值 = 不传参，由后端取数据窗口末日（**不取系统当天**，保证可复现）
          title="留空 = 数据窗口末日（不取系统当天，保证可复现）"
        />
      </div>

      <div className="flex items-center gap-1">
        {AS_OF_PRESETS.map((preset) => (
          <Button
            key={preset.label}
            variant={asOf === preset.value ? "secondary" : "outline"}
            size="xs"
            onClick={() => setAsOf(preset.value)}
          >
            {preset.label}
          </Button>
        ))}
      </div>

      <Select
        value={ruleFilter}
        onValueChange={(value) =>
          setRuleFilter(value as ComplianceRuleFilter)
        }
      >
        <SelectTrigger className="w-[136px]" aria-label="按规则筛选">
          <span>
            {
              COMPLIANCE_RULE_OPTIONS.find((o) => o.value === ruleFilter)
                ?.label
            }
          </span>
        </SelectTrigger>
        <SelectContent>
          {COMPLIANCE_RULE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={levelFilter}
        onValueChange={(value) =>
          setLevelFilter(value as ComplianceLevelFilter)
        }
      >
        <SelectTrigger className="w-[112px]" aria-label="按等级筛选">
          <span>
            {
              COMPLIANCE_LEVEL_OPTIONS.find((o) => o.value === levelFilter)
                ?.label
            }
          </span>
        </SelectTrigger>
        <SelectContent>
          {COMPLIANCE_LEVEL_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button
        variant="outline"
        size="xs"
        disabled={loading}
        onClick={() => void load()}
      >
        <RefreshCw className={loading ? "size-3.5 animate-spin" : "size-3.5"} />
        {loading ? "扫描中…" : "重新扫描"}
      </Button>

      {data ? (
        <span className="text-[13px] text-muted-foreground">
          共 <span className="text-foreground">{data.total}</span> 条风险 ·
          高 <span className="text-foreground">{high}</span> · 中{" "}
          <span className="text-foreground">{medium}</span>
          <span className="ml-1.5 text-[11px]">
            （扫描 {data.employee_count} 人）
          </span>
        </span>
      ) : null}
    </div>
  );
}
