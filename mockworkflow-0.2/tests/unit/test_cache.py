"""Tests for in-memory LRU cache."""

import time

import pytest

from backend.cache import MemoryCache


def test_basic_set_get():
    cache = MemoryCache(maxsize=2)
    cache.set("a", 1)
    assert cache.get("a") == 1


def test_missing_raises():
    cache = MemoryCache()
    with pytest.raises(KeyError):
        cache.get("missing")


def test_ttl_expires():
    cache = MemoryCache()
    cache.set("a", 1, ttl=0.05)
    assert cache.get("a") == 1
    time.sleep(0.1)
    with pytest.raises(KeyError):
        cache.get("a")


def test_lru_eviction():
    cache = MemoryCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # should evict "a"
    with pytest.raises(KeyError):
        cache.get("a")
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_mru_promotion():
    cache = MemoryCache(maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # promote "a" to MRU
    cache.set("c", 3)  # should evict "b" instead of "a"
    assert cache.get("a") == 1
    with pytest.raises(KeyError):
        cache.get("b")


def test_delete():
    cache = MemoryCache()
    cache.set("a", 1)
    assert cache.delete("a") is True
    assert cache.delete("a") is False


def test_clear():
    cache = MemoryCache()
    cache.set("a", 1)
    cache.clear()
    with pytest.raises(KeyError):
        cache.get("a")


def test_info():
    cache = MemoryCache(maxsize=10)
    cache.set("a", 1)
    info = cache.info()
    assert info["maxsize"] == 10
    assert info["size"] == 1


def test_decorator():
    cache = MemoryCache()
    call_count = 0

    @cache.cached()
    def add(x, y):
        nonlocal call_count
        call_count += 1
        return x + y

    assert add(2, 3) == 5
    assert add(2, 3) == 5
    assert call_count == 1  # second call hit cache


def test_decorator_with_ttl():
    cache = MemoryCache()
    call_count = 0

    @cache.cached(ttl=0.05)
    def greet(name):
        nonlocal call_count
        call_count += 1
        return f"hello {name}"

    assert greet("world") == "hello world"
    time.sleep(0.1)
    assert greet("world") == "hello world"
    assert call_count == 2  # expired and recomputed
