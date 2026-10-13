"use client";

import type { ReactNode } from "react";

import { AUTH_REQUIRED } from "@/api/session";
import { Skeleton } from "@/components/ui/skeleton";

import { LoginForm } from "./login-form";
import { useSession } from "./use-session";

/**
 * P7-N：整站的登录门。**有意放在 `AppShell` 外层** —— 没登录时连侧栏 / 顶栏都不渲染，
 * 否则会出现"能点导航但每个接口都 401"的半成品状态（那正是最容易假以为能用的样子）。
 *
 * **为什么不拆路由 / 加 middleware**：现有 14 个页面都在 `app/` 下共享同一个 RootLayout，
 * 改路由结构会牵动全部它们；在布局层挡一道是触达面最小的做法。
 *
 * dev 形态（`AUTH_REQUIRED === false`）**整段直通**，维持现在的开发体验。
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const session = useSession();

  if (!AUTH_REQUIRED) return <>{children}</>;

  // 首帧还没读到 sessionStorage ⇒ 骨架，不当成未登录（理由见 `use-session.ts`）
  if (session === undefined) {
    return (
      <div className="flex h-dvh flex-col gap-3 p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-dvh w-full" />
      </div>
    );
  }

  if (session === null) return <LoginForm />;

  return <>{children}</>;
}
