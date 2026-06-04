import {
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Check, ChevronDown } from "lucide-react";

export interface SelectOption {
  value: string;
  label: string;
  /** When true, the option is shown but cannot be selected. */
  disabled?: boolean;
  /** Render as a non-selectable section header instead of an option. */
  header?: boolean;
}

interface SelectProps {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  disabled?: boolean;
  /** Classes for the trigger button (e.g. the shared input style). */
  className?: string;
}

/**
 * Dark, app-styled dropdown replacing the native `<select>`, whose popup the OS
 * renders unstyled (the "square, ugly" menu). The list is positioned with
 * `fixed` from the trigger's rect so it is never clipped by a scrollable modal,
 * and it closes on outside click (capture phase, to survive a modal panel's
 * `stopPropagation`), scroll, resize, or Escape.
 */
export function Select({
  value,
  options,
  onChange,
  ariaLabel,
  disabled = false,
  className = "",
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);
  const [activeIndex, setActiveIndex] = useState(-1);

  const selected = options.find((o) => o.value === value);
  const selectable = () =>
    options.map((o, i) => (o.header || o.disabled ? -1 : i)).filter((i) => i >= 0);

  // Anchor the floating list to the trigger each time it opens.
  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    setRect({ top: r.bottom + 4, left: r.left, width: r.width });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        triggerRef.current?.contains(target) ||
        dropdownRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    };
    const onScroll = (event: Event) => {
      // Scrolling inside the dropdown's own list must NOT close it; only a
      // scroll outside (which would move the anchored trigger) should dismiss.
      if (dropdownRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    const dismiss = () => setOpen(false);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("click", onPointer, true);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", dismiss);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", onPointer, true);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", dismiss);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Keep the highlighted option scrolled into view as it changes.
  useEffect(() => {
    if (open) activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open]);

  // Open the list and highlight the current value (for keyboard nav).
  const openList = () => {
    setActiveIndex(options.findIndex((o) => o.value === value));
    setOpen(true);
  };

  const choose = (next: string) => {
    onChange(next);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const moveActive = (delta: number) => {
    const sel = selectable();
    if (!sel.length) return;
    const cur = sel.indexOf(activeIndex);
    const pos =
      cur < 0
        ? delta > 0
          ? 0
          : sel.length - 1
        : Math.max(0, Math.min(sel.length - 1, cur + delta));
    setActiveIndex(sel[pos]);
  };

  const onKeyDown = (event: ReactKeyboardEvent) => {
    if (disabled) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) openList();
      else moveActive(event.key === "ArrowDown" ? 1 : -1);
    } else if (open && event.key === "Enter") {
      event.preventDefault();
      if (activeIndex >= 0) choose(options[activeIndex].value);
    } else if (open && (event.key === "Home" || event.key === "End")) {
      event.preventDefault();
      const sel = selectable();
      if (sel.length) setActiveIndex(event.key === "Home" ? sel[0] : sel[sel.length - 1]);
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
        className={`flex cursor-pointer items-center justify-between gap-2 ${className}`}
      >
        <span className="truncate">{selected?.label ?? ""}</span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-zinc-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && rect && (
        <div
          ref={dropdownRef}
          role="listbox"
          style={{
            position: "fixed",
            top: rect.top,
            left: rect.left,
            width: rect.width,
          }}
          className="z-[100] max-h-60 overflow-y-auto rounded-xl border border-white/10 bg-[#1a1d27] p-1 shadow-xl"
        >
          {options.map((option, i) => {
            if (option.header) {
              return (
                <div
                  key={option.value}
                  className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500"
                >
                  {option.label}
                </div>
              );
            }
            const active = option.value === value;
            const highlighted = i === activeIndex;
            const isDisabled = option.disabled ?? false;
            return (
              <button
                key={option.value}
                ref={highlighted ? activeRef : undefined}
                type="button"
                role="option"
                aria-selected={active}
                aria-disabled={isDisabled}
                disabled={isDisabled}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => choose(option.value)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  isDisabled
                    ? "cursor-not-allowed text-zinc-500"
                    : active
                      ? "bg-violet-600/30 text-white"
                      : highlighted
                        ? "bg-white/10 text-white"
                        : "text-zinc-200 hover:bg-white/10"
                }`}
              >
                <span className="truncate">{option.label}</span>
                {active && (
                  <Check size={15} className="shrink-0 text-violet-300" />
                )}
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}
