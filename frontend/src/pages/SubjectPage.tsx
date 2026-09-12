import { useEffect, useState } from "react";
import { catalog, type CourseSummary } from "../lib/catalog";

interface Props {
  slug: string;
  name: string;
  /** Narrows the subject's courses to one major, when one is selected. */
  major?: string | null;
  onOpenCourse: (code: string) => void;
  onBack: () => void;
}

export default function SubjectPage({
  slug,
  name,
  major,
  onOpenCourse,
  onBack,
}: Props) {
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

  const pages = Math.ceil(count / 25);

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <button
        onClick={onBack}
        className="text-sm text-slate-500 hover:text-slate-900 mb-4"
      >
        ← All subjects
      </button>

      <h1 className="text-2xl font-bold text-slate-900">{name}</h1>
      <p className="text-slate-500 mt-1 mb-6">
        {count} course{count === 1 ? "" : "s"}
        {major ? " in the selected major" : ""}
      </p>

      {loading ? (
        <div className="py-12 text-center text-slate-400">Loading…</div>
      ) : courses.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-slate-50 py-12 text-center text-slate-500">
          No courses here for that major.
        </div>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {courses.map((course) => (
            <li key={course.id}>
              <button
                onClick={() => onOpenCourse(course.code)}
                className="w-full text-left px-4 py-3 hover:bg-slate-50 flex items-baseline gap-3"
              >
                <span className="font-mono text-slate-900 w-24 shrink-0">
                  {course.display_code}
                </span>
                <span className="text-slate-700 flex-1">{course.name}</span>
                {course.credit_hours != null && (
                  <span className="text-xs text-slate-400 shrink-0">
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
            className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-slate-500">
            Page {page} of {pages}
          </span>
          <button
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
