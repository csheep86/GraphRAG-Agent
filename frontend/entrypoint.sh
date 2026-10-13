#!/bin/sh
# P7-E：让 Base URL 在**容器启动时**可变，而不是只能靠重建镜像。
#
# 背景（为什么不改一处就够）：`NEXT_PUBLIC_*` 会在 `next build` 时被内联成字面量，
# 所以交付时 `build_delivery_images.py` 把地址烧进 bundle 之后，客户换域名 / IP
# 就只剩「重建镜像」这一条路（这条要求已写进审计 B4）。
#
# 破法：启动时把环境变量写成 `public/env.js`，页面经 `<Script strategy="beforeInteractive">`
# 先载它，再由 `src/api/client.ts::runtimeApiBaseUrl()` 优先采用 ⇒ `docker compose restart` 即可生效。
#
# ⚠️ **这里故意只处理 API 地址。** `NEXT_PUBLIC_USE_MOCK`（R18 红线）**必须**留在构建期：
#    若它也能在运行时被改，客户现场就能把那道"默认不容错"的 Mock 开关打开
#    ——页面照跑、数据全是假的。同理 `NEXT_PUBLIC_APP_ENV` 也不在此列。
set -eu

mkdir -p /app/public

cat > /app/public/env.js <<EOF
window.__ENV__ = {
  "NEXT_PUBLIC_API_BASE_URL": "${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:8000}"
};
EOF

exec "$@"
