// Lightweight toast notifications — a tiny module-level pub/sub store with an
// imperative API (`toast.success(...)`), rendered by the <Toaster/> mounted once
// in App. Replaces the old inline green "download complete" banners that pushed
// the layout around (Flat Minimal redesign): a toast floats, it doesn't reflow.

export type ToastKind = "success" | "error" | "info";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastOptions {
  kind?: ToastKind;
  /** Auto-dismiss after this many ms; 0 keeps it until dismissed. Default 4500. */
  duration?: number;
  /** Optional single action button (e.g. "Open folder"). */
  action?: ToastAction;
}

export interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
  duration: number;
  action?: ToastAction;
}

type Listener = (toasts: ToastItem[]) => void;

let toasts: ToastItem[] = [];
const listeners = new Set<Listener>();
let nextId = 1;

function emit(): void {
  for (const listener of listeners) listener(toasts);
}

/** Subscribe to the toast list; immediately called with the current list. */
export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener);
  listener(toasts);
  return () => {
    listeners.delete(listener);
  };
}

/** Remove a toast (auto-dismiss timer, close button, or action click). */
export function dismissToast(id: number): void {
  toasts = toasts.filter((item) => item.id !== id);
  emit();
}

/** Show a toast; returns its id. */
export function showToast(message: string, options: ToastOptions = {}): number {
  const id = nextId++;
  toasts = [
    ...toasts,
    {
      id,
      message,
      kind: options.kind ?? "info",
      duration: options.duration ?? 4500,
      action: options.action,
    },
  ];
  emit();
  return id;
}

/** Ergonomic helpers. */
export const toast = {
  show: showToast,
  success: (message: string, options?: Omit<ToastOptions, "kind">) =>
    showToast(message, { ...options, kind: "success" }),
  error: (message: string, options?: Omit<ToastOptions, "kind">) =>
    showToast(message, { ...options, kind: "error" }),
  info: (message: string, options?: Omit<ToastOptions, "kind">) =>
    showToast(message, { ...options, kind: "info" }),
  dismiss: dismissToast,
};
