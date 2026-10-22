"use client";

import ReactMarkdown from "react-markdown";
import { ResearchTrace } from "./ResearchSteps";
import type { RunTrace } from "./ChatView";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Props = {
  role: "user" | "assistant";
  content: string;
  runId?: string | null;
  /** Steps already known for this run (finished in this session); otherwise loaded on demand. */
  trace?: RunTrace;
};

export function MessageBubble({ role, content, runId, trace }: Props) {
  const isUser = role === "user";

  return (
    <div
      className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`rounded-2xl ${
          isUser
            ? "max-w-[75%] bg-[#171a3a] px-4 py-3 text-white"
            : "w-full border border-white/70 bg-white/85 px-6 py-5 text-slate-800 shadow-sm"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm">{content}</p>
        ) : (
          <div className="space-y-4">
            {runId && (
              <ResearchTrace
                runId={runId}
                events={trace?.events}
                totalSeconds={trace?.totalSeconds}
              />
            )}
            {runId && (
              <a
                href={`${API_BASE}/runs/${runId}/report.pdf`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-[#2f3c97] px-3 py-1.5 text-sm font-medium text-white transition hover:bg-[#253279]"
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
                    d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                Download report (PDF)
              </a>
            )}
            <div className="report-md">
            <ReactMarkdown
              components={{
                a: ({ href, children }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-700 hover:underline"
                  >
                    {children}
                  </a>
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
          </div>
        )}
      </div>
    </div>
  );
}
