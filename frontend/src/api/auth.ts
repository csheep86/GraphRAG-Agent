import type { components } from "@/types/api";

import { request } from "./client";
import { type AuthSession, clearSession, saveSession } from "./session";

type LoginRequest = components["schemas"]["LoginRequest"];
type LoginResponse = components["schemas"]["LoginResponse"];

/**
 * P7-N：登录（后端 `/api/v1/auth/login` 早已真实现 —— P2-C）。
 *
 * **本文件只做"接上去"，不做"重新实现"**：签发 / 校验 / 席位计数（`activated_at`
 * 由首次成功登录回填）全在后端，前端既不碰口令也不自己判身份。
 *
 * ⚠️ **401 的错误文案必须原样显示**，不要自己翻译成「账号不存在」/「口令错误」：
 * 后端刻意把这三种情况压成同一句（防账号枚举），前端一区分就把那道防护抹了。
 */
export function login(body: LoginRequest): Promise<LoginResponse> {
  return request<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * 把登录结果落成会话；返回会话对象便于 UI 直接用（`user_id` / `org_id` 回显）。
 *
 * `username` 由调用方传进来（登录表单里用户自己填的那串）—— 它不是从后端响应里推出来的，
 * 后端并没有返回这个字段，顶栏回显只用这一个来源。
 */
export function startSession(
  response: LoginResponse,
  username: string,
): AuthSession {
  const session: AuthSession = {
    token: response.access_token,
    userId: response.user_id,
    orgId: response.org_id,
    username,
    expiresAt: new Date(response.expires_at).getTime(),
  };
  saveSession(session);
  return session;
}

/** 登出。后端没有注销端点（JWT 无状态）⇒ 本地丢弃 token 即可 */
export function logout(): void {
  clearSession();
}
