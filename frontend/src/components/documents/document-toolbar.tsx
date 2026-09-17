"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { formatNumber } from "@/lib/format";
import { STATUS_FILTER_OPTIONS } from "@/lib/status";
import { useDocumentStore, type StatusFilter } from "@/store/use-document-store";

export function DocumentToolbar({ total }: { total: number }) {
  const keyword = useDocumentStore((state) => state.keyword);
  const status = useDocumentStore((state) => state.status);
  const setKeyword = useDocumentStore((state) => state.setKeyword);
  const setStatus = useDocumentStore((state) => state.setStatus);

  // 本地态 + 300ms 防抖，避免每次按键都触发请求
  const [draft, setDraft] = useState(keyword);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (draft !== keyword) setKeyword(draft);
    }, 300);
    return () => clearTimeout(timer);
  }, [draft, keyword, setKeyword]);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="relative w-[320px] max-w-full">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="搜索文件名或类型…"
          aria-label="搜索文件名或类型"
          className="h-9 pl-8 text-[13px]"
        />
      </div>

      <Select
        value={status}
        onValueChange={(value) => setStatus(value as StatusFilter)}
      >
        <SelectTrigger className="w-[124px]" aria-label="按状态筛选">
          {/* 直接渲染文案而非 SelectValue：保证 SSR 首屏即显示「全部状态」，避免水合闪烁 */}
          <span>
            {STATUS_FILTER_OPTIONS.find((option) => option.value === status)?.label}
          </span>
        </SelectTrigger>
        <SelectContent>
          {STATUS_FILTER_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <span className="text-[13px] text-muted-foreground">
        共 {formatNumber(total)} 份文档
      </span>
    </div>
  );
}
