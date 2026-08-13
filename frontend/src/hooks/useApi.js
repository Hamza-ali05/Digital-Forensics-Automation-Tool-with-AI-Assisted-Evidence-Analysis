import { useCallback, useRef, useState } from "react";

/**
 * Unwrap Axios responses or pass through service return values.
 */
function unwrapResult(result) {
  if (
    result &&
    typeof result === "object" &&
    Object.prototype.hasOwnProperty.call(result, "data") &&
    Object.prototype.hasOwnProperty.call(result, "status") &&
    Object.prototype.hasOwnProperty.call(result, "config")
  ) {
    return result.data;
  }
  return result;
}

/**
 * Generic API call state: loading → success/error.
 *
 * @example
 * const { data, loading, error, execute } = useApi(casesService.list);
 * useEffect(() => { execute(); }, [execute]);
 *
 * @param {Function} apiFunction Async function to invoke.
 */
export default function useApi(apiFunction) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const fnRef = useRef(apiFunction);
  fnRef.current = apiFunction;

  const reset = useCallback(() => {
    setData(null);
    setLoading(false);
    setError(null);
  }, []);

  const execute = useCallback(async (...args) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fnRef.current(...args);
      const payload = unwrapResult(result);
      setData(payload);
      setLoading(false);
      return payload;
    } catch (err) {
      setError(err);
      setLoading(false);
      throw err;
    }
  }, []);

  return { data, loading, error, execute, reset };
}
