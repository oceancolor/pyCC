// Original TS source: services/analytics/
// Analytics stub - TODO: Implement full analytics

/// Log an analytics event (stub).
/// TODO: Implement full telemetry and analytics.
pub fn log_event(_event_name: &str, _metadata: Option<&serde_json::Value>) {
    // TODO: Implement event logging to analytics backend
}

pub mod growthbook {
    /// Get a feature value from GrowthBook (stub).
    /// TODO: Implement GrowthBook feature flags.
    pub fn get_feature_value_cached_may_be_stale<T: Default>(
        _feature_key: &str,
    ) -> T {
        T::default()
    }
}
