import type { components } from "@/types/api";

/* ============================================================================
 * API 层入口。UI 只依赖 `src/api/*` 暴露的函数，不直接 fetch。
 * 后端就绪后只需把 NEXT_PUBLIC_USE_MOCK 置为 false，UI 无需改动。
 * ========================================================================== */

// 使用 `||` 而非 `??`：环境变量被显式置空时也要回退到默认值
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export const APP_ENV = process.env.NEXT_PUBLIC_APP_ENV || "development";

// dev-only 默认 org_id：与 backend/.env.development DEFAULT_ORG_ID 同步。
// 仅当 NEXT_PUBLIC_APP_ENV 显式 === "development" 时注入 X-Org-Id；
// 读 raw env 而非 APP_ENV 常量，避免 prod build 忘设 env 时被 fallback 误注入。
const DEV_DEFAULT_ORG_ID =
  process.env.NEXT_PUBLIC_DEV_DEFAULT_ORG_ID ||
  "00000000-0000-4000-8000-000000000001";

/**
 * 默认走 Mock：契约内端点（见 CONTRACT_COVERED_PATTERNS）已随 v1.0.0 实装，
 * 契约外端点属已知缺口（后端未定义），仍走 Mock。
 */
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";

/**
 * 契约内端点路径模式（Sprint 4.10.1.6 起唯一真源）。
 * 路径参数（如 {document_id}）用 [^/]+ 占位；精确锚定 ^$ 避免误匹配。
 * 契约新增端点时必须同步这里；漏更新会让新端点走 mock 而非真实接口。
 */
const CONTRACT_COVERED_PATTERNS: RegExp[] = [
  /^\/api\/v1\/agent\/query$/,
  /^\/api\/v1\/documents$/,
  /^\/api\/v1\/documents\/upload$/,
  /^\/api\/v1\/documents\/[^/]+\/graph$/,
  /^\/api\/v1\/documents\/[^/]+\/status$/,
  // Sprint 6 批次 C：引用溯源端点。漏登记会让 USE_MOCK=false 时该端点走 Mock，
  // 与 §5.3「关 Mock 硬门槛」直接冲突 —— 契约新增端点必须同步此处。
  /^\/api\/v1\/documents\/[^/]+\/chunks\/[^/]+$/,
  /^\/api\/v1\/graph\/overview$/,
  /^\/api\/v1\/entities\/[^/]+$/,
];

/**
 * 接口级 mock 判定：
 *  - USE_MOCK=true → 全 Mock（开发态零依赖）
 *  - USE_MOCK=false → 仅契约内端点走真实；契约外端点仍走 Mock（避免 UI 全红）
 */
export function shouldMock(path: string): boolean {
  if (USE_MOCK) return true;
  return !CONTRACT_COVERED_PATTERNS.some((re) => re.test(path));
}

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
      ...(process.env.NEXT_PUBLIC_APP_ENV === "development"
        ? { "X-Org-Id": DEV_DEFAULT_ORG_ID }
        : {}),
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
