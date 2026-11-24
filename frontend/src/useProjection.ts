import {useEffect, useState} from 'react';
import {api} from './api';

/** Never display results from a previously selected mission, mode or run. */
export function useProjection<T>(path: string | null, revision?: string) {
  const [result, setResult] = useState<{path: string; data?: T; error?: string}>();
  useEffect(() => {
    if (!path) return;
    let current = true;
    api<T>(path).then(data => {
      if (current) setResult({path, data});
    }).catch(error => {
      if (current) setResult({path, error: String(error)});
    });
    return () => { current = false; };
  }, [path, revision]);

  return result?.path === path ? result : undefined;
}
