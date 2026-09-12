import { useEffect, useMemo, useState } from "react";
import {
  catalog,
  type CourseSummary,
  type Major,
  type Requirement,
  type Subject,
} from "../lib/catalog";

interface Props {
  /** The selected major slug; starts as the signed-in student's own. */
  myMajor?: string | null;
  /** The student's actual major, so we only badge it when it really is theirs. */
  ownMajor?: string | null;
  /** Lifted so the choice survives navigating into a subject and back. */
  onMajorChange: (slug: string | null) => void;
  onOpenSubject: (slug: string, name: string) => void;
  onOpenCourse: (code: string) => void;
}

export default function BrowsePage({
  myMajor,
  ownMajor,
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
  // How many the same search finds with no major filter. Non-zero only when
  // the filter is what emptied the results, so we can say so.
  const [hiddenByFilter, setHiddenByFilter] = useState(0);
  const [searching, setSearching] = useState(false);
  const [loading, setLoading] = useState(true);
  // null = browse by subject as before. Set only with a major chosen, since
  // that is the only case where "required" means anything.
  const [requirement, setRequirement] = useState<Requirement | null>(null);
  const [planCourses, setPlanCourses] = useState<CourseSummary[] | null>(null);
  const [planTotal, setPlanTotal] = useState(0);

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
    const timer = setTimeout(async () => {
      try {
        const page = await catalog.courses({
          search: text,
          major: major ?? undefined,
        });
        setHits(page.results);
        // Empty because of the filter, or genuinely nothing? Ask again
        // without the major so we can tell the student which it is.
        if (page.count === 0 && major) {
          const everywhere = await catalog.courses({ search: text });
          setHiddenByFilter(everywhere.count);
        } else {
          setHiddenByFilter(0);
        }
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query, major]);

  // Clearing the major has to clear the requirement view too, or the page
  // would sit on "Required courses" for nobody.
  useEffect(() => {
    if (!major) setRequirement(null);
  }, [major]);

  useEffect(() => {
    if (!major || !requirement) {
      setPlanCourses(null);
      return;
    }
    let live = true;
    catalog.courses({ major, requirement }).then((page) => {
      if (!live) return;
      setPlanCourses(page.results);
      setPlanTotal(page.count);
    });
    return () => {
      live = false;
    };
  }, [major, requirement]);

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
        {ownMajor && major === ownMajor && (
          <span className="text-slate-400">· your major</span>
        )}

        {/* Only meaningful with a major: the study plan is per degree. */}
        {major && (
          <div className="ml-auto flex rounded-lg border border-slate-300 overflow-hidden">
            {(
              [
                [null, "All"],
                ["compulsory", "Required"],
                ["elective", "Elective"],
              ] as [Requirement | null, string][]
            ).map(([value, label]) => (
              <button
                key={label}
                onClick={() => setRequirement(value)}
                className={`px-3 py-1.5 ${
                  requirement === value
                    ? "bg-slate-900 text-white"
                    : "bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
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
                  <RequirementBadge course={course} />
                </button>
              </li>
            ))}
            {!searching && hits.length === 0 && hiddenByFilter === 0 && (
              <li className="px-4 py-6 text-center text-slate-400">
                Nothing matched “{query}”.
              </li>
            )}
            {!searching && hits.length === 0 && hiddenByFilter > 0 && (
              <li className="px-4 py-6 text-center">
                <p className="text-slate-700">
                  No match in this major — but{" "}
                  {hiddenByFilter === 1
                    ? "1 course elsewhere matches"
                    : `${hiddenByFilter} courses elsewhere match`}{" "}
                  “{query}”.
                </p>
                <button
                  onClick={() => setMajor(null)}
                  className="mt-3 rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-800"
                >
                  Clear the major filter
                </button>
              </li>
            )}
          </ul>
        </section>
      ) : planCourses !== null ? (
        <section>
          <h2 className="text-sm font-medium text-slate-500 mb-3">
            {planTotal}{" "}
            {requirement === "compulsory" ? "required" : "elective"} course
            {planTotal === 1 ? "" : "s"} in this study plan
          </h2>
          <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
            {planCourses.map((course) => (
              <li key={course.id}>
                <button
                  onClick={() => onOpenCourse(course.code)}
                  className="w-full text-left px-4 py-3 hover:bg-slate-50"
                >
                  <span className="font-mono text-slate-900">
                    {course.display_code}
                  </span>
                  <span className="text-slate-600"> — {course.name}</span>
                  <RequirementBadge course={course} showCategory />
                </button>
              </li>
            ))}
            {planCourses.length === 0 && (
              <li className="px-4 py-6 text-center text-slate-400">
                No study plan has been imported for this major yet.
              </li>
            )}
            {planCourses.length < planTotal && (
              <li className="px-4 py-3 text-center text-xs text-slate-400">
                Showing the first {planCourses.length} of {planTotal}.
              </li>
            )}
          </ul>
        </section>
      ) : (
        <>
          <SubjectGrid title="Subjects" subjects={mine} onOpen={onOpenSubject} />
          <SubjectGrid
            title="Taken across majors"
            subjects={shared}
            onOpen={onOpenSubject}
            muted
          />
        </>
      )}
    </div>
  );
}

/**
 * Says whether a course is required, and nothing at all when we don't know.
 * A course the study plan never mentions must not be labelled "elective" —
 * that would state something the plan does not.
 */
function RequirementBadge({
  course,
  showCategory,
}: {
  course: CourseSummary;
  showCategory?: boolean;
}) {
  if (!course.requirement) return null;
  const required = course.requirement === "compulsory";
  return (
    <span
      className={`ml-2 rounded px-1.5 py-0.5 text-[11px] align-middle ${
        required
          ? "bg-slate-900 text-white"
          : "bg-slate-100 text-slate-600 border border-slate-200"
      }`}
    >
      {required ? "Required" : "Elective"}
      {showCategory && course.requirement_category
        ? ` · ${course.requirement_category}`
        : ""}
    </span>
  );
}

function SubjectGrid({
  title,
  subjects,
  onOpen,
  muted,
}: {
  title: string;
  subjects: Subject[];
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
