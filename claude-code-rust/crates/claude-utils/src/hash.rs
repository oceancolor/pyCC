// 原始 TS: utils/hash.ts
//! Non-cryptographic and cryptographic hash utilities.
//!
//! Uses `seahash` for fast non-crypto hashing (equivalent to djb2/Bun.hash)
//! and `sha2` for crypto-quality hashing.

use std::hash::{Hash, Hasher};

/// djb2 string hash — fast non-cryptographic hash returning a signed 32-bit integer.
/// Deterministic across runtimes. Use when you need stable on-disk output.
pub fn djb2_hash(s: &str) -> i32 {
    let mut hash: i32 = 0;
    for c in s.bytes() {
        hash = hash.wrapping_shl(5).wrapping_sub(hash).wrapping_add(c as i32);
    }
    hash
}

/// Hash arbitrary content for change detection.
/// Uses a fast non-crypto hash (seahash). Not suitable for security purposes.
pub fn hash_content(content: &str) -> u64 {
    seahash::hash(content.as_bytes())
}

/// Hash arbitrary content to a hex string using SHA-256 (crypto-quality).
pub fn hash_content_sha256(content: &str) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(content.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Hash two strings without allocating a concatenated temp string.
/// Uses seahash seeding to naturally disambiguate ("ts","code") vs ("tsc","ode").
pub fn hash_pair(a: &str, b: &str) -> u64 {
    // Seed the second hash with the first hash value
    let seed_a = seahash::hash(a.as_bytes());
    // XOR with a separator to distinguish positions
    let seed_b = seahash::hash_seeded(b.as_bytes(), seed_a, 0, 0, 0);
    seed_b
}

/// Hash a pair to a hex string using SHA-256 (stable, crypto-quality).
pub fn hash_pair_sha256(a: &str, b: &str) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(a.as_bytes());
    hasher.update(b"\0"); // separator
    hasher.update(b.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Hash a generic value using Rust's standard `Hash` trait + seahash.
pub fn hash_value<T: Hash>(value: &T) -> u64 {
    let mut hasher = seahash::SeaHasher::new();
    value.hash(&mut hasher);
    hasher.finish()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_djb2_hash_deterministic() {
        assert_eq!(djb2_hash("hello"), djb2_hash("hello"));
        assert_ne!(djb2_hash("hello"), djb2_hash("world"));
    }

    #[test]
    fn test_hash_content_deterministic() {
        assert_eq!(hash_content("hello"), hash_content("hello"));
        assert_ne!(hash_content("hello"), hash_content("world"));
    }

    #[test]
    fn test_hash_pair_order_matters() {
        // ("ts","code") should differ from ("tsc","ode")
        assert_ne!(hash_pair("ts", "code"), hash_pair("tsc", "ode"));
        // Symmetric: same order = same hash
        assert_eq!(hash_pair("a", "b"), hash_pair("a", "b"));
    }

    #[test]
    fn test_hash_content_sha256() {
        let h = hash_content_sha256("hello");
        assert_eq!(h.len(), 64); // hex SHA-256
        assert_eq!(h, hash_content_sha256("hello"));
    }
}
