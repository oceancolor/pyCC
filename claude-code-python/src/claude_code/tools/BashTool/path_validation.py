"""
Bash-specific path validation for command arguments.

Checks if bash commands try to access paths outside allowed project directories.
Validates output redirections and path-based commands (cd, ls, find, etc.).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple

# ─── Internal import stubs with graceful fallback ─────────────────────────────

try:
    from claude_code.utils.permissions.path_validation import (
        expand_tilde,
        FileOperationType,
        format_directory_list,
        is_dangerous_removal_path,
        validate_path,
    )
except ImportError:
    FileOperationType = Literal["read", "write", "create"]

    def expand_tilde(path: str) -> str:
        if path == "~" or path.startswith("~/") or path.startswith("~\\"):
            return os.path.expanduser("~") + path[1:]
        return path

    def format_directory_list(directories: List[str]) -> str:
        MAX_DIRS = 5
        count = len(directories)
        if count <= MAX_DIRS:
            return ", ".join(f"'{d}'" for d in directories)
        first = ", ".join(f"'{d}'" for d in directories[:MAX_DIRS])
        return f"{first}, and {count - MAX_DIRS} more"

    def is_dangerous_removal_path(path: str) -> bool:
        dangerous = {"/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
                     "/boot", "/dev", "/proc", "/sys", "/var"}
        home = os.path.expanduser("~")
        return path in dangerous or path == home

    def validate_path(
        file_path: str,
        cwd: str,
        tool_permission_context: Any,
        operation_type: str,
    ) -> Any:
        # Minimal fallback: always allow (for standalone use without full permission system)
        clean = expand_tilde(re.sub(r"^['\"]|['\"]$", "", file_path))
        resolved = os.path.realpath(os.path.join(cwd, clean) if not os.path.isabs(clean) else clean)
        return type("R", (), {"allowed": True, "resolved_path": resolved, "decision_reason": None})()

try:
    from claude_code.utils.permissions.filesystem import (
        all_working_directories,
    )
except ImportError:
    def all_working_directories(ctx: Any):
        return []

try:
    from claude_code.utils.permissions.permission_update import create_read_rule_suggestion
except ImportError:
    def create_read_rule_suggestion(directory: str, destination: str):
        return None

try:
    from claude_code.utils.path import get_directory_for_path
except ImportError:
    def get_directory_for_path(path: str) -> str:
        return str(Path(path).parent)

try:
    from claude_code.utils.bash.ast import Redirect, SimpleCommand
except ImportError:
    class Redirect:
        def __init__(self, op: str = ">", target: str = ""):
            self.op = op
            self.target = target

    class SimpleCommand:
        def __init__(self, argv: List[str] = None, text: str = "", env_vars=None):
            self.argv = argv or []
            self.text = text
            self.env_vars = env_vars or []

try:
    from claude_code.utils.bash.commands import (
        extract_output_redirections,
        split_command_deprecated,
    )
except ImportError:
    def extract_output_redirections(command: str):
        redirections = []
        # Simple regex-based extraction for fallback
        for m in re.finditer(r'(?:>>|>(?!>))\s*(\S+)', command):
            target = m.group(1)
            op = ">>" if m.group(0).startswith(">>") else ">"
            redirections.append({"target": target, "operator": op})
        return type("R", (), {"redirections": redirections, "has_dangerous_redirection": False})()

    def split_command_deprecated(command: str) -> List[str]:
        # Very naive split on | ; & for fallback
        parts = re.split(r'[|;&]', command)
        return [p.strip() for p in parts if p.strip()]

try:
    from claude_code.utils.bash.shell_quote import try_parse_shell_command
except ImportError:
    def try_parse_shell_command(cmd: str, env_fn=None):
        try:
            import shlex
            tokens = shlex.split(cmd)
            return type("R", (), {"success": True, "tokens": tokens})()
        except Exception:
            return type("R", (), {"success": False, "tokens": []})()

try:
    from claude_code.tools.bash_tool.bash_permissions import strip_safe_wrappers
except ImportError:
    _SAFE_WRAPPER_RE = re.compile(
        r'^(?:timeout\s+[\d.]+[smhd]?\s+|nice(?:\s+-n\s+\d+|\s+-\d+)?\s+|nohup\s+|time\s+|stdbuf\s+(?:-[ioe]\S+\s+)+)'
    )

    def strip_safe_wrappers(cmd: str) -> str:
        prev = None
        while prev != cmd:
            prev = cmd
            cmd = _SAFE_WRAPPER_RE.sub("", cmd, count=1).strip()
        return cmd

try:
    from claude_code.tools.BashTool.sed_validation import sed_command_is_allowed_by_allowlist
except ImportError:
    def sed_command_is_allowed_by_allowlist(cmd: str) -> bool:
        # Conservatively: only allow obvious read-only sed (-n with p/P/l flags, no -i)
        if "-i" in cmd:
            return False
        if re.search(r'\b-n\b', cmd):
            return True
        return False


# ─── Path command types and extractors ────────────────────────────────────────

PathCommand = Literal[
    "cd", "ls", "find", "mkdir", "touch", "rm", "rmdir", "mv", "cp",
    "cat", "head", "tail", "sort", "uniq", "wc", "cut", "paste", "column",
    "tr", "file", "stat", "diff", "awk", "strings", "hexdump", "od",
    "base64", "nl", "grep", "rg", "sed", "git", "jq",
    "sha256sum", "sha1sum", "md5sum",
]

SUPPORTED_PATH_COMMANDS: List[str] = [
    "cd", "ls", "find", "mkdir", "touch", "rm", "rmdir", "mv", "cp",
    "cat", "head", "tail", "sort", "uniq", "wc", "cut", "paste", "column",
    "tr", "file", "stat", "diff", "awk", "strings", "hexdump", "od",
    "base64", "nl", "grep", "rg", "sed", "git", "jq",
    "sha256sum", "sha1sum", "md5sum",
]

ACTION_VERBS: Dict[str, str] = {
    "cd": "change directories to",
    "ls": "list files in",
    "find": "search files in",
    "mkdir": "create directories in",
    "touch": "create or modify files in",
    "rm": "remove files from",
    "rmdir": "remove directories from",
    "mv": "move files to/from",
    "cp": "copy files to/from",
    "cat": "concatenate files from",
    "head": "read the beginning of files from",
    "tail": "read the end of files from",
    "sort": "sort contents of files from",
    "uniq": "filter duplicate lines from files in",
    "wc": "count lines/words/bytes in files from",
    "cut": "extract columns from files in",
    "paste": "merge files from",
    "column": "format files from",
    "tr": "transform text from files in",
    "file": "examine file types in",
    "stat": "read file stats from",
    "diff": "compare files from",
    "awk": "process text from files in",
    "strings": "extract strings from files in",
    "hexdump": "display hex dump of files from",
    "od": "display octal dump of files from",
    "base64": "encode/decode files from",
    "nl": "number lines in files from",
    "grep": "search for patterns in files from",
    "rg": "search for patterns in files from",
    "sed": "edit files in",
    "git": "access files with git from",
    "jq": "process JSON from files in",
    "sha256sum": "compute SHA-256 checksums for files in",
    "sha1sum": "compute SHA-1 checksums for files in",
    "md5sum": "compute MD5 checksums for files in",
}

COMMAND_OPERATION_TYPE: Dict[str, str] = {
    "cd": "read",
    "ls": "read",
    "find": "read",
    "mkdir": "create",
    "touch": "create",
    "rm": "write",
    "rmdir": "write",
    "mv": "write",
    "cp": "write",
    "cat": "read",
    "head": "read",
    "tail": "read",
    "sort": "read",
    "uniq": "read",
    "wc": "read",
    "cut": "read",
    "paste": "read",
    "column": "read",
    "tr": "read",
    "file": "read",
    "stat": "read",
    "diff": "read",
    "awk": "read",
    "strings": "read",
    "hexdump": "read",
    "od": "read",
    "base64": "read",
    "nl": "read",
    "grep": "read",
    "rg": "read",
    "sed": "write",
    "git": "read",
    "jq": "read",
    "sha256sum": "read",
    "sha1sum": "read",
    "md5sum": "read",
}


# ─── Flag filtering helpers ───────────────────────────────────────────────────

def filter_out_flags(args: List[str]) -> List[str]:
    """
    Extract positional (non-flag) arguments, correctly handling the POSIX `--`
    end-of-options delimiter.
    """
    result: List[str] = []
    after_double_dash = False
    for arg in args:
        if after_double_dash:
            result.append(arg)
        elif arg == "--":
            after_double_dash = True
        elif not (arg and arg.startswith("-")):
            result.append(arg)
    return result


def parse_pattern_command(
    args: List[str],
    flags_with_args: Set[str],
    defaults: Optional[List[str]] = None,
) -> List[str]:
    """Parse grep/rg style commands (pattern then paths)."""
    if defaults is None:
        defaults = []
    paths: List[str] = []
    pattern_found = False
    after_double_dash = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg is None:
            i += 1
            continue

        if not after_double_dash and arg == "--":
            after_double_dash = True
            i += 1
            continue

        if not after_double_dash and arg.startswith("-"):
            flag = arg.split("=")[0]
            if flag in ("-e", "--regexp", "-f", "--file"):
                pattern_found = True
            if flag and flag in flags_with_args and "=" not in arg:
                i += 1
            i += 1
            continue

        # First non-flag is pattern, rest are paths
        if not pattern_found:
            pattern_found = True
            i += 1
            continue
        paths.append(arg)
        i += 1

    return paths if paths else defaults


# ─── Per-command path extractors ──────────────────────────────────────────────

def _extract_cd(args: List[str]) -> List[str]:
    if not args:
        return [os.path.expanduser("~")]
    return [" ".join(args)]


def _extract_ls(args: List[str]) -> List[str]:
    paths = filter_out_flags(args)
    return paths if paths else ["."]


def _extract_find(args: List[str]) -> List[str]:
    paths: List[str] = []
    path_flags: Set[str] = {
        "-newer", "-anewer", "-cnewer", "-mnewer", "-samefile",
        "-path", "-wholename", "-ilname", "-lname", "-ipath", "-iwholename",
    }
    newer_pattern = re.compile(r"^-newer[acmBt][acmtB]$")
    found_non_global_flag = False
    after_double_dash = False

    i = 0
    while i < len(args):
        arg = args[i]
        if not arg:
            i += 1
            continue

        if after_double_dash:
            paths.append(arg)
            i += 1
            continue

        if arg == "--":
            after_double_dash = True
            i += 1
            continue

        if arg.startswith("-"):
            if arg in ("-H", "-L", "-P"):
                i += 1
                continue
            found_non_global_flag = True
            if arg in path_flags or newer_pattern.match(arg):
                if i + 1 < len(args) and args[i + 1]:
                    paths.append(args[i + 1])
                    i += 2
                    continue
            i += 1
            continue

        if not found_non_global_flag:
            paths.append(arg)
        i += 1

    return paths if paths else ["."]


def _extract_tr(args: List[str]) -> List[str]:
    has_delete = any(
        a == "-d" or a == "--delete" or (a.startswith("-") and "d" in a)
        for a in args
    )
    non_flags = filter_out_flags(args)
    return non_flags[1 if has_delete else 2:]


def _extract_grep(args: List[str]) -> List[str]:
    flags = {
        "-e", "--regexp", "-f", "--file", "--exclude", "--include",
        "--exclude-dir", "--include-dir", "-m", "--max-count",
        "-A", "--after-context", "-B", "--before-context", "-C", "--context",
    }
    paths = parse_pattern_command(args, flags)
    if not paths and any(a in ("-r", "-R", "--recursive") for a in args):
        return ["."]
    return paths


def _extract_rg(args: List[str]) -> List[str]:
    flags = {
        "-e", "--regexp", "-f", "--file", "-t", "--type",
        "-T", "--type-not", "-g", "--glob", "-m", "--max-count",
        "--max-depth", "-r", "--replace", "-A", "--after-context",
        "-B", "--before-context", "-C", "--context",
    }
    return parse_pattern_command(args, flags, ["."])


def _extract_sed(args: List[str]) -> List[str]:
    paths: List[str] = []
    skip_next = False
    script_found = False
    after_double_dash = False

    i = 0
    while i < len(args):
        if skip_next:
            skip_next = False
            i += 1
            continue

        arg = args[i]
        if not arg:
            i += 1
            continue

        if not after_double_dash and arg == "--":
            after_double_dash = True
            i += 1
            continue

        if not after_double_dash and arg.startswith("-"):
            if arg in ("-f", "--file"):
                if i + 1 < len(args) and args[i + 1]:
                    paths.append(args[i + 1])
                    skip_next = True
                script_found = True
            elif arg in ("-e", "--expression"):
                skip_next = True
                script_found = True
            elif "e" in arg or "f" in arg:
                script_found = True
            i += 1
            continue

        if not script_found:
            script_found = True
            i += 1
            continue

        paths.append(arg)
        i += 1

    return paths


def _extract_jq(args: List[str]) -> List[str]:
    paths: List[str] = []
    flags_with_args: Set[str] = {
        "-e", "--expression", "-f", "--from-file",
        "--arg", "--argjson", "--slurpfile", "--rawfile",
        "--args", "--jsonargs", "-L", "--library-path",
        "--indent", "--tab",
    }
    filter_found = False
    after_double_dash = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg is None:
            i += 1
            continue

        if not after_double_dash and arg == "--":
            after_double_dash = True
            i += 1
            continue

        if not after_double_dash and arg.startswith("-"):
            flag = arg.split("=")[0]
            if flag in ("-e", "--expression"):
                filter_found = True
            if flag and flag in flags_with_args and "=" not in arg:
                i += 1
            i += 1
            continue

        if not filter_found:
            filter_found = True
            i += 1
            continue
        paths.append(arg)
        i += 1

    return paths


def _extract_git(args: List[str]) -> List[str]:
    if len(args) >= 1 and args[0] == "diff":
        if "--no-index" in args:
            file_paths = filter_out_flags(args[1:])
            return file_paths[:2]
    return []


# ─── PATH_EXTRACTORS registry ─────────────────────────────────────────────────

PATH_EXTRACTORS: Dict[str, Callable[[List[str]], List[str]]] = {
    "cd": _extract_cd,
    "ls": _extract_ls,
    "find": _extract_find,
    "mkdir": filter_out_flags,
    "touch": filter_out_flags,
    "rm": filter_out_flags,
    "rmdir": filter_out_flags,
    "mv": filter_out_flags,
    "cp": filter_out_flags,
    "cat": filter_out_flags,
    "head": filter_out_flags,
    "tail": filter_out_flags,
    "sort": filter_out_flags,
    "uniq": filter_out_flags,
    "wc": filter_out_flags,
    "cut": filter_out_flags,
    "paste": filter_out_flags,
    "column": filter_out_flags,
    "tr": _extract_tr,
    "file": filter_out_flags,
    "stat": filter_out_flags,
    "diff": filter_out_flags,
    "awk": filter_out_flags,
    "strings": filter_out_flags,
    "hexdump": filter_out_flags,
    "od": filter_out_flags,
    "base64": filter_out_flags,
    "nl": filter_out_flags,
    "grep": _extract_grep,
    "rg": _extract_rg,
    "sed": _extract_sed,
    "git": _extract_git,
    "jq": _extract_jq,
    "sha256sum": filter_out_flags,
    "sha1sum": filter_out_flags,
    "md5sum": filter_out_flags,
}

# ─── Command-specific validators ──────────────────────────────────────────────

COMMAND_VALIDATOR: Dict[str, Callable[[List[str]], bool]] = {
    "mv": lambda args: not any(a and a.startswith("-") for a in args),
    "cp": lambda args: not any(a and a.startswith("-") for a in args),
}


# ─── Dangerous removal check ──────────────────────────────────────────────────

def check_dangerous_removal_paths(
    command: str,
    args: List[str],
    cwd: str,
) -> Dict[str, Any]:
    """
    Checks if an rm/rmdir command targets dangerous paths that should always
    require explicit user approval.
    """
    extractor = PATH_EXTRACTORS.get(command)
    if extractor is None:
        return {"behavior": "passthrough", "message": f"No dangerous removals detected for {command} command"}

    paths = extractor(args)

    for path in paths:
        clean_path = expand_tilde(re.sub(r"^['\"]|['\"]$", "", path))
        if os.path.isabs(clean_path):
            absolute_path = clean_path
        else:
            absolute_path = os.path.join(cwd, clean_path)

        if is_dangerous_removal_path(absolute_path):
            return {
                "behavior": "ask",
                "message": (
                    f"Dangerous {command} operation detected: '{absolute_path}'\n\n"
                    "This command would remove a critical system directory. This requires explicit "
                    "approval and cannot be auto-allowed by permission rules."
                ),
                "decision_reason": {
                    "type": "other",
                    "reason": f"Dangerous {command} operation on critical path: {absolute_path}",
                },
                "suggestions": [],
            }

    return {
        "behavior": "passthrough",
        "message": f"No dangerous removals detected for {command} command",
    }


# ─── Core validation functions ────────────────────────────────────────────────

def validate_command_paths(
    command: str,
    args: List[str],
    cwd: str,
    tool_permission_context: Any,
    compound_command_has_cd: Optional[bool] = None,
    operation_type_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate paths for a specific command."""
    extractor = PATH_EXTRACTORS.get(command)
    if extractor is None:
        return {"behavior": "passthrough", "message": f"Command '{command}' is not a path-restricted command"}

    paths = extractor(args)
    operation_type = operation_type_override or COMMAND_OPERATION_TYPE.get(command, "read")

    # Check command-specific validators
    validator = COMMAND_VALIDATOR.get(command)
    if validator and not validator(args):
        return {
            "behavior": "ask",
            "message": (
                f"{command} with flags requires manual approval to ensure path safety. "
                f"For security, Claude Code cannot automatically validate {command} commands "
                f"that use flags, as some flags like --target-directory=PATH can bypass path validation."
            ),
            "decision_reason": {
                "type": "other",
                "reason": f"{command} command with flags requires manual approval",
            },
        }

    # SECURITY: Block write operations in compound commands containing 'cd'
    if compound_command_has_cd and operation_type != "read":
        return {
            "behavior": "ask",
            "message": (
                "Commands that change directories and perform write operations require explicit "
                "approval to ensure paths are evaluated correctly. For security, Claude Code cannot "
                "automatically determine the final working directory when 'cd' is used in compound commands."
            ),
            "decision_reason": {
                "type": "other",
                "reason": "Compound command contains cd with write operation - manual approval required to prevent path resolution bypass",
            },
        }

    for path in paths:
        validated = validate_path(path, cwd, tool_permission_context, operation_type)
        allowed = getattr(validated, "allowed", True)
        resolved_path = getattr(validated, "resolved_path", path)
        decision_reason = getattr(validated, "decision_reason", None)

        if not allowed:
            working_dirs = list(all_working_directories(tool_permission_context))
            dir_list_str = format_directory_list(working_dirs)

            message = (
                decision_reason["reason"]
                if decision_reason and decision_reason.get("type") in ("other", "safetyCheck")
                else f"{command} in '{resolved_path}' was blocked. For security, Claude Code may only "
                     f"{ACTION_VERBS.get(command, 'access files in')} the allowed working directories for this session: {dir_list_str}."
            )

            if decision_reason and decision_reason.get("type") == "rule":
                return {"behavior": "deny", "message": message, "decision_reason": decision_reason}

            return {
                "behavior": "ask",
                "message": message,
                "blocked_path": resolved_path,
                "decision_reason": decision_reason,
            }

    return {
        "behavior": "passthrough",
        "message": f"Path validation passed for {command} command",
    }


