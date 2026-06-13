/**
 * Compile-time guarantee that every locale provides the full English key set.
 *
 * Locales are loaded lazily at runtime (see `index.ts`), so they're no longer
 * statically imported there — which would otherwise be where TypeScript caught a
 * missing key. This module re-establishes that check with **type-only** imports
 * (`typeof import(...)`), so it adds zero runtime code / bundle weight while still
 * failing `tsc` if any locale drops a key. English literal values are widened to
 * `string`, so only the key structure must match.
 */

import type { en } from "./locales/en";

type Stringify<T> = {
  [K in keyof T]: T[K] extends string ? string : Stringify<T[K]>;
};
type Translation = Stringify<typeof en>;

// `Assert<T>` only compiles when T has every key of the English shape.
type Assert<T extends Translation> = T;

export type LocaleCompletenessChecks = [
  Assert<typeof import("./locales/es").es>,
  Assert<typeof import("./locales/fr").fr>,
  Assert<typeof import("./locales/de").de>,
  Assert<typeof import("./locales/it").it>,
  Assert<typeof import("./locales/pt").pt>,
  Assert<typeof import("./locales/ru").ru>,
  Assert<typeof import("./locales/pl").pl>,
  Assert<typeof import("./locales/uk").uk>,
  Assert<typeof import("./locales/id").id>,
  Assert<typeof import("./locales/hi").hi>,
  Assert<typeof import("./locales/zh").zh>,
  Assert<typeof import("./locales/ja").ja>,
  Assert<typeof import("./locales/ko").ko>,
];
