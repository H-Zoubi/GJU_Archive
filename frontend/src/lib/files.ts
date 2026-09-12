// Files API: the browser talks to Django for permission and to the bucket for
// bytes. Nothing here ever sees an object key — a download is a signed URL the
// server mints after checking entitlement.

export interface Resource {
  id: number;
  title: string;
  description: string;
  type: string;
  type_label: string;
  kind: "file" | "link";
  course_code: string;
  course_name: string;
  term_label: string | null;
  instructor_name: string | null;
  uploader_name: string;
  url: string;
  size_bytes: number | null;
  mime_type: string;
  original_filename: string;
  source: string;
  status: "pending" | "approved" | "rejected" | "removed";
  download_count: number;
  created_at: string;
}

export interface UploadMeta {
  course: string;
  type: string;
  title: string;
  description?: string;
  term?: number | null;
  instructor?: number | null;
}

/** A denial the API reports with a machine-readable reason (see entitlements.py). */
export class GateError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

async function csrfToken(): Promise<string> {
  let token = getCookie("csrftoken");
  if (!token) {
    await fetch("/api/auth/csrf/", { credentials: "include" });
    token = getCookie("csrftoken");
  }
  return token ?? "";
}

async function jsonPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRFToken": await csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const { detail, code } = data as { detail?: string; code?: string };
    throw new GateError(code ?? "error", detail ?? "Something went wrong.");
  }
  return data as T;
}

/**
 * SHA-256 of the file, computed in the browser.
 *
 * This is what makes the duplicate check possible before anything is uploaded:
 * we can ask "do you already have this file?" without sending it. It is also
 * the object key the server derives, so the same PDF never costs storage twice.
 */
export async function hashFile(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface ExistsResult {
  exists: boolean;
  in_this_course: boolean;
  resources: Resource[];
}

export async function checkExists(sha256: string, course?: string): Promise<ExistsResult> {
  const params = new URLSearchParams({ sha256 });
  if (course) params.set("course", course);
  const res = await fetch(`/api/resources/exists/?${params}`, { credentials: "include" });
  if (!res.ok) throw new Error("Could not check for duplicates.");
  return (await res.json()) as ExistsResult;
}

/**
 * PUT the file straight at the bucket.
 *
 * XHR rather than fetch purely for `upload.onprogress` — a 50 MB slide deck on
 * campus wifi needs a progress bar, and fetch still cannot report upload
 * progress in browsers.
 */
function putToBucket(
  url: string,
  file: File,
  headers: Record<string, string>,
  onProgress?: (fraction: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    for (const [key, value] of Object.entries(headers)) xhr.setRequestHeader(key, value);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`Upload failed (${xhr.status}).`));
    xhr.onerror = () => reject(new Error("Upload failed. Check your connection."));
    xhr.send(file);
  });
}

export type UploadStage = "hashing" | "checking" | "uploading" | "finishing";

export interface UploadResult {
  resource: Resource;
  /** True when the archive already had this file and nothing was uploaded. */
  skipped: boolean;
}

interface StartResponse {
  resource_id: number;
  upload_url: string;
  method: string;
  headers: Record<string, string>;
}

/**
 * The whole upload: hash, duplicate check, direct PUT, then confirm.
 *
 * The confirm step is not optional — until it succeeds the server treats the
 * upload as abandoned and serves nothing, which is what stops a half-written
 * object from ever reaching another student.
 */
export async function uploadFile(
  file: File,
  meta: UploadMeta,
  onStage?: (stage: UploadStage, progress: number) => void,
): Promise<UploadResult> {
  onStage?.("hashing", 0);
  const sha256 = await hashFile(file);

  onStage?.("checking", 0);
  const duplicate = await checkExists(sha256, meta.course);
  if (duplicate.in_this_course) {
    return { resource: duplicate.resources[0], skipped: true };
  }

  const start = await jsonPost<StartResponse>("/api/uploads/", {
    ...meta,
    filename: file.name,
    size_bytes: file.size,
    sha256,
  });

  onStage?.("uploading", 0);
  await putToBucket(start.upload_url, file, start.headers, (p) => onStage?.("uploading", p));

  onStage?.("finishing", 1);
  const resource = await jsonPost<Resource>(`/api/uploads/${start.resource_id}/complete/`);
  return { resource, skipped: false };
}

export async function listResources(params: {
  course?: string;
  type?: string;
  search?: string;
}): Promise<Resource[]> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value);
  const res = await fetch(`/api/resources/?${query}`, { credentials: "include" });
  if (!res.ok) throw new Error("Could not load files.");
  const data = (await res.json()) as { results: Resource[] };
  return data.results;
}

export async function myUploads(): Promise<Resource[]> {
  const res = await fetch("/api/uploads/mine/", { credentials: "include" });
  if (!res.ok) throw new Error("Could not load your uploads.");
  return (await res.json()) as Resource[];
}

/**
 * Ask for a download URL and open it.
 *
 * Throws a GateError when access is refused, so the caller can show the sign-in
 * prompt (or, once a paywall exists, the upgrade prompt) instead of a generic
 * error. The URL is short-lived by design and must not be cached or shared.
 */
export async function getDownloadUrl(
  resourceId: number,
  { inline = false } = {},
): Promise<string> {
  const res = await fetch(
    `/api/resources/${resourceId}/download/${inline ? "?inline=1" : ""}`,
    { credentials: "include" },
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const { detail, code } = data as { detail?: string; code?: string };
    throw new GateError(code ?? "error", detail ?? "This file is not available.");
  }
  return (data as { url: string }).url;
}
