"use client";

import { useEffect, useState } from "react";

import {
  type AuthSession,
  SESSION_CHANGED_EVENT,
  readSession,
} from "@/api/session";

/**
 * 订阅当前会话。
 *
 * **三态是有意的**：
 * - `undefined` = 还没读（首帧）⇒ 交给 UI 显示骨架，**不要**直接当成未登录：
 *   `sessionStorage` 在 SSR 阶段不存在，把"还没读到"当成"没有"会让每次刷新都闪一下登录页；
 * - `null` = 确实没有（或已过期 / 被 401 清掉）；
 * - 对象 = 已登录。
 *
 * 会话的任何变化都走 `SESSION_CHANGED_EVENT`（登录 / 登出 / 请求层收到 401），
 * 所以调用方不必自己轮询。
 */
export function useSession(): AuthSession | null | undefined {
  const [session, setSession] = useState<AuthSession | null | undefined>(
    undefined,
  );

  useEffect(() => {
    const sync = () => setSession(readSession());
    sync();
    window.addEventListener(SESSION_CHANGED_EVENT, sync);
    return () => window.removeEventListener(SESSION_CHANGED_EVENT, sync);
  }, []);

  return session;
}
