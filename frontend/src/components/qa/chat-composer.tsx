"use client";

import { useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChatStore } from "@/store/use-chat-store";

export function ChatComposer() {
  const send = useChatStore((state) => state.send);
  const sending = useChatStore((state) => state.sending);

  const [value, setValue] = useState("");
  const canSubmit = value.trim().length > 0 && !sending;

  const submit = () => {
    if (!canSubmit) return;
    const question = value.trim();
    setValue("");
    void send(question);
  };

  return (
    <div className="border-t border-border px-4 py-3.5">
      <div className="flex items-end gap-2 rounded-xl border border-border bg-white/[0.02] px-3 py-2 transition-colors focus-within:border-primary/50">
        <Textarea
          value={value}
          rows={1}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder="输入你的问题，支持追问…"
          aria-label="输入你的问题"
          className="max-h-32 flex-1 py-1 text-[13px]"
        />

        <Button
          size="icon-sm"
          onClick={submit}
          disabled={!canSubmit}
          aria-label="发送"
        >
          {sending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <ArrowUp className="size-4" />
          )}
        </Button>
      </div>
    </div>
  );
}
