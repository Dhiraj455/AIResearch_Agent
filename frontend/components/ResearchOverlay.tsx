"use client";

type Props = {
  show: boolean;
  prompt: string;
};

export function ResearchOverlay({ show, prompt }: Props) {
  if (!show) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="mx-4 max-w-md rounded-2xl bg-white p-8 shadow-xl dark:bg-zinc-900">
        <div className="mb-4 flex justify-center">
          <div className="h-14 w-14 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent" />
        </div>
        <h3 className="mb-2 text-center text-lg font-semibold">
          Research in progress
        </h3>
        <p className="mb-4 text-center text-sm text-zinc-500">
          This may take 5–10 minutes. Please don&apos;t close this page.
        </p>
        <p className="rounded-lg bg-zinc-100 px-3 py-2 text-sm dark:bg-zinc-800">
          &ldquo;{prompt}&rdquo;
        </p>
      </div>
    </div>
  );
}
