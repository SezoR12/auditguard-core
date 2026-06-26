import { useCallback, useEffect, useRef, useState } from "react";

const FIVE_MIN = 5 * 60 * 1000;

/** Load data once, expose {data, loading, error, reload}, auto-refresh every 5 min. */
export function useAutoRefresh<T>(fetcher: () => Promise<T>, intervalMs = FIVE_MIN) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetcherRef.current());
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطأ في تحميل البيانات");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    const id = setInterval(() => void reload(), intervalMs);
    return () => clearInterval(id);
  }, [reload, intervalMs]);

  return { data, loading, error, reload };
}
