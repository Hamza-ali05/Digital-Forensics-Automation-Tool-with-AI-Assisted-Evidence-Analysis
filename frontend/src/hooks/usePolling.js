import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Poll ``fetchFunction`` on an interval while enabled.
 *
 * @param {Function} fetchFunction Async fetcher (no args).
 * @param {number} intervalMs Poll interval in milliseconds.
 * @param {boolean} [enabled=true] When false, polling is paused.
 */
export default function usePolling(fetchFunction, intervalMs, enabled = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isPolling, setIsPolling] = useState(Boolean(enabled));

  const fnRef = useRef(fetchFunction);
  fnRef.current = fetchFunction;
  const intervalRef = useRef(null);
  const mountedRef = useRef(true);

  const tick = useCallback(async (isInitial) => {
    if (isInitial) {
      setLoading(true);
    }
    try {
      const result = await fnRef.current();
      const payload =
        result &&
        typeof result === "object" &&
        Object.prototype.hasOwnProperty.call(result, "data") &&
        Object.prototype.hasOwnProperty.call(result, "status") &&
        Object.prototype.hasOwnProperty.call(result, "config")
          ? result.data
          : result;
      if (mountedRef.current) {
        setData(payload);
        setError(null);
        setLoading(false);
      }
      return payload;
    } catch (err) {
      if (mountedRef.current) {
        setError(err);
        setLoading(false);
      }
      return undefined;
    }
  }, []);

  const clearTimer = useCallback(() => {
    if (intervalRef.current != null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const stopPolling = useCallback(() => {
    clearTimer();
    setIsPolling(false);
  }, [clearTimer]);

  const startPolling = useCallback(() => {
    setIsPolling(true);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimer();
    };
  }, [clearTimer]);

  useEffect(() => {
    clearTimer();

    if (!enabled || !isPolling) {
      return undefined;
    }

    let cancelled = false;

    (async () => {
      if (!cancelled) {
        await tick(true);
      }
    })();

    const ms = Math.max(250, Number(intervalMs) || 5000);
    intervalRef.current = window.setInterval(() => {
      tick(false);
    }, ms);

    return () => {
      cancelled = true;
      clearTimer();
    };
  }, [enabled, isPolling, intervalMs, tick, clearTimer]);

  return {
    data,
    loading,
    error,
    isPolling: Boolean(enabled && isPolling),
    stopPolling,
    startPolling,
  };
}
