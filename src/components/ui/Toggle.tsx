import type { ReactNode } from "react";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Visible text shown to the left of the switch. */
  label: string;
  /** Optional icon rendered before the label. */
  icon?: ReactNode;
  /** Optional element rendered after the label (e.g. a help "?" popover). */
  help?: ReactNode;
  /** Extra classes for the container (e.g. "w-full" to stretch in a column). */
  className?: string;
}

/**
 * A labelled on/off switch. Only the switch itself is interactive — clicking the
 * label area does nothing, so adjacent controls (like a help popover) work too.
 */
export function Toggle({
  checked,
  onChange,
  label,
  icon,
  help,
  className,
}: ToggleProps) {
  return (
    <div
      className={`flex min-h-11 items-center justify-between gap-3 rounded-xl border border-white/10 bg-surface px-4 py-2 text-sm ${
        className ?? ""
      }`}
    >
      {/* min-w-0 + wrapping so a long label (some locales run 40+ chars) grows the
          row height instead of overflowing the fixed box and colliding with the
          switch / the next toggle. */}
      <span className="flex min-w-0 items-center gap-2">
        {icon}
        <span className="min-w-0 break-words">{label}</span>
        {help}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
          checked ? "bg-violet-500" : "bg-white/15"
        }`}
      >
        <span
          className={`inline-block size-4 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </button>
    </div>
  );
}
