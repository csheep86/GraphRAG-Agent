import { create } from "zustand";

import { askPolicy } from "@/api/policy-qa";
import { ApiError } from "@/api/client";
import type { components } from "@/types/api";

type AgentQueryResponse = components["schemas"]["AgentQueryResponse"];

/** 演示预设问题（**都落在语料里**，避免问空：名字取自 `demo/attendance/`） */
export const PRESET_QUESTIONS: readonly string[] = [
  "李静的月加班超过上限了吗？",
  "张伟在武汉光谷出差期间的缺卡该怎么处理？",
];

type PolicyQaStore = {
  question: string;
  asking: boolean;
  error: string | null;
  result: AgentQueryResponse | null;
  ask: (question: string) => Promise<void>;
  setQuestion: (question: string) => void;
};

/**
 * 政策问答子页数据源（批次 E2）。
 *
 * **问答 unlike 合规扫描不做轮询**：`/agent/query` 是同步 POST，一次往返出结论。
 * 失败也不保留上一次结果——`result` 置空，避免屏幕上留着上一个问题的答案
 * 冒充当前问题的结论（那是另一种「答非所问」）。
 */
export const usePolicyQaStore = create<PolicyQaStore>((set) => ({
  question: PRESET_QUESTIONS[0],
  asking: false,
  error: null,
  result: null,

  setQuestion: (question) => set({ question }),

  ask: async (question) => {
    set({ asking: true, error: null, result: null, question });
    try {
      const result = await askPolicy(question);
      set({ result, asking: false });
    } catch (error) {
      set({
        asking: false,
        error:
          error instanceof ApiError
            ? `${error.code}：${error.message}`
            : error instanceof Error
              ? error.message
              : "问答失败",
      });
    }
  },
}));
