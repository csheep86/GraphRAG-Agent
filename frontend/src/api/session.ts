/**
 * P7-N：登录会话的**存储**与**失效判定**。
 *
 * ⚠️ **为什么单独一个文件，而不是塞进 `auth.ts`**：
 * `client.ts` 发请求时要读 token，而 `auth.ts` 要靠 `client.ts` 的 `request()` 去登录
 * ⇒ 两者互相 import 会成环。抽出这一层之后依赖是单向的：
 * `client.ts` → 本文件 ← `auth.ts`。
 *
 * ⚠️ **用 `sessionStorage` 而不是 `localStorage`**（用户裁决 2026-10-13）：
 * 少一层长期驻留 —— 关掉标签页即失效。
 * 它**不防 XSS**（同源脚本仍读得到 token），真正的加固要 HttpOnly cookie，
 * 那要改后端登录响应 + CSRF 防护 ⇒ 已裁决不做，理由见 `changes/P7-N/proposal.md` §6。
 */

const STORAGE_KEY = "graphrag.auth.session";

/** 会话变了（登录成功 / 登出 / 被后端判定失效）⇒ 需要重新渲染 UI */
export const SESSION_CHANGED_EVENT = "graphrag:session-changed";

/**
 * 是否要求登录。
 *
 * **只看构建期注入的 `NEXT_PUBLIC_APP_ENV`，且端点判定写死 `=== "production"`**
 * （同 `client.ts` 里 dev header 那处的写法：宁可 prod 忘配就退回要求登录，
 * 也不用一个 fallback 把兜底行为悄悄带进生产）。
 *
 * **为什么 dev 形态不要求**：dev 走的是 `X-Org-Id` / dev token 那条兜底路，
 * 本仓库 14 个页面的本地开发都靠它 ⇒ 一开强制登录，开发调试当场进不去。
 * 而 P7-C 已经把那条路收口为生产不可达（护栏 G-27）⇒ 生产不要求登录就没有任何入口。
 */
export const AUTH_REQUIRED = process.env.NEXT_PUBLIC_APP_ENV === "production";

export interface AuthSession {
  token: string;
  userId: string;
  orgId: string;
  /**
   * 登录时**用户自己填的**用户名 —— 只为顶栏回显真实身份。
   * 后端 `LoginResponse` 不返回它（`user_id` / `org_id` 才是权威），
   * 所以这里存的是用户刚才输入的那串字：不是从别处推断出来的。
   */
  username: string;
  /** epoch 毫秒；来自 `LoginResponse.expires_at` */
  expiresAt: number;
}

/** 会话缺失 / 已过期都返回 null，并把过期的数据清掉 */
export function readSession(): AuthSession | null {
  if (typeof window === "undefined") return null;

  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (
      typeof parsed.token !== "string" ||
      typeof parsed.expiresAt !== "number"
    ) {
      throw new Error("session shape mismatch");
    }
    if (parsed.expiresAt <= Date.now()) {
      // 过期 ⇒ 当作没有。留着它只会让每个请求都白挨一次 401（§5 第 2 条：没有 refresh 端点）。
      clearSession();
      return null;
    }
    return {
      token: parsed.token,
      userId: parsed.userId ?? "",
      orgId: parsed.orgId ?? "",
      username: parsed.username ?? "",
      expiresAt: parsed.expiresAt,
    };
  } catch {
    // 形状不对（版本升级 / 被人手改过）⇒ 清掉，别让 UI 卡在一个坏状态上
    clearSession();
    return null;
  }
}

export function saveSession(session: AuthSession): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}
