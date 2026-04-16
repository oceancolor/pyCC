// 原始 TS: utils/set.ts
//! Optimized set operations.
//!
//! All operations are implemented for speed — hot paths avoid unnecessary allocation.

use std::collections::HashSet;
use std::hash::Hash;

/// Return elements in `a` that are not in `b`.
pub fn difference<A: Hash + Eq + Clone>(a: &HashSet<A>, b: &HashSet<A>) -> HashSet<A> {
    a.iter().filter(|item| !b.contains(*item)).cloned().collect()
}

/// Return true if any element in `a` is also in `b`.
pub fn intersects<A: Hash + Eq>(a: &HashSet<A>, b: &HashSet<A>) -> bool {
    if a.is_empty() || b.is_empty() {
        return false;
    }
    // Iterate over the smaller set for efficiency
    let (small, large) = if a.len() <= b.len() { (a, b) } else { (b, a) };
    small.iter().any(|item| large.contains(item))
}

/// Return true if every element in `a` is also in `b`.
pub fn every<A: Hash + Eq>(a: &HashSet<A>, b: &HashSet<A>) -> bool {
    a.iter().all(|item| b.contains(item))
}

/// Return the union of `a` and `b`.
pub fn union<A: Hash + Eq + Clone>(a: &HashSet<A>, b: &HashSet<A>) -> HashSet<A> {
    a.iter().chain(b.iter()).cloned().collect()
}

/// Return the intersection of `a` and `b`.
pub fn intersection<A: Hash + Eq + Clone>(a: &HashSet<A>, b: &HashSet<A>) -> HashSet<A> {
    let (small, large) = if a.len() <= b.len() { (a, b) } else { (b, a) };
    small.iter().filter(|item| large.contains(*item)).cloned().collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn set<T: Hash + Eq>(items: Vec<T>) -> HashSet<T> {
        items.into_iter().collect()
    }

    #[test]
    fn test_difference() {
        let a = set(vec![1, 2, 3, 4]);
        let b = set(vec![3, 4, 5]);
        let d = difference(&a, &b);
        assert_eq!(d, set(vec![1, 2]));
    }

    #[test]
    fn test_intersects() {
        let a = set(vec![1, 2, 3]);
        let b = set(vec![3, 4, 5]);
        let c = set(vec![6, 7]);
        assert!(intersects(&a, &b));
        assert!(!intersects(&a, &c));
        assert!(!intersects(&set::<i32>(vec![]), &b));
    }

    #[test]
    fn test_every() {
        let a = set(vec![1, 2]);
        let b = set(vec![1, 2, 3]);
        let c = set(vec![1, 4]);
        assert!(every(&a, &b));
        assert!(!every(&c, &b));
    }

    #[test]
    fn test_union() {
        let a = set(vec![1, 2, 3]);
        let b = set(vec![3, 4, 5]);
        let u = union(&a, &b);
        assert_eq!(u, set(vec![1, 2, 3, 4, 5]));
    }

    #[test]
    fn test_intersection() {
        let a = set(vec![1, 2, 3, 4]);
        let b = set(vec![2, 4, 6]);
        let i = intersection(&a, &b);
        assert_eq!(i, set(vec![2, 4]));
    }
}
