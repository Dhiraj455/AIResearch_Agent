"use client";

import { useRef, useEffect } from "react";

type Props = {
  placeholder: string;
  onSubmit: (value: string) => void;
  onStop?: () => void;
  isRunning?: boolean;
  isStopping?: boolean;
  disabled?: boolean;
};

export function ChatInput({
  placeholder,
  onSubmit,
  onStop,
  isRunning = false,
  isStopping = false,
  disabled = false,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const inputDisabled = disabled || isRunning;

  const handleSubmit = () => {
    const el = textareaRef.current;
    if (!el || inputDisabled) return;
    const value = el.value.trim();
    if (!value) return;
    onSubmit(value);
    el.value = "";
    el.style.height = "auto";
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const resize = () => {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    };
    el.addEventListener("input", resize);
    return () => el.removeEventListener("input", resize);
  }, []);

  return (
    <div className="border-t border-slate-200/65 bg-white/35 px-6 py-4 lg:px-10">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 rounded-3xl border border-white/75 bg-white/75 p-3 shadow-sm backdrop-blur-sm">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            placeholder={placeholder}
            onKeyDown={handleKeyDown}
            disabled={inputDisabled}
            rows={1}
            className="flex-1 resize-none rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 caret-indigo-600 placeholder:text-slate-400 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:bg-slate-50"
          />
          {isRunning ? (
            <button
              onClick={onStop}
              disabled={isStopping}
              title="Stop the research run"
              className="flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-3 text-sm font-medium text-rose-700 transition hover:bg-rose-100 disabled:opacity-60"
            >
              <span className="h-2.5 w-2.5 rounded-[2px] bg-rose-600" />
              {isStopping ? "Stopping…" : "Stop"}
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={inputDisabled}
              className="rounded-2xl bg-[#171a3a] px-5 py-3 text-sm font-medium text-white transition hover:bg-[#0f1230] disabled:opacity-50"
            >
              Send
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full bg-[#171a3a] px-3 py-1.5 text-xs font-medium text-white">Deep Research</span>
          <span className="rounded-full bg-[#171a3a] px-3 py-1.5 text-xs font-medium text-white">Claim Check</span>
          <span className="rounded-full bg-[#171a3a] px-3 py-1.5 text-xs font-medium text-white">Search</span>
          <span className="rounded-full bg-[#171a3a] px-3 py-1.5 text-xs font-medium text-white">Summarize</span>
        </div>
      </div>
    </div>
  );
}
