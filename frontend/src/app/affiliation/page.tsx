"use client";

import { useEffect } from "react";

import { SuspicionTable } from "@/components/affiliation/suspicion-table";
import { SuspicionToolbar } from "@/components/affiliation/suspicion-toolbar";
import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { useAffiliationStore } from "@/store/use-affiliation-store";

export default function AffiliationPage() {
  const load = useAffiliationStore((state) => state.load);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="疑点清单"
          description="系统基于已完成解析的文档自动识别关联关系疑点，每条带原文证据链，可逐条复核。"
        />

        <SuspicionToolbar />
        <SuspicionTable />
      </div>
    </PageShell>
  );
}
