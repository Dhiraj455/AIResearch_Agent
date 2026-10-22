"use client";

import { useEffect, useState } from "react";
import { api, type ResearchEvent } from "@/lib/api";

/**
 * A pipeline event. `ts` is the server time it happened (seconds); `at` is the client time it
 * arrived (ms), used as a fallback for older runs without `ts`.
 */
export type TimedEvent = ResearchEvent & { ts?: number; at?: number };

/** Event time in ms, preferring the server timestamp. */
function eventTime(ev: TimedEvent): number | undefined {
  return typeof ev.ts === "number" ? ev.ts * 1000 : ev.at;
}

export type ResearchStatus = "running" | "stopping" | "done";

type Chip = { label: string; tone?: "ok" | "bad" | "muted" };

type Step = {
  id: string;
  title: string;
  status: "running" | "done" | "warn";
  detail?: string;
  chips: Chip[];
  failures: number;
  startedAt?: number;
  endedAt?: number;
};

const MAX_CHIPS = 8;

function list(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : [];
}

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function host(url: unknown): string {
  try {
    return new URL(String(url)).hostname.replace(/^www\./, "");
  } catch {
    return String(url);
  }
}

function plural(n: number, word: string, pluralWord = `${word}s`): string {
  return `${n} ${n === 1 ? word : pluralWord}`;
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

/** Turn the raw event stream into a short list of human-readable steps. */
function buildSteps(events: TimedEvent[]): Step[] {
  const steps: Step[] = [];
  const cur = () => steps[steps.length - 1];
  const start = (id: string, title: string, at?: number) => {
    const prev = cur();
    if (prev && prev.status === "running") {
      prev.status = "done";
      prev.endedAt = at;
    }
    steps.push({ id: `${id}-${steps.length}`, title, status: "running", chips: [], failures: 0, startedAt: at });
  };
  const finish = (at?: number, status: Step["status"] = "done") => {
    const s = cur();
    if (s) {
      s.status = status;
      s.endedAt = at;
    }
  };

  for (const raw of events) {
    const ev = { ...raw, at: eventTime(raw) };
    const p = ev.payload ?? {};
    switch (ev.type) {
      case "plan_started":
        start("plan", "Planning research angles", ev.at);
        break;
      case "plan_created": {
        const angles = list(p.angles);
        const s = cur();
        if (s) {
          s.title = `Planned ${plural(angles.length, "research angle")}`;
          s.chips = angles.map((label) => ({ label }));
        }
        finish(ev.at);
        break;
      }
      case "search_started":
        start(
          "search",
          num(p.iter) > 0 ? `Pass ${num(p.iter) + 1} · Searching for missing evidence` : "Searching the web",
          ev.at
        );
        break;
      case "search_queries": {
        const s = cur();
        if (s) s.chips = list(p.queries).map((label) => ({ label: `“${label}”`, tone: "muted" }));
        break;
      }
      case "search_error":
        if (cur()) cur().failures += 1;
        break;
      case "search_done": {
        const s = cur();
        if (s) s.detail = `${plural(s.chips.length, "query", "queries")} · ${plural(num(p.new_results), "new result")}`;
        finish(ev.at);
        break;
      }
      case "fetch_started":
        start("fetch", "Reading sources", ev.at);
        break;
      case "doc_fetched":
        cur()?.chips.push({ label: host(p.url) + (p.cached ? " · cached" : ""), tone: "ok" });
        break;
      case "doc_fetch_failed": {
        const s = cur();
        if (s) {
          s.chips.push({ label: host(p.url), tone: "bad" });
          s.failures += 1;
        }
        break;
      }
      case "fetch_done": {
        const s = cur();
        if (s) {
          const ok = s.chips.filter((c) => c.tone === "ok").length;
          s.title = ok ? `Read ${plural(ok, "source")}` : "No new sources to read";
        }
        finish(ev.at);
        break;
      }
      case "extract_started":
        start("extract", "Extracting verbatim quotes", ev.at);
        break;
      case "extract_failed":
        if (cur()) cur().failures += 1;
        break;
      case "extract_done": {
        const s = cur();
        if (s) {
          const parts = [plural(num(p.new_evidence), "quote") + " extracted"];
          if (num(p.quote_not_found)) parts.push(`${num(p.quote_not_found)} not found in source → refuted`);
          if (num(p.empty_snippets)) parts.push(`${num(p.empty_snippets)} empty skipped`);
          s.detail = parts.join(" · ");
        }
        finish(ev.at);
        break;
      }
      case "claims_verify_started":
        start("verify-claims", "Verifying claims with the skeptic quorum", ev.at);
        break;
      case "verifier_failed":
        if (cur()) cur().failures += 1;
        break;
      case "claims_verified": {
        const s = cur();
        if (s) {
          const parts = [`${num(p.supported)} supported`, `${num(p.refuted)} refuted`];
          if (p.agreement != null) parts.push(`${Math.round(num(p.agreement) * 100)}% model agreement`);
          s.detail = parts.join(" · ");
          s.chips = list(p.models).map((m) => ({ label: m.replace(/^openai:/, ""), tone: "muted" }));
        }
        finish(ev.at);
        break;
      }
      case "coverage_check_started":
        start("coverage", "Checking coverage", ev.at);
        break;
      case "coverage_check_done": {
        const s = cur();
        if (s) {
          const gaps = list(p.gaps);
          s.title = gaps.length ? `Found ${plural(gaps.length, "coverage gap")}` : "Coverage looks complete";
          s.detail =
            `${plural(num(p.verified_claims), "verified claim")} from ${plural(num(p.unique_sources), "source")}` +
            ` (${num(p.academic_sources)} academic, ${num(p.industry_sources)} industry)`;
          s.chips = gaps.map((label) => ({ label, tone: "muted" }));
        }
        finish(ev.at);
        break;
      }
      case "write_started":
        start("write", "Writing the report", ev.at);
        if (cur()) cur().detail = `from ${plural(num(p.verified_evidence), "verified claim")}`;
        break;
      case "write_skipped": {
        const s = cur();
        if (s) {
          s.title = "No verified evidence — report not written";
          s.detail = "Writing one would mean answering from model memory.";
        }
        finish(ev.at, "warn");
        break;
      }
      case "write_done":
        finish(ev.at);
        break;
      case "verify_started":
        start("review", "Reviewing citations", ev.at);
        break;
      case "verify_done": {
        const s = cur();
        if (s) s.detail = num(p.issues) ? `${plural(num(p.issues), "issue")} to fix` : "No issues found";
        finish(ev.at);
        break;
      }
      case "verify_failed":
        finish(ev.at, "warn");
        break;
      case "revise_started":
        start("revise", "Revising the report", ev.at);
        break;
      case "revise_done":
        finish(ev.at);
        break;
    }
  }
  return steps;
}

function StepIcon({ status }: { status: Step["status"] }) {
  if (status === "running") {
    return <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />;
  }
  if (status === "warn") {
    return (
      <span className="flex h-4 w-4 items-center justify-center rounded-full bg-amber-100 text-[10px] font-bold text-amber-700">
        !
      </span>
    );
  }
  return (
    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 text-white">
      <svg className="h-2.5 w-2.5" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M2.5 6.5l2.2 2.2 4.8-5.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

const chipTone: Record<NonNullable<Chip["tone"]>, string> = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
  bad: "border-rose-200 bg-rose-50 text-rose-700 line-through decoration-rose-300",
  muted: "border-slate-200 bg-slate-50 text-slate-600",
};

function StepRow({ step, isLast }: { step: Step; isLast: boolean }) {
  const shown = step.chips.slice(0, MAX_CHIPS);
  const hidden = step.chips.length - shown.length;
  const duration =
    step.startedAt && step.endedAt ? formatDuration((step.endedAt - step.startedAt) / 1000) : null;

  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      {!isLast && <span className="absolute left-[7px] top-5 h-[calc(100%-12px)] w-px bg-slate-200" />}
      <span className="relative z-10 mt-0.5 shrink-0">
        <StepIcon status={step.status} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className={`text-sm font-medium ${step.status === "running" ? "text-slate-900" : "text-slate-700"}`}>
            {step.title}
            {step.status === "running" && <span className="text-slate-400">…</span>}
          </p>
          {duration && <span className="shrink-0 text-[11px] tabular-nums text-slate-400">{duration}</span>}
        </div>
        {(step.detail || step.failures > 0) && (
          <p className="mt-0.5 text-xs text-slate-500">
            {step.detail}
            {step.failures > 0 && (
              <span className="text-rose-600">
                {step.detail ? " · " : ""}
                {plural(step.failures, "failure")}
              </span>
            )}
          </p>
        )}
        {shown.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {shown.map((c, i) => (
              <span
                key={`${c.label}-${i}`}
                className={`max-w-[18rem] truncate rounded-full border px-2 py-0.5 text-[11px] ${chipTone[c.tone ?? "muted"]}`}
                title={c.label}
              >
                {c.label}
              </span>
            ))}
            {hidden > 0 && <span className="px-1 py-0.5 text-[11px] text-slate-400">+{hidden} more</span>}
          </div>
        )}
      </div>
    </li>
  );
}

