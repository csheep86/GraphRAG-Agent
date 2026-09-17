import type { DocumentFileType } from "@/types/mock";

/** 上传大小上限（对齐 M1 硬约束 H2：单文件 ≤ 100MB） */
export const MAX_UPLOAD_SIZE_MB = 100;

/** MIME / 扩展名白名单（对齐 M1 硬约束 H2：pdf / docx / csv） */
export const ALLOWED_EXTENSIONS = ["pdf", "docx", "doc", "csv"] as const;

/** 由文件名推断展示用类型 */
export function inferFileType(filename: string): DocumentFileType {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return "PDF";
  if (ext === "docx" || ext === "doc") return "DOCX";
  return "CSV";
}

export type FileValidationResult = { ok: true } | { ok: false; reason: string };

/** 前端预校验，避免明显不合规的文件打到后端（后端仍会二次校验） */
export function validateFile(file: File): FileValidationResult {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!ALLOWED_EXTENSIONS.includes(ext as (typeof ALLOWED_EXTENSIONS)[number])) {
    return { ok: false, reason: "仅支持 PDF / DOCX / CSV 格式" };
  }

  const sizeMb = file.size / 1024 / 1024;
  if (sizeMb > MAX_UPLOAD_SIZE_MB) {
    return { ok: false, reason: `文件大小超过 ${MAX_UPLOAD_SIZE_MB}MB 上限` };
  }

  return { ok: true };
}

/** 人类可读体积 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
