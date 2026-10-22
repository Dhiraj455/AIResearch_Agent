"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Sidebar } from "@/components/Sidebar";
import { ChatView, type ActiveResearch, type RunTrace } from "@/components/ChatView";
import type { TimedEvent } from "@/components/ResearchSteps";
import { api, ResearchCancelledError, type Chat, type ChatSummary } from "@/lib/api";

function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

function MainApp() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [selectedChat, setSelectedChat] = useState<Chat | null>(null);
  const [isLoadingChats, setIsLoadingChats] = useState(true);
  const [isLoadingChat, setIsLoadingChat] = useState(false);
  const [research, setResearch] = useState<ActiveResearch | null>(null);
  const [traces, setTraces] = useState<Record<string, RunTrace>>({});
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const isBusy = research !== null || isSending;

  const fetchChats = useCallback(async () => {
    try {
      const list = await api.listChats();
      setChats(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load chats");
    } finally {
      setIsLoadingChats(false);
    }
  }, []);

  const fetchChat = useCallback(
    async (chatId: string) => {
      setIsLoadingChat(true);
      setError(null);
      try {
        const chat = await api.getChat(chatId);
        setSelectedChat(chat);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load chat");
      } finally {
        setIsLoadingChat(false);
      }
    },
    []
  );

  useEffect(() => {
    fetchChats();
  }, [fetchChats]);

  useEffect(() => {
    if (selectedChatId) {
      fetchChat(selectedChatId);
    } else {
      setSelectedChat(null);
    }
  }, [selectedChatId, fetchChat]);

  const handleNewResearch = () => {
    if (isBusy) return;
    setSelectedChatId(null);
    setSelectedChat(null);
    setError(null);
    setNotice(null);
  };

  const handleSelectChat = (id: string) => {
    if (isBusy) return;
    setSelectedChatId(id);
    setError(null);
    setNotice(null);
  };

  const runResearch = async (content: string) => {
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = Date.now();
    const collected: TimedEvent[] = [];
    setResearch({ prompt: content, events: [], startedAt, runId: null, stopping: false });

    try {
      const res = await api.runResearchStream(
        content,
        (ev) => {
          if (ev.type === "run_started") {
            const runId = String(ev.payload.run_id);
            setResearch((r) => (r ? { ...r, runId } : r));
            return;
          }
          const timed: TimedEvent = { ...ev, at: Date.now() };
          collected.push(timed);
          setResearch((r) => (r ? { ...r, events: [...r.events, timed] } : r));
        },
        controller.signal
      );
      const totalSeconds = Number(res.stats?.total_s) || (Date.now() - startedAt) / 1000;
      setTraces((t) => ({ ...t, [res.run_id]: { events: collected, totalSeconds } }));
      setSelectedChatId(res.chat_id);
      await fetchChats();
      await fetchChat(res.chat_id);
    } catch (e) {
      if (e instanceof ResearchCancelledError || isAbort(e)) {
        setNotice("Research stopped. Nothing was saved.");
      } else {
        setError(e instanceof Error ? e.message : "Research failed");
      }
    } finally {
      abortRef.current = null;
      setResearch(null);
    }
  };

  const handleStop = async () => {
    if (!research || research.stopping) return;
    setResearch((r) => (r ? { ...r, stopping: true } : r));
    try {
      if (research.runId) await api.cancelResearch(research.runId);
    } catch {
      // The abort below still frees the UI; the server stops on its next cancellation check.
    }
    abortRef.current?.abort();
  };

  const handleSendMessage = async (content: string) => {
    if (isBusy) return;
    setError(null);
    setNotice(null);

    if (!selectedChatId) {
      await runResearch(content);
      return;
    }

    setIsSending(true);
    setSelectedChat((prev) =>
      prev
        ? {
            ...prev,
            messages: [
              ...prev.messages,
              { role: "user", content, run_id: null, created_at: new Date().toISOString() },
            ],
          }
        : prev
    );
    try {
      const res = await api.sendMessage(selectedChatId, content, false);
      setSelectedChat((prev) =>
        prev
          ? {
              ...prev,
              messages: [
                ...prev.messages,
                {
                  role: "assistant",
                  content: res.message.content,
                  run_id: res.message.run_id,
                  created_at: new Date().toISOString(),
                },
              ],
            }
          : prev
      );
      await fetchChats();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send message");
    } finally {
      setIsSending(false);
    }
  };

  const title = selectedChat?.title ?? research?.prompt;

  return (
    <div className="relative flex h-screen items-stretch justify-center p-3 sm:p-4">
      <div className="flex h-full w-full max-w-[1680px] overflow-hidden rounded-[1.75rem] border border-white/60 bg-white/70 shadow-[0_20px_70px_rgba(31,43,94,0.18)] backdrop-blur-xl">
        <Sidebar
          chats={chats}
          selectedChatId={selectedChatId}
          onSelectChat={handleSelectChat}
          onNewResearch={handleNewResearch}
          locked={isBusy}
          isChatsLoading={isLoadingChats}
        />
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-white/30">
          <header className="flex items-center justify-between gap-4 border-b border-slate-200/65 bg-white/45 px-6 py-4 lg:px-10">
            <div className="min-w-0">
              <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-slate-500">
                Daily Research Workspace
              </p>
              <h1 className="truncate text-xl font-semibold text-slate-900">
                AI Research Agent
                {title ? (
                  <span className="ml-2 text-base font-medium text-slate-500">- {title}</span>
                ) : null}
              </h1>
            </div>
            <button className="shrink-0 rounded-full bg-[#141735] px-4 py-2 text-xs font-semibold text-white shadow-sm">
              Research Pro
            </button>
          </header>
          {error && (
            <div className="mx-6 mt-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800 lg:mx-10">
              {error}
            </div>
          )}
          {notice && (
            <div className="mx-6 mt-3 flex items-center justify-between rounded-xl border border-slate-200 bg-white/80 px-4 py-2 text-sm text-slate-700 lg:mx-10">
              {notice}
              <button onClick={() => setNotice(null)} className="text-xs font-medium text-slate-500 hover:text-slate-800">
                Dismiss
              </button>
            </div>
          )}
          <ChatView
            chat={selectedChat}
            research={research}
            traces={traces}
            onSendMessage={handleSendMessage}
            onStop={handleStop}
            isLoading={isLoadingChat && !!selectedChatId}
            isSending={isSending}
          />
        </main>
      </div>
    </div>
  );
}

export default function Home() {
  return <MainApp />;
}
