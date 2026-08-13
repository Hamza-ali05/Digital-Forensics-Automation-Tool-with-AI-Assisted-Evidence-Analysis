import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Normalise common paginated API shapes into { items, total }.
 */
function normalisePageResult(result, pageSize) {
  const payload =
    result &&
    typeof result === "object" &&
    Object.prototype.hasOwnProperty.call(result, "data") &&
    Object.prototype.hasOwnProperty.call(result, "status") &&
    Object.prototype.hasOwnProperty.call(result, "config")
      ? result.data
      : result;

  if (Array.isArray(payload)) {
    return { items: payload, total: payload.length };
  }

  if (payload && typeof payload === "object") {
    const items =
      payload.items ||
      payload.results ||
      payload.data ||
      payload.cases ||
      payload.jobs ||
      [];
    const total =
      payload.total ??
      payload.count ??
      payload.total_count ??
      (Array.isArray(items) ? items.length : 0);
    return {
      items: Array.isArray(items) ? items : [],
      total: Number(total) || 0,
    };
  }

  return { items: [], total: 0, pageSize };
}

/**
 * Paginated data fetching with page navigation helpers.
 *
 * ``fetchFunction`` is called as ``fetchFunction({ page, pageSize })``.
 *
 * @param {Function} fetchFunction
 * @param {{ pageSize?: number, autoLoad?: boolean }} [options]
 */
export default function usePagination(fetchFunction, options = {}) {
  const { pageSize = 20, autoLoad = true } = options;
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(Boolean(autoLoad));
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const fnRef = useRef(fetchFunction);
  fnRef.current = fetchFunction;

  const totalPages = Math.max(1, Math.ceil((total || 0) / pageSize) || 1);

  const loadPage = useCallback(
    async (targetPage) => {
      const nextPage = Math.max(1, targetPage);
      setLoading(true);
      setError(null);
      try {
        const result = await fnRef.current({ page: nextPage, pageSize });
        const normalised = normalisePageResult(result, pageSize);
        setData(normalised.items);
        setTotal(normalised.total);
        setPage(nextPage);
        setLoading(false);
        return normalised;
      } catch (err) {
        setError(err);
        setLoading(false);
        throw err;
      }
    },
    [pageSize]
  );

  useEffect(() => {
    if (!autoLoad) {
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        await loadPage(1);
      } catch {
        if (cancelled) return;
      }
    })();
    return () => {
      cancelled = true;
    };
    // Initial load only when autoLoad/pageSize change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad, pageSize]);

  const goToPage = useCallback(
    (targetPage) => loadPage(targetPage),
    [loadPage]
  );

  const nextPage = useCallback(() => {
    if (page < totalPages) {
      return loadPage(page + 1);
    }
    return Promise.resolve({ items: data, total });
  }, [page, totalPages, loadPage, data, total]);

  const prevPage = useCallback(() => {
    if (page > 1) {
      return loadPage(page - 1);
    }
    return Promise.resolve({ items: data, total });
  }, [page, loadPage, data, total]);

  const refresh = useCallback(() => loadPage(page), [loadPage, page]);

  return {
    data,
    loading,
    error,
    page,
    pageSize,
    total,
    totalPages,
    goToPage,
    nextPage,
    prevPage,
    refresh,
  };
}
