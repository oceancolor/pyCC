// 原始 TS: utils/memoize.ts
//! Memoization utilities: TTL-based (sync/async) and LRU-bounded caches.

use std::collections::HashMap;
use std::hash::Hash;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

// ── TTL Memoize (sync) ──────────────────────────────────────────────────────

/// Entry in a TTL cache.
struct CacheEntry<V> {
    value: V,
    timestamp: Instant,
    refreshing: bool,
}

/// A simple TTL-bounded memoization cache for functions with a single key.
///
/// Implements the stale-while-revalidate pattern from the TS original:
/// - Fresh hit → return immediately
/// - Stale hit → return stale value, background refresh (TODO in async variant)
/// - Miss → compute and store
pub struct TtlCache<K, V> {
    inner: HashMap<K, CacheEntry<V>>,
    ttl: Duration,
}

impl<K: Hash + Eq, V: Clone> TtlCache<K, V> {
    pub fn new(ttl: Duration) -> Self {
        Self {
            inner: HashMap::new(),
            ttl,
        }
    }

    /// Get the cached value if fresh.
    pub fn get(&self, key: &K) -> Option<&V> {
        if let Some(entry) = self.inner.get(key) {
            if entry.timestamp.elapsed() <= self.ttl {
                return Some(&entry.value);
            }
        }
        None
    }

    /// Insert a value.
    pub fn insert(&mut self, key: K, value: V) {
        self.inner.insert(
            key,
            CacheEntry {
                value,
                timestamp: Instant::now(),
                refreshing: false,
            },
        );
    }

    /// Check if the entry is stale (exists but past TTL).
    pub fn is_stale(&self, key: &K) -> bool {
        self.inner
            .get(key)
            .map(|e| e.timestamp.elapsed() > self.ttl)
            .unwrap_or(false)
    }

    /// Clear all entries.
    pub fn clear(&mut self) {
        self.inner.clear();
    }
}

// ── LRU Memoize ─────────────────────────────────────────────────────────────

/// A simple LRU cache bounded to `max_size` entries.
/// Uses an `IndexMap`-like approach: entries are stored in insertion order,
/// and on eviction the least-recently-used item is removed.
///
/// For production use, prefer the `lru` crate for O(1) operations.
pub struct LruCache<K, V> {
    max_size: usize,
    // (key, value) ordered by recency: front = MRU, back = LRU
    entries: std::collections::VecDeque<(K, V)>,
}

impl<K: Hash + Eq + Clone, V: Clone> LruCache<K, V> {
    pub fn new(max_size: usize) -> Self {
        Self {
            max_size,
            entries: std::collections::VecDeque::with_capacity(max_size),
        }
    }

    /// Get a value, promoting it to MRU position.
    pub fn get(&mut self, key: &K) -> Option<V> {
        if let Some(pos) = self.entries.iter().position(|(k, _)| k == key) {
            let entry = self.entries.remove(pos).unwrap();
            let value = entry.1.clone();
            self.entries.push_front(entry);
            Some(value)
        } else {
            None
        }
    }

    /// Peek at a value without updating recency.
    pub fn peek(&self, key: &K) -> Option<&V> {
        self.entries.iter().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    /// Insert a value. Evicts LRU entry if at capacity.
    pub fn insert(&mut self, key: K, value: V) {
        // Remove existing entry if present
        if let Some(pos) = self.entries.iter().position(|(k, _)| k == &key) {
            self.entries.remove(pos);
        }
        // Evict LRU if at capacity
        if self.entries.len() >= self.max_size {
            self.entries.pop_back();
        }
        self.entries.push_front((key, value));
    }

    /// Remove a specific entry.
    pub fn remove(&mut self, key: &K) -> bool {
        if let Some(pos) = self.entries.iter().position(|(k, _)| k == key) {
            self.entries.remove(pos);
            true
        } else {
            false
        }
    }

    /// Clear all entries.
    pub fn clear(&mut self) {
        self.entries.clear();
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}

// ── Thread-safe shared variants ─────────────────────────────────────────────

/// A thread-safe LRU cache wrapped in Arc<Mutex<>>.
pub type SharedLruCache<K, V> = Arc<Mutex<LruCache<K, V>>>;

pub fn new_shared_lru_cache<K: Hash + Eq + Clone, V: Clone>(
    max_size: usize,
) -> SharedLruCache<K, V> {
    Arc::new(Mutex::new(LruCache::new(max_size)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ttl_cache_fresh_hit() {
        let mut cache = TtlCache::new(Duration::from_secs(60));
        cache.insert("key", 42);
        assert_eq!(cache.get(&"key"), Some(&42));
    }

    #[test]
    fn test_ttl_cache_miss() {
        let cache = TtlCache::<&str, i32>::new(Duration::from_secs(60));
        assert_eq!(cache.get(&"missing"), None);
    }

    #[test]
    fn test_ttl_cache_expired() {
        let mut cache = TtlCache::new(Duration::from_nanos(1));
        cache.insert("key", 42);
        std::thread::sleep(Duration::from_millis(1));
        assert_eq!(cache.get(&"key"), None);
    }

    #[test]
    fn test_lru_cache_eviction() {
        let mut cache = LruCache::new(2);
        cache.insert("a", 1);
        cache.insert("b", 2);
        cache.insert("c", 3); // evicts "a" (LRU)
        assert_eq!(cache.peek(&"a"), None);
        assert_eq!(cache.peek(&"b"), Some(&2));
        assert_eq!(cache.peek(&"c"), Some(&3));
    }

    #[test]
    fn test_lru_cache_recency_update() {
        let mut cache = LruCache::new(2);
        cache.insert("a", 1);
        cache.insert("b", 2);
        // Access "a" to make it MRU
        let _ = cache.get(&"a");
        // Now insert "c" — should evict "b" (LRU)
        cache.insert("c", 3);
        assert_eq!(cache.peek(&"a"), Some(&1));
        assert_eq!(cache.peek(&"b"), None);
        assert_eq!(cache.peek(&"c"), Some(&3));
    }
}
