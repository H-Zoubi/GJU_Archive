import { useAuth } from "../lib/auth";

export default function HomePage() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <span className="font-bold text-slate-900">GJU Vault</span>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-500">{user?.email}</span>
            <button
              onClick={() => logout()}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-100 transition"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-10">
        <h1 className="text-2xl font-bold text-slate-900">
          Welcome{user?.full_name ? `, ${user.full_name}` : ""} 👋
        </h1>
        <p className="text-slate-500 mt-2">
          You're signed in. Browsing courses and materials is coming next.
        </p>
      </main>
    </div>
  );
}
