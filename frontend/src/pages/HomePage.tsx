import { useState } from "react";
import { useAuth } from "../lib/auth";
import BrowsePage from "./BrowsePage";
import CoursePage from "./CoursePage";
import SubjectPage from "./SubjectPage";

type View =
  | { name: "browse" }
  | { name: "subject"; slug: string; title: string }
  | { name: "course"; code: string };

export default function HomePage() {
  const { user, logout } = useAuth();
  const [view, setView] = useState<View>({ name: "browse" });
  // Kept here so it survives navigating into a subject and back.
  const [major, setMajor] = useState<string | null>(user?.major?.slug ?? null);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <button
            onClick={() => setView({ name: "browse" })}
            className="font-bold text-slate-900"
          >
            GJU Vault
          </button>
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

      {view.name === "browse" && (
        <BrowsePage
          myMajor={major}
          onMajorChange={setMajor}
          onOpenSubject={(slug, title) =>
            setView({ name: "subject", slug, title })
          }
          onOpenCourse={(code) => setView({ name: "course", code })}
        />
      )}

      {view.name === "subject" && (
        <SubjectPage
          slug={view.slug}
          name={view.title}
          major={major}
          onOpenCourse={(code) => setView({ name: "course", code })}
          onBack={() => setView({ name: "browse" })}
        />
      )}

      {view.name === "course" && (
        <CoursePage
          code={view.code}
          onBack={() => setView({ name: "browse" })}
        />
      )}
    </div>
  );
}
