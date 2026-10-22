// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

// Ensure a working `localStorage` for tests that opt into the jsdom environment.
// Newer Node (22+) ships an experimental global `localStorage` that is inert
// without `--localstorage-file`, and under it jsdom may not install its own —
// leaving `localStorage` undefined or throwing. A tiny in-memory polyfill keeps
// the store tests (presets/queue/batch) deterministic across Node versions.
function installLocalStorage(): void {
  let works = false;
  try {
    const ls = (globalThis as { localStorage?: Storage }).localStorage;
    if (ls) {
      ls.setItem("__probe__", "1");
      ls.removeItem("__probe__");
      works = true;
    }
  } catch {
    works = false;
  }
  if (works) return;

  const store = new Map<string, string>();
  const polyfill: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => void store.delete(key),
    setItem: (key: string, value: string) => void store.set(key, String(value)),
  };
  Object.defineProperty(globalThis, "localStorage", {
    value: polyfill,
    configurable: true,
    writable: true,
  });
}

installLocalStorage();
