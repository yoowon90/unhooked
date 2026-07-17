"""Unit tests for the in-process TTL cache.

Timing-sensitive behavior is tested with a controllable clock: the cache uses
``time.monotonic`` for expiry, so we monkeypatch ``website.cache.time.monotonic``
to advance deterministically rather than sleeping.
"""
import pytest

from website.cache import TTLCache


@pytest.fixture
def clock(monkeypatch):
    """A controllable monotonic clock. Starts at t=0; advance via clock.t."""
    state = {'t': 0.0}

    def fake_monotonic():
        return state['t']
    monkeypatch.setattr('website.cache.time.monotonic', fake_monotonic)
    return state


# ── construction ──────────────────────────────────────────────────────────────

def test_invalid_ttl_rejected():
    with pytest.raises(ValueError):
        TTLCache(default_ttl=0)
    with pytest.raises(ValueError):
        TTLCache(default_ttl=-1)


def test_invalid_max_size_rejected():
    with pytest.raises(ValueError):
        TTLCache(max_size=0)


# ── get / set ─────────────────────────────────────────────────────────────────

def test_get_returns_set_value(clock):
    c = TTLCache(default_ttl=10)
    c.set('a', 1)
    assert c.get('a') == 1


def test_get_miss_without_loader_returns_none(clock):
    c = TTLCache(default_ttl=10)
    assert c.get('missing') is None


def test_get_miss_with_loader_populates(clock):
    c = TTLCache(default_ttl=10)
    calls = {'n': 0}

    def loader():
        calls['n'] += 1
        return 'computed'

    assert c.get('k', loader) == 'computed'
    # Second get is a hit — loader not called again.
    assert c.get('k', loader) == 'computed'
    assert calls['n'] == 1


def test_expired_entry_is_a_miss(clock):
    c = TTLCache(default_ttl=5)
    c.set('k', 'v')
    clock['t'] = 6  # past the TTL
    assert c.get('k') is None


def test_custom_ttl_overrides_default(clock):
    c = TTLCache(default_ttl=100)
    c.set('k', 'v', ttl=2)
    clock['t'] = 3
    assert c.get('k') is None  # expired under the custom ttl
    c.set('k2', 'v2', ttl=2)
    clock['t'] = 4
    # still within nothing else — just confirm custom ttl < default worked
    c.set('k3', 'v3')
    clock['t'] = 50
    assert c.get('k3') == 'v3'  # default ttl (100) still valid at t=50


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_track_hits_and_misses(clock):
    c = TTLCache(default_ttl=10)
    c.set('a', 1)
    c.get('a')           # hit
    c.get('a')           # hit
    c.get('missing')     # miss
    stats = c.stats()
    assert stats['hits'] == 2
    assert stats['misses'] == 1
    assert stats['size'] == 1


def test_hit_rate_is_zero_when_no_lookups(clock):
    c = TTLCache(default_ttl=10)
    assert c.hit_rate == 0.0


def test_clear_resets_store_and_stats(clock):
    c = TTLCache(default_ttl=10)
    c.set('a', 1)
    c.get('a')
    c.clear()
    assert len(c) == 0
    assert c.stats() == {'hits': 0, 'misses': 0, 'size': 0}


# ── max_size eviction ─────────────────────────────────────────────────────────

def test_max_size_evicts_oldest(clock):
    c = TTLCache(default_ttl=100, max_size=2)
    c.set('a', 1)
    c.set('b', 2)
    c.set('c', 3)  # exceeds max_size -> 'a' evicted (oldest)
    assert 'a' not in c
    assert c.get('b') == 2
    assert c.get('c') == 3


def test_overwriting_existing_key_does_not_evict(clock):
    c = TTLCache(default_ttl=100, max_size=2)
    c.set('a', 1)
    c.set('b', 2)
    c.set('a', 99)  # overwrite, not a new key
    assert c.get('a') == 99
    assert c.get('b') == 2  # still present


# ── __contains__ / __len__ ────────────────────────────────────────────────────

def test_contains_reflects_freshness(clock):
    c = TTLCache(default_ttl=5)
    c.set('k', 'v')
    assert 'k' in c
    clock['t'] = 6
    assert 'k' not in c


def test_len_counts_current_entries(clock):
    c = TTLCache(default_ttl=10)
    c.set('a', 1)
    c.set('b', 2)
    assert len(c) == 2


# ── prune (no expired entries — sweep is a no-op) ─────────────────────────────

def test_prune_with_no_expired_entries_is_noop(clock):
    c = TTLCache(default_ttl=100)
    c.set('a', 1)
    c.set('b', 2)
    assert c.prune() == 0
    assert len(c) == 2


# ── peek / touch / configure ──────────────────────────────────────────────────

def test_peek_does_not_touch_stats(clock):
    c = TTLCache(default_ttl=10)
    c.set('a', 1)
    assert c.peek('a') == 1
    assert c.peek('missing') is None
    # neither a hit nor a miss was counted
    assert c.stats() == {'hits': 0, 'misses': 0, 'size': 1}


def test_touch_refreshes_ttl(clock):
    c = TTLCache(default_ttl=5)
    c.set('k', 'v')
    clock['t'] = 4          # near expiry
    assert c.touch('k')      # reset ttl
    clock['t'] = 8          # past original expiry, within the refreshed one
    assert c.get('k') == 'v'


def test_touch_missing_key_returns_false(clock):
    c = TTLCache(default_ttl=10)
    assert c.touch('nope') is False


def test_configure_lowers_max_size_and_evicts(clock):
    c = TTLCache(default_ttl=100, max_size=5)
    for i in range(5):
        c.set(i, i)
    c.configure(max_size=2)
    assert len(c) == 2
    # oldest three were evicted; keys 3 and 4 remain
    assert c.get(3) == 3
    assert c.get(4) == 4


def test_configure_rejects_bad_values(clock):
    c = TTLCache(default_ttl=100)
    with pytest.raises(ValueError):
        c.configure(default_ttl=0)
    with pytest.raises(ValueError):
        c.configure(max_size=0)
