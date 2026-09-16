# frontend/CODEBUDDY.md — 前端作用域规则

> 本文件只作用于 `frontend/`，与仓库根 `CODEBUDDY.md` 共同生效；冲突时以根规则为准。

## 1. 契约同步（铁律）

- **修改 `contracts/openapi.yaml` 后，必须运行 `npm run gen:api` 同步类型。**
- 真源是 `contracts/openapi.yaml`（其真源又是 `backend/app/schemas/`），`src/types/api.d.ts` 是**生成物**。
- 生成物**必须提交**；**禁止手工编辑**，任何手改都会被下次 `gen:api` 覆盖。
- 业务代码只引用 `components["schemas"][...]` / `operations[...]`，**禁止手写与契约重名的接口类型**。
- 发现契约字段不足以表达需求时，**先改后端 Pydantic 模型并重新导出契约**，不得在前端私自扩展类型
  （根规则 §功能预留原则：不匹配时立刻停止并输出「接口对齐清单」）。

## 2. 常用命令

```bash
npm install       # 安装依赖（提交 package-lock.json）
npm run dev       # 本地启动
npm run gen:api   # 由 ../contracts/openapi.yaml 生成 src/types/api.d.ts
npm run lint      # ESLint
```

## 3. 环境变量

- 只使用 `NEXT_PUBLIC_` 前缀暴露给浏览器；**禁止硬编码 Base URL**（根规则 §环境与依赖规则）。
