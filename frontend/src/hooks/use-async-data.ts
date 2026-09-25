"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface State<T> {
  key: string;
  data: T;
  error: string | null;
}

/**
 * Generic async data hook.
 *
 * The loader is kept in a ref so callers can pass an inline closure without
 * re-triggering the request; re-fetching is driven by the `key` (and manual
 * `reload`). While a new key is in flight, `loading` is true and the previous
 * data is retained.
 */
export function useAsyncData<T>(
  key: string,
  loader: (signal: AbortSignal) => Promise<T>,
  initial: T,
): { data: T; loading: boolean; error: string | null; reload: () => void } {
  const [state, setState] = useState<State<T>>({ key: "", data: initial, error: null });
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);

  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const data = await loaderRef.current(controller.signal);
        if (!controller.signal.aborted) setState({ key, data, error: null });
      } catch (cause) {
        if (!controller.signal.aborted) {
          setState((previous) => ({
            key,
            data: previous.data,
            error: cause instanceof Error ? cause.message : "Request failed",
          }));
        }
      }
    })();
    return () => controller.abort();
  }, [key, nonce]);

  const settled = state.key === key;
  const reload = useCallback(() => setNonce((value) => value + 1), []);

  return {
    data: state.data,
    loading: !settled,
    error: settled ? state.error : null,
    reload,
  };
}
