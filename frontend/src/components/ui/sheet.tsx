"use client";

import * as SheetPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * 右侧滑出抽屉（Sprint 6 批次 C：引用溯源）。
 *
 * `ui/dialog.tsx` 是**居中**对话框，溯源需要贴右侧、不遮挡左侧对话区，
 * 故另开本组件——仍复用 Radix Dialog 的无障碍语义（Esc 关闭 / 焦点陷阱 /
 * 遮罩点击关闭），不引入第二个弹层库。
 */
export const Sheet = SheetPrimitive.Root;
export const SheetClose = SheetPrimitive.Close;
export const SheetTitle = SheetPrimitive.Title;
export const SheetDescription = SheetPrimitive.Description;

export function SheetContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof SheetPrimitive.Content>) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-black/55" />
      <SheetPrimitive.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex w-[440px] max-w-[92vw] flex-col border-l border-border bg-background shadow-2xl outline-none",
          className,
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close
          aria-label="关闭"
          className="absolute right-3 top-3 flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
        >
          <X className="size-4" />
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}
