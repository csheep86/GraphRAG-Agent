import { Badge } from "@/components/ui/badge";
import { DOCUMENT_STATUS_META } from "@/lib/status";
import type { DocumentStatus } from "@/types/mock";

/** 文档状态标签：已完成=紫 · 处理中=蓝 · 失败=红 · 待处理=灰（对齐 p01 / p02） */
export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const meta = DOCUMENT_STATUS_META[status];

  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}
