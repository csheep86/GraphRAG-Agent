"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, ChevronDown, LogOut, Settings, UserRound } from "lucide-react";

import { logout } from "@/api/auth";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useSession } from "@/components/auth/use-session";
import { breadcrumbFor } from "@/lib/nav";

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
  // 用 breadcrumbFor 而非 matchNavItem：子页（如 /attendance/compliance）
  // 要显示「合规预警」，否则顶栏会跟侧栏一样停在「考勤域」。
  const current = breadcrumbFor(pathname);

  // P7-N：顶栏的账号区此前是**硬编码的假身份**（「林默 · 管理员」），连「退出登录」
  // 点了都没反应 —— 它属于"看起来能跑"的那类 UI，正好借本批把它接到真会话上：
  // 有会话显示真实用户名、退出真生效；dev 形态显示「开发态」，不再冒充某个具体的人。
  const session = useSession();
  const displayName = session?.username || "";

  return (
    <header className="relative z-40 flex h-[var(--topbar-height)] shrink-0 items-center gap-4 border-b border-border bg-card px-5">
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
        <span className="text-foreground">{current}</span>
      </nav>

      {/* 右：通知 + 账号 */}
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          aria-label="通知"
          className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Bell className="size-4" />
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-2 rounded-md py-1 pr-1.5 pl-1 text-[13px] text-foreground transition-colors hover:bg-muted"
            >
              <Avatar className="size-6">
                <AvatarFallback className="bg-gradient-to-br from-[#4f7dff] to-[#3b5bf6] text-[11px] text-white">
                  {displayName ? displayName.slice(0, 1) : "开"}
                </AvatarFallback>
              </Avatar>
              <span className="text-muted-foreground">
                {displayName ? (
                  displayName
                ) : (
                  // dev 兜底形态下确实没有登录身份 ⇒ 说"开发态"，不编一个用户名
                  <span className="text-foreground">开发态</span>
                )}
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
            {/* P7-N：真的退出。后端 JWT 无状态、没有注销端点 ⇒ 丢弃本地会话即回到登录态 */}
            <DropdownMenuItem onClick={() => logout()} disabled={!session}>
              <LogOut />
              退出登录
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
