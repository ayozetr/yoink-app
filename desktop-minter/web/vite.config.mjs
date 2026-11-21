// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres
//
// Bundles main.js (+ bgutils-js) into a single self-contained IIFE, so the native
// UI's hidden WebView can run the PO-token minter from one embedded script with no
// module resolution. Run from the repo root (where node_modules lives):
//
//   node_modules/.bin/vite build --config desktop-minter/web/vite.config.mjs
//
// Output: desktop-minter/web/dist/minter.js (committed; the Rust crate embeds it).

import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  publicDir: false,
  build: {
    lib: {
      entry: resolve("desktop-minter/web/main.js"),
      formats: ["iife"],
      name: "YoinkMinter",
      fileName: () => "minter.js",
    },
    outDir: resolve("desktop-minter/web/dist"),
    rollupOptions: { output: { inlineDynamicImports: true } },
    target: "esnext",
    minify: true,
    emptyOutDir: true,
  },
});
