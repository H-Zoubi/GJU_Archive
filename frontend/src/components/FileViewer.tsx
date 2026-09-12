import { Suspense, lazy, useEffect, useState } from "react";
import { GateError, getDownloadUrl, type Resource } from "../lib/files";

const PdfViewer = lazy(() => import("./PdfViewer"));

const IMAGE_MIME_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
]);
const TEXT_MIME_TYPES = new Set(["text/plain", "text/markdown"]);

/**
 * In-site preview for a file, opened over the page rather than navigating
 * away -- the point is that looking at a file and downloading it are two
 * different actions, so a future paywall can gate only the second one.
 */
export default function FileViewer({
  resource,
  onClose,
  onDownload,
}: {
  resource: Resource;
  onClose: () => void;
  /** Reuses the caller's own download flow, so gating/errors stay in one place. */
  onDownload: (resource: Resource) => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setUrl(null);
    setError(null);
    getDownloadUrl(resource.id, { inline: true })
      .then((u) => {
        if (!cancelled) setUrl(u);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof GateError ? err.message : "Could not open this file.");
      });
    return () => {
      cancelled = true;
    };
  }, [resource.id]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex h-full max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 border-b border-slate-200 px-4 py-3">
          <p className="min-w-0 truncate font-medium text-slate-800">{resource.title}</p>
          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={() => onDownload(resource)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              Download
            </button>
            <button
              onClick={onClose}
              aria-label="Close preview"
              className="rounded-lg px-2 py-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1">
          {error ? (
            <p className="p-8 text-center text-sm text-slate-500">{error}</p>
          ) : !url ? (
            <p className="p-8 text-center text-sm text-slate-400">Opening…</p>
          ) : (
            <FileBody resource={resource} url={url} />
          )}
        </div>
      </div>
    </div>
  );
}

function FileBody({ resource, url }: { resource: Resource; url: string }) {
  if (resource.mime_type === "application/pdf") {
    return (
      <Suspense
        fallback={<p className="p-8 text-center text-sm text-slate-400">Loading preview…</p>}
      >
        <PdfViewer url={url} />
      </Suspense>
    );
  }

  if (IMAGE_MIME_TYPES.has(resource.mime_type)) {
    return (
      <div className="flex h-full items-center justify-center overflow-auto bg-slate-100 p-4">
        <img src={url} alt={resource.title} className="max-h-full max-w-full object-contain" />
      </div>
    );
  }

  if (TEXT_MIME_TYPES.has(resource.mime_type)) {
    return <TextBody url={url} />;
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-1 p-8 text-center">
      <p className="text-sm text-slate-500">
        There's no in-site preview for this file type yet.
      </p>
      <p className="text-xs text-slate-400">Use Download above to open it.</p>
    </div>
  );
}

function TextBody({ url }: { url: string }) {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(url)
      .then((res) => res.text())
      .then((body) => {
        if (!cancelled) setText(body);
      })
      .catch(() => {
        if (!cancelled) setText("This file could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  return (
    <pre className="h-full overflow-auto whitespace-pre-wrap break-words bg-slate-50 p-4 text-sm text-slate-800">
      {text ?? "Loading…"}
    </pre>
  );
}
