"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Loader2, RefreshCw, Split } from "lucide-react";

import { CANDIDATE_STATUS_OPTIONS } from "@/api/ontology";
import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { CandidateTable } from "@/components/ontology/candidate-table";
import { CorrectionDialog } from "@/components/ontology/correction-dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import {
  useOntologyStore,
  type CandidateStatusFilter,
} from "@/store/use-ontology-store";

/**
 * M6 批次 B：**本体校正 GUI**（m6 §1.1 第 2 条）。
 *
 * ✅ 契约已实装：`GET /api/v1/ontology/candidates` + `POST /ontology/merge` /
 * `/rename` / `/split`（P5-G 真实现 + P5-I 候选读端点）。
 *
 * **明确未做**（m6 §1.2 Out of Scope + 本批 10 条 Non-goals）：
 * 批量校正 / 撤销栈 / 本体版本对比；`ontology/confirm` / `cold-start` 的 LLM 建议；
 * 前端角色判断（后端 `require_permission` 在跑，前端只把 403 显示出来）。
 */
export default function OntologyPage() {
  const load = useOntologyStore((state) => state.load);
  const loading = useOntologyStore((state) => state.loading);
  const statusFilter = useOntologyStore((state) => state.statusFilter);
  const setStatusFilter = useOntologyStore((state) => state.setStatusFilter);
  const total = useOntologyStore((state) => state.total);
  const lastKgVersion = useOntologyStore((state) => state.lastKgVersion);
  const graphRefreshedAt = useOntologyStore((state) => state.graphRefreshedAt);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="本体校正"
          description="从实体消解候选里挑出实体，发起合并 / 拆分 / 改名三个动作。动作同步完成并产出新的图谱版本，图谱视图会随即刷新到该版本。"
        />

        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={() => void load()} disabled={loading}>
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            {loading ? "加载中…" : "刷新"}
          </Button>

          <Select
            value={statusFilter}
            onValueChange={(value) =>
              setStatusFilter(value as CandidateStatusFilter)
            }
          >
            <SelectTrigger className="w-[132px]" aria-label="按处置档位筛选">
              {/* 直接渲染文案而非 SelectValue：保证 SSR 首屏有字，避免水合闪烁 */}
              <span>
                {
                  CANDIDATE_STATUS_OPTIONS.find((o) => o.value === statusFilter)
                    ?.label
                }
              </span>
            </SelectTrigger>
            <SelectContent>
              {CANDIDATE_STATUS_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <span className="text-[13px] text-muted-foreground">
            共 {total} 条候选
          </span>
        </div>

        {lastKgVersion ? (
          <div className="rounded-lg border border-primary/30 bg-primary/[0.06] px-3 py-2.5 text-[12px] leading-relaxed text-foreground">
            <div className="flex items-center gap-1.5 font-medium">
              <Split className="size-3.5" />
              动作已应用，产出新图谱版本
            </div>
            <div className="mt-1 font-mono text-[11px]">{lastKgVersion}</div>
            <div className="mt-1 text-muted-foreground">
              {graphRefreshedAt
                ? "图谱视图已刷新到该版本（`GET /graph/overview` 按版本继承读，刷新后是完整图谱）。"
                : "图谱视图正在刷新…"}
              <Link href="/graph" className="ml-1 text-primary hover:underline">
                查看图谱
              </Link>
            </div>
          </div>
        ) : null}

        <CandidateTable />
        <CorrectionDialog />
      </div>
    </PageShell>
  );
}
