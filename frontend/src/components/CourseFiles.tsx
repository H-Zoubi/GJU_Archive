import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import {
  GateError,
  getDownloadUrl,
  listResources,
  uploadFile,
  type Resource,
  type UploadStage,
} from "../lib/files";

// Kept short on purpose: nobody tags consistently across a dozen
// near-synonyms, and a course where the same exam is filed four ways is
// harder to search than one tagged bluntly. Mirrors ResourceType in
// resources/models.py, minus "video", which only applies to links.
//
// A native <select> renders text only, so these are marked with emoji. The
// file-format badges below are real DOM and can be styled properly.
const TYPES = [
  ["slides", "📊 Slides"],
  ["exam", "📝 Exams & quizzes"],
  ["assignment", "📋 Assignments & projects"],
  ["notes", "📓 Notes & summaries"],
  ["lab", "🔬 Lab"],
  ["book", "📚 Book"],
  ["other", "📦 Other"],
] as const;

/**
 * What the file actually is, by extension.
 *
 * Separate from the resource `type` above: that says what the file is *for*
 * (an exam, a summary), this says what will open it. A student scanning the
 * list wants to know at a glance which rows are slide decks.
 */
const FORMATS: Record<string, { label: string; className: string }> = {
  pdf: { label: "PDF", className: "bg-red-100 text-red-700" },
  ppt: { label: "PPT", className: "bg-orange-100 text-orange-700" },
  pptx: { label: "PPT", className: "bg-orange-100 text-orange-700" },
  doc: { label: "DOC", className: "bg-blue-100 text-blue-700" },
  docx: { label: "DOC", className: "bg-blue-100 text-blue-700" },
  xls: { label: "XLS", className: "bg-emerald-100 text-emerald-700" },
  xlsx: { label: "XLS", className: "bg-emerald-100 text-emerald-700" },
  zip: { label: "ZIP", className: "bg-slate-200 text-slate-600" },
  png: { label: "IMG", className: "bg-purple-100 text-purple-700" },
  jpg: { label: "IMG", className: "bg-purple-100 text-purple-700" },
  jpeg: { label: "IMG", className: "bg-purple-100 text-purple-700" },
  gif: { label: "IMG", className: "bg-purple-100 text-purple-700" },
  webp: { label: "IMG", className: "bg-purple-100 text-purple-700" },
  txt: { label: "TXT", className: "bg-slate-100 text-slate-600" },
  md: { label: "TXT", className: "bg-slate-100 text-slate-600" },
};

const LINK_FORMAT = { label: "LINK", className: "bg-sky-100 text-sky-700" };
const UNKNOWN_FORMAT = { label: "FILE", className: "bg-slate-100 text-slate-500" };

function FormatBadge({ resource }: { resource: Resource }) {
  const extension = resource.original_filename.split(".").pop()?.toLowerCase() ?? "";
  const format =
    resource.kind === "link" ? LINK_FORMAT : FORMATS[extension] ?? UNKNOWN_FORMAT;
  return (
    <span
      // The label already reads as the format, so it is redundant to a screen
      // reader announcing the filename next to it.
      aria-hidden="true"
      className={`shrink-0 rounded-md px-1.5 py-1 text-[10px] font-semibold tracking-wide ${format.className}`}
    >
      {format.label}
    </span>
  );
}

const STAGE_LABEL: Record<UploadStage, string> = {
  hashing: "Reading file…",
  checking: "Checking for duplicates…",
  uploading: "Uploading…",
  finishing: "Finishing up…",
};

