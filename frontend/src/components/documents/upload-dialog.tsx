"use client";

import { useRef, useState } from "react";
import { CloudUpload, FileText, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB, formatFileSize, validateFile } from "@/lib/file";
import { cn } from "@/lib/utils";
import { useDocumentStore } from "@/store/use-document-store";

export function UploadDialog() {
  const open = useDocumentStore((state) => state.uploadOpen);
  const setOpen = useDocumentStore((state) => state.setUploadOpen);
  const upload = useDocumentStore((state) => state.upload);
  const uploading = useDocumentStore((state) => state.uploading);

  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setFile(null);
    setError(null);
    setDragging(false);
  };

  const pick = (next: File | undefined) => {
    if (!next) return;
    const result = validateFile(next);
    if (!result.ok) {
      setError(result.reason);
      setFile(null);
      return;
    }
    setError(null);
    setFile(next);
  };

  const handleOpenChange = (next: boolean) => {
    if (uploading) return;
    setOpen(next);
    if (!next) reset();
  };

  const handleSubmit = async () => {
    if (!file) {
      setError("请先选择要上传的文件");
      return;
    }
    await upload(file);
    reset();
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>上传文档</DialogTitle>
          <DialogDescription>
            支持 PDF / DOCX / CSV，单文件不超过 {MAX_UPLOAD_SIZE_MB}MB。上传后立即返回
            task_id，解析在后台异步执行。
          </DialogDescription>
        </DialogHeader>

        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              inputRef.current?.click();
            }
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            pick(event.dataTransfer.files[0]);
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border px-6 py-10 text-center transition-colors",
            dragging ? "border-primary/60 bg-primary/[0.06]" : "hover:bg-white/[0.03]",
          )}
        >
          <CloudUpload className="size-6 text-muted-foreground" />
          <p className="text-[13px] text-foreground">
            点击选择文件，或拖拽到此处
          </p>
          <p className="text-xs text-muted-foreground">
            {ALLOWED_EXTENSIONS.join(" / ").toUpperCase()}
          </p>

          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.doc,.csv"
            className="hidden"
            onChange={(event) => pick(event.target.files?.[0])}
          />
        </div>

        {file ? (
          <div className="flex items-center gap-2.5 rounded-lg border border-border bg-white/[0.02] px-3 py-2.5">
            <FileText className="size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">
              {file.name}
            </span>
            <span className="shrink-0 text-[11px] text-muted-foreground">
              {formatFileSize(file.size)}
            </span>
          </div>
        ) : null}

        {error ? (
          <p className="text-xs text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => handleOpenChange(false)}
            disabled={uploading}
          >
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={uploading}>
            {uploading ? <Loader2 className="size-4 animate-spin" /> : null}
            {uploading ? "上传中…" : "开始上传"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
