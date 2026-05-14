"""MCP collapse classifier. Ported from MCPTool/classifyForCollapse.ts"""
from __future__ import annotations
import re
from typing import Optional

# Search tools — collapse by default
_SEARCH_TOOLS: frozenset[str] = frozenset([
    # Slack
    "slack_search_public", "slack_search_public_and_private",
    "slack_search_channels", "slack_search_users",
    # GitHub
    "search_code", "search_repositories", "search_issues",
    "search_pull_requests", "search_orgs", "search_users",
    # Linear
    "search_documentation",
    # Datadog
    "search_logs", "search_spans", "search_rum_events", "search_audit_logs",
    "search_monitors", "search_monitor_groups",
    "find_slow_spans", "find_monitors_matching_pattern",
    # Sentry
    "search_docs", "search_events", "search_issue_events",
    "find_organizations", "find_teams", "find_projects",
    "find_releases", "find_dsns",
    # Notion
    "search",
    # Gmail
    "gmail_search_messages",
    # Google Drive
    "google_drive_search",
    # Google Calendar
    "gcal_find_my_free_time", "gcal_find_meeting_times", "gcal_find_user_emails",
    # Atlassian/Jira
    "search_jira_issues_using_jql", "search_confluence_using_cql",
    "lookup_jira_account_id",
])

# Read tools — collapse by default
_READ_TOOLS: frozenset[str] = frozenset([
    # Slack
    "slack_get_channel_history", "slack_get_thread_replies",
    "slack_get_users", "slack_get_user_profile",
    # GitHub
    "get_file_contents", "get_issue", "get_pull_request",
    "get_pull_request_files", "get_pull_request_diff",
    "get_pull_request_reviews", "get_pull_request_comments",
    "get_commit", "list_commits", "list_branches",
    "list_issues", "list_pull_requests", "list_tags",
    "list_workflows", "get_workflow", "get_workflow_run",
    # Notion
    "get_page", "get_block_children", "get_database",
    # Google Drive
    "google_drive_read_file",
    # Google Calendar
    "gcal_list_events", "gcal_get_event",
    # Jira / Confluence
    "get_jira_issue", "get_confluence_page",
])


def _to_snake_case(name: str) -> str:
    """Normalize camelCase/kebab-case to snake_case for matching."""
    # kebab-case → snake_case
    name = name.replace("-", "_")
    # camelCase → snake_case
    name = re.sub(r"([A-Z])", r"_\1", name).lower().lstrip("_")
    return name


def classify_for_collapse(tool_name: str, tool_use: dict) -> Optional[str]:
    """Return 'search' or 'read' if the tool should be collapsed in the UI, else None.

    Uses explicit allowlists keyed on normalized snake_case tool name.
    Conservative: unknown tools do not collapse.
    """
    normalized = _to_snake_case(tool_name)
    if normalized in _SEARCH_TOOLS:
        return "search"
    if normalized in _READ_TOOLS:
        return "read"
    return None
