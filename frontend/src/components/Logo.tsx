export default function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex flex-col items-center ${className}`}>
      <svg
        viewBox="0 0 100 100"
        className="h-[2em] w-[2em] shrink-0"
        fill="currentColor"
        aria-hidden="true"
      >
        <polygon points="50,8 92,36 8,36" fill="none" stroke="currentColor" strokeWidth="4" />
        <text
          x="50"
          y="33"
          textAnchor="middle"
          fontFamily="'Libre Caslon Text', Georgia, serif"
          fontWeight="700"
          fontSize="12"
        >
          GJU
        </text>
        <rect x="10" y="40" width="80" height="6" />
        <rect x="14" y="50" width="8" height="32" />
        <rect x="30" y="50" width="8" height="32" />
        <rect x="46" y="50" width="8" height="32" />
        <rect x="62" y="50" width="8" height="32" />
        <rect x="78" y="50" width="8" height="32" />
        <rect x="8" y="86" width="84" height="6" />
      </svg>
      <span
        className="mt-1 text-[0.32em] uppercase tracking-[0.35em]"
        style={{ fontFamily: "'Libre Caslon Text', Georgia, serif" }}
      >
        Archive
      </span>
    </span>
  );
}
