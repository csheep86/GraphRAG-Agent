import { create } from "zustand";

import { ApiError } from "@/api/client";
import { getDocumentChunk } from "@/api/documents";
import { listMessages, listSessions, sendQuestion } from "@/api/qa";
import type { ChatMessage, ChatSession, Citation } from "@/types/mock";
import type { components } from "@/types/api";

type DocumentChunkResponse = components["schemas"]["DocumentChunkResponse"];

/**
 * 批次 C 原文抽屉的错误态：保留 HTTP 状态与后端 `detail.reason`，
 * 便于 UI 区分「跨租户 403 / 片段缺失 404 / 其它」——**不**降级为空原文。
 */
export type ChunkViewerError = {
  status: number;
  message: string;
  reason: string | null;
};

/** 稳定的空数组引用，避免 selector 每次返回新引用导致无限重渲染 */
const EMPTY_MESSAGES: ChatMessage[] = [];

type ChatStore = {
  sessions: ChatSession[];
  messagesBySession: Record<string, ChatMessage[]>;
  activeSessionId: string | null;

  sessionsLoading: boolean;
  messagesLoading: boolean;
  sending: boolean;

  /** 当前在右侧「引用证据」面板中聚焦的 assistant 消息 */
  evidenceMessageId: string | null;

  /* ---- 批次 C：引用溯源抽屉 ---- */
  /** 抽屉聚焦的引用条目；非 null 即抽屉打开 */
  chunkCitation: Citation | null;
  /** 回查到的原文片段全文（失败时为 null） */
  chunk: DocumentChunkResponse | null;
  chunkLoading: boolean;
  chunkError: ChunkViewerError | null;

  initialize: () => Promise<void>;
  selectSession: (sessionId: string) => Promise<void>;
  createSession: () => void;
  send: (question: string) => Promise<void>;
  selectEvidence: (messageId: string) => void;
  openChunk: (citation: Citation) => Promise<void>;
  closeChunk: () => void;
};

