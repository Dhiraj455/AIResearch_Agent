"use client";

import type { ResearchEvent } from "@/lib/api";

type Props = {
  show: boolean;
  prompt: string;
  events?: ResearchEvent[];
};

function count(v: unknown): number {
  return Array.isArray(v) ? v.length : Number(v ?? 0);
}

function host(url: unknown): string {
  try {
    return new URL(String(url)).hostname.replace(/^www\./, "");
  } catch {
    return String(url);
  }
}

/** Human-readable label for a pipeline event, or null to hide it. */
function describe(ev: ResearchEvent): string | null {
  const p = ev.payload ?? {};
  switch (ev.type) {
    case "plan_started":
      return "Planning research angles";
    case "plan_created":
      return `Planned ${count(p.angles)} angles and ${count(p.queries)} queries`;
    case "search_queries":
      return Number(p.iter) > 0
        ? `Pass ${Number(p.iter) + 1}: ${count(p.queries)} follow-up queries for gaps`
        : `Searching ${count(p.queries)} queries`;
    case "search_done":
      return `Found ${p.new_results} new results`;
    case "doc_fetched":
      return `Read ${host(p.url)}${p.cached ? " (cached)" : ""}`;
    case "extract_done":
      return `Extracted ${p.new_evidence} quotes (${p.quote_not_found} not found in source)`;
    case "claims_verify_started":
      return "Skeptic quorum verifying claims";
    case "claims_verified":
      return `Verified ${p.supported}, refuted ${p.refuted}`;
    case "coverage_check_done":
      return count(p.gaps) ? `${count(p.gaps)} coverage gaps remaining` : "Coverage looks complete";
    case "write_started":
      return "Writing report";
    case "verify_started":
      return "Reviewing report citations";
    case "revise_started":
      return "Revising report";
    default:
      return null;
  }
}

export function ResearchOverlay({ show, prompt, events = [] }: Props) {
  if (!show) return null;

  const steps = events.map(describe).filter((s): s is string => !!s).slice(-6);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 backdrop-blur-md">
      <div className="mx-4 max-w-md rounded-3xl border border-white/65 bg-white/85 p-8 shadow-2xl">
        <div className="mb-4 flex justify-center">
          <div className="h-14 w-14 animate-spin rounded-full border-4 border-[#323a8a] border-t-transparent" />
        </div>
        <h3 className="mb-2 text-center text-lg font-semibold text-slate-900">
          Research in progress
        </h3>
        <p className="mb-4 text-center text-sm text-slate-600">
          This may take 5–10 minutes. Please don&apos;t close this page.
        </p>
        <p className="rounded-xl border border-white/70 bg-white/80 px-3 py-2 text-sm text-slate-700">
          &ldquo;{prompt}&rdquo;
        </p>
        {steps.length > 0 && (
          <ul className="mt-4 space-y-1.5 text-sm text-slate-600">
            {steps.map((s, i) => (
              <li
                key={`${i}-${s}`}
                className={i === steps.length - 1 ? "font-medium text-slate-900" : ""}
              >
                {i === steps.length - 1 ? "▸ " : "✓ "}
                {s}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
