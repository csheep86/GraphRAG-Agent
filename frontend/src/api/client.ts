import type { components } from "@/types/api";

/* ============================================================================
 * API 层入口。UI 只依赖 `src/api/*` 暴露的函数，不直接 fetch。
 * 后端就绪后只需把 NEXT_PUBLIC_USE_MOCK 置为 false，UI 无需改动。
 * ========================================================================== */

// 使用 `||` 而非 `??`：环境变量被显式置空时也要回退到默认值
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export const APP_ENV = process.env.NEXT_PUBLIC_APP_ENV || "development";

/**
 * 默认走 Mock：contracts/openapi.yaml 中除 health / upload / status 外，
 * 其余端点当前实现状态为 501 NOT_IMPLEMENTED（Sprint 3 范围）。
 */
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";

export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type ErrorCode = components["schemas"]["ErrorCode"];

/** 统一错误响应体（CODEBUDDY.md §错误响应规范）对应的异常 */
export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly status: number;
  readonly traceId: string;
  readonly detail: Record<string, unknown> | null;

  constructor(payload: ErrorResponse, status: number) {
    super(payload.message);
    this.name = "ApiError";
    this.code = payload.code;
    this.status = status;
    this.traceId = payload.trace_id;
    this.detail = (payload.detail as Record<string, unknown> | null) ?? null;
  }
}

/** 真实 HTTP 调用；Mock 模式下不会被触发 */
export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const isFormData =
    typeof FormData !== "undefined" && init.body instanceof FormData;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...init.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let payload: ErrorResponse | null = null;
    try {
      payload = (await response.json()) as ErrorResponse;
    } catch {
      payload = null;
    }

    throw new ApiError(
      payload ?? {
        code: "HTTP_ERROR",
        message: `Request failed with status ${response.status}`,
        detail: null,
        trace_id: response.headers.get("X-Trace-Id") ?? "",
      },
      response.status,
    );
  }

  return (await response.json()) as T;
}

/** Mock 网络延迟，保证加载态可见 */
export function delay(ms = 320): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 生成本地唯一 id（仅 Mock 使用） */
export function mockId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}
