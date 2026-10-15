import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import {
  dismissToast,
  subscribeToasts,
  type ToastItem,
  type ToastKind,
} from "../../lib/toast";

const ICONS: Record<ToastKind, typeof Info> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

const ICON_COLORS: Record<ToastKind, string> = {
  success: "text-emerald-400",
  error: "text-red-400",
  info: "text-accent-soft",
};

/**
 * Floating toast stack (bottom-right). Replaces the old inline success/error
 * banners that reflowed the layout — a toast floats above everything and
 * auto-dismisses. Mounted once at the app root; driven by the `toast` store.
 */
export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => subscribeToasts(setItems), []);

  if (items.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
      {items.map((item) => (
        <ToastRow key={item.id} item={item} />
      ))}
    </div>
  );
}

function ToastRow({ item }: { item: ToastItem }) {
  const Icon = ICONS[item.kind];

  useEffect(() => {
    if (item.duration <= 0) return;
    const timer = window.setTimeout(() => dismissToast(item.id), item.duration);
    return () => window.clearTimeout(timer);
  }, [item.id, item.duration]);

  return (
    <div className="toast-in pointer-events-auto flex items-start gap-3 rounded-xl border border-line/10 bg-surface px-4 py-3 shadow-lg shadow-black/20">
      <Icon size={18} className={`mt-0.5 shrink-0 ${ICON_COLORS[item.kind]}`} />
      <p className="min-w-0 flex-1 break-words text-sm text-fg">{item.message}</p>
      {item.action && (
        <button
          type="button"
          onClick={() => {
            item.action!.onClick();
            dismissToast(item.id);
          }}
          className="shrink-0 whitespace-nowrap text-sm font-medium text-accent-soft transition hover:text-accent"
        >
          {item.action.label}
        </button>
      )}
      <button
        type="button"
        onClick={() => dismissToast(item.id)}
        className="-mr-1 shrink-0 text-fg-faint transition hover:text-fg"
        aria-label="×"
      >
        <X size={15} />
      </button>
    </div>
  );
}
