"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { systemNav, workspaceNav, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

function isActive(pathname: string, item: NavItem): boolean {
  if (item.href === "/") return pathname === "/";
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavGroup({ title, items }: { title: string; items: NavItem[] }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col gap-1">
      <p className="px-3 pb-1.5 text-[11px] font-medium tracking-[0.14em] text-muted-foreground/60 uppercase">
        {title}
      </p>

      {items.map((item) => {
        const active = isActive(pathname, item);
        const Icon = item.icon;

        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors",
              active
                ? "bg-accent font-medium text-foreground"
                : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground",
            )}
          >
            <Icon
              className={cn(
                "size-4 shrink-0",
                active ? "text-primary" : "text-muted-foreground",
              )}
            />
            <span className="truncate">{item.label}</span>
          </Link>
        );
      })}
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="flex w-[var(--sidebar-width)] shrink-0 flex-col gap-6 overflow-y-auto scrollbar-subtle border-r border-border bg-background px-3 py-5">
      <NavGroup title="Workspace" items={workspaceNav} />
      <NavGroup title="System" items={systemNav} />
    </aside>
  );
}
