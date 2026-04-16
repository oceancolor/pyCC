// Original TS source: utils/array.ts
// Array utility functions

/// Intersperse elements with a separator function.
pub fn intersperse<A, F>(items: Vec<A>, separator: F) -> Vec<A>
where
    F: Fn(usize) -> A,
{
    let mut result = Vec::with_capacity(items.len() * 2);
    for (i, item) in items.into_iter().enumerate() {
        if i > 0 {
            result.push(separator(i));
        }
        result.push(item);
    }
    result
}

/// Count elements satisfying a predicate.
pub fn count<T, F>(items: &[T], pred: F) -> usize
where
    F: Fn(&T) -> bool,
{
    items.iter().filter(|x| pred(x)).count()
}

/// Return unique elements, preserving first occurrence order.
pub fn uniq<T: Eq + std::hash::Hash + Clone>(xs: impl IntoIterator<Item = T>) -> Vec<T> {
    let mut seen = std::collections::HashSet::new();
    let mut result = Vec::new();
    for x in xs {
        if seen.insert(x.clone()) {
            result.push(x);
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_intersperse() {
        let v = vec![1, 2, 3];
        let result = intersperse(v, |_| 0);
        assert_eq!(result, vec![1, 0, 2, 0, 3]);
    }

    #[test]
    fn test_intersperse_empty() {
        let v: Vec<i32> = vec![];
        let result = intersperse(v, |_| 0);
        assert_eq!(result, vec![]);
    }

    #[test]
    fn test_count() {
        let v = vec![1, 2, 3, 4, 5];
        assert_eq!(count(&v, |x| x % 2 == 0), 2);
    }

    #[test]
    fn test_uniq() {
        let v = vec![1, 2, 2, 3, 1, 4];
        assert_eq!(uniq(v), vec![1, 2, 3, 4]);
    }
}
