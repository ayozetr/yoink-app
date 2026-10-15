import { useEffect, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { useFocusTrap } from "../../lib/useFocusTrap";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
}

/**
 * Right-side slide-over panel (Flat Minimal). Used for secondary flows — like
 * editing audio tags — so a complex form doesn't expand inline and shove the
 * main view around. Backdrop click + Escape close it; focus is trapped inside.
 *
 * It slides (and the backdrop fades) on both open and close: when `open` turns
 * false it stays mounted playing the exit animation, then unmounts itself on
 * animationend — CSS-keyframe driven, matching the toast pattern.
 */
export function Drawer({ open, onClose, title, children }: DrawerProps) {
  const ref = useFocusTrap<HTMLDivElement>(open);
  const [mounted, setMounted] = useState(open);

  // Opening again after a close: remount. Setting state during render (guarded)
  // is the supported way to react to a prop change without an extra paint.
  if (open && !mounted) setMounted(true);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      // Let an inner dropdown/popover consume Escape first.
      if (
        event.key === "Escape" &&
        !document.querySelector('[role="listbox"], [data-popover="true"]')
      ) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!mounted) return null;

  return (
    <div
      role="presentation"
      onClick={onClose}
      className={`fixed inset-0 z-50 flex justify-end bg-black/60 ${
        open ? "backdrop-in" : "backdrop-out"
      }`}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        // Unmount once the exit slide finishes (only the panel's own animation,
        // never an inner element's that bubbled up).
        onAnimationEnd={(event) => {
          if (!open && event.target === event.currentTarget) setMounted(false);
        }}
        className={`flex h-full w-full max-w-md flex-col border-l border-line/10 bg-surface shadow-2xl shadow-black/40 outline-none ${
          open ? "drawer-in" : "drawer-out"
        }`}
      >
        <div className="flex items-center justify-between border-b border-line/10 px-5 py-4">
          <div className="min-w-0 truncate font-semibold text-fg">{title}</div>
          <button
            type="button"
            onClick={onClose}
            className="-mr-1 shrink-0 text-fg-faint transition hover:text-fg"
            aria-label="×"
          >
            <X size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
