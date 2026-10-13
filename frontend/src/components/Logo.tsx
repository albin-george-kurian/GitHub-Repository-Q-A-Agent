import { useId } from "react";

/** Product mark: a git branch line bent into a question mark, with commit nodes. */
export default function Logo({ size = 32, className }: { size?: number; className?: string }) {
  const gradientId = useId();
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="Repo Q&A"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#a855f7" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="13" fill={`url(#${gradientId})`} />
      <path
        d="M16.5 18.5a7.5 7.5 0 1 1 11.2 6.5c-2.3 1.3-3.7 2.8-3.7 5.6v1.4"
        fill="none"
        stroke="#fff"
        strokeWidth="3.4"
        strokeLinecap="round"
      />
      <circle cx="16.5" cy="18.5" r="3.3" fill={`url(#${gradientId})`} stroke="#fff" strokeWidth="2.4" />
      <circle cx="31.5" cy="18.5" r="3.3" fill={`url(#${gradientId})`} stroke="#fff" strokeWidth="2.4" />
      <circle cx="24" cy="39.5" r="3.3" fill="#fff" />
    </svg>
  );
}
