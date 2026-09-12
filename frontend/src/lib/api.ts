// Thin API client. Requests go to /api (Vite proxies to Django in dev), so
// everything is same-origin and session + CSRF cookies just work.

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_gju_verified: boolean;
  /** Whether to offer the review dashboard. The API enforces this too. */
  can_moderate: boolean;
  /** Set once the student picks a major; drives the default browse filter. */
  major: { slug: string; name: string } | null;
  /** Filled in from MyGJU at signup/login; null until then. */
  entry_year: number | null;
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

async function ensureCsrf(): Promise<string> {
  let token = getCookie("csrftoken");
  if (!token) {
    await fetch("/api/auth/csrf/", { credentials: "include" });
    token = getCookie("csrftoken");
  }
  return token ?? "";
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const csrf = await ensureCsrf();
  const res = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrf,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, (data as { detail?: string }).detail ?? "Something went wrong.");
  }
  return data as T;
}

export const api = {
  async me(): Promise<User | null> {
    const res = await fetch("/api/auth/me/", { credentials: "include" });
    if (res.status === 200) return (await res.json()) as User;
    return null;
  },
  login(email: string, password: string): Promise<User> {
    return post<User>("/api/auth/login/", { email, password });
  },
  logout(): Promise<void> {
    return post<void>("/api/auth/logout/");
  },
};

export { ApiError };
