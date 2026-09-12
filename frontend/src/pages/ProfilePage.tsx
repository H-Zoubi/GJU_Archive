import { useAuth } from "../lib/auth";

/**
 * A student's own info, filled in automatically from MyGJU at signup (or at
 * their next login, if it wasn't captured yet) -- see
 * accounts.services.refresh_profile_from_mygju on the backend. Nothing here
 * is editable; there is no form because there is nothing to submit.
 */
export default function ProfilePage() {
  const { user } = useAuth();
  if (!user) return null;

  const rows: Array<[string, string]> = [
    ["Email", user.email],
    ["Role", user.role],
    ["GJU verified", user.is_gju_verified ? "Yes" : "No"],
    ["Major", user.major?.name ?? "Not yet known"],
    ["Entry year", user.entry_year != null ? String(user.entry_year) : "Not yet known"],
  ];

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">My profile</h1>
      <p className="text-slate-500 dark:text-slate-400 mt-1">
        Major and entry year are pulled from MyGJU automatically -- there is
        nothing to fill in by hand.
      </p>

      <dl className="mt-6 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between px-4 py-3">
            <dt className="text-sm text-slate-500 dark:text-slate-400">{label}</dt>
            <dd className="text-sm font-medium text-slate-900 dark:text-slate-100">{value}</dd>
          </div>
        ))}
      </dl>

      {(user.major == null || user.entry_year == null) && (
        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
          Some info is still missing -- it fills in automatically the next
          time you sign in.
        </p>
      )}
    </div>
  );
}
