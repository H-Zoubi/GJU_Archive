import { useState, type FormEvent } from "react";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import Logo from "../components/Logo";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl text-slate-900 dark:text-slate-100">
            <Logo />
          </h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">Sign in with your GJU account</p>
        </div>

        <form
          onSubmit={onSubmit}
          className="bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 p-6 space-y-4"
        >
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1"
            >
              GJU email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@gju.edu.jo"
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 outline-none focus:ring-2 focus:ring-slate-900/10 dark:focus:ring-slate-100/10 focus:border-slate-400 dark:focus:border-slate-500"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1"
            >
              GJU password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 outline-none focus:ring-2 focus:ring-slate-900/10 dark:focus:ring-slate-100/10 focus:border-slate-400 dark:focus:border-slate-500"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 font-medium py-2.5 hover:bg-slate-800 dark:hover:bg-slate-300 disabled:opacity-60 transition"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>

          <p className="text-xs text-slate-400 dark:text-slate-500 text-center pt-1">
            No sign-up needed — your GJU account signs you in.
          </p>
        </form>
      </div>
    </div>
  );
}
