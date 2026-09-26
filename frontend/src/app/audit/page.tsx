"use client";

import { useEffect } from "react";

import { AuditTable } from "@/components/audit/audit-table";
import { AuditToolbar } from "@/components/audit/audit-toolbar";
import { PageHeader, PageShell } from "@/components/layout/page-shell";
import { useAuditStore } from "@/store/use-audit-store";

/**
 * 权限审计页（M5，Sprint 8.1 批次 A）。
 *
 * ✅ 契约已实装（`GET /api/v1/audit` / `GET /api/v1/audit/trace/{trace_id}`）：
 * `USE_MOCK=false` 下走真实后端，全站关 Mock 硬门槛达成。
 *
 * **明确未做**（属 S11，不在本批次范围）：RBAC 三粒度过滤、敏感字段脱敏器、RLS——
 * 本页因此只展示当前租户的记录，不提供按角色 / 用户的筛选。
 */
export default function AuditPage() {
  const load = useAuditStore((state) => state.load);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <PageShell>
      <div className="flex flex-col gap-5">
        <PageHeader
          title="权限审计"
          description="账号操作与数据访问的审计记录：每次 API 调用留一条，可按 trace_id 回看整条调用链。"
        />

        <AuditToolbar />
        <AuditTable />
      </div>
    </PageShell>
  );
}
