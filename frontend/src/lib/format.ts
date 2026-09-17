/**
 * 格式化工具。
 *
 * 刻意不使用 `Intl` / `toLocaleString`：SSR 与 CSR 的 ICU 数据或时区不一致时
 * 会造成 hydration 不匹配。这里全部用纯字符串运算，输出可预测。
 */

/** 千分位数字；空值输出 `--`（对齐 p02 表格中非完成态实体数的展示） */
export function formatNumber(
  value: number | null | undefined,
  fractionDigits = 0,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  if (!Number.isFinite(value)) return "--";

  const fixed = value.toFixed(fractionDigits);
  const [integer, fraction] = fixed.split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return fraction ? `${grouped}.${fraction}` : grouped;
}

/** 百分比：97.8 -> "97.8%" */
export function formatPercent(
  value: number | null | undefined,
  fractionDigits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${formatNumber(value, fractionDigits)}%`;
}

/** 带符号的环比：12.6 -> "+12.6%"；-3.2 -> "-3.2%" */
export function formatDelta(value: number, fractionDigits = 1): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value, fractionDigits)}%`;
}

/** ISO 8601 -> "2026-09-17 10:42" */
export function formatDateTime(value: string): string {
  const [date, time = ""] = value.split("T");
  return `${date} ${time.slice(0, 5)}`.trim();
}

/** ISO 8601 -> "10:42" */
export function formatTime(value: string): string {
  return value.split("T")[1]?.slice(0, 5) ?? "";
}

/** ISO 8601 -> "2026-09-17" */
export function formatDate(value: string): string {
  return value.split("T")[0] ?? value;
}
