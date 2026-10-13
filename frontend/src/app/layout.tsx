import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";

import { AppShell } from "@/components/layout/app-shell";
import { AuthGate } from "@/components/auth/auth-gate";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "GraphRAG Studio · 企业知识库工作台",
  description: "多模态企业知识库平台 · 文档解析 / 实体抽取 / 图谱问答",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // 单浅色主题（侧栏深色由 --sidebar-* 独立承担），不再挂 dark 变体
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full">
        {/* P7-N：登录门套在 AppShell **外面** —— 未登录时不渲染侧栏 / 顶栏 */}
        <AuthGate>
          <AppShell>{children}</AppShell>
        </AuthGate>
      </body>
      {/* P7-E：容器启动时由 `frontend/entrypoint.sh` 生成的运行时环境变量。
          `beforeInteractive` 是**必须的** —— 它保证 `window.__ENV__` 先就位，
          业务 bundle 里 `client.ts::runtimeApiBaseUrl()` 才读得到；换成 `afterInteractive`
          会用构建期那个地址闪一次，症状是「首次请求打到旧 IP / 旧域名」。 */}
      <Script src="/env.js" strategy="beforeInteractive" />
    </html>
  );
}
