"use client";

import { useRef, useEffect } from "react";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import type { Chat, Message } from "@/lib/api";

type Props = {
  chat: Chat | null;
  onSendMessage: (content: string) => void;
  isLoading: boolean;
  isResearching: boolean;
};

export function ChatView({
  chat,
  onSendMessage,
  isLoading,
  isResearching,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [chat?.messages?.length]);

  const messages = chat?.messages ?? [];
  const hasReport = messages.some((m) => m.role === "assistant" && m.run_id);

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-white dark:bg-zinc-950">
      <div
        ref={scrollRef}
        className="scrollbar-theme flex-1 overflow-y-auto bg-white p-6 dark:bg-zinc-950"
      >
        {messages.length === 0 && !isResearching && (
          <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
            <div className="rounded-2xl bg-emerald-100/50 p-8 dark:bg-emerald-900/20">
              <svg
                className="mx-auto mb-4 h-16 w-16 text-emerald-600 dark:text-emerald-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <h2 className="mb-2 text-xl font-semibold">AI Research Agent</h2>
              <p className="max-w-sm text-zinc-600 dark:text-zinc-400">
                Enter a research question below. I&apos;ll search the web, gather
                sources, and create a grounded report with citations.
              </p>
            </div>
          </div>
        )}
        {isResearching && messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
            <p className="text-zinc-500">
              Research in progress... This may take 5–10 minutes.
            </p>
            <p className="text-sm text-zinc-400">
              Searching, fetching sources, and synthesizing a report.
            </p>
          </div>
        )}
        {messages.length > 0 && (
          <div className="mx-auto flex max-w-3xl flex-col gap-6">
            {messages.map((msg: Message, i: number) => (
              <MessageBubble
                key={i}
                role={msg.role}
                content={msg.content}
                runId={msg.run_id}
              />
            ))}
            {isResearching && messages[messages.length - 1]?.role === "user" && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-2xl bg-zinc-100 px-4 py-3 dark:bg-zinc-800">
                  <div className="h-2 w-2 animate-bounce rounded-full bg-emerald-500 [animation-delay:0ms]" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-emerald-500 [animation-delay:150ms]" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-emerald-500 [animation-delay:300ms]" />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      <ChatInput
        placeholder={
          hasReport
            ? "Ask a follow-up question..."
            : "What would you like to research?"
        }
        onSubmit={onSendMessage}
        disabled={isLoading || isResearching}
      />
    </div>
  );
}
