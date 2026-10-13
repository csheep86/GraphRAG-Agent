# D-1 容器化（Sprint 10.3）— frontend 运行镜像
#
# 纪律来源（`docs/deployment-spec.md` §2）：frontend 走 **`next start`**（**非** `next dev`）。
#
# **红线（R18 / PRD §7.2 零假数据）**：`NEXT_PUBLIC_USE_MOCK` 默认即 `true`
# （`src/api/client.ts` `!== "false"`）⇒ 不显式置 false，容器化的前端会**静默走 Mock**，
# 看起来能跑、数据全是假的。`NEXT_PUBLIC_*` 在 **build 时内联**，故必须在构建阶段注入。
#
# **构建期 vs 运行时（P7-E 划的线，别越过）**：
# - `NEXT_PUBLIC_USE_MOCK` / `NEXT_PUBLIC_APP_ENV`：**只能**构建期给，运行时不许改
#   （理由就是上面那条红线：能改 = 能在现场打开假数据）；
# - `NEXT_PUBLIC_API_BASE_URL`：构建期给的是**默认值**，容器启动时还可用
#   `entrypoint.sh` 覆盖一层（写到 `public/env.js`）⇒ 换域名不必重建镜像。

FROM node:22-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# 三个 NEXT_PUBLIC_ 均为 build-arg，便于现场改 API 地址后重建
ARG NEXT_PUBLIC_USE_MOCK=false
ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_USE_MOCK=${NEXT_PUBLIC_USE_MOCK} \
    NEXT_PUBLIC_APP_ENV=${NEXT_PUBLIC_APP_ENV} \
    NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN npm run build

FROM node:22-slim AS runtime

ENV NODE_ENV=production
WORKDIR /app

COPY --from=build /app/package.json /app/package-lock.json ./
# 只装运行时依赖（`next` 在 dependencies 中，`next start` 可用）
RUN npm ci --omit=dev

COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public

# P7-E：启动时把 `NEXT_PUBLIC_API_BASE_URL` 写成 `public/env.js`（详见脚本内注释）
# ⇒ 客户换域名 / IP 后 `docker compose restart` 即生效，**不需要**重建镜像。
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 3000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["npm", "run", "start"]
