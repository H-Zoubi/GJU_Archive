import { useEffect, useState } from "react";
import { byTerm, catalog, type CourseDetail } from "../lib/catalog";
import CourseFiles from "../components/CourseFiles";

interface Props {
  code: string;
  onBack: () => void;
}

export default function CoursePage({ code, onBack }: Props) {
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    catalog
      .course(code)
      .then(setCourse)
      .catch(() => setCourse(null))
      .finally(() => setLoading(false));
  }, [code]);

  if (loading) {
    return <div className="py-20 text-center text-slate-400">Loading…</div>;
  }
  if (!course) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-20 text-center">
        <p className="text-slate-500">Couldn’t find {code}.</p>
        <button onClick={onBack} className="mt-4 text-slate-900 underline">
          Go back
        </button>
      </div>
    );
  }

  // Each group is one semester this course ran — the course history.
  const history = byTerm(course.offerings);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <button
        onClick={onBack}
        className="text-sm text-slate-500 hover:text-slate-900 mb-4"
      >
        ← Back
      </button>

      <div className="flex items-baseline gap-3 flex-wrap">
        <h1 className="font-mono text-2xl font-bold text-slate-900">
          {course.display_code}
        </h1>
        <span className="text-xl text-slate-700">{course.name}</span>
      </div>

      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        {course.credit_hours != null && (
          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">
            {course.credit_hours} credit hours
          </span>
        )}
        {course.majors.map((major) => (
          <span
            key={major.id}
            className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600"
          >
            {major.name}
          </span>
        ))}
      </div>

      {course.prerequisites.length > 0 && (
        <p className="mt-4 text-sm text-slate-600">
          Prerequisites:{" "}
          {course.prerequisites.map((p) => p.display_code).join(", ")}
        </p>
      )}

      <CourseFiles courseCode={course.code} />

      <section className="mt-8">
        <h2 className="text-sm font-medium text-slate-500 mb-3">
          Offered in {history.length} semester
          {history.length === 1 ? "" : "s"}
        </h2>

        {history.length === 0 ? (
          <p className="text-slate-400">No recorded offerings yet.</p>
        ) : (
          <div className="space-y-4">
            {history.map(([label, offerings]) => (
              <div
                key={label}
                className="rounded-xl border border-slate-200 bg-white overflow-hidden"
              >
                <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-700">
                  {label}
                  <span className="ml-2 font-normal text-slate-400">
                    {offerings.length} section
                    {offerings.length === 1 ? "" : "s"}
                  </span>
                </div>
                <ul className="divide-y divide-slate-100">
                  {offerings.map((offering) => (
                    <li
                      key={offering.id}
                      className="px-4 py-2.5 flex items-baseline gap-3 text-sm"
                    >
                      <span className="text-slate-400 w-12 shrink-0">
                        §{offering.section_number || "—"}
                      </span>
                      <span className="text-slate-700 flex-1">
                        {offering.instructors.length > 0
                          ? offering.instructors
                              .map((i) => i.full_name)
                              .join(", ")
                          : "No instructor listed"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

    </div>
  );
}