function formatSize(bytes: number | null): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function CourseFiles({ courseCode }: { courseCode: string }) {
  const { user } = useAuth();
  const [resources, setResources] = useState<Resource[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);

  const refresh = useCallback(() => {
    listResources({ course: courseCode })
      .then(setResources)
      .catch(() => setResources([]));
  }, [courseCode]);

  useEffect(refresh, [refresh]);

  async function download(resource: Resource) {
    setNotice(null);
    try {
      const url = await getDownloadUrl(resource.id);
      // The signed URL is short-lived, so it is used immediately and never
      // stored anywhere.
      window.location.href = url;
    } catch (error) {
      // A GateError already carries a message written for the student
      // ("Sign in with your GJU account to download"), so it is shown as-is.
      setNotice(
        error instanceof GateError ? error.message : "Could not start the download.",
      );
    }
  }

  return (
    <section className="mt-8">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-slate-500">
          Files {resources ? `(${resources.length})` : ""}
        </h2>
        {user && (
          <button
            onClick={() => setShowUpload((open) => !open)}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
          >
            {showUpload ? "Cancel" : "Upload a file"}
          </button>
        )}
      </div>

      {showUpload && (
        <UploadForm
          courseCode={courseCode}
          onDone={(message) => {
            setShowUpload(false);
            setNotice(message);
            refresh();
          }}
        />
      )}

      {notice && (
        <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {notice}
        </p>
      )}

      {resources === null ? (
        <p className="text-slate-400">Loading…</p>
      ) : resources.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-400">
          Nothing here yet.{" "}
          {user ? "Be the first to upload." : "Sign in with your GJU account to contribute."}
        </p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
          {resources.map((resource) => (
            <li key={resource.id} className="flex items-center gap-3 px-4 py-3">
              <FormatBadge resource={resource} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-slate-800">{resource.title}</p>
                <p className="text-xs text-slate-400">
                  {[
                    resource.type_label,
                    resource.term_label,
                    resource.instructor_name,
                    formatSize(resource.size_bytes),
                    `${resource.download_count} downloads`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              {resource.kind === "link" ? (
                <a
                  href={resource.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="shrink-0 text-sm text-slate-600 underline hover:text-slate-900"
                >
                  Open link
                </a>
              ) : (
                <button
                  onClick={() => download(resource)}
                  className="shrink-0 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                >
                  Download
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function UploadForm({
  courseCode,
  onDone,
}: {
  courseCode: string;
  onDone: (message: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  // Deliberately unset: a preselected type is one the student never looks at,
  // and a whole course of files mislabelled "past paper" is worse than a
  // moment's friction choosing.
  const [type, setType] = useState<string>("");
  const [stage, setStage] = useState<UploadStage | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !type) return;
    setError(null);
    try {
      const result = await uploadFile(
        file,
        { course: courseCode, type, title: title || file.name },
        (nextStage, fraction) => {
          setStage(nextStage);
          setProgress(fraction);
        },
      );
      onDone(
        result.skipped
          ? "That file was already in the archive, so nothing was uploaded."
          : result.resource.status === "approved"
            ? "Uploaded and published."
            : "Uploaded. A moderator will review it shortly.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setStage(null);
    }
  }

  const busy = stage !== null;

  return (
    <form
      onSubmit={submit}
      className="mb-4 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4"
    >
      <input
        type="file"
        onChange={(event) => {
          const picked = event.target.files?.[0] ?? null;
          setFile(picked);
          if (picked && !title) setTitle(picked.name.replace(/\.[^.]+$/, ""));
        }}
        className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-200 file:px-3 file:py-1.5 file:text-sm"
      />
      <div className="flex gap-3">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Title"
          className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm"
        />
        <select
          value={type}
          onChange={(event) => setType(event.target.value)}
          className={`rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm ${
            type ? "text-slate-900" : "text-slate-400"
          }`}
        >
          <option value="" disabled>
            Choose a type…
          </option>
          {TYPES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {busy && (
        <div>
          <p className="text-xs text-slate-500">{STAGE_LABEL[stage]}</p>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full bg-slate-900 transition-all"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={!file || !type || busy}
          className="rounded-lg bg-slate-900 px-4 py-1.5 text-sm text-white disabled:opacity-40"
        >
          Upload
        </button>
        {file && !type && (
          <span className="text-xs text-slate-500">Pick a type first.</span>
        )}
      </div>
    </form>
  );
}
