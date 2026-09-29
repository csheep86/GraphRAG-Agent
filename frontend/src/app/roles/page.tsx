import { Info } from "lucide-react";

import { PlaceholderPage } from "@/components/common/placeholder-page";
import { Badge } from "@/components/ui/badge";

/** 权限与角色（demo 有此视图）——功能预留：契约无端点，不接后端、不填示意值。 */
export default function RolesPage() {
  return (
    <PlaceholderPage
      title="权限与角色"
      description="角色矩阵与权限分配（当前版本未提供该能力）。"
      badge={
        <Badge variant="muted" className="gap-1.5">
          <Info className="size-3" />
          功能预留
        </Badge>
      }
    />
  );
}
