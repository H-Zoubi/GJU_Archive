import { useEffect, useState } from "react";
import { catalog, type CourseSummary } from "../lib/catalog";

interface Props {
  slug: string;
  /** Narrows the subject's courses to one major, when one is selected. */
  major?: string | null;
  onOpenCourse: (code: string) => void;
  onBack: () => void;
}

export default function SubjectPage({
  slug,
  major,
  onOpenCourse,
  onBack,
}: Props) {
  // Fetched rather than passed in: this page has its own URL, so it has to
  // stand up on a cold load with nothing but the slug.
  const [name, setName] = useState("");
  const [courses, setCourses] = useState<CourseSummary[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    catalog
      .courses({ subject: slug, major: major ?? undefined, page })
      .then((result) => {
        setCourses(result.results);
        setCount(result.count);
      })
      .finally(() => setLoading(false));
  }, [slug, major, page]);

  useEffect(() => setPage(1), [slug, major]);

  useEffect(() => {
    catalog
      .subject(slug)
      .then((subject) => setName(subject.name))
      .catch(() => setName(slug));
  }, [slug]);

  const pages = Math.ceil(count / 25);

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <button
        onClick={onBack}
        className="text-sm text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 mb-4"
      >
        ← All subjects
      </button>

      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{name || " "}</h1>
      <p className="text-slate-500 dark:text-slate-400 mt-1 mb-6">
        {count} course{count === 1 ? "" : "s"}
        {major ? " in the selected major" : ""}
      </p>

      {loading ? (
        <div className="py-12 text-center text-slate-400 dark:text-slate-500">Loading…</div>
      ) : courses.length === 0 ? (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 py-12 text-center text-slate-500 dark:text-slate-400">
          No courses here for that major.
        </div>
      ) : (
        <ul className="divide-y divide-slate-200 dark:divide-slate-800 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          {courses.map((course) => (
            <li key={course.id}>
              <button
                onClick={() => onOpenCourse(course.code)}
                className="w-full text-left px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-baseline gap-3"
              >
                <span className="font-mono text-slate-900 dark:text-slate-100 w-24 shrink-0">
                  {course.display_code}
                </span>
                <span className="text-slate-700 dark:text-slate-300 flex-1">{course.name}</span>
                {course.credit_hours != null && (
                  <span className="text-xs text-slate-400 dark:text-slate-500 shrink-0">
                    {course.credit_hours} cr
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {pages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-3 text-sm">
          <button
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-lg border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 px-3 py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-slate-500 dark:text-slate-400">
            Page {page} of {pages}
          </span>
          <button
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 px-3 py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
