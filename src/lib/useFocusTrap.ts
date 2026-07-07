import { useEffect, useRef } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), ' +
  'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Trap keyboard focus inside a dialog while it's open: move focus into the
 * dialog on mount, cycle Tab/Shift+Tab within it, and restore focus to the
 * previously-focused element on close. Returns a ref to attach to the dialog
 * container (give it `tabIndex={-1}` so it can hold focus as a fallback).
 */
export function useFocusTrap<T extends HTMLElement>(active = true) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const container = ref.current;
    if (!active || !container) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const items = () =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null,
      );

    const focusables = items();
    (focusables[0] ?? container).focus();

    // When nothing is focusable yet — a dialog whose fields mount later (a cold
    // React.lazy chunk, or content gated behind a fetch) — focus parks on the
    // container. Watch for the first field to appear and move focus to it once it
    // does, as long as focus is still on the container (don't yank it from the user).
    let fieldWatcher: MutationObserver | null = null;
    if (!focusables.length) {
      fieldWatcher = new MutationObserver(() => {
        const first = items()[0];
        if (first && document.activeElement === container) {
          first.focus();
          fieldWatcher?.disconnect();
          fieldWatcher = null;
        }
      });
      fieldWatcher.observe(container, { childList: true, subtree: true });
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const focusables = items();
      if (!focusables.length) {
        event.preventDefault();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    container.addEventListener("keydown", onKey);
    return () => {
      container.removeEventListener("keydown", onKey);
      fieldWatcher?.disconnect();
      previouslyFocused?.focus?.();
    };
  }, [active]);

  return ref;
}
