import { clearToken } from "./auth-store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("ai-research-token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function handleUnauthorized(): void {
  clearToken();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("auth:unauthorized"));
  }
}

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
      ...getAuthHeaders(),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 401) handleUnauthorized();
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
      ...getAuthHeaders(),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 401) handleUnauthorized();
    const err = await res.text();
    throw new Error(err || `API error ${res.status}`);
  }
  return res;
}

export const api = {
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

  getReport: (runId: string) =>
    fetchApiNoJson(`/runs/${runId}/report`).then((r) => r.text()),
};
