import {
  CalendarDays,
  CircleCheck,
  Database,
  FileText,
  FlaskConical,
  LayoutGrid,
  MessageSquare,
  Network,
  Package,
  ScrollText,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Split,
  UserCog,
  Users,
  Wrench,
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
  /** 右上角小标（如「规划中」）—— 对外沟通状态，不是装饰 */
  badge?: string;
  /**
   * 已规划但**没有页面**：渲染为不可点条目（不是死链）。
   * 与 `placeholder` 的区别：`placeholder` 有路由、只是不接后端。
   */
  disabled?: boolean;
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
  // P5-I（2026-10-09）：M6 批次 B 本体校正 GUI。真实接后端四端点（候选读 +
  // merge / rename / split），**不是** placeholder。
  {
    label: "本体校正",
    breadcrumb: "本体校正",
    href: "/ontology",
    icon: Split,
  },
];

/**
 * 侧栏分组 DOMAIN —— 对齐 `docs/demo.html:409-416` 的 7 个业务域。
 *
 * **本次 Sprint 只做考勤域**（Sprint 9.5 提案 §3.2 明确划界）：其余 6 个域
 * 标「规划中」且 **不可点**（`disabled`）——给它们一个能跳的路由等于宣称
 * 已交付，与 A16「诚实可核」冲突；宁可留一个灰掉的入口。
 *
 * 考勤域下三个子页（政策问答 / 异常归因 / 合规预警）**不进侧栏**，由
 * `/attendance` 域首页进入，避免侧栏被同一个域的三层结构撑爆。
 */
export const domainNav: NavItem[] = [
  {
    label: "考勤",
    breadcrumb: "考勤域",
    href: "/attendance",
    icon: CalendarDays,
  },
  {
    label: "售后",
    breadcrumb: "售后域",
    href: "/service",
    icon: Wrench,
    badge: "规划中",
    disabled: true,
  },
  {
    label: "研发",
    breadcrumb: "研发域",
    href: "/rd",
    icon: FlaskConical,
    badge: "规划中",
    disabled: true,
  },
  {
    label: "供应链",
    breadcrumb: "供应链域",
    href: "/supply",
    icon: Package,
    badge: "规划中",
    disabled: true,
  },
  {
    label: "HR能力",
    breadcrumb: "HR 能力域",
    href: "/hr",
    icon: Users,
    badge: "规划中",
    disabled: true,
  },
  {
    label: "质量",
    breadcrumb: "质量域",
    href: "/quality",
    icon: CircleCheck,
    badge: "规划中",
    disabled: true,
  },
  {
    label: "专利",
    breadcrumb: "专利域",
    href: "/patent",
    icon: ScrollText,
    badge: "规划中",
    disabled: true,
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
    label: "数据源接入",
    breadcrumb: "数据源接入",
    href: "/data-sources",
    icon: Database,
    placeholder: true,
  },
  {
    label: "权限与角色",
    breadcrumb: "权限与角色",
    href: "/roles",
    icon: UserCog,
    placeholder: true,
  },
  {
    label: "权限审计",
    breadcrumb: "权限审计",
    href: "/audit",
    icon: ShieldCheck,
    // Sprint 8.1 批次 A 起已是真实页（`GET /api/v1/audit` 进契约），不再是预留位。
    // 该标记当前无 UI 消费点，但留着 true 就是一条假声明——与 A16「诚实可核」冲突。
  },
];

const allNav = [...workspaceNav, ...domainNav, ...systemNav];

/**
 * 面包屑末级文案。
 *
 * 子页（如 `/attendance/compliance`）在 `allNav` 里没有精确项，靠前缀匹配
 * 到 `/attendance`——但面包屑末级若显示「考勤域」就跟父级重名了，故按
 * **路径末段**补一档映射；取不到就退回 `matchNavItem` 的 breadcrumb。
 */
const SUB_ROUTE_BREADCRUMB: Record<string, string> = {
  compliance: "合规预警",
  attribution: "异常归因",
  qa: "政策问答",
};

export function breadcrumbFor(pathname: string): string {
  const item = matchNavItem(pathname);
  if (item.href === pathname) return item.breadcrumb;

  const last = pathname.split("/").filter(Boolean).pop();
  return (last && SUB_ROUTE_BREADCRUMB[last]) || item.breadcrumb;
}

/** 通过 pathname 匹配当前激活项；`/` 需精确匹配 */
export function matchNavItem(pathname: string): NavItem {
  const exact = allNav.find((item) => item.href === pathname);
  if (exact) return exact;

  const prefix = allNav
    .filter((item) => item.href !== "/")
    .find((item) => pathname.startsWith(item.href));

  return prefix ?? workspaceNav[0];
}
