"""In-memory LRU cache with TTL support.

Intended for single-instance deployment to avoid repeated heavy work
(e.g., rule store loading, sample profiling, vector search).
"""
import time
from collections import OrderedDict
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class MemoryCache:
    """Thread-safe (via GIL) in-memory cache with LRU eviction and optional TTL.

    Uses OrderedDict so that ``move_to_end`` gives LRU semantics.
    """

    def __init__(self, maxsize: int = 256, default_ttl: float | None = None):
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._store: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()

    # -- core API --

    def get(self, key: str) -> Any:
        """Retrieve a value or raise KeyError if missing/expired."""
        if key not in self._store:
            raise KeyError(key)
        value, expiry = self._store[key]
        if expiry is not None and time.time() > expiry:
            self._store.pop(key, None)
            raise KeyError(key)
        # Promote to MRU
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store a value. ttl=None means no expiration."""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expiry = time.time() + effective_ttl if effective_ttl else None
        # If key already exists, update and move to end
        if key in self._store:
            self._store.pop(key, None)
        # Evict oldest if at capacity
        while len(self._store) >= self._maxsize:
            self._store.popitem(last=False)
        self._store[key] = (value, expiry)

    def delete(self, key: str) -> bool:
        """Remove a key. Returns True if it existed."""
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()

    def keys(self) -> list[str]:
        """Return current (non-expired) keys."""
        now = time.time()
        return [k for k, (_, e) in self._store.items() if e is None or now <= e]

    def info(self) -> dict[str, int | float | None]:
        return {
            "maxsize": self._maxsize,
            "size": len(self._store),
            "default_ttl": self._default_ttl,
        }

    # -- decorator --

    def cached(
        self,
        key_fn: Callable[..., str] | None = None,
        ttl: float | None = None,
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Decorator that caches function results.

        ``key_fn`` receives the same *args, **kwargs and should return a string key.
        If omitted, the key is ``func_name|args|kwargs`` (naive but safe).
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            def wrapper(*args: Any, **kwargs: Any) -> T:
                if key_fn:
                    cache_key = key_fn(*args, **kwargs)
                else:
                    cache_key = _default_key(func.__name__, *args, **kwargs)
                try:
                    return self.get(cache_key)
                except KeyError:
                    result = func(*args, **kwargs)
                    self.set(cache_key, result, ttl=ttl)
                    return result
            return wrapper
        return decorator


def _default_key(name: str, *args: Any, **kwargs: Any) -> str:
    """Naive but deterministic cache key."""
    return f"{name}:{repr(args)}:{repr(sorted(kwargs.items()))}"


# Global app-level cache (singleton)
_app_cache = MemoryCache(maxsize=512, default_ttl=300)


def get_app_cache() -> MemoryCache:
    return _app_cache
