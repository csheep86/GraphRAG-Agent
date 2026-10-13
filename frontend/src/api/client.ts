import type { components } from "@/types/api";

import { clearSession, readSession } from "./session";

/* ============================================================================
 * API 层入口。UI 只依赖 `src/api/*` 暴露的函数，不直接 fetch。
 * 后端就绪后只需把 NEXT_PUBLIC_USE_MOCK 置为 false，UI 无需改动。
 * ========================================================================== */

// 使用 `||` 而非 `??`：环境变量被显式置空时也要回退到默认值
const BUILD_TIME_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

/**
 * **运行时**那一层 API 地址（P7-E）。
 *
 * **为什么需要它**：`NEXT_PUBLIC_*` 在 **build 期**被内联成立面量
 * （`process.env.NEXT_PUBLIC_*` 编译时就被替换掉）⇒ 客户把自己的域名 / IP 换掉之后，
 * 旧的写法只能**重建镜像**。破法是「运行时再补一层」：容器入口点启动时把环境变量
 * 写成 `public/env.js`，页面用 `<Script strategy="beforeInteractive">` 先载它，
 * 这里再优先读 `window.__ENV__`（生成逻辑见 `frontend/entrypoint.sh`）。
 *
 * **优先级：运行时 > 构建期 > 内置默认**。
 *
 * ⚠️ **红线：只有 API 地址享受运行时。`NEXT_PUBLIC_USE_MOCK`（R18）刻意留在构建期**
 * —— 若它也能在现场被改，客户就能把那个"默认不容错"的 Mock 开关打开，
 * 页面看起来能跑、数据全是假的（这段对照 `frontend/Dockerfile` 顶部的 R18 红线）。
 */
function runtimeApiBaseUrl(): string | undefined {
  if (typeof window === "undefined") return undefined;
  const injected = (
    window as unknown as { __ENV__?: Record<string, string | undefined> }
  ).__ENV__?.NEXT_PUBLIC_API_BASE_URL;
  return injected || undefined;
}

export const API_BASE_URL = runtimeApiBaseUrl() || BUILD_TIME_API_BASE_URL;

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
  // Sprint 9.5 批次 C3：问答端点（D1 起带 reasoning_path）。漏登记会让政策问答页走 Mock。
  // （**F-P7D-2**：这一条原本在本数组里登记了**两次**，P7-N 改动本文件时顺带清掉 ——
  //  其余分组本次未动）
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
  // Sprint 7.2 批次 B：M4 疑点四端点（spec §5.5）。批次 C 的疑点页要能关 Mock 跑真实接口，
  // 漏登记会让 §5.3「关 Mock 硬门槛」直接失败 —— 契约新增端点必须同步此处。
  /^\/api\/v1\/affiliation\/detect$/,
  /^\/api\/v1\/affiliation\/tasks\/[^/]+$/,
  /^\/api\/v1\/affiliation\/suspicions$/,
  /^\/api\/v1\/affiliation\/suspicions\/[^/]+$/,
  // Sprint 8.1 批次 A：M5 审计两个只读端点。漏登记会让它们走 mock，
  // 与 plan §7.2「审计页关 Mock 硬门槛」直接冲突 —— 契约新增端点必须同步此处。
  /^\/api\/v1\/audit$/,
  /^\/api\/v1\/audit\/trace\/[^/]+$/,
  // Sprint 9.5 批次 C3：考勤域合规扫描。漏登记会让 USE_MOCK=false 时该端点走 Mock，
  // 屏幕上的风险清单就不再是真机算出来的 —— 契约新增端点必须同步此处。
  /^\/api\/v1\/attendance\/compliance\/scan$/,
  // 批次 C4：考勤域异常归因两端点（清单 + 归因）。同理，漏登记会让它们走 Mock。
  /^\/api\/v1\/attendance\/anomalies$/,
  /^\/api\/v1\/attendance\/anomalies\/explain$/,
  // P5-I（2026-10-09）：M6 校正 GUI 的四条端点（候选读 + merge / rename / split）。
  // ⚠️ 漏登记的后果不是报错而是**静默走假数据**：USE_MOCK=false 时点三动作打到的是
  // 本地 mock，页面看起来"成功"、图谱其实一行没变 —— 与本仓「不假造成功」直接冲突。
  /^\/api\/v1\/ontology\/candidates$/,
  /^\/api\/v1\/ontology\/merge$/,
  /^\/api\/v1\/ontology\/rename$/,
  /^\/api\/v1\/ontology\/split$/,
  // P7-D（2026-10-13）：把此前漏登记的 8 条契约端点一次补齐，使
  // 「契约 paths - 白名单」的差集为 **0**（用户裁决：全部纳管、豁免清单为空）。
  //
  // 事实口径（别误读成"修线上问题"）：这 8 条当时在 UI 侧**没有调用点**
  // （全仓只命中生成物 types/api.d.ts 与 mock/audit.ts 里的字符串），
  // 所以此改动是**收口机制**——将来谁接上真页面，不必再冒一次静默 Mock。
  // 登录页 / 成本仪表盘页本身仍是缺口，本批不做（Non-goals 第 1 条）。
  /^\/api\/v1\/auth\/login$/,
  /^\/api\/v1\/cost\/dashboard$/,
  /^\/api\/v1\/graph\/versions\/[^/]+\/activate$/,
  /^\/api\/v1\/health$/,
  /^\/api\/v1\/license\/status$/,
  /^\/api\/v1\/ontology\/active$/,
  /^\/api\/v1\/ontology\/cold-start$/,
  /^\/api\/v1\/ontology\/confirm$/,
  //
  // 从此 **不许手工维护**这份清单：漏/多一条都会让
  // backend/tests/test_frontend_contract_coverage.py 变红（CI 后端 job 必跑）。
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

/** 登录端点自己**不带** Authorization —— 那时还没会话；带着旧 token 只会干扰换账号。 */
const LOGIN_PATH = "/api/v1/auth/login";

/**
 * P7-N：给请求挂上 `Authorization: Bearer <token>`（契约写死的携带方式，见 `LoginResponse`）。
 *
 * 没有会话就**不挂头**，交给后端返回 401 ⇒ 上层把 UI 带回登录态。
 * **不要**为了"让请求看起来能跑"去伪造一个凭据。
 */
function authHeaders(path: string): Record<string, string> {
  if (path === LOGIN_PATH) return {};
  const token = readSession()?.token;
  return token ? { Authorization: `Bearer ${token}` } : {};
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
      ...authHeaders(path),
      ...init.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    // P7-N：**401 一律按"会话不在了"处理**（登录端点自身的 401 除外 —— 那时还没有会话，
    // 是口令不对）。
    //
    // 为什么不留着 token 让下一个请求自己再试一次：带着失效的 token，
    // 页面上每个接口都会挨一次 401，症状是"一直在 loading / 到处红"，很难归因。
    // 清掉之后 UI 回到登录态，用户看得懂。**不做静默重试** —— 重试成功会掩盖事实。
    if (response.status === 401 && path !== LOGIN_PATH) {
      clearSession();
    }
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
