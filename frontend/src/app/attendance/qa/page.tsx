"use client";

import { SendHorizontal, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { ReasoningPath } from "@/components/qa/reasoning-path";
import { VerdictBar } from "@/components/qa/verdict-bar";
import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PRESET_QUESTIONS, usePolicyQaStore } from "@/store/use-policy-qa-store";

/**
 * 考勤域 · 政策问答子页（Sprint 9.5 批次 E2 / 后端批次 D1）。
 *
 * ✅ 契约已实装：`POST /api/v1/agent/query`（D1 起响应带 `reasoning_path`）。
 *
 * 演示的是「M3 的答案是怎么来的」：不是只给一句话，而是把
 * **问句 → 锚点实体 → 沿关系跳转 → 命中的条款 / 事实**这条链画出来，
 * 每一跳都带起点 / 终点（id 可回查图谱）+ 关系 + 该跳来源。
 *
 * **一处必须说清的限制**：Mock 模式下 `reasoning_path` 取自真机图谱，
 * 但回答文本是**占位**（本机无 LLM 凭据），界面上有提示条标注，不当结论读。
 */
export default function AttendanceQaPage() {
  const setQuestion = usePolicyQaStore((state) => state.setQuestion);
  const asking = usePolicyQaStore((state) => state.asking);
  const error = usePolicyQaStore((state) => state.error);
  const result = usePolicyQaStore((state) => state.result);
  const ask = usePolicyQaStore((state) => state.ask);
  const [draft, setDraft] = useState<string>(PRESET_QUESTIONS[0]);

  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="政策问答"
          description="答案来自图谱 + 制度检索：下方推理路径给出每一跳的实体、关系与来源，可逐跳回查。LLM 只出措辞，数值由规则引擎给出。"
        />

        <Card className="px-5 py-4">
          <div className="flex flex-wrap items-center gap-2">
            {PRESET_QUESTIONS.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => {
                  setDraft(preset);
                  void ask(preset);
                }}
                className={`rounded-lg border px-2.5 py-1 text-[11px] transition-colors ${
                  draft === preset
                    ? "border-primary/50 bg-white/[0.06] text-foreground"
                    : "border-border text-muted-foreground hover:bg-white/[0.04]"
                }`}
              >
                {preset}
              </button>
            ))}
          </div>

          <div className="mt-3 flex gap-2">
            <input
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                setQuestion(event.target.value);
              }}
              placeholder="问一句制度相关的问题…"
              className="min-w-0 flex-1 rounded-lg border border-border bg-transparent px-3 py-2 text-[13px] text-foreground outline-none placeholder:text-muted-foreground/60"
            />
            <button
              type="button"
              disabled={asking || draft.trim().length === 0}
              onClick={() => void ask(draft.trim())}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-[12px] text-foreground transition-colors hover:bg-white/[0.06] disabled:opacity-50"
            >
              <SendHorizontal className="size-3.5" />
              提问
            </button>
          </div>
        </Card>

        {error ? (
          <div className="rounded-lg border border-[#f87171]/40 bg-[#f87171]/[0.07] p-3">
            <p className="flex items-center gap-1.5 text-[12px] font-medium text-[#f87171]">
              <TriangleAlert className="size-3.5" />
              问答未完成
            </p>
            <p className="mt-1 text-[11px] leading-relaxed text-foreground/85">
              {error}
            </p>
          </div>
        ) : null}

        {asking ? (
          <Card className="space-y-3 px-5 py-5">
            <Skeleton className="h-3 w-48" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </Card>
        ) : result ? (
          <div className="flex flex-col gap-4">
            <VerdictBar result={result} />

            <Card className="px-5 py-4">
              <h3 className="text-[12px] font-medium text-muted-foreground">回答</h3>
              <p className="mt-2 text-[13px] leading-relaxed whitespace-pre-line text-foreground/90">
                {result.answer}
              </p>
            </Card>

            <Card className="px-5 py-4">
              <h3 className="text-[12px] font-medium text-muted-foreground">
                推理路径（每一跳都可在图谱里回查）
              </h3>
              <div className="mt-3">
                <ReasoningPath hops={result.reasoning_path ?? null} />
              </div>
            </Card>
          </div>
        ) : null}
      </div>
    </PageShell>
  );
}
