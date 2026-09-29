"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { domainNav, systemNav, workspaceNav, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

function isActive(pathname: string, item: NavItem): boolean {
  if (item.href === "/") return pathname === "/";
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavGroup({ title, items }: { title: string; items: NavItem[] }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-1">
      <p className="px-3 pb-1.5 text-[11px] font-semibold tracking-[0.14em] text-sidebar-muted uppercase">
        {title}
      </p>

      {items.map((item) => {
        const active = isActive(pathname, item);
        const Icon = item.icon;

        /**
         * 已规划、无页面的域（Sprint 9.5 只做考勤域）：渲染成**不可点**条目。
         * 用 `<div>` 而非 `<Link>`——给一个不存在的路由就是死链，
         * 比灰掉的入口更糟（点进去 404 会被读成"做了但坏了"）。
         */
        if (item.disabled) {
          return (
            <div
              key={item.href}
              aria-disabled="true"
              title="本 Sprint 未做该业务域"
              className="flex cursor-not-allowed items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] text-sidebar-foreground/45"
            >
              <Icon className="size-4 shrink-0 text-sidebar-foreground/40" />
              <span className="truncate">{item.label}</span>
              {item.badge ? (
                <span className="ml-auto shrink-0 rounded border border-sidebar-foreground/20 px-1.5 py-px text-[10px] text-sidebar-muted">
                  {item.badge}
                </span>
              ) : null}
            </div>
          );
        }

        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors",
              active
                ? "bg-sidebar-active font-medium text-white"
                : "text-sidebar-foreground hover:bg-sidebar-hover hover:text-white",
            )}
          >
            {/* 激活态左侧指示条（对齐 demo .nav-item.active::before） */}
            {active ? (
              <span
                aria-hidden
                className="absolute top-2 bottom-2 left-0 w-[3px] rounded-r-[3px] bg-sidebar-accent"
              />
            ) : null}
            <Icon
              className={cn(
                "size-4 shrink-0",
                active ? "text-sidebar-accent" : "text-sidebar-foreground",
              )}
            />
            <span className="truncate">{item.label}</span>
            {item.badge ? (
              <span className="ml-auto shrink-0 rounded border border-sidebar-foreground/20 px-1.5 py-px text-[10px] text-sidebar-muted">
                {item.badge}
              </span>
            ) : null}
          </Link>
        );
      })}
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="sidebar-surface flex w-[var(--sidebar-width)] shrink-0 flex-col gap-6 overflow-y-auto px-3 py-5 text-sidebar-foreground scrollbar-subtle">
      <NavGroup title="Workspace" items={workspaceNav} />
      {/* Sprint 9.5：业务域分组。7 个域里只有考勤域有页面，其余标「规划中」不可点 */}
      <NavGroup title="Domain" items={domainNav} />
      <NavGroup title="System" items={systemNav} />

      {/*
        Sprint 9.5 批次 E5（R9）：数据来源全局标注。
        放在侧栏底部而非页脚——本应用没有全局页脚，而这一句必须**每页都在**
        （客户看到「42h 加班」时，同一屏就该看到这是仿真语料）。
      */}
      <p className="mt-auto px-3 pt-2 text-[10px] leading-relaxed text-sidebar-muted">
        演示语料（仿真）· 非真实客户数据
      </p>
    </aside>
  );
}