function useElapsed(startedAt: number | undefined, active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return startedAt ? (now - startedAt) / 1000 : 0;
}

type Props = {
  events: TimedEvent[];
  status: ResearchStatus;
  startedAt?: number;
  totalSeconds?: number;
};

/** Live step-by-step view of a research run, shown inside the chat. */
export function ResearchSteps({ events, status, startedAt, totalSeconds }: Props) {
  const running = status !== "done";
  const [open, setOpen] = useState(running);
  const elapsed = useElapsed(startedAt, running);
  const steps = buildSteps(events);
  if (status === "done") {
    for (const s of steps) if (s.status === "running") s.status = "done";
  }

  const coverage = [...events].reverse().find((e) => e.type === "coverage_check_done")?.payload;
  const summary = coverage
    ? `${plural(num(coverage.verified_claims), "verified claim")} · ${plural(num(coverage.unique_sources), "source")}`
    : null;
  const seconds = running ? elapsed : totalSeconds;

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/85 shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2.5">
          {running ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
          ) : (
            <StepIcon status="done" />
          )}
          <span className="text-sm font-semibold text-slate-900">
            {status === "stopping" ? "Stopping research…" : running ? "Researching" : "Research complete"}
          </span>
          {seconds != null && seconds > 0 && (
            <span className="text-xs tabular-nums text-slate-500">{formatDuration(seconds)}</span>
          )}
          {!running && summary && <span className="hidden text-xs text-slate-500 sm:inline">· {summary}</span>}
        </span>
        <span className="text-xs font-medium text-indigo-700">{open ? "Hide steps" : "Show steps"}</span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-4 py-3">
          {steps.length === 0 ? (
            <p className="text-sm text-slate-500">Starting…</p>
          ) : (
            <ol>
              {steps.map((s, i) => (
                <StepRow key={s.id} step={s} isLast={i === steps.length - 1} />
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

/** Collapsed steps for a finished run; loads them from the backend on first open if not already known. */
export function ResearchTrace({
  runId,
  events,
  totalSeconds,
}: {
  runId: string;
  events?: TimedEvent[];
  totalSeconds?: number;
}) {
  const [loaded, setLoaded] = useState<{ events: TimedEvent[]; total?: number } | null>(
    events ? { events, total: totalSeconds } : null
  );
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (loaded) return;
    let cancelled = false;
    api
      .getRunEvents(runId)
      .then((r) => {
        if (!cancelled) setLoaded({ events: r.events, total: num(r.stats.total_s) || undefined });
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [runId, loaded]);

  if (failed || !loaded || loaded.events.length === 0) return null;
  return <ResearchSteps events={loaded.events} status="done" totalSeconds={loaded.total} />;
}
