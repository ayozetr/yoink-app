interface ProgressBarProps {
  /** Completion percentage, 0-100. */
  percent: number;
}

/** Slim gradient progress bar used by the active-download indicator. */
export function ProgressBar({ percent }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, percent));

  return (
    <div className="h-3 rounded-full bg-surface overflow-hidden">
      <div
        className="h-full rounded-full bg-gradient-to-r from-violet-600 to-blue-500 transition-[width] duration-300"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
