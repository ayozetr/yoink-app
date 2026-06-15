/**
 * Resolves the local backend's base URL (host + port) once at startup.
 *
 * The backend normally listens on port 8756, but the packaged desktop app falls
 * back to an OS-assigned free port when 8756 is already taken by another program.
 * In that case the Tauri shell knows the real port and exposes it through the
 * `backend_port` command; we query it before the first request so every call —
 * REST and WebSocket — targets the right port.
 *
 * Resolution order:
 *   1. `VITE_API_BASE_URL` (build-time override, e.g. `scripts/dev.py` custom port)
 *   2. the `backend_port` the Tauri shell picked at launch (desktop app)
 *   3. the default `http://127.0.0.1:8756/api`
 *
 * Outside the Tauri runtime (plain browser dev) steps 2 is skipped and the
 * default — or the build-time override — is used.
 */

const BUILD_OVERRIDE: string | undefined = import.meta.env.VITE_API_BASE_URL;
const DEFAULT_BASE = "http://127.0.0.1:8756/api";

let base = BUILD_OVERRIDE ?? DEFAULT_BASE;

/** The resolved API base (e.g. `http://127.0.0.1:8756/api`). */
export function getApiBase(): string {
  return base;
}

/** Override the base explicitly (used by tests). */
export function setApiBase(next: string): void {
  base = next;
}

/** True when running inside the Tauri webview (vs. a plain browser). */
function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * Resolve the base URL once, before the app renders.
 *
 * A build-time override always wins; otherwise, inside the desktop shell, ask
 * Tauri which port the backend actually bound. Any failure leaves the default
 * in place, so the web build and dev mode are unaffected.
 */
export async function resolveApiBase(): Promise<void> {
  if (BUILD_OVERRIDE || !isTauri()) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const port = await invoke<number>("backend_port");
    if (port && port > 0) base = `http://127.0.0.1:${port}/api`;
  } catch {
    // Not in Tauri, or the command is unavailable — keep the default port.
  }
}