def create_path_checker(
    command: str,
    operation_type_override: Optional[str] = None,
) -> Callable[[List[str], str, Any, Optional[bool]], Dict[str, Any]]:
    """
    Returns a path checker function for the given command.
    The returned function validates paths and adds suggestions to ask results.
    """
    def checker(
        args: List[str],
        cwd: str,
        context: Any,
        compound_command_has_cd: Optional[bool] = None,
    ) -> Dict[str, Any]:
        result = validate_command_paths(
            command, args, cwd, context, compound_command_has_cd, operation_type_override
        )

        if result.get("behavior") == "deny":
            return result

        if command in ("rm", "rmdir"):
            dangerous = check_dangerous_removal_paths(command, args, cwd)
            if dangerous.get("behavior") != "passthrough":
                return dangerous

        if result.get("behavior") == "passthrough":
            return result

        if result.get("behavior") == "ask":
            op_type = operation_type_override or COMMAND_OPERATION_TYPE.get(command, "read")
            suggestions: List[Dict[str, Any]] = []

            blocked_path = result.get("blocked_path")
            if blocked_path:
                if op_type == "read":
                    suggestion = create_read_rule_suggestion(get_directory_for_path(blocked_path), "session")
                    if suggestion:
                        suggestions.append(suggestion)
                else:
                    suggestions.append({
                        "type": "addDirectories",
                        "directories": [get_directory_for_path(blocked_path)],
                        "destination": "session",
                    })

            if op_type in ("write", "create"):
                suggestions.append({"type": "setMode", "mode": "acceptEdits", "destination": "session"})

            result = dict(result)
            result["suggestions"] = suggestions

        return result

    return checker


