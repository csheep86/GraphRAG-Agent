import {
  FileText,
  LayoutGrid,
  MessageSquare,
  Network,
  Settings,
  ShieldAlert,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  /** 侧栏展示名（保持中文） */
  label: string;
  /** 面包屑末级（保持中文） */
  breadcrumb: string;
  href: string;
  icon: LucideIcon;
  /** 设计稿尚未覆盖的页面，UI 预留空位，不接后端 */
  placeholder?: boolean;
};

/** 侧栏分组 WORKSPACE */
export const workspaceNav: NavItem[] = [
  { label: "工作台", breadcrumb: "工作台概览", href: "/", icon: LayoutGrid },
  { label: "文档管理", breadcrumb: "文档管理", href: "/documents", icon: FileText },
  { label: "知识问答", breadcrumb: "知识问答", href: "/qa", icon: MessageSquare },
  { label: "知识图谱", breadcrumb: "知识图谱", href: "/graph", icon: Network },
  // Sprint 7.3 批次 C：M4 疑点清单（真实接后端四端点，非 placeholder）。
  // 图标用 ShieldAlert（告警）而非 ShieldCheck——后者已归 system 组的「权限审计」。
  {
    label: "疑点清单",
    breadcrumb: "疑点清单",
    href: "/affiliation",
    icon: ShieldAlert,
  },
];

/** 侧栏分组 SYSTEM —— 设计稿仅给出入口，功能预留 */
export const systemNav: NavItem[] = [
  {
    label: "系统设置",
    breadcrumb: "系统设置",
    href: "/settings",
    icon: Settings,
    placeholder: true,
  },
  {
    label: "权限审计",
    breadcrumb: "权限审计",
    href: "/audit",
    icon: ShieldCheck,
    placeholder: true,
  },
];

const allNav = [...workspaceNav, ...systemNav];

/** 通过 pathname 匹配当前激活项；`/` 需精确匹配 */
export function matchNavItem(pathname: string): NavItem {
  const exact = allNav.find((item) => item.href === pathname);
  if (exact) return exact;

  const prefix = allNav
    .filter((item) => item.href !== "/")
    .find((item) => pathname.startsWith(item.href));

  return prefix ?? workspaceNav[0];
}
