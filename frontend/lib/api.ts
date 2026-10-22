const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ChatSummary = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type Message = {
  role: "user" | "assistant";
  content: string;
  run_id: string | null;
  created_at: string;
};

export type Chat = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages: Message[];
  last_run_id: string | null;
};

export type RunResponse = {
  run_id: string;
  chat_id: string;
  status: string;
  events: number;
};

export type SendMessageResponse = {
  message: {
    role: string;
    content: string;
    run_id: string | null;
  };
};

async function fetchApi<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `API error ${res.status}`);
  }
  return res.json();
}

async function fetchApiNoJson(
  path: string,
  options?: RequestInit
): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `API error ${res.status}`);
  }
  return res;
}

export type ResearchEvent = {
  type: string;
  payload: Record<string, unknown>;
};

export type ResearchResult = {
  run_id: string;
  chat_id: string;
  stats?: Record<string, unknown>;
};

export type RunEvents = {
  events: ResearchEvent[];
  stats: Record<string, unknown>;
};

/** Thrown by runResearchStream when the run was stopped via cancelResearch. */
export class ResearchCancelledError extends Error {
  constructor() {
    super("Research stopped");
    this.name = "ResearchCancelledError";
  }
}

/**
 * POST /run/stream and read SSE frames until `done`, `cancelled`, or `error` arrives.
 * Every other event (including `run_started`, which carries the run_id) goes to onEvent.
 */
async function runResearchStream(
  prompt: string,
  onEvent: (ev: ResearchEvent) => void,
  signal?: AbortSignal
): Promise<ResearchResult> {
  const res = await fetch(`${API_BASE}/run/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.text();
    throw new Error(err || `API error ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (!data) continue; // keepalive comment
      const ev = JSON.parse(data) as ResearchEvent;
      if (ev.type === "error") {
        throw new Error(String(ev.payload.detail ?? "Research failed"));
      }
      if (ev.type === "cancelled") {
        throw new ResearchCancelledError();
      }
      if (ev.type === "done") {
        return ev.payload as ResearchResult;
      }
      onEvent(ev);
    }
  }
  throw new Error("Research stream ended unexpectedly");
}

export const api = {
  runResearchStream,

  runResearch: (prompt: string) =>
    fetchApi<RunResponse>("/run", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),

  listChats: () => fetchApi<ChatSummary[]>("/chats"),

  getChat: (chatId: string) => fetchApi<Chat>(`/chats/${chatId}`),

  sendMessage: (chatId: string, content: string, research = false) =>
    fetchApi<SendMessageResponse>(`/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, research }),
    }),

  createChat: () =>
    fetchApi<{ chat_id: string }>("/chats", { method: "POST" }),

  cancelResearch: (runId: string) =>
    fetchApi<{ status: string }>(`/runs/${runId}/cancel`, { method: "POST" }),

  getRunEvents: (runId: string) => fetchApi<RunEvents>(`/runs/${runId}/events`),

  getReport: (runId: string) =>
    fetchApiNoJson(`/runs/${runId}/report`).then((r) => r.text()),
};
