// Catalog API: subjects, courses and their per-semester offerings.
// These endpoints are public (the catalog is browsable without signing in);
// only downloads require a GJU account.

export interface Subject {
  id: number;
  name: string;
  slug: string;
  is_university_wide: boolean;
  course_count: number;
  prefixes: string[];
}

export type Requirement = "compulsory" | "elective";

export interface CourseSummary {
  id: number;
  code: string;
  display_code: string;
  name: string;
  credit_hours: number | null;
  slug: string;
  // Only set when the request named a major, since a course is compulsory
  // *for* a degree, not in itself. Null also covers courses that major's
  // study plan simply does not list.
  requirement: Requirement | null;
  requirement_category: "university" | "school" | "program" | "remedial" | null;
}

export interface Term {
  id: number;
  season: string;
  year: number;
  is_current: boolean;
  label: string;
}

export interface InstructorSummary {
  id: number;
  full_name: string;
  title: string;
}

export interface Offering {
  id: number;
  course_code: string;
  course_name: string;
  term: Term;
  section_number: string;
  campus: string;
  language: string;
  instructors: InstructorSummary[];
}

export interface CourseDetail extends CourseSummary {
  description: string;
  level: number | null;
  majors: { id: number; code: string; name: string; slug: string }[];
  prerequisites: CourseSummary[];
  offerings: Offering[];
}

export interface Major {
  id: number;
  code: string;
  name: string;
  slug: string;
  course_count: number;
}

interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: "include" });
  if (!response.ok) {
    throw new Error(`${response.status} on ${path}`);
  }
  return (await response.json()) as T;
}

export const catalog = {
  subjects(): Promise<Subject[]> {
    // Deliberately unpaginated server-side — 28 rows, shown as one list.
    return getJson<Subject[]>("/api/subjects/");
  },

  subject(slug: string): Promise<Subject> {
    return getJson<Subject>(`/api/subjects/${slug}/`);
  },

  majors(): Promise<Page<Major>> {
    return getJson<Page<Major>>("/api/majors/");
  },

  courses(params: {
    subject?: string;
    major?: string;
    search?: string;
    requirement?: Requirement;
    page?: number;
  }): Promise<Page<CourseSummary>> {
    const query = new URLSearchParams();
    if (params.subject) query.set("subject", params.subject);
    if (params.major) query.set("major", params.major);
    if (params.search) query.set("search", params.search);
    // Ignored by the API without a major, which is correct rather than an
    // error: "compulsory for nobody in particular" has no meaning.
    if (params.requirement) query.set("requirement", params.requirement);
    if (params.page && params.page > 1) query.set("page", String(params.page));
    return getJson<Page<CourseSummary>>(`/api/courses/?${query}`);
  },

  course(code: string): Promise<CourseDetail> {
    return getJson<CourseDetail>(`/api/courses/${code}/`);
  },
};

/** Group a course's offerings by term, newest first — the "course history". */
export function byTerm(offerings: Offering[]): [string, Offering[]][] {
  const groups = new Map<string, Offering[]>();
  for (const offering of offerings) {
    const key = offering.term.label;
    const list = groups.get(key);
    if (list) list.push(offering);
    else groups.set(key, [offering]);
  }
  const order = { summer: 0, second: 1, first: 2 } as Record<string, number>;
  return [...groups.entries()].sort((a, b) => {
    const x = a[1][0].term;
    const y = b[1][0].term;
    return y.year - x.year || (order[y.season] ?? 0) - (order[x.season] ?? 0);
  });
}

/** Distinct instructors across a course's offerings, most recent term first. */
export function instructorsOf(offerings: Offering[]): string[] {
  const seen = new Set<string>();
  for (const [, group] of byTerm(offerings)) {
    for (const offering of group) {
      for (const person of offering.instructors) seen.add(person.full_name);
    }
  }
  return [...seen];
}
