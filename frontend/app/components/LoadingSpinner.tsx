/**
 * LoadingSpinner — accessible animated spinner.
 */

interface LoadingSpinnerProps {
  /** Screen-reader label. Defaults to "Loading…" */
  label?: string;
  /** Tailwind size class for width/height. Defaults to "h-6 w-6". */
  size?: string;
}

export default function LoadingSpinner({
  label = "Loading…",
  size = "h-6 w-6",
}: LoadingSpinnerProps) {
  return (
    <span
      role="status"
      aria-label={label}
      className="inline-flex items-center justify-center"
    >
      <svg
        className={`animate-spin text-indigo-600 ${size}`}
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span className="sr-only">{label}</span>
    </span>
  );
}
