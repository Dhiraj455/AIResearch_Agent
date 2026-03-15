"use client";

import type { ChatSummary } from "@/lib/api";

type Props = {
  chats: ChatSummary[];
  selectedChatId: string | null;
  onSelectChat: (id: string) => void;
  onNewResearch: () => void;
  onLogout: () => void;
  userEmail: string | null;
  isLoading: boolean;
  isChatsLoading?: boolean;
};

export function Sidebar({
  chats,
  selectedChatId,
  onSelectChat,
  onNewResearch,
  onLogout,
  userEmail,
  isLoading,
  isChatsLoading = false,
}: Props) {
  return (
    <aside className="flex h-full w-64 flex-col border-r border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-col gap-2 p-3">
        <button
          onClick={onNewResearch}
          disabled={isLoading}
          className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
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
        {userEmail && (
          <div className="flex flex-col gap-1 border-t border-zinc-200 pt-3 dark:border-zinc-700">
            <p className="truncate px-2 text-xs text-zinc-500" title={userEmail}>
              {userEmail}
            </p>
            <button
              onClick={onLogout}
              className="rounded-lg px-4 py-2 text-left text-sm text-zinc-600 transition hover:bg-zinc-200 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
      <div className="scrollbar-theme flex-1 overflow-y-auto px-2">
        <p className="mb-2 px-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
          Chats
        </p>
        {isChatsLoading && chats.length === 0 && (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
          </div>
        )}
        {!isChatsLoading && chats.length === 0 && (
          <p className="px-2 py-4 text-sm text-zinc-500">
            No chats yet. Start a research to create one.
          </p>
        )}
        {chats.map((chat) => (
          <button
            key={chat.id}
            onClick={() => onSelectChat(chat.id)}
            className={`mb-1 w-full rounded-lg px-3 py-2.5 text-left text-sm transition ${
              selectedChatId === chat.id
                ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100"
                : "hover:bg-zinc-200 dark:hover:bg-zinc-800"
            }`}
          >
            <span className="line-clamp-2">
              {chat.title || "Untitled chat"}
            </span>
            <span className="mt-0.5 block text-xs text-zinc-500">
              {chat.message_count} message{chat.message_count !== 1 ? "s" : ""}
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}
