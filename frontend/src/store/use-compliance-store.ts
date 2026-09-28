import { create } from "zustand";

import { scanCompliance } from "@/api/compliance";
import { ApiError } from "@/api/client";
import { COMPLIANCE_ERROR_MESSAGE } from "@/lib/compliance";
import type {
  ComplianceLevelFilter,
  ComplianceRuleFilter,
} from "@/lib/compliance";
import type { components } from "@/types/api";

type ComplianceScanResponse = components["schemas"]["ComplianceScanResponse"];
type ComplianceFinding = components["schemas"]["ComplianceFinding"];

type ComplianceStore = {
  /** 最近一次扫描结果；从未成功过为 `null` */
  data: ComplianceScanResponse | null;
  loading: boolean;
  initialized: boolean;
  error: string | null;

  /** 观察日：空串 = 交给后端取数据窗口末日（不传该参数） */
  asOf: string;
  ruleFilter: ComplianceRuleFilter;
  levelFilter: ComplianceLevelFilter;

  /** 详情抽屉当前风险 */
  detail: ComplianceFinding | null;

  load: () => Promise<void>;
  setAsOf: (value: string) => void;
  setRuleFilter: (value: ComplianceRuleFilter) => void;
  setLevelFilter: (value: ComplianceLevelFilter) => void;
  openDetail: (finding: ComplianceFinding) => void;
  closeDetail: () => void;
};

/**
 * 合规预警页数据源（Sprint 9.5 批次 E4）。
 *
 * **筛选走后端参数**而非前端内存过滤：契约支持 `rule` / `level` / `as_of`，
 * 用前端过滤等于把后端能力闲置；代价是每次筛选一次请求（秒级，纯读）。
 * 注意 `rule_values[]` 后端始终全量返回——**判据不因过滤而消失**，
 * 这是本页可核查性的根基，别在前端把它也过滤掉。
 */
export const useComplianceStore = create<ComplianceStore>((set, get) => ({
  data: null,
  loading: true,
  initialized: false,
  error: null,

  asOf: "",
  ruleFilter: "all",
  levelFilter: "all",

  detail: null,

  load: async () => {
    set({ loading: true, error: null });
    const { asOf, ruleFilter, levelFilter } = get();
    try {
      const data = await scanCompliance({
        as_of: asOf || undefined,
        rule: ruleFilter === "all" ? undefined : ruleFilter,
        level: levelFilter === "all" ? undefined : levelFilter,
      });
      set({ data, loading: false, initialized: true });
    } catch (error) {
      // 409 的两个业务码有专门文案；其余回落到后端 message（含 trace_id 可查）
      const message =
        error instanceof ApiError
          ? (COMPLIANCE_ERROR_MESSAGE[error.code] ?? error.message)
          : error instanceof Error
            ? error.message
            : "合规扫描失败";
      set({ loading: false, initialized: true, error: message });
    }
  },

  setAsOf: (asOf) => set({ asOf }),
  setRuleFilter: (ruleFilter) => set({ ruleFilter }),
  setLevelFilter: (levelFilter) => set({ levelFilter }),

  openDetail: (detail) => set({ detail }),
  closeDetail: () => set({ detail: null }),
}));
