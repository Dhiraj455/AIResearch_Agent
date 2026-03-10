"use client";

import { useRef, useEffect } from "react";

type Props = {
  placeholder: string;
  onSubmit: (value: string) => void;
  disabled?: boolean;
};

export function ChatInput({
  placeholder,
  onSubmit,
  disabled = false,
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const el = textareaRef.current;
    if (!el || disabled) return;
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
    <div className="border-t border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mx-auto flex max-w-3xl gap-2">
        <textarea
          ref={textareaRef}
          placeholder={placeholder}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none rounded-xl border border-zinc-300 bg-zinc-50 px-4 py-3 text-sm placeholder-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:placeholder-zinc-400"
        />
        <button
          onClick={handleSubmit}
          disabled={disabled}
          className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
