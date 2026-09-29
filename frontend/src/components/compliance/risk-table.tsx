"use client";

import { SearchX, TriangleAlert } from "lucide-react";

import { FindingDetailSheet } from "@/components/compliance/finding-detail-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { COMPLIANCE_LEVEL_META, COMPLIANCE_RULE_META } from "@/lib/compliance";
import { useComplianceStore } from "@/store/use-compliance-store";

const COLUMNS = [
  "等级",
  "员工",
  "风险",
  "实测 / 阈值",
  "计算过程",
  "建议动作",
  "",
];

export function RiskTable() {
  const data = useComplianceStore((state) => state.data);
  const loading = useComplianceStore((state) => state.loading);
  const initialized = useComplianceStore((state) => state.initialized);
  const error = useComplianceStore((state) => state.error);
  const openDetail = useComplianceStore((state) => state.openDetail);

  const showSkeleton = loading || !initialized;
  const findings = data?.findings ?? [];

  /**
   * 「没判据」与「没风险」必须分开说。
   * `skipped_rules` 非空 = 规则值没解析出来、该规则**没跑**，此时清单短
   * 不代表风险少。静默显示"共 N 条"会让演示观众以为系统扫全了。
   */
  const skipped = data?.skipped_rules ?? [];
  const unresolved = data?.unresolved ?? [];

  return (
    <div className="flex flex-col gap-3">
      {error ? (
        <div className="rounded-lg border border-severity-high/40 bg-severity-high/[0.07] p-3">
          <p className="flex items-center gap-1.5 text-[12px] font-medium text-severity-high">
            <TriangleAlert className="size-3.5" />
            扫描未完成
          </p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/85">
            {error}
          </p>
        </div>
      ) : null}

      {!error && (skipped.length > 0 || unresolved.length > 0) ? (
        <div className="rounded-lg border border-severity-mid/35 bg-severity-mid/[0.07] p-3">
          <p className="flex items-center gap-1.5 text-[12px] font-medium text-severity-mid">
            <TriangleAlert className="size-3.5" />
            有规则没跑，清单不完整（不是「无风险」）
          </p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-foreground/85">
            {skipped.length > 0
              ? `跳过规则：${skipped.join("、")}（规则值未解析出来，未用默认值兜底）。`
              : ""}
            {unresolved.length > 0
              ? `未解析的规则值：${unresolved.join("、")}。`
              : ""}
          </p>
        </div>
      ) : null}

      <Card className="overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {COLUMNS.map((column) => (
                <TableHead key={column}>{column}</TableHead>
              ))}
            </TableRow>
          </TableHeader>

          <TableBody>
            {showSkeleton
              ? Array.from({ length: 5 }).map((_, index) => (
                  <TableRow key={index} className="hover:bg-transparent">
                    <TableCell>
                      <Skeleton className="h-5 w-10 rounded-md" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-3.5 w-28" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-5 w-24 rounded-md" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-3.5 w-16" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-3.5 w-64" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-3.5 w-48" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-7 w-14 rounded-md" />
                    </TableCell>
                  </TableRow>
                ))
              : findings.map((finding) => {
                  const level = COMPLIANCE_LEVEL_META[finding.level];

                  return (
                    <TableRow
                      key={`${finding.rule}-${finding.employee_id}`}
                      className="cursor-pointer"
                      onClick={() => openDetail(finding)}
                    >
                      <TableCell>
                        <Badge variant={level.variant}>{level.label}</Badge>
                      </TableCell>

                      <TableCell>
                        <span className="block text-[13px] text-foreground">
                          {finding.employee_name}
                        </span>
                        <span className="block font-mono text-[10px] text-muted-foreground">
                          {finding.employee_id} · {finding.department}
                        </span>
                      </TableCell>

                      <TableCell>
                        <span className="text-[13px] text-foreground">
                          {/* 中文名优先用后端 rule_label，避免两端各写一份 */}
                          {finding.rule_label}
                        </span>
                        <span className="block text-[10px] text-muted-foreground">
                          {finding.work_time_system}
                        </span>
                      </TableCell>

                      <TableCell className="whitespace-nowrap text-[13px]">
                        <span className="font-medium text-foreground">
                          {finding.observed}
                        </span>
                        <span className="text-muted-foreground">
                          {" "}
                          / {finding.threshold} {finding.unit}
                        </span>
                      </TableCell>

                      <TableCell className="max-w-[340px]">
                        <span
                          className="block truncate text-[12px] text-foreground/90"
                          title={finding.calculation}
                        >
                          {finding.calculation}
                        </span>
                      </TableCell>

                      <TableCell className="max-w-[240px]">
                        <span
                          className="block truncate text-[12px] text-muted-foreground"
                          title={`${COMPLIANCE_RULE_META[finding.rule].action}（前端建议，非制度条款）`}
                        >
                          {COMPLIANCE_RULE_META[finding.rule].action}
                        </span>
                      </TableCell>

                      <TableCell>
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={(event) => {
                            event.stopPropagation();
                            openDetail(finding);
                          }}
                        >
                          {finding.evidence.length} 条证据
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
          </TableBody>
        </Table>

        {!showSkeleton && !error && findings.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
            <SearchX className="size-6 text-muted-foreground/60" />
            <p className="text-[13px] text-foreground">
              {skipped.length > 0 ? "没有可判定的风险" : "本次扫描没有命中风险"}
            </p>
            <p className="text-xs text-muted-foreground">
              {skipped.length > 0
                ? "下列规则因缺判据被跳过，请先补齐制度文档："
                : "试试把规则 / 等级筛选切回「全部」，或换一个观察日。"}
            </p>
            {skipped.length > 0 ? (
              <p className="font-mono text-[11px] text-muted-foreground">
                {skipped.join(" / ")}
              </p>
            ) : null}
          </div>
        ) : null}
      </Card>

      <FindingDetailSheet />
    </div>
  );
}
