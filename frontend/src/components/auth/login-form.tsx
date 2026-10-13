"use client";

import { type FormEvent, useState } from "react";

import { login, startSession } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";

/**
 * P7-N：登录表单。
 *
 * **失败时原样显示后端给的那句话**：后端把「账号不存在 / 口令错误 / 已停用」
 * 压成同一条 401 文案（防账号枚举），前端一旦自己再细分，那道防护就没了。
 *
 * 同理，这里**不**自行判断"网络不通"去换成别的措辞 —— 真有网络问题时
 * 显示的是一句泛化的失败提示，宁可含糊也不编原因。
 */
export function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const response = await login({ username, password });
      // 存会话即 dispatch 事件 ⇒ `AuthGate` / 顶栏自行重渲染，这里不做页面跳转
      startSession(response, username);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "登录失败，请稍后再试",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex h-dvh items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-base">登录 GraphRAG Studio</CardTitle>
          <CardDescription>
            请使用部署时分配的账号登录
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-3" onSubmit={onSubmit}>
            <Input
              name="username"
              autoComplete="username"
              placeholder="用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={pending}
              required
            />
            <Input
              name="password"
              type="password"
              autoComplete="current-password"
              placeholder="口令"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={pending}
              required
            />

            {error ? (
              <p role="alert" className="text-[13px] text-destructive">
                {error}
              </p>
            ) : null}

            <Button type="submit" disabled={pending || !username || !password}>
              {pending ? "登录中…" : "登录"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