function createId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function nowStamp(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/** 知识问答（p03）数据源：会话列表 + 各会话消息 */
export const useChatStore = create<ChatStore>((set, get) => ({
  sessions: [],
  messagesBySession: {},
  activeSessionId: null,

  sessionsLoading: true,
  messagesLoading: false,
  sending: false,

  evidenceMessageId: null,

  chunkCitation: null,
  chunk: null,
  chunkLoading: false,
  chunkError: null,

  initialize: async () => {
    if (get().sessions.length > 0) return;

    set({ sessionsLoading: true });
    const sessions = await listSessions();
    set({
      sessions,
      sessionsLoading: false,
      activeSessionId: sessions[0]?.id ?? null,
    });

    const first = sessions[0];
    if (first) {
      set({ messagesLoading: true });
      const messages = await listMessages(first.id);
      set((state) => ({
        messagesBySession: { ...state.messagesBySession, [first.id]: messages },
        messagesLoading: false,
      }));
    }
  },

  selectSession: async (sessionId) => {
    if (get().activeSessionId === sessionId) return;

    set({ activeSessionId: sessionId, evidenceMessageId: null });

    if (get().messagesBySession[sessionId]) return;

    set({ messagesLoading: true });
    const messages = await listMessages(sessionId);
    set((state) => ({
      messagesBySession: { ...state.messagesBySession, [sessionId]: messages },
      messagesLoading: false,
    }));
  },

  createSession: () => {
    const sessionId = createId("session");
    const session: ChatSession = {
      id: sessionId,
      title: "新的会话",
      updated_at_label: "刚刚",
      doc_count: 0,
    };

    set((state) => ({
      sessions: [session, ...state.sessions],
      activeSessionId: sessionId,
      evidenceMessageId: null,
      messagesBySession: { ...state.messagesBySession, [sessionId]: [] },
    }));
  },

  send: async (question) => {
    const trimmed = question.trim();
    if (trimmed.length === 0 || get().sending) return;

    // 先确定不可变的会话 id：闭包中引用 `let` 变量会丢失类型收窄
    const existingSessionId = get().activeSessionId;
    const sessionId: string = existingSessionId ?? createId("session");

    if (!existingSessionId) {
      const created: ChatSession = {
        id: sessionId,
        title: trimmed.slice(0, 14),
        updated_at_label: "刚刚",
        doc_count: 0,
      };
      set((state) => ({
        sessions: [created, ...state.sessions],
        activeSessionId: sessionId,
        messagesBySession: { ...state.messagesBySession, [sessionId]: [] },
      }));
    }

    const userMessage: ChatMessage = {
      id: createId("msg"),
      role: "user",
      content: trimmed,
      created_at: nowStamp(),
    };

    set((state) => ({
      sending: true,
      messagesBySession: {
        ...state.messagesBySession,
        [sessionId]: [
          ...(state.messagesBySession[sessionId] ?? []),
          userMessage,
        ],
      },
    }));

    try {
      const answer = await sendQuestion({
        session_id: sessionId,
        question: trimmed,
      });

      set((state) => ({
        sending: false,
        evidenceMessageId: answer.id,
        messagesBySession: {
          ...state.messagesBySession,
          [sessionId]: [...(state.messagesBySession[sessionId] ?? []), answer],
        },
      }));
    } catch (error) {
      const failure: ChatMessage = {
        id: createId("msg"),
        role: "assistant",
        content: `检索失败：${error instanceof Error ? error.message : "未知错误"}。本次不给出结论，请稍后重试。`,
        created_at: nowStamp(),
        refused: true,
        confidence: "low",
        citations: [],
        kg_nodes: [],
        kg_relations: [],
        token_usage: null,
      };

      set((state) => ({
        sending: false,
        messagesBySession: {
          ...state.messagesBySession,
          [sessionId]: [...(state.messagesBySession[sessionId] ?? []), failure],
        },
      }));
    }
  },

  selectEvidence: (messageId) => set({ evidenceMessageId: messageId }),

  /**
   * 批次 C：点击引用标注 → 回查该 `chunk_id` 的原文全文。
   * 失败时保留状态与 `reason`（403 跨租户 / 404 片段缺失），**不**写入占位文本。
   */
  openChunk: async (citation) => {
    set({
      chunkCitation: citation,
      chunk: null,
      chunkError: null,
      chunkLoading: true,
    });

    try {
      const chunk = await getDocumentChunk(citation.doc_id, citation.chunk_id);
      set({ chunk, chunkLoading: false });
    } catch (error) {
      const apiError = error instanceof ApiError ? error : null;
      const reason = apiError?.detail?.["reason"];

      set({
        chunk: null,
        chunkLoading: false,
        chunkError: {
          status: apiError?.status ?? 0,
          message:
            apiError?.message ??
            (error instanceof Error ? error.message : "未知错误"),
          reason: typeof reason === "string" ? reason : null,
        },
      });
    }
  },

  closeChunk: () =>
    set({
      chunkCitation: null,
      chunk: null,
      chunkLoading: false,
      chunkError: null,
    }),
}));

/* ------------------------------ 派生选择器 ------------------------------ */

export function selectActiveMessages(state: ChatStore): ChatMessage[] {
  const sessionId = state.activeSessionId;
  if (!sessionId) return EMPTY_MESSAGES;
  return state.messagesBySession[sessionId] ?? EMPTY_MESSAGES;
}

export function selectActiveSession(state: ChatStore): ChatSession | null {
  const sessionId = state.activeSessionId;
  if (!sessionId) return null;
  return state.sessions.find((session) => session.id === sessionId) ?? null;
}

/**
 * 右侧「引用证据」面板的数据源：
 * 优先取用户手动聚焦的消息，否则回退到最近一条带证据的 assistant 消息。
 */
export function selectEvidenceMessage(state: ChatStore): ChatMessage | null {
  const messages = selectActiveMessages(state);

  if (state.evidenceMessageId) {
    const hit = messages.find(
      (message) => message.id === state.evidenceMessageId,
    );
    if (hit) return hit;
  }

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "assistant") continue;
    const hasEvidence =
      (message.kg_nodes?.length ?? 0) > 0 ||
      (message.kg_relations?.length ?? 0) > 0 ||
      (message.citations?.length ?? 0) > 0;
    if (hasEvidence) return message;
  }

  return null;
}
