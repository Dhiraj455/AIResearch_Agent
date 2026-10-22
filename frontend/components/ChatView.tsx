"use client";

import { useRef, useEffect } from "react";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { ResearchSteps, type TimedEvent } from "./ResearchSteps";
import type { Chat, Message } from "@/lib/api";

/** A research run in progress (before its chat exists). */
export type ActiveResearch = {
  prompt: string;
  events: TimedEvent[];
  startedAt: number;
  runId: string | null;
  stopping: boolean;
};

/** Steps of a run finished in this session, so they show without refetching. */
export type RunTrace = { events: TimedEvent[]; totalSeconds: number };

type Props = {
  chat: Chat | null;
  research: ActiveResearch | null;
  traces: Record<string, RunTrace>;
  onSendMessage: (content: string) => void;
  onStop: () => void;
  isLoading: boolean;
  isSending: boolean;
};

export function ChatView({
  chat,
  research,
  traces,
  onSendMessage,
  onStop,
  isLoading,
  isSending,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const messages = chat?.messages ?? [];
  const hasReport = messages.some((m) => m.role === "assistant" && m.run_id);
  const isEmpty = messages.length === 0 && !research;

  // Keep the newest message / step in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages.length, research?.events.length, isSending]);

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent">
      <div
        ref={scrollRef}
        className="scrollbar-theme flex-1 overflow-y-auto bg-transparent px-6 py-6 lg:px-10"
      >
        {isEmpty && (
          <div className="flex h-full flex-col justify-center gap-8 pb-10">
            <div className="mx-auto max-w-3xl text-center">
              <h2 className="text-4xl font-semibold leading-tight tracking-tight text-slate-900 lg:text-5xl">
                Hi there, ready to build
                <br />
                research that holds up?
              </h2>
              <p className="mt-4 text-base text-slate-500">
                Every claim in the report is checked against its source by three independent models.
              </p>
            </div>
            <div className="mx-auto grid w-full max-w-5xl grid-cols-1 gap-4 md:grid-cols-3">
              {[
                "Create a plan, angles, and search strategy for your topic.",
                "Collect and compare claims from multiple sources with citations.",
                "Verify report quality for missing angles and weak evidence.",
              ].map((text, i) => (
                <div
                  key={text}
                  className="rounded-3xl border border-white/70 bg-white/75 p-6 text-left shadow-sm"
                >
                  <p className="text-sm font-medium text-slate-800">{text}</p>
                  <p className="mt-6 text-xs text-slate-500">
                    {i === 0 ? "Fast start" : i === 1 ? "Evidence flow" : "Verification"}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
        {!isEmpty && (
          <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
            {messages.map((msg: Message, i: number) => (
              <MessageBubble
                key={i}
                role={msg.role}
                content={msg.content}
                runId={msg.run_id}
                trace={msg.run_id ? traces[msg.run_id] : undefined}
              />
            ))}
            {research && (
              <>
                <MessageBubble role="user" content={research.prompt} />
                <ResearchSteps
                  events={research.events}
                  status={research.stopping ? "stopping" : "running"}
                  startedAt={research.startedAt}
                />
              </>
            )}
            {isSending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1.5 rounded-2xl border border-white/70 bg-white/80 px-4 py-3 shadow-sm">
                  <div className="h-2 w-2 animate-bounce rounded-full bg-indigo-500 [animation-delay:0ms]" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-indigo-500 [animation-delay:150ms]" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-indigo-500 [animation-delay:300ms]" />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      <ChatInput
        placeholder={
          research
            ? "Research in progress…"
            : hasReport
              ? "Ask a follow-up question..."
              : "What would you like to research?"
        }
        onSubmit={onSendMessage}
        onStop={onStop}
        isRunning={research !== null}
        isStopping={research?.stopping ?? false}
        disabled={isLoading || isSending}
      />
    </div>
  );
}
