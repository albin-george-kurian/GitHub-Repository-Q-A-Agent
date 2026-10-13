/** Product mark: a git branch line bent into a question mark, with commit nodes.
 *  Monochrome; colors come from CSS (.logo-*), so it inverts with the theme. */
export default function Logo({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={className ? `logo ${className}` : "logo"}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="Repo Q&A"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect className="logo-bg" width="48" height="48" rx="11" />
      <path
        className="logo-stroke"
        d="M16.5 18.5a7.5 7.5 0 1 1 11.2 6.5c-2.3 1.3-3.7 2.8-3.7 5.6v1.4"
        fill="none"
        strokeWidth="3.4"
        strokeLinecap="round"
      />
      <circle className="logo-node" cx="16.5" cy="18.5" r="3.3" strokeWidth="2.4" />
      <circle className="logo-node" cx="31.5" cy="18.5" r="3.3" strokeWidth="2.4" />
      <circle className="logo-dot" cx="24" cy="39.5" r="3.3" />
    </svg>
  );
}
