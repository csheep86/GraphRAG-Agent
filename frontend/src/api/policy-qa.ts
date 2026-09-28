import { delay, request, shouldMock } from "./client";
import { MOCK_POLICY_QA } from "./mock/policy-qa";
import type { components } from "@/types/api";

type AgentQueryResponse = components["schemas"]["AgentQueryResponse"];

const PATH = "/api/v1/agent/query";

/**
 * 政策问答（Sprint 9.5 批次 E2 → 后端批次 D1）。
 *
 * ✅ 契约已实装：`POST /api/v1/agent/query`，批次 D1 起响应新增 `reasoning_path`
 * （多跳推理路径）。LLM 出措辞、规则引擎出数值，**路径由图谱确定性构造**。
 *
 * **可空语义**（前端必须区分，二者含义相反）：
 * - `null` ⇒ 拒答分支**未产出**路径（路径是证据链，拒答时不给，避免误读成有据可依）；
 * - `[]` ⇒ 检索了但**零命中**（问句没锚到实体 / 锚点走不到条款与事实）。
 */
export async function askPolicy(question: string): Promise<AgentQueryResponse> {
  if (shouldMock(PATH)) {
    await delay(700);
    return { ...MOCK_POLICY_QA, trace_id: MOCK_POLICY_QA.trace_id };
  }

  return request<AgentQueryResponse>(PATH, {
    method: "POST",
    body: JSON.stringify({ question, scope: "cross_doc" }),
  });
}
