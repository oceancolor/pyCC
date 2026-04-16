// Original TS source: services/oauth/
// OAuth authentication stub

/// OAuth tokens
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OAuthTokens {
    pub access_token: String,
    pub refresh_token: Option<String>,
    pub expires_at: Option<i64>,
}

/// Get OAuth headers for API requests.
/// TODO: Implement full OAuth flow.
pub fn get_oauth_headers(access_token: &str) -> std::collections::HashMap<String, String> {
    let mut headers = std::collections::HashMap::new();
    headers.insert("Authorization".to_string(), format!("Bearer {}", access_token));
    headers
}
