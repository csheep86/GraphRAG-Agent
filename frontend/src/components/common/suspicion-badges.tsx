import { Badge } from "@/components/ui/badge";
import {
  SUSPICION_SEVERITY_META,
  SUSPICION_STATUS_META,
  SUSPICION_TYPE_META,
} from "@/lib/status";
import type {
  AffiliationSeverity,
  AffiliationSuspicionStatus,
  AffiliationSuspicionType,
} from "@/types/mock";

/**
 * 疑点三枚标签（Sprint 7.3 批次 C）。
 * 取值全部来自契约枚举，文案与语义色集中在 `lib/status.ts` 的 `SUSPICION_*_META`
 * ——照 `DocumentStatusBadge` 的写法，组件只做取表渲染。
 */

export function SuspicionTypeBadge({
  type,
}: {
  type: AffiliationSuspicionType;
}) {
  const meta = SUSPICION_TYPE_META[type];
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}

export function SuspicionSeverityBadge({
  severity,
}: {
  severity: AffiliationSeverity;
}) {
  const meta = SUSPICION_SEVERITY_META[severity];
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}

export function SuspicionStatusBadge({
  status,
}: {
  status: AffiliationSuspicionStatus;
}) {
  const meta = SUSPICION_STATUS_META[status];
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}
