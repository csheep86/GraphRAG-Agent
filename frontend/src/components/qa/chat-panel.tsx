"use client";

import { useEffect, useRef } from "react";
import { Loader2, MoreHorizontal, Share2, Trash2 } from "lucide-react";

import { ChatComposer } from "@/components/qa/chat-composer";
import { ChatMessageItem } from "@/components/qa/chat-message-item";
import { Card, CardAction, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { selectActiveMessages, selectActiveSession, useChatStore } from "@/store/use-chat-store";

export function ChatPanel() {
  const session = useChatStore(selectActiveSession);
  const messages = useChatStore(selectActiveMessages);
  const messagesLoading = useChatStore((state) => state.messagesLoading);
  const sending = useChatStore((state) => state.sending);
  const selectEvidence = useChatStore((state) => state.selectEvidence);

  const scrollRef = useRef<HTMLDivElement>(null);

  // 新消息或发送中状态变化时，滚动到底部
  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages.length, sending]);

  return (
    <Card className="flex h-full min-h-0 min-w-0 flex-col gap-0 overflow-hidden">
      <CardHeader className="border-b border-border px-5 py-3.5">
        <div className="min-w-0 space-y-1">
          <CardTitle className="truncate">
            {session?.title ?? "新的会话"}
          </CardTitle>
          <p className="truncate text-[11px] text-muted-foreground">
            基于 {session?.doc_count ?? 0} 份文档 · 图谱增强检索
          </p>
        </div>

        <CardAction>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label="会话操作"
                className="flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
              >
                <MoreHorizontal className="size-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuItem>
                <Share2 />
                分享会话
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Trash2 />
                删除会话
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </CardAction>
      </CardHeader>

      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto scrollbar-subtle px-5 py-5"
      >
        {messagesLoading ? (
          <div className="flex flex-col gap-4">
            <Skeleton className="h-20 w-full rounded-xl" />
            <Skeleton className="h-32 w-full rounded-xl" />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {messages.map((message) => (
              <ChatMessageItem
                key={message.id}
                message={message}
                onSelectEvidence={selectEvidence}
              />
            ))}

            {messages.length === 0 ? (
              <div className="py-16 text-center">
                <p className="text-[13px] text-foreground">开始一次图谱问答</p>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  回答会附带可追溯的引用来源，无证据时会明确拒答。
                </p>
              </div>
            ) : null}

            {sending ? (
              <div className="flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                正在检索图谱并生成回答…
              </div>
            ) : null}
          </div>
        )}
      </div>

      <ChatComposer />
    </Card>
  );
}
