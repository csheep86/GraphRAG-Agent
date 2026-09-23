"use client";

import { useEffect } from "react";

import { ChatPanel } from "@/components/qa/chat-panel";
import { ChunkViewer } from "@/components/qa/chunk-viewer";
import { EvidencePanel } from "@/components/qa/evidence-panel";
import { SessionList } from "@/components/qa/session-list";
import { useChatStore } from "@/store/use-chat-store";

export default function QaPage() {
  const initialize = useChatStore((state) => state.initialize);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  return (
    <div className="flex min-h-0 flex-1 flex-col p-6">
      {/* 三栏：历史会话 / 对话区 / 引用证据（比例对齐 p03 设计稿） */}
      <div className="grid min-h-0 flex-1 grid-cols-[200px_minmax(0,1fr)_272px] gap-4 2xl:grid-cols-[220px_minmax(0,1fr)_300px]">
        <SessionList />
        <ChatPanel />
        <EvidencePanel />
      </div>

      {/* 批次 C：引用溯源抽屉（不占三栏栅格，按需滑出） */}
      <ChunkViewer />
    </div>
  );
}
