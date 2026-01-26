type CacheEntry<T> = {
  expiresAt: number;
  value: T;
};

const DEFAULT_TTL_MS = 60_000;
const cache = new Map<string, CacheEntry<unknown>>();

export function getFromCache<T>(key: string): T | null {
  const entry = cache.get(key);
  if (!entry) {
    console.debug("[cache] miss", { key });
    return null;
  }
  if (entry.expiresAt <= Date.now()) {
    console.debug("[cache] stale", { key });
    cache.delete(key);
    return null;
  }
  console.debug("[cache] hit", { key });
  return entry.value as T;
}

export function setInCache<T>(key: string, value: T, ttlMs = DEFAULT_TTL_MS): void {
  const expiresAt = Date.now() + ttlMs;
  cache.set(key, { expiresAt, value });
  console.debug("[cache] set", { key, ttlMs, expiresAt, size: cache.size });
}

export function clearCache(key?: string): void {
  if (key) {
    cache.delete(key);
    console.debug("[cache] delete", { key, size: cache.size });
    return;
  }
  cache.clear();
  console.debug("[cache] clear all");
}

export function getCacheSize(): number {
  return cache.size;
}
