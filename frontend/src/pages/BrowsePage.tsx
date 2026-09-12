import { useEffect, useMemo, useState } from "react";
import {
  catalog,
  type CourseSummary,
  type Major,
  type Subject,
} from "../lib/catalog";

interface Props {
  /** The selected major slug; starts as the signed-in student's own. */
  myMajor?: string | null;
  /** Lifted so the choice survives navigating into a subject and back. */
  onMajorChange: (slug: string | null) => void;
  onOpenSubject: (slug: string, name: string) => void;
  onOpenCourse: (code: string) => void;
}

export default function BrowsePage({
  myMajor,
  onMajorChange,
  onOpenSubject,
  onOpenCourse,
}: Props) {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [majors, setMajors] = useState<Major[]>([]);
  // null = every major. Defaults to the student's own once we know it.
  const major = myMajor ?? null;
  const setMajor = onMajorChange;
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<CourseSummary[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([catalog.subjects(), catalog.majors()])
      .then(([s, m]) => {
        setSubjects(s);
        setMajors(m.results);
      })
      .finally(() => setLoading(false));
  }, []);

  // Debounced search: students mostly arrive knowing a code like CS223.
  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setHits(null);
      return;
    }
    setSearching(true);
    const timer = setTimeout(() => {
      catalog
        .courses({ search: text, major: major ?? undefined })
        .then((page) => setHits(page.results))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query, major]);

  // When a major is chosen, its own subjects come first and the
  // everyone-takes-it ones (German, Maths…) drop to a separate group.
  const [mine, shared] = useMemo(() => {
    const own = subjects.filter((s) => !s.is_university_wide);
    const wide = subjects.filter((s) => s.is_university_wide);
    return [own, wide];
  }, [subjects]);

  if (loading) {
    return (
      <div className="py-20 text-center text-slate-400">Loading catalog…</div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="mb-6">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search a course — CS223, or “data structures”"
          className="w-full rounded-xl border border-slate-300 px-4 py-3 text-lg outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-900/10"
        />
      </div>

      <div className="flex items-center gap-2 mb-8 text-sm">
        <span className="text-slate-500">Major:</span>
        <select
          value={major ?? ""}
          onChange={(e) => setMajor(e.target.value || null)}
          className="rounded-lg border border-slate-300 px-2 py-1.5"
        >
          <option value="">All majors</option>
          {majors.map((m) => (
            <option key={m.slug} value={m.slug}>
              {m.name}
            </option>
          ))}
        </select>
        {myMajor && major === myMajor && (
          <span className="text-slate-400">· your major</span>
        )}
      </div>

      {hits !== null ? (
        <section>
          <h2 className="text-sm font-medium text-slate-500 mb-3">
            {searching ? "Searching…" : `${hits.length} result(s)`}
          </h2>
          <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
            {hits.map((course) => (
              <li key={course.id}>
                <button
                  onClick={() => onOpenCourse(course.code)}
                  className="w-full text-left px-4 py-3 hover:bg-slate-50"
                >
                  <span className="font-mono text-slate-900">
                    {course.display_code}
                  </span>
                  <span className="text-slate-600"> — {course.name}</span>
                </button>
              </li>
            ))}
            {!searching && hits.length === 0 && (
              <li className="px-4 py-6 text-center text-slate-400">
                Nothing matched “{query}”.
              </li>
            )}
          </ul>
        </section>
      ) : (
        <>
          <SubjectGrid
            title="Subjects"
            subjects={mine}
            major={major}
            onOpen={onOpenSubject}
          />
          <SubjectGrid
            title="Taken across majors"
            subjects={shared}
            major={major}
            onOpen={onOpenSubject}
            muted
          />
        </>
      )}
    </div>
  );
}

function SubjectGrid({
  title,
  subjects,
  major,
  onOpen,
  muted,
}: {
  title: string;
  subjects: Subject[];
  major: string | null;
  onOpen: (slug: string, name: string) => void;
  muted?: boolean;
}) {
  if (subjects.length === 0) return null;
  return (
    <section className="mb-10">
      <h2 className="text-sm font-medium text-slate-500 mb-3">{title}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {subjects.map((subject) => (
          <button
            key={subject.slug}
            onClick={() => onOpen(subject.slug, subject.name)}
            className={`text-left rounded-xl border p-4 transition hover:border-slate-400 hover:shadow-sm ${
              muted
                ? "border-slate-200 bg-slate-50"
                : "border-slate-200 bg-white"
            }`}
          >
            <div className="font-medium text-slate-900">{subject.name}</div>
            <div className="mt-1 text-xs text-slate-500">
              {subject.course_count} course
              {subject.course_count === 1 ? "" : "s"}
              {major ? " · filtered by major" : ""}
            </div>
            <div className="mt-2 font-mono text-[11px] text-slate-400">
              {subject.prefixes.join(" · ")}
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
