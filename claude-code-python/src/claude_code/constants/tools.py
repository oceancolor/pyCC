"""
Tool name constants
原始 TS: src/constants/tools.ts + various tools/*/constants.ts

bun:bundle feature() → Python 环境变量 / feature flags dict
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Tool names (from individual tool files)
# ---------------------------------------------------------------------------

AGENT_TOOL_NAME = "Agent"
ASK_USER_QUESTION_TOOL_NAME = "AskUserQuestion"
BASH_TOOL_NAME = "Bash"
BRIEF_TOOL_NAME = "Brief"
CONFIG_TOOL_NAME = "Config"
ENTER_PLAN_MODE_TOOL_NAME = "EnterPlanMode"
ENTER_WORKTREE_TOOL_NAME = "EnterWorktree"
EXIT_PLAN_MODE_TOOL_NAME = "ExitPlanMode"
EXIT_WORKTREE_TOOL_NAME = "ExitWorktree"
FILE_EDIT_TOOL_NAME = "Edit"
FILE_READ_TOOL_NAME = "Read"
FILE_WRITE_TOOL_NAME = "Write"
GLOB_TOOL_NAME = "Glob"
GREP_TOOL_NAME = "Grep"
LSP_TOOL_NAME = "LSP"
LIST_MCP_RESOURCES_TOOL_NAME = "ListMcpResources"
MCP_TOOL_NAME = "MCP"
MCP_AUTH_TOOL_NAME = "McpAuth"
NOTEBOOK_EDIT_TOOL_NAME = "NotebookEdit"
POWER_SHELL_TOOL_NAME = "PowerShell"
READ_MCP_RESOURCE_TOOL_NAME = "ReadMcpResource"
REPL_TOOL_NAME = "REPL"
REMOTE_TRIGGER_TOOL_NAME = "RemoteTrigger"
SCHEDULE_CRON_TOOL_NAME = "ScheduleCron"
SEND_MESSAGE_TOOL_NAME = "SendMessage"
SKILL_TOOL_NAME = "Skill"
SLEEP_TOOL_NAME = "Sleep"
SYNTHETIC_OUTPUT_TOOL_NAME = "SyntheticOutput"
TASK_CREATE_TOOL_NAME = "TaskCreate"
TASK_GET_TOOL_NAME = "TaskGet"
TASK_LIST_TOOL_NAME = "TaskList"
TASK_UPDATE_TOOL_NAME = "TaskUpdate"
TASK_STOP_TOOL_NAME = "TaskStop"
TASK_OUTPUT_TOOL_NAME = "TaskOutput"
TODO_WRITE_TOOL_NAME = "TodoWrite"
TOOL_SEARCH_TOOL_NAME = "ToolSearch"
WEB_FETCH_TOOL_NAME = "WebFetch"
WEB_SEARCH_TOOL_NAME = "WebSearch"
WORKFLOW_TOOL_NAME = "Workflow"
CRON_CREATE_TOOL_NAME = "CronCreate"
CRON_DELETE_TOOL_NAME = "CronDelete"
CRON_LIST_TOOL_NAME = "CronList"

SHELL_TOOL_NAMES: frozenset[str] = frozenset({BASH_TOOL_NAME})

# ---------------------------------------------------------------------------
# Tool allowlists / blocklists
# ---------------------------------------------------------------------------

def _is_env_truthy(key: str) -> bool:
    return os.environ.get(key, "").lower() in ("1", "true", "yes")


ALL_AGENT_DISALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        TASK_OUTPUT_TOOL_NAME,
        EXIT_PLAN_MODE_TOOL_NAME,
        ENTER_PLAN_MODE_TOOL_NAME,
        # Allow Agent tool for agents when user is ant (enables nested agents)
        *( [] if os.environ.get("USER_TYPE") == "ant" else [AGENT_TOOL_NAME]),
        ASK_USER_QUESTION_TOOL_NAME,
        TASK_STOP_TOOL_NAME,
        # TODO: WORKFLOW_SCRIPTS feature flag
        # WORKFLOW_TOOL_NAME,  # add when feature is enabled
    }
)

CUSTOM_AGENT_DISALLOWED_TOOLS: frozenset[str] = frozenset(ALL_AGENT_DISALLOWED_TOOLS)

ASYNC_AGENT_ALLOWED_TOOLS: frozenset[str] = frozenset({
    FILE_READ_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
    TODO_WRITE_TOOL_NAME,
    GREP_TOOL_NAME,
    WEB_FETCH_TOOL_NAME,
    GLOB_TOOL_NAME,
    *SHELL_TOOL_NAMES,
    FILE_EDIT_TOOL_NAME,
    FILE_WRITE_TOOL_NAME,
    NOTEBOOK_EDIT_TOOL_NAME,
    SKILL_TOOL_NAME,
    SYNTHETIC_OUTPUT_TOOL_NAME,
    TOOL_SEARCH_TOOL_NAME,
    ENTER_WORKTREE_TOOL_NAME,
    EXIT_WORKTREE_TOOL_NAME,
})

IN_PROCESS_TEAMMATE_ALLOWED_TOOLS: frozenset[str] = frozenset({
    TASK_CREATE_TOOL_NAME,
    TASK_GET_TOOL_NAME,
    TASK_LIST_TOOL_NAME,
    TASK_UPDATE_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
    # TODO: AGENT_TRIGGERS feature flag
    # CRON_CREATE_TOOL_NAME, CRON_DELETE_TOOL_NAME, CRON_LIST_TOOL_NAME,
})

COORDINATOR_MODE_ALLOWED_TOOLS: frozenset[str] = frozenset({
    AGENT_TOOL_NAME,
    TASK_STOP_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
    SYNTHETIC_OUTPUT_TOOL_NAME,
})
