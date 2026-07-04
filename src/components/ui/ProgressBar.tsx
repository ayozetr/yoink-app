interface ProgressBarProps {
  /** Completion percentage, 0-100. */
  percent: number;
  /** Extra classes for the track (e.g. "mt-1 h-1" for a slim inline bar);
   * defaults to the standard "h-3" height. */
  className?: string;
}

/** Slim gradient progress bar used by the active-download indicators. */
export function ProgressBar({ percent, className = "h-3" }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, percent));

  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={`overflow-hidden rounded-full bg-surface ${className}`}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-violet-600 to-blue-500 transition-[width] duration-300"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
