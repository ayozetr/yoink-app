/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend API base URL; overridable for the dev / packaged setups. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Injected at build time from package.json (see vite.config.ts). */
declare const __APP_VERSION__: string;
