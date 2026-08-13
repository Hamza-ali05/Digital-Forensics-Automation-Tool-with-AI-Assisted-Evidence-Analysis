import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Persist React state in ``localStorage`` with JSON serialisation.
 *
 * @param {string} key Storage key.
 * @param {*} initialValue Fallback when missing/invalid.
 * @returns {[*, Function]} storedValue and setStoredValue (supports updater fn).
 */
export default function useLocalStorage(key, initialValue) {
  const initialRef = useRef(initialValue);

  const readValue = useCallback(() => {
    if (typeof window === "undefined") {
      return initialRef.current;
    }
    try {
      const raw = window.localStorage.getItem(key);
      if (raw === null || raw === undefined) {
        return initialRef.current;
      }
      return JSON.parse(raw);
    } catch {
      return initialRef.current;
    }
  }, [key]);

  const [storedValue, setStoredValueState] = useState(readValue);

  useEffect(() => {
    setStoredValueState(readValue());
  }, [key, readValue]);

  const setStoredValue = useCallback(
    (value) => {
      setStoredValueState((prev) => {
        const next = typeof value === "function" ? value(prev) : value;
        try {
          window.localStorage.setItem(key, JSON.stringify(next));
        } catch {
          // Ignore quota / private-mode failures.
        }
        return next;
      });
    },
    [key]
  );

  return [storedValue, setStoredValue];
}
