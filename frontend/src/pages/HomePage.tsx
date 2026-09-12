import {
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useAuth } from "../lib/auth";
import Logo from "../components/Logo";
import BrowsePage from "./BrowsePage";
import CoursePage from "./CoursePage";
import ModerationPage from "./ModerationPage";
import ProfilePage from "./ProfilePage";
import SubjectPage from "./SubjectPage";

/**
 * The app shell and its routes.
 *
 * Which page you are on lives in the URL, not in component state. That is what
 * makes a refresh keep your place, the back button work, and a course page
 * something you can paste into the Telegram group.
 */
export default function HomePage() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <Link to="/" className="text-lg text-slate-900 hover:text-slate-600">
            <Logo />
          </Link>
          <div className="flex items-center gap-3 text-sm">
            {/* Convenience only: the moderation API checks permission itself,
                so hiding this link is not what keeps students out. */}
            {user?.can_moderate && (
              <Link
                to="/moderation"
                className="text-slate-600 hover:text-slate-900 font-medium"
              >
                Review queue
              </Link>
            )}
            <Link to="/profile" className="text-slate-600 hover:text-slate-900">
              {user?.email}
            </Link>
            <button
              onClick={() => logout()}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-100 transition"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <Routes>
        <Route path="/" element={<BrowseRoute />} />
        <Route path="/subjects/:slug" element={<SubjectRoute />} />
        <Route path="/courses/:code" element={<CourseRoute />} />
        <Route path="/moderation" element={<ModerationRoute />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="*" element={<BrowseRoute />} />
      </Routes>
    </div>
  );
}

/**
 * The selected major is a search param rather than state.
 *
 * It survives a refresh, and it makes "the CS view of this" a link someone can
 * send to a classmate. Defaults to the student's own major when absent.
 */
function useMajor(): [string | null, (slug: string | null) => void] {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();

  const raw = params.get("major");
  // "all" is stored explicitly so clearing the filter is distinguishable from
  // never having chosen one -- otherwise it would snap back to their own major.
  const major = raw === null ? user?.major?.slug ?? null : raw === "all" ? null : raw;

  const setMajor = (slug: string | null) => {
    const next = new URLSearchParams(params);
    next.set("major", slug ?? "all");
    setParams(next, { replace: true });
  };

  return [major, setMajor];
}

function BrowseRoute() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [major, setMajor] = useMajor();

  return (
    <BrowsePage
      myMajor={major}
      ownMajor={user?.major?.slug ?? null}
      onMajorChange={setMajor}
      onOpenSubject={(slug) => navigate(`/subjects/${slug}`)}
      onOpenCourse={(code) => navigate(`/courses/${code}`)}
    />
  );
}

function SubjectRoute() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const [major] = useMajor();

  return (
    <SubjectPage
      slug={slug}
      major={major}
      onOpenCourse={(code) => navigate(`/courses/${code}`)}
      onBack={() => navigate(-1)}
    />
  );
}

function ModerationRoute() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // A student who types the URL is sent home rather than shown a page that
  // can only fail. The API refuses them regardless -- this is about not
  // presenting a dead end, not about access.
  if (!user?.can_moderate) return <Navigate to="/" replace />;

  return <ModerationPage onOpenCourse={(code) => navigate(`/courses/${code}`)} />;
}

function CourseRoute() {
  const { code = "" } = useParams();
  const navigate = useNavigate();

  return <CoursePage code={code} onBack={() => navigate(-1)} />;
}