def parse_command_arguments(cmd: str) -> List[str]:
    """
    Parse command arguments using shell-quote, converting glob objects to strings.
    """
    parse_result = try_parse_shell_command(cmd, lambda env: f"${env}")
    if not getattr(parse_result, "success", False):
        return []
    tokens = getattr(parse_result, "tokens", [])
    extracted_args: List[str] = []

    for arg in tokens:
        if isinstance(arg, str):
            extracted_args.append(arg)
        elif (
            isinstance(arg, dict)
            and arg.get("op") == "glob"
            and "pattern" in arg
        ):
            extracted_args.append(str(arg["pattern"]))

    return extracted_args


def validate_single_path_command(
    cmd: str,
    cwd: str,
    tool_permission_context: Any,
    compound_command_has_cd: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Validates a single command for path constraints and shell safety.
    """
    stripped_cmd = strip_safe_wrappers(cmd)
    extracted_args = parse_command_arguments(stripped_cmd)

    if not extracted_args:
        return {"behavior": "passthrough", "message": "Empty command - no paths to validate"}

    base_cmd, *args = extracted_args
    if not base_cmd or base_cmd not in SUPPORTED_PATH_COMMANDS:
        return {"behavior": "passthrough", "message": f"Command '{base_cmd}' is not a path-restricted command"}

    operation_type_override = None
    if base_cmd == "sed" and sed_command_is_allowed_by_allowlist(stripped_cmd):
        operation_type_override = "read"

    path_checker = create_path_checker(base_cmd, operation_type_override)
    return path_checker(args, cwd, tool_permission_context, compound_command_has_cd)


def validate_single_path_command_argv(
    cmd: Any,  # SimpleCommand
    cwd: str,
    tool_permission_context: Any,
    compound_command_has_cd: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Like validate_single_path_command but operates on AST-derived argv directly.
    Avoids the shell-quote single-quote backslash bug.
    """
    argv = strip_wrappers_from_argv(getattr(cmd, "argv", []))
    if not argv:
        return {"behavior": "passthrough", "message": "Empty command - no paths to validate"}

    base_cmd, *args = argv
    if not base_cmd or base_cmd not in SUPPORTED_PATH_COMMANDS:
        return {"behavior": "passthrough", "message": f"Command '{base_cmd}' is not a path-restricted command"}

    operation_type_override = None
    cmd_text = getattr(cmd, "text", "")
    if base_cmd == "sed" and sed_command_is_allowed_by_allowlist(strip_safe_wrappers(cmd_text)):
        operation_type_override = "read"

    path_checker = create_path_checker(base_cmd, operation_type_override)
    return path_checker(args, cwd, tool_permission_context, compound_command_has_cd)


def validate_output_redirections(
    redirections: List[Dict[str, str]],
    cwd: str,
    tool_permission_context: Any,
    compound_command_has_cd: Optional[bool] = None,
) -> Dict[str, Any]:
    """Validate output redirections."""
    # SECURITY: Block output redirections in compound commands containing 'cd'
    if compound_command_has_cd and redirections:
        return {
            "behavior": "ask",
            "message": (
                "Commands that change directories and write via output redirection require explicit "
                "approval to ensure paths are evaluated correctly. For security, Claude Code cannot "
                "automatically determine the final working directory when 'cd' is used in compound commands."
            ),
            "decision_reason": {
                "type": "other",
                "reason": "Compound command contains cd with output redirection - manual approval required to prevent path resolution bypass",
            },
        }

    for redir in redirections:
        target = redir.get("target", "")
        # /dev/null is always safe
        if target == "/dev/null":
            continue

        validated = validate_path(target, cwd, tool_permission_context, "create")
        allowed = getattr(validated, "allowed", True)
        resolved_path = getattr(validated, "resolved_path", target)
        decision_reason = getattr(validated, "decision_reason", None)

        if not allowed:
            working_dirs = list(all_working_directories(tool_permission_context))
            dir_list_str = format_directory_list(working_dirs)

            if decision_reason and decision_reason.get("type") in ("other", "safetyCheck"):
                message = decision_reason["reason"]
            elif decision_reason and decision_reason.get("type") == "rule":
                message = f"Output redirection to '{resolved_path}' was blocked by a deny rule."
            else:
                message = f"Output redirection to '{resolved_path}' was blocked. For security, Claude Code may only write to files in the allowed working directories for this session: {dir_list_str}."

            if decision_reason and decision_reason.get("type") == "rule":
                return {"behavior": "deny", "message": message, "decision_reason": decision_reason}

            return {
                "behavior": "ask",
                "message": message,
                "blocked_path": resolved_path,
                "decision_reason": decision_reason,
                "suggestions": [{
                    "type": "addDirectories",
                    "directories": [get_directory_for_path(resolved_path)],
                    "destination": "session",
                }],
            }

    return {"behavior": "passthrough", "message": "No unsafe redirections found"}


def ast_redirects_to_output_redirections(
    redirects: List[Any],
) -> Tuple[List[Dict[str, str]], bool]:
    """
    Convert AST-derived Redirect list to the format expected by
    validate_output_redirections.
    """
    redirections: List[Dict[str, str]] = []
    for r in redirects:
        op = getattr(r, "op", "")
        target = getattr(r, "target", "")
        if op in (">", ">|", "&>"):
            redirections.append({"target": target, "operator": ">"})
        elif op in (">>", "&>>"):
            redirections.append({"target": target, "operator": ">>"})
        elif op == ">&":
            if not re.match(r"^\d+$", target):
                redirections.append({"target": target, "operator": ">"})
        # Input redirects (<, <<, <&, <<<) are skipped
    return redirections, False  # AST targets are fully resolved — no dangerous redirections


def check_path_constraints(
    input_data: Dict[str, Any],
    cwd: str,
    tool_permission_context: Any,
    compound_command_has_cd: Optional[bool] = None,
    ast_redirects: Optional[List[Any]] = None,
    ast_commands: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Checks path constraints for commands that access the filesystem.
    Also validates output redirections.

    Returns:
        - 'ask'         if any path command or redirection tries to access outside allowed directories
        - 'deny'        if a deny rule explicitly blocks a path
        - 'passthrough' if all paths are within allowed directories
    """
    command = input_data.get("command", "")

    # SECURITY: Process substitution check (skip on AST path — already caught by checkSemantics)
    if not ast_commands and re.search(r'>>\s*>\s*\(|>\s*>\s*\(|<\s*\(', command):
        return {
            "behavior": "ask",
            "message": "Process substitution (>(...) or <(...)) can execute arbitrary commands and requires manual approval",
            "decision_reason": {
                "type": "other",
                "reason": "Process substitution requires manual approval",
            },
        }

    # Extract and validate output redirections
    if ast_redirects is not None:
        redirections, has_dangerous = ast_redirects_to_output_redirections(ast_redirects)
    else:
        redir_result = extract_output_redirections(command)
        redirections = getattr(redir_result, "redirections", [])
        has_dangerous = getattr(redir_result, "has_dangerous_redirection", False)

    if has_dangerous:
        return {
            "behavior": "ask",
            "message": "Shell expansion syntax in paths requires manual approval",
            "decision_reason": {
                "type": "other",
                "reason": "Shell expansion syntax in paths requires manual approval",
            },
        }

    # Convert to dict format if needed (AST returns dicts, legacy returns objects)
    redir_dicts = []
    for r in redirections:
        if isinstance(r, dict):
            redir_dicts.append(r)
        else:
            redir_dicts.append({"target": getattr(r, "target", ""), "operator": getattr(r, "operator", ">")})

    redirection_result = validate_output_redirections(
        redir_dicts, cwd, tool_permission_context, compound_command_has_cd
    )
    if redirection_result.get("behavior") != "passthrough":
        return redirection_result

    # Validate commands
    if ast_commands is not None:
        for cmd in ast_commands:
            result = validate_single_path_command_argv(
                cmd, cwd, tool_permission_context, compound_command_has_cd
            )
            if result.get("behavior") in ("ask", "deny"):
                return result
    else:
        commands = split_command_deprecated(command)
        for cmd in commands:
            result = validate_single_path_command(
                cmd, cwd, tool_permission_context, compound_command_has_cd
            )
            if result.get("behavior") in ("ask", "deny"):
                return result

    return {
        "behavior": "passthrough",
        "message": "All path commands validated successfully",
    }


# ─── Wrapper stripping ────────────────────────────────────────────────────────

_TIMEOUT_FLAG_VALUE_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")


def _skip_timeout_flags(a: List[str]) -> int:
    """Parse timeout's GNU flags, return argv index of the DURATION token, or -1."""
    i = 1
    while i < len(a):
        arg = a[i]
        next_ = a[i + 1] if i + 1 < len(a) else None
        if arg in ("--foreground", "--preserve-status", "--verbose"):
            i += 1
        elif re.match(r"^--(?:kill-after|signal)=[A-Za-z0-9_.+-]+$", arg):
            i += 1
        elif arg in ("--kill-after", "--signal") and next_ and _TIMEOUT_FLAG_VALUE_RE.match(next_):
            i += 2
        elif arg == "--":
            i += 1
            break
        elif arg.startswith("--"):
            return -1
        elif arg == "-v":
            i += 1
        elif arg in ("-k", "-s") and next_ and _TIMEOUT_FLAG_VALUE_RE.match(next_):
            i += 2
        elif re.match(r"^-[ks][A-Za-z0-9_.+-]+$", arg):
            i += 1
        elif arg.startswith("-"):
            return -1
        else:
            break
    return i


def _skip_stdbuf_flags(a: List[str]) -> int:
    """Parse stdbuf's flags; returns argv index of wrapped COMMAND, or -1."""
    i = 1
    while i < len(a):
        arg = a[i]
        if re.match(r"^-[ioe]$", arg) and i + 1 < len(a):
            i += 2
        elif re.match(r"^-[ioe].", arg):
            i += 1
        elif re.match(r"^--(input|output|error)=", arg):
            i += 1
        elif arg.startswith("-"):
            return -1
        else:
            break
    return i if i > 1 and i < len(a) else -1


def _skip_env_flags(a: List[str]) -> int:
    """Parse env's VAR=val and safe flags; returns argv index of wrapped COMMAND, or -1."""
    i = 1
    while i < len(a):
        arg = a[i]
        if "=" in arg and not arg.startswith("-"):
            i += 1
        elif arg in ("-i", "-0", "-v"):
            i += 1
        elif arg == "-u" and i + 1 < len(a):
            i += 2
        elif arg.startswith("-"):
            return -1
        else:
            break
    return i if i < len(a) else -1


def strip_wrappers_from_argv(argv: List[str]) -> List[str]:
    """
    Argv-level counterpart to strip_safe_wrappers (bash_permissions.py).
    Strips wrapper commands from AST-derived argv.
    """
    a = list(argv)
    while True:
        if not a:
            return a
        if a[0] in ("time", "nohup"):
            a = a[2:] if len(a) > 1 and a[1] == "--" else a[1:]
        elif a[0] == "timeout":
            i = _skip_timeout_flags(a)
            if i < 0 or i >= len(a) or not re.match(r"^\d+(?:\.\d+)?[smhd]?$", a[i]):
                return a
            a = a[i + 1:]
        elif a[0] == "nice":
            if len(a) > 2 and a[1] == "-n" and re.match(r"^-?\d+$", a[2]):
                a = a[4:] if len(a) > 3 and a[3] == "--" else a[3:]
            elif len(a) > 1 and re.match(r"^-\d+$", a[1]):
                a = a[3:] if len(a) > 2 and a[2] == "--" else a[2:]
            else:
                a = a[2:] if len(a) > 1 and a[1] == "--" else a[1:]
        elif a[0] == "stdbuf":
            i = _skip_stdbuf_flags(a)
            if i < 0:
                return a
            a = a[i:]
        elif a[0] == "env":
            i = _skip_env_flags(a)
            if i < 0:
                return a
            a = a[i:]
        else:
            return a


# ─── Public exports ───────────────────────────────────────────────────────────

__all__ = [
    "ACTION_VERBS",
    "COMMAND_OPERATION_TYPE",
    "COMMAND_VALIDATOR",
    "PATH_EXTRACTORS",
    "SUPPORTED_PATH_COMMANDS",
    "ast_redirects_to_output_redirections",
    "check_dangerous_removal_paths",
    "check_path_constraints",
    "create_path_checker",
    "filter_out_flags",
    "parse_command_arguments",
    "parse_pattern_command",
    "strip_wrappers_from_argv",
    "validate_command_paths",
    "validate_output_redirections",
    "validate_single_path_command",
    "validate_single_path_command_argv",
]
