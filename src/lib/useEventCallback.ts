import { useCallback, useLayoutEffect, useRef } from "react";

/**
 * A callback with a stable identity that always invokes the latest `fn`. Unlike
 * `useCallback`, it needs no dependency list and never goes stale — ideal for event
 * handlers passed to `React.memo` children, so a parent that re-renders often (e.g.
 * one holding download-progress state that ticks several times a second) doesn't
 * force those children to reconcile.
 */
export function useEventCallback<A extends unknown[], R>(
  fn: (...args: A) => R,
): (...args: A) => R {
  const ref = useRef(fn);
  useLayoutEffect(() => {
    ref.current = fn;
  });
  return useCallback((...args: A) => ref.current(...args), []);
}
