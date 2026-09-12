import { useCallback, useEffect, useState } from "react";
import {
  moderate,
  moderateBulk,
  moderationQueue,
  previewUrl,
  type ModerationAction,
  type PendingResource,
} from "../lib/files";

function formatSize(bytes: number | null): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * The review queue.
 *
 * Built for one motion: look at the file, decide, move on. Decisions apply
 * optimistically -- the row leaves the list immediately rather than after a
 * round trip, because waiting on the network between every approval is what
 * makes a queue feel like work. A failure puts the row back and says so.
 */
export default function ModerationPage({ onOpenCourse }: { onOpenCourse: (code: string) => void }) {
  const [queue, setQueue] = useState<PendingResource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    moderationQueue()
      .then((data) => setQueue(data.results))
      .catch(() => setError("Could not load the review queue."));
  }, []);

  useEffect(refresh, [refresh]);

  async function decide(resource: PendingResource, action: ModerationAction) {
    setError(null);
    const previous = queue;
    setQueue((rows) => (rows ?? []).filter((row) => row.id !== resource.id));
    try {
      await moderate(resource.id, action);
    } catch {
      setQueue(previous);
      setError(`Could not ${action} "${resource.title}". Nothing was changed.`);
    }
  }

  async function approveAll() {
    if (!queue?.length) return;
    setError(null);
    setBusy(true);
    const previous = queue;
    try {
      await moderateBulk(
        queue.map((row) => row.id),
        "approve",
      );
      setQueue([]);
    } catch {
      setQueue(previous);
      setError("Could not approve everything. Nothing was changed.");
    } finally {
      setBusy(false);
    }
  }

  async function open(resource: PendingResource) {
    try {
      window.open(await previewUrl(resource.id), "_blank", "noopener");
    } catch {
      setError("Could not open that file.");
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Review queue</h1>
          <p className="text-slate-500 mt-1">
            {queue === null
              ? "Loading…"
              : queue.length === 0
                ? "Nothing waiting. Everything students have uploaded is published."
                : `${queue.length} upload${queue.length === 1 ? "" : "s"} waiting, oldest first.`}
          </p>
        </div>
        {!!queue?.length && (
          <button
            onClick={approveAll}
            disabled={busy}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-40"
          >
            Approve all {queue.length}
          </button>
        )}
      </div>

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {!!queue?.length && (
        <ul className="mt-6 space-y-3">
          {queue.map((resource) => (
            <li
              key={resource.id}
              className="rounded-xl border border-slate-200 bg-white p-4"
            >
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{resource.title}</p>
                  <p className="mt-0.5 text-sm text-slate-500">
                    <button
                      onClick={() => onOpenCourse(resource.course_code)}
                      className="underline hover:text-slate-900"
                    >
                      {resource.course_code}
                    </button>{" "}
                    · {resource.type_label}
                    {resource.term_label ? ` · ${resource.term_label}` : ""}
                    {resource.size_bytes ? ` · ${formatSize(resource.size_bytes)}` : ""}
                  </p>
                  {/* The filename is often the clearest sign something is
                      mislabelled, so it is shown rather than hidden behind the
                      title the uploader typed. */}
                  {resource.original_filename && (
                    <p className="mt-0.5 font-mono text-xs text-slate-400 truncate">
                      {resource.original_filename}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-slate-400">
                    {resource.uploader_email ?? "system import"}
                    {" · "}
                    {resource.uploader_approved_count} approved before
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {resource.kind === "file" ? (
                    <button
                      onClick={() => open(resource)}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                    >
                      Preview
                    </button>
                  ) : (
                    <a
                      href={resource.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                    >
                      Open link
                    </a>
                  )}
                  <button
                    onClick={() => decide(resource, "reject")}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-red-50 hover:text-red-700"
                  >
                    Reject
                  </button>
                  <button
                    onClick={() => decide(resource, "approve")}
                    className="rounded-lg bg-emerald-600 px-4 py-1.5 text-sm text-white hover:bg-emerald-700"
                  >
                    Approve
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
