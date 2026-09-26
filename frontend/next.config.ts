import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 允许 127.0.0.1 访问 dev 资源（HMR/水合）。缺省只认 localhost，
  // 用 http://127.0.0.1:3000 打开时客户端 JS 会被拦截，页面永远停在骨架屏。
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
