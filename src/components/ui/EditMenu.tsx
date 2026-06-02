import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

type EditTarget = HTMLInputElement | HTMLTextAreaElement;

interface MenuState {
  x: number;
  y: number;
  target: EditTarget;
}

/** Set an input's value the way React expects, so controlled state updates. */
function setReactValue(el: EditTarget, value: string) {
  const proto =
    el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  setter?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function isEditable(el: HTMLElement | null): EditTarget | null {
  const field = el?.closest("input, textarea") as EditTarget | null;
  if (!field || field.disabled || field.readOnly) return null;
  if (field instanceof HTMLInputElement) {
    const t = field.type;
    if (t === "checkbox" || t === "radio" || t === "range") return null;
  }
  return field;
}

/**
 * Replaces the webview's native context menu (which exposes Print / Save as /
 * Reload) with a minimal Cut / Copy / Paste menu — and only on text fields.
 * Right-clicking anywhere else shows nothing.
 */
export function EditMenu() {
  const { t } = useTranslation();
  const [menu, setMenu] = useState<MenuState | null>(null);

  useEffect(() => {
    const close = () => setMenu(null);
    const onContextMenu = (event: MouseEvent) => {
      event.preventDefault(); // kill the native menu everywhere
      const field = isEditable(event.target as HTMLElement | null);
      if (field) {
        field.focus();
        setMenu({ x: event.clientX, y: event.clientY, target: field });
      } else {
        setMenu(null);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("contextmenu", onContextMenu);
    // Close on the capture phase: modals stopPropagation() on their panel to
    // avoid closing when you click inside, which would also swallow a bubbling
    // "click" before it reaches window. Capture runs window -> target first.
    window.addEventListener("click", close, true);
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("contextmenu", onContextMenu);
      window.removeEventListener("click", close, true);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  if (!menu) return null;

  const { target } = menu;
  const start = target.selectionStart ?? 0;
  const end = target.selectionEnd ?? 0;
  const hasSelection = start !== end;

  const copy = async () => {
    const text = target.value.slice(start, end);
    if (text) await navigator.clipboard.writeText(text);
  };
  const cut = async () => {
    const text = target.value.slice(start, end);
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setReactValue(target, target.value.slice(0, start) + target.value.slice(end));
    target.setSelectionRange(start, start);
  };
  const paste = async () => {
    const text = await navigator.clipboard.readText();
    setReactValue(
      target,
      target.value.slice(0, start) + text + target.value.slice(end),
    );
    const pos = start + text.length;
    target.setSelectionRange(pos, pos);
  };

  const run = (action: () => Promise<void>) => (e: React.MouseEvent) => {
    e.preventDefault(); // keep the field's focus/selection
    void action().finally(() => setMenu(null));
  };

  const itemClass =
    "w-full px-3 py-1.5 text-left transition-colors hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent";

  return (
    <div
      style={{ left: menu.x, top: menu.y }}
      className="fixed z-[200] min-w-[150px] overflow-hidden rounded-lg border border-white/10 bg-[#1a1d27] py-1 text-sm text-zinc-200 shadow-xl"
    >
      <button type="button" disabled={!hasSelection} onMouseDown={run(cut)} className={itemClass}>
        {t("common.cut")}
      </button>
      <button type="button" disabled={!hasSelection} onMouseDown={run(copy)} className={itemClass}>
        {t("common.copy")}
      </button>
      <button type="button" onMouseDown={run(paste)} className={itemClass}>
        {t("common.paste")}
      </button>
    </div>
  );
}
