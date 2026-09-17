"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, ChevronDown, LogOut, Settings, UserRound } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { matchNavItem } from "@/lib/nav";

/** 品牌标识：蓝色圆角方块 + 白色内嵌图形（对齐设计稿 Logo） */
function BrandMark() {
  return (
    <span className="relative flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[#5b8cff] to-[#3b5bf6] shadow-[0_4px_16px_-4px_rgba(79,125,255,0.85)]">
      <span className="h-3.5 w-4 rounded-[4px] bg-white/95" />
      <span className="absolute top-1.5 left-1.5 h-1.5 w-1.5 rounded-[2px] bg-[#3b5bf6]" />
    </span>
  );
}

export function TopBar() {
  const pathname = usePathname();
  const current = matchNavItem(pathname);

  return (
    <header className="relative z-40 flex h-[var(--topbar-height)] shrink-0 items-center gap-4 border-b border-border bg-background px-5">
      {/* 左：品牌 */}
      <Link
        href="/"
        className="flex w-[calc(var(--sidebar-width)-1.25rem)] shrink-0 items-center gap-2.5"
      >
        <BrandMark />
        <span className="text-[15px] font-semibold tracking-tight text-foreground">
          GraphRAG Studio
        </span>
      </Link>

      {/* 中：面包屑（居中，全中文） */}
      <nav
        aria-label="面包屑"
        className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-2 text-[13px] md:flex"
      >
        <span className="text-muted-foreground">工作台</span>
        <span className="text-muted-foreground/40">/</span>
        <span className="text-foreground">{current.breadcrumb}</span>
      </nav>

      {/* 右：通知 + 账号 */}
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          aria-label="通知"
          className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
        >
          <Bell className="size-4" />
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-2 rounded-md py-1 pr-1.5 pl-1 text-[13px] text-foreground transition-colors hover:bg-white/[0.06]"
            >
              <Avatar className="size-6">
                <AvatarFallback className="bg-gradient-to-br from-[#4f7dff] to-[#3b5bf6] text-[11px] text-white">
                  林
                </AvatarFallback>
              </Avatar>
              <span className="text-muted-foreground">
                林默 · <span className="text-foreground">管理员</span>
              </span>
              <ChevronDown className="size-3.5 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel>账号</DropdownMenuLabel>
            <DropdownMenuItem>
              <UserRound />
              个人资料
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Settings />
              偏好设置
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <LogOut />
              退出登录
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
