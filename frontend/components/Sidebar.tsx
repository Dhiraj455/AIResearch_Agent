"use client";

import type { ChatSummary } from "@/lib/api";

type Props = {
  chats: ChatSummary[];
  selectedChatId: string | null;
  onSelectChat: (id: string) => void;
  onNewResearch: () => void;
  /** True while research or a follow-up is running: switching chats is blocked. */
  locked: boolean;
  isChatsLoading?: boolean;
};

export function Sidebar({
  chats,
  selectedChatId,
  onSelectChat,
  onNewResearch,
  locked,
  isChatsLoading = false,
}: Props) {
  return (
    <aside className="flex h-full w-72 flex-col border-r border-slate-200/70 bg-white/55">
      <div className="flex flex-col gap-2 p-4">
        <div className="mb-1 flex items-center gap-2 rounded-full bg-white/80 px-3 py-2 text-xs text-slate-600 shadow-sm">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[#1e2346] text-[10px] font-semibold text-white">
            AI
          </span>
          Assistant v2.6
        </div>
        <button
          onClick={onNewResearch}
          disabled={locked}
          title={locked ? "Wait for the current research to finish, or stop it" : undefined}
          className="flex items-center gap-2 rounded-full bg-[#171a3a] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#0f1230] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <svg
            className="h-4 w-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
          New research
        </button>
        {locked && (
          <p className="flex items-center gap-2 px-2 text-xs text-slate-500">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />
            Working… chats are locked until it finishes
          </p>
        )}
      </div>
      <div className="scrollbar-theme flex-1 overflow-y-auto px-3 pb-3">
        <p className="mb-2 px-2 text-xs font-medium uppercase tracking-wider text-slate-500">
          Chats
        </p>
        {isChatsLoading && chats.length === 0 && (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-[#323a8a] border-t-transparent" />
          </div>
        )}
        {!isChatsLoading && chats.length === 0 && (
          <p className="rounded-2xl bg-white/70 px-3 py-4 text-sm text-slate-500">
            No chats yet. Start a research to create one.
          </p>
        )}
        {chats.map((chat) => (
          <button
            key={chat.id}
            onClick={() => onSelectChat(chat.id)}
            disabled={locked}
            className={`mb-1.5 w-full rounded-2xl border px-3 py-3 text-left text-sm transition disabled:cursor-not-allowed ${
              selectedChatId === chat.id
                ? "border-indigo-200 bg-indigo-50/85 text-indigo-950"
                : "border-white/50 bg-white/60 text-slate-700 hover:bg-white disabled:opacity-60 disabled:hover:bg-white/60"
            }`}
          >
            <span className="line-clamp-2">
              {chat.title || "Untitled chat"}
            </span>
            <span className="mt-0.5 block text-xs text-slate-500">
              {chat.message_count} message{chat.message_count !== 1 ? "s" : ""}
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}
