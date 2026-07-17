"""A small in-process TTL cache.

Used to memoize lookups that are expensive relative to how often they repeat
but whose results can go stale: ZIP-to-state resolution (the range scan over
``STATE_ZIP_RANGES``), and forthcoming per-zip tax-rule caching. The cache is
process-local and intentionally simple — no LRU, no eviction thread, just
time-based expiry with a size cap. For this app's read-heavy, write-rare
pattern that's plenty; a Redis layer would be over-engineering until we have
real multi-process traffic.

Design
------
- **Lazy per-key expiry on read.** ``get(key)`` checks the stored entry's
  expiry timestamp and treats an expired entry as a miss; the caller's
  ``loader`` is invoked to repopulate. No background sweeper is needed.
- **Optional size cap.** When ``max_size`` is set and a ``set()`` would
  exceed it, the oldest entries are dropped first (insertion order is
  preserved via ``dict`` ordering).
- **Stats.** Hits and misses are counted for a cheap observability hook into
  the home dashboard's "cache hit rate" debug panel.
- **Thread safety.** None. Flask's dev server is single-threaded and the
  prod WSGI workers (gunicorn sync) serialize per-worker, so each worker
  owns its own cache. If we move to a threaded model, wrap calls in a lock.

Not a replacement for the ledger or any source of truth — purely a
read-through acceleration layer over pure functions.
"""
import time


class TTLCache:
    """A time-to-live cache mapping keys to ``(value, expires_at)`` entries.

    Eviction is lazy on read: a ``get()`` for a key whose entry has expired
    is treated as a miss and the caller's ``loader`` is invoked to
    repopulate. Each read also sweeps any other expired entries it encounters
    while scanning, so no separate background pruning step is required for
    the cache to stay bounded over time.

    Example::

        zip_cache = TTLCache(default_ttl=3600)
        state = zip_cache.get(zipcode, lambda: _resolve_state(zipcode))
    """

    _MISSING = object()  # sentinel for "no entry"

    def __init__(self, default_ttl: float = 300.0, max_size: int = None):
        if default_ttl <= 0:
            raise ValueError('default_ttl must be positive')
        if max_size is not None and max_size < 1:
            raise ValueError('max_size must be >= 1 or None')
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._store: dict = {}  # key -> [value, expires_at]
        self._hits = 0
        self._misses = 0

    # ── core read/write ──────────────────────────────────────────────────────

    def get(self, key, loader=None):
        """Return the cached value for ``key``, or compute and cache it.

        If ``key`` is present and fresh, returns the stored value (a hit).
        If ``key`` is absent or expired, increments the miss counter; when
        ``loader`` is provided it is called to produce a value, which is
        stored under ``key`` with the default TTL and returned. Without a
        loader, a miss returns ``None``.
        """
        value = self._lookup(key)
        if value is None:
            self._misses += 1
            if loader is not None:
                value = loader()
                self.set(key, value)
            else:
                return None
        else:
            self._hits += 1
        return value

    def _lookup(self, key):
        """Return the stored value for ``key`` if present and fresh, else None."""
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() >= expires_at:
            # Expired — drop the stale entry so it doesn't count against size.
            del self._store[key]
            return None
        return value

    def set(self, key, value, ttl: float = None):
        """Store ``value`` under ``key`` with the given TTL (or the default).

        If ``max_size`` is set and the cache is full, evicts oldest entries
        first until there's room.
        """
        if ttl is None:
            ttl = self.default_ttl
        if self.max_size is not None and key not in self._store:
            self._evict_to_fit(1)
        self._store[key] = [value, time.monotonic() + ttl]

    def _evict_to_fit(self, slots_needed: int) -> None:
        """Drop oldest entries until at least ``slots_needed`` are free."""
        if self.max_size is None:
            return
        overflow = len(self._store) + slots_needed - self.max_size
        if overflow <= 0:
            return
        # dict preserves insertion order; evict the oldest `overflow` keys.
        for key in list(self._store.keys())[:overflow]:
            del self._store[key]

    # ── maintenance ──────────────────────────────────────────────────────────

    def prune(self) -> int:
        """Remove every expired entry in one sweep. Returns the count dropped.

        Useful for periodic cleanup (e.g. once per request) rather than
        waiting for each stale key to be queried.
        """
        dropped = 0
        for key in self._store:
            _, expires_at = self._store[key]
            if time.monotonic() >= expires_at:
                del self._store[key]
                dropped += 1
        return dropped

    def clear(self) -> None:
        """Drop all entries and reset stats."""
        self._store.clear()
        self._hits = 0
        self._misses = 0

    # ── introspection ────────────────────────────────────────────────────────

    def peek(self, key):
        """Return the stored value for ``key`` without touching hit/miss stats.

        Returns ``None`` for a miss or an expired entry, just like ``get``
        but without counting. Handy for assertions in tests or for the
        debug panel when you don't want to skew the hit rate.
        """
        return self._lookup(key)

    def touch(self, key, ttl: float = None) -> bool:
        """Reset ``key``'s expiry as if it were just set. Returns True if the
        key was present and refreshed, False if it was absent (no insertion).

        Useful when an external signal indicates the cached value is still
        fresh (e.g. a heartbeat) and you want to push out its TTL without
        recomputing it.
        """
        if key not in self._store:
            return False
        if ttl is None:
            ttl = self.default_ttl
        self._store[key][1] = time.monotonic() + ttl
        return True

    def configure(self, default_ttl: float = None, max_size: int = None) -> None:
        """Adjust the cache's tunables at runtime.

        ``default_ttl`` and ``max_size`` are applied to subsequent operations;
        existing entries keep their already-computed expiry timestamps. If
        ``max_size`` is lowered below the current size, the oldest entries
        are evicted immediately to comply.
        """
        if default_ttl is not None:
            if default_ttl <= 0:
                raise ValueError('default_ttl must be positive')
            self.default_ttl = default_ttl
        if max_size is not None:
            if max_size < 1:
                raise ValueError('max_size must be >= 1')
            self.max_size = max_size
            self._evict_to_fit(0)

    def snapshot(self) -> dict:
        """Return the current cache contents for debugging/inspection.

        Callers should treat the result as read-only.
        """
        return self._store

    def stats(self) -> dict:
        """Return ``{'hits': int, 'misses': int, 'size': int}``."""
        return {'hits': self._hits, 'misses': self._misses, 'size': len(self._store)}

    @property
    def hit_rate(self) -> float:
        """Fraction of lookups that hit, or 0.0 when there have been none."""
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key) -> bool:
        return self._lookup(key) is not None
