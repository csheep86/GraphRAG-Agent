"use client";

import { useState } from "react";
import { Plus, Search } from "lucide-react";

import { Card, CardAction, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/use-chat-store";

export function SessionList() {
  const sessions = useChatStore((state) => state.sessions);
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const selectSession = useChatStore((state) => state.selectSession);
  const createSession = useChatStore((state) => state.createSession);

  const [keyword, setKeyword] = useState("");

  const visible = keyword.trim()
    ? sessions.filter((session) => session.title.includes(keyword.trim()))
    : sessions;

  return (
    <Card className="flex h-full min-h-0 flex-col gap-0 overflow-hidden">
      <CardHeader className="px-4 pt-4 pb-3">
        <CardTitle>历史会话</CardTitle>
        <CardAction>
          <button
            type="button"
            onClick={createSession}
            aria-label="新建会话"
            className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus className="size-4" />
          </button>
        </CardAction>
      </CardHeader>

      <div className="px-3 pb-3">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索会话"
            aria-label="搜索会话"
            className="h-8 pl-7 text-xs"
          />
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto scrollbar-subtle px-3 pb-3">
        {visible.map((session) => {
          const active = session.id === activeSessionId;

          return (
            <button
              key={session.id}
              type="button"
              onClick={() => selectSession(session.id)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "rounded-lg px-3 py-2.5 text-left transition-colors",
                active
                  ? "bg-accent ring-1 ring-primary/25 ring-inset"
                  : "hover:bg-foreground/[0.04]",
              )}
            >
              <p
                className={cn(
                  "truncate text-[13px]",
                  active ? "font-medium text-foreground" : "text-foreground/85",
                )}
              >
                {session.title}
              </p>
              <p className="mt-1 truncate text-[11px] text-muted-foreground">
                {session.updated_at_label}
              </p>
            </button>
          );
        })}

        {/* 首次进入列表为空是**预期**（后端无会话端点，见 use-chat-store 注释）：
            如实说明，不用假会话填充占位。 */}
        {visible.length === 0 ? (
          <div className="px-3 py-6 text-center">
            <p className="text-[11px] text-muted-foreground">
              {keyword.trim() ? "没有匹配的会话" : "暂无会话"}
            </p>
            {keyword.trim() ? null : (
              <p className="mt-1.5 text-[11px] text-muted-foreground/80">
                提问后在此生成 · 仅保存在本机，刷新后清空
              </p>
            )}
          </div>
        ) : null}
      </div>
    </Card>
  );
}
