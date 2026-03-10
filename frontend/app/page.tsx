"use client";

import { useState, useEffect, useCallback } from "react";
import { Sidebar } from "@/components/Sidebar";
import { ChatView } from "@/components/ChatView";
import { ResearchOverlay } from "@/components/ResearchOverlay";
import { api, type Chat, type ChatSummary } from "@/lib/api";

export default function Home() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [selectedChat, setSelectedChat] = useState<Chat | null>(null);
  const [isLoadingChats, setIsLoadingChats] = useState(true);
  const [isLoadingChat, setIsLoadingChat] = useState(false);
  const [isResearching, setIsResearching] = useState(false);
  const [researchPrompt, setResearchPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);

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
    setSelectedChatId(null);
    setSelectedChat(null);
    setError(null);
  };

  const handleSelectChat = (id: string) => {
    setSelectedChatId(id);
    setError(null);
  };

  const handleSendMessage = async (content: string) => {
    setError(null);

    if (!selectedChatId) {
      // Research mode: POST /run
      setIsResearching(true);
      setResearchPrompt(content);
      try {
        const res = await api.runResearch(content);
        setSelectedChatId(res.chat_id);
        await fetchChats();
        await fetchChat(res.chat_id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Research failed");
      } finally {
        setIsResearching(false);
        setResearchPrompt("");
      }
      return;
    }

    // Chat mode: follow-up
    try {
      const res = await api.sendMessage(selectedChatId, content, false);
      setSelectedChat((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          messages: [
            ...prev.messages,
            { role: "user", content, run_id: null, created_at: new Date().toISOString() },
            {
              role: "assistant",
              content: res.message.content,
              run_id: res.message.run_id,
              created_at: new Date().toISOString(),
            },
          ],
        };
      });
      await fetchChats();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send message");
    }
  };

  return (
    <div className="flex h-screen bg-white dark:bg-zinc-950">
      <Sidebar
        chats={chats}
        selectedChatId={selectedChatId}
        onSelectChat={handleSelectChat}
        onNewResearch={handleNewResearch}
        isLoading={isResearching}
        isChatsLoading={isLoadingChats}
      />
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white dark:bg-zinc-950">
        <header className="flex items-center gap-3 border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-950">
          <h1 className="text-lg font-semibold">AI Research Agent</h1>
          {selectedChat?.title && (
            <span className="text-sm text-zinc-500">— {selectedChat.title}</span>
          )}
        </header>
        {error && (
          <div className="mx-4 mt-2 rounded-lg bg-red-100 px-4 py-2 text-sm text-red-800 dark:bg-red-900/30 dark:text-red-200">
            {error}
          </div>
        )}
        <ChatView
          chat={selectedChat}
          onSendMessage={handleSendMessage}
          isLoading={isLoadingChat && !!selectedChatId}
          isResearching={isResearching && !selectedChatId}
        />
      </main>
      <ResearchOverlay show={isResearching} prompt={researchPrompt} />
    </div>
  );
}
