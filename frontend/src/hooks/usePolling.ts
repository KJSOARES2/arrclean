import { useEffect, useRef, useState, useCallback } from 'react';

export function usePolling<T>(
  asyncFn: () => Promise<T>,
  intervalMs: number = 10000,
  enabled: boolean = true
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const isMounted = useRef(true);

  const execute = useCallback(async () => {
    try {
      const result = await asyncFn();
      if (isMounted.current) {
        setData(result);
        setError(null);
      }
    } catch (err: any) {
      if (isMounted.current) {
        setError(err);
      }
    } finally {
      if (isMounted.current) {
        setLoading(false);
      }
    }
  }, [asyncFn]);

  useEffect(() => {
    isMounted.current = true;
    execute();

    if (!enabled || intervalMs <= 0) return;

    const interval = setInterval(() => {
      // Pause polling if tab is backgrounded
      if (!document.hidden) {
        execute();
      }
    }, intervalMs);

    return () => {
      isMounted.current = false;
      clearInterval(interval);
    };
  }, [execute, intervalMs, enabled]);

  return { data, error, loading, refresh: execute };
}
