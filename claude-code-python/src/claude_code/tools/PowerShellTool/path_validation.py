"""
PowerShell-specific path validation for command arguments.

Extracts file paths from PowerShell commands using the AST parser
and validates they stay within allowed project directories.
Follows the same patterns as BashTool/path_validation.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, NamedTuple, Optional, Set, Tuple

# ─── Internal import stubs with graceful fallback ─────────────────────────────

try:
    from claude_code.utils.permissions.path_validation import (
        is_dangerous_removal_path,
        is_path_in_sandbox_write_allowlist,
    )
except ImportError:
    def is_dangerous_removal_path(path: str) -> bool:
        dangerous = {"/", "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
                     "/boot", "/dev", "/proc", "/sys", "/var"}
        home = os.path.expanduser("~")
        expanded = os.path.expanduser(path)
        return expanded in dangerous or path in dangerous or expanded == home

    def is_path_in_sandbox_write_allowlist(path: str) -> bool:
        return False

try:
    from claude_code.utils.permissions.filesystem import (
        all_working_directories,
        check_editable_internal_path,
        check_path_safety_for_auto_edit,
        check_readable_internal_path,
        matching_rule_for_input,
        path_in_allowed_working_path,
    )
except ImportError:
    def all_working_directories(ctx: Any):
        return []

    def check_editable_internal_path(path: str, opts: dict):
        return type("R", (), {"behavior": "deny"})()

    def check_path_safety_for_auto_edit(path: str, paths=None):
        return type("R", (), {"safe": True})()

    def check_readable_internal_path(path: str, opts: dict):
        return type("R", (), {"behavior": "deny"})()

    def matching_rule_for_input(path: str, ctx: Any, ptype: str, kind: str):
        return None

    def path_in_allowed_working_path(path: str, ctx: Any, paths=None) -> bool:
        return False

try:
    from claude_code.utils.permissions.permission_update import create_read_rule_suggestion
except ImportError:
    def create_read_rule_suggestion(directory: str, destination: str):
        return None

try:
    from claude_code.utils.path import contains_path_traversal, get_directory_for_path
except ImportError:
    def contains_path_traversal(path: str) -> bool:
        return ".." in path

    def get_directory_for_path(path: str) -> str:
        return str(Path(path).parent)

try:
    from claude_code.utils.cwd import get_cwd
except ImportError:
    def get_cwd() -> str:
        return os.getcwd()

try:
    from claude_code.utils.platform import get_platform
except ImportError:
    def get_platform() -> str:
        import platform
        return "windows" if platform.system() == "Windows" else "posix"

try:
    from claude_code.utils.fs_operations import get_fs_implementation, safe_resolve_path
except ImportError:
    def get_fs_implementation():
        return None

    def safe_resolve_path(fs, path: str):
        resolved = os.path.realpath(path)
        return type("R", (), {"resolved_path": resolved, "is_canonical": True})()

try:
    from claude_code.utils.powershell.parser import (
        is_null_redirection_target,
        is_powershell_parameter,
        ParsedCommandElement,
        ParsedPowerShellCommand,
    )
except ImportError:
    def is_null_redirection_target(target: str) -> bool:
        return target in ("$null", "/dev/null", "nul", "NUL")

    def is_powershell_parameter(arg: str, element_type: Optional[str] = None) -> bool:
        return element_type == "Parameter" if element_type else arg.startswith("-")

    class ParsedCommandElement:
        def __init__(self):
            self.name = ""
            self.args: List[str] = []
            self.element_types: Optional[List[str]] = None
            self.redirections: Optional[List[Any]] = None

    class ParsedPowerShellCommand:
        def __init__(self):
            self.valid = False
            self.statements: List[Any] = []

try:
    from claude_code.tools.PowerShellTool.common_parameters import COMMON_SWITCHES, COMMON_VALUE_PARAMS
except ImportError:
    COMMON_SWITCHES: List[str] = [
        "-verbose", "-debug", "-erroraction", "-warningaction",
        "-informationaction", "-errorvariable", "-warningvariable",
        "-informationvariable", "-outvariable", "-outbuffer",
        "-pipelinevariable",
    ]
    COMMON_VALUE_PARAMS: List[str] = []

try:
    from claude_code.tools.PowerShellTool.read_only_validation import resolve_to_canonical
except ImportError:
    # Minimal alias map for standalone use
    _CANONICAL_MAP: Dict[str, str] = {
        "gc": "get-content", "cat": "get-content", "type": "get-content",
        "gci": "get-childitem", "ls": "get-childitem", "dir": "get-childitem",
        "gi": "get-item", "gp": "get-itemproperty",
        "sc": "set-content", "ac": "add-content",
        "ri": "remove-item", "rm": "remove-item", "del": "remove-item",
        "rd": "remove-item", "rmdir": "remove-item", "erase": "remove-item",
        "ni": "new-item", "mkdir": "new-item",
        "cp": "copy-item", "copy": "copy-item", "cpi": "copy-item",
        "mv": "move-item", "move": "move-item", "mi": "move-item",
        "ren": "rename-item", "rni": "rename-item",
        "si": "set-item",
        "sl": "set-location", "cd": "set-location", "chdir": "set-location",
        "pushd": "push-location", "popd": "pop-location",
        "iwr": "invoke-webrequest", "wget": "invoke-webrequest", "curl": "invoke-webrequest",
        "irm": "invoke-restmethod",
        "of": "out-file",
    }

    def resolve_to_canonical(name: str) -> str:
        lower = name.lower()
        return _CANONICAL_MAP.get(lower, lower)


# ─── Types ────────────────────────────────────────────────────────────────────

FileOperationType = Literal["read", "write", "create"]

MAX_DIRS_TO_LIST = 5
# PowerShell wildcards: only * ? [ ] — braces are LITERAL
GLOB_PATTERN_REGEX = re.compile(r"[*?\[\]]")


class PathCheckResult(NamedTuple):
    allowed: bool
    decision_reason: Optional[Dict[str, Any]] = None


class ResolvedPathCheckResult(NamedTuple):
    allowed: bool
    resolved_path: str
    decision_reason: Optional[Dict[str, Any]] = None


class CmdletPathConfig:
    """Per-cmdlet parameter configuration."""

    def __init__(
        self,
        operation_type: FileOperationType,
        path_params: List[str],
        known_switches: List[str],
        known_value_params: List[str],
        leaf_only_path_params: Optional[List[str]] = None,
        positional_skip: int = 0,
        optional_write: bool = False,
    ):
        self.operation_type = operation_type
        self.path_params = path_params
        self.known_switches = known_switches
        self.known_value_params = known_value_params
        self.leaf_only_path_params = leaf_only_path_params or []
        self.positional_skip = positional_skip
        self.optional_write = optional_write


# ─── Cmdlet configuration table ───────────────────────────────────────────────

CMDLET_PATH_CONFIG: Dict[str, CmdletPathConfig] = {
    # ─── Write/create operations ──────────────────────────────────────
    "set-content": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-passthru", "-force", "-whatif", "-confirm", "-usetransaction", "-nonewline", "-asbytestream"],
        known_value_params=["-value", "-filter", "-include", "-exclude", "-credential", "-encoding", "-stream"],
    ),
    "add-content": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-passthru", "-force", "-whatif", "-confirm", "-usetransaction", "-nonewline", "-asbytestream"],
        known_value_params=["-value", "-filter", "-include", "-exclude", "-credential", "-encoding", "-stream"],
    ),
    "remove-item": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-recurse", "-force", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-filter", "-include", "-exclude", "-credential", "-stream"],
    ),
    "clear-content": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-filter", "-include", "-exclude", "-credential", "-stream"],
    ),
    "out-file": CmdletPathConfig(
        operation_type="write",
        path_params=["-filepath", "-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-append", "-force", "-noclobber", "-nonewline", "-whatif", "-confirm"],
        known_value_params=["-inputobject", "-encoding", "-width"],
    ),
    "tee-object": CmdletPathConfig(
        operation_type="write",
        path_params=["-filepath", "-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-append"],
        known_value_params=["-inputobject", "-variable", "-encoding"],
    ),
    "export-csv": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-append", "-force", "-noclobber", "-notypeinformation", "-includetypeinformation",
                        "-useculture", "-noheader", "-whatif", "-confirm"],
        known_value_params=["-inputobject", "-delimiter", "-encoding", "-quotefields", "-usequotes"],
    ),
    "export-clixml": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-noclobber", "-whatif", "-confirm"],
        known_value_params=["-inputobject", "-depth", "-encoding"],
    ),
    "new-item": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        leaf_only_path_params=["-name"],
        known_switches=["-force", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-itemtype", "-value", "-credential", "-type"],
    ),
    "copy-item": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp", "-destination"],
        known_switches=["-container", "-force", "-passthru", "-recurse", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-filter", "-include", "-exclude", "-credential", "-fromsession", "-tosession"],
    ),
    "move-item": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp", "-destination"],
        known_switches=["-force", "-passthru", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-filter", "-include", "-exclude", "-credential"],
    ),
    "rename-item": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-passthru", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-newname", "-credential", "-filter", "-include", "-exclude"],
    ),
    "set-item": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-passthru", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-value", "-credential", "-filter", "-include", "-exclude"],
    ),
    # ─── Read operations ──────────────────────────────────────────────
    "get-content": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-usetransaction", "-wait", "-raw", "-asbytestream"],
        known_value_params=["-readcount", "-totalcount", "-tail", "-first", "-head", "-last",
                            "-filter", "-include", "-exclude", "-credential", "-delimiter", "-encoding", "-stream"],
    ),
    "get-childitem": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-recurse", "-force", "-name", "-usetransaction", "-followsymlink",
                        "-directory", "-file", "-hidden", "-readonly", "-system"],
        known_value_params=["-filter", "-include", "-exclude", "-depth", "-attributes", "-credential"],
    ),
    "get-item": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-usetransaction"],
        known_value_params=["-filter", "-include", "-exclude", "-credential", "-stream"],
    ),
    "get-itemproperty": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-usetransaction"],
        known_value_params=["-name", "-filter", "-include", "-exclude", "-credential"],
    ),
    "get-itempropertyvalue": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-usetransaction"],
        known_value_params=["-name", "-filter", "-include", "-exclude", "-credential"],
    ),
    "get-filehash": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=[],
        known_value_params=["-algorithm", "-inputstream"],
    ),
    "get-acl": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-audit", "-allcentralaccesspolicies", "-usetransaction"],
        known_value_params=["-inputobject", "-filter", "-include", "-exclude"],
    ),
    "format-hex": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-raw"],
        known_value_params=["-inputobject", "-encoding", "-count", "-offset"],
    ),
    "test-path": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-isvalid", "-usetransaction"],
        known_value_params=["-filter", "-include", "-exclude", "-pathtype", "-credential", "-olderthan", "-newerthan"],
    ),
    "resolve-path": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-relative", "-usetransaction", "-force"],
        known_value_params=["-credential", "-relativebasepath"],
    ),
    "convert-path": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-usetransaction"],
        known_value_params=[],
    ),
    "select-string": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-simplematch", "-casesensitive", "-quiet", "-list", "-notmatch",
                        "-allmatches", "-noemphasis", "-raw"],
        known_value_params=["-inputobject", "-pattern", "-include", "-exclude", "-encoding", "-context", "-culture"],
    ),
    "set-location": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-passthru", "-usetransaction"],
        known_value_params=["-stackname"],
    ),
    "push-location": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-passthru", "-usetransaction"],
        known_value_params=["-stackname"],
    ),
    "pop-location": CmdletPathConfig(
        operation_type="read",
        path_params=[],
        known_switches=["-passthru", "-usetransaction"],
        known_value_params=["-stackname"],
    ),
    "select-xml": CmdletPathConfig(
        operation_type="read",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=[],
        known_value_params=["-xml", "-content", "-xpath", "-namespace"],
    ),
    "get-winevent": CmdletPathConfig(
        operation_type="read",
        path_params=["-path"],
        known_switches=["-force", "-oldest"],
        known_value_params=["-listlog", "-logname", "-listprovider", "-providername", "-maxevents",
                            "-computername", "-credential", "-filterxpath", "-filterxml", "-filterhashtable"],
    ),
    # ─── Write-path cmdlets with output parameters ────────────────────
    "invoke-webrequest": CmdletPathConfig(
        operation_type="write",
        path_params=["-outfile", "-infile"],
        positional_skip=1,
        optional_write=True,
        known_switches=["-allowinsecureredirect", "-allowunencryptedauthentication", "-disablekeepalive",
                        "-nobodyprogress", "-passthru", "-preservefileauthorizationmetadata", "-resume",
                        "-skipcertificatecheck", "-skipheadervalidation", "-skiphttperrorcheck",
                        "-usebasicparsing", "-usedefaultcredentials"],
        known_value_params=["-uri", "-method", "-body", "-contenttype", "-headers", "-maximumredirection",
                            "-maximumretrycount", "-proxy", "-proxycredential", "-retryintervalsec",
                            "-sessionvariable", "-timeoutsec", "-token", "-transferencoding", "-useragent",
                            "-websession", "-credential", "-authentication", "-certificate",
                            "-certificatethumbprint", "-form", "-httpversion"],
    ),
    "invoke-restmethod": CmdletPathConfig(
        operation_type="write",
        path_params=["-outfile", "-infile"],
        positional_skip=1,
        optional_write=True,
        known_switches=["-allowinsecureredirect", "-allowunencryptedauthentication", "-disablekeepalive",
                        "-followrellink", "-nobodyprogress", "-passthru", "-preservefileauthorizationmetadata",
                        "-resume", "-skipcertificatecheck", "-skipheadervalidation", "-skiphttperrorcheck",
                        "-usebasicparsing", "-usedefaultcredentials"],
        known_value_params=["-uri", "-method", "-body", "-contenttype", "-headers", "-maximumfollowrellink",
                            "-maximumredirection", "-maximumretrycount", "-proxy", "-proxycredential",
                            "-responseheaderstvariable", "-retryintervalsec", "-sessionvariable",
                            "-statuscodevariable", "-timeoutsec", "-token", "-transferencoding",
                            "-useragent", "-websession", "-credential", "-authentication", "-certificate",
                            "-certificatethumbprint", "-form", "-httpversion"],
    ),
    "expand-archive": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp", "-destinationpath"],
        known_switches=["-force", "-passthru", "-whatif", "-confirm"],
        known_value_params=[],
    ),
    "compress-archive": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp", "-destinationpath"],
        known_switches=["-force", "-update", "-passthru", "-whatif", "-confirm"],
        known_value_params=["-compressionlevel"],
    ),
    "set-itemproperty": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-passthru", "-force", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-name", "-value", "-type", "-filter", "-include", "-exclude", "-credential", "-inputobject"],
    ),
    "new-itemproperty": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-name", "-value", "-propertytype", "-type", "-filter", "-include", "-exclude", "-credential"],
    ),
    "remove-itemproperty": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-name", "-filter", "-include", "-exclude", "-credential"],
    ),
    "clear-item": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-force", "-whatif", "-confirm", "-usetransaction"],
        known_value_params=["-filter", "-include", "-exclude", "-credential"],
    ),
    "export-alias": CmdletPathConfig(
        operation_type="write",
        path_params=["-path", "-literalpath", "-pspath", "-lp"],
        known_switches=["-append", "-force", "-noclobber", "-passthru", "-whatif", "-confirm"],
        known_value_params=["-name", "-description", "-scope", "-as"],
    ),
}

# ─── Element types safe for path extraction ──────────────────────────────────
SAFE_PATH_ELEMENT_TYPES: Set[str] = {"StringConstant", "Parameter"}


# ─── Helper functions ─────────────────────────────────────────────────────────

def matches_param(param_lower: str, param_list: List[str]) -> bool:
    """
    Check if a lowercase parameter name (with leading dash) matches any entry
    in the given param list, accounting for PowerShell's prefix-matching behavior.
    """
    for p in param_list:
        if p == param_lower or (len(param_lower) > 1 and p.startswith(param_lower)):
            return True
    return False


def has_complex_colon_value(raw_value: str) -> bool:
    """
    Returns True if a colon-syntax value contains expression constructs that
    mask the real runtime path (arrays, subexpressions, variables, backtick escapes).
    """
    return (
        "," in raw_value
        or raw_value.startswith("(")
        or raw_value.startswith("[")
        or "`" in raw_value
        or "@(" in raw_value
        or raw_value.startswith("@{")
        or "$" in raw_value
    )


def format_directory_list(directories: List[str]) -> str:
    dir_count = len(directories)
    if dir_count <= MAX_DIRS_TO_LIST:
        return ", ".join(f"'{d}'" for d in directories)
    first_dirs = ", ".join(f"'{d}'" for d in directories[:MAX_DIRS_TO_LIST])
    return f"{first_dirs}, and {dir_count - MAX_DIRS_TO_LIST} more"


def expand_tilde(file_path: str) -> str:
    """Expands tilde (~) at the start of a path to the user's home directory."""
    if file_path == "~" or file_path.startswith("~/") or file_path.startswith("~\\"):
        return os.path.expanduser("~") + file_path[1:]
    return file_path


def is_dangerous_removal_raw_path(file_path: str) -> bool:
    """
    Checks the raw user-provided path (pre-realpath) for dangerous removal targets.
    Checks the tilde-expanded, backslash-normalized form.
    """
    expanded = expand_tilde(re.sub(r"^['\"]|['\"]$", "", file_path)).replace("\\", "/")
    return is_dangerous_removal_path(expanded)


def dangerous_removal_deny(path: str) -> Dict[str, Any]:
    """Return a deny PermissionResult for dangerous removal targets."""
    return {
        "behavior": "deny",
        "message": f"Remove-Item on system path '{path}' is blocked. This path is protected from removal.",
        "decision_reason": {
            "type": "other",
            "reason": "Removal targets a protected system path",
        },
    }


def get_glob_base_directory(file_path: str) -> str:
    """Return the base directory before the first glob character."""
    match = GLOB_PATTERN_REGEX.search(file_path)
    if match is None:
        return file_path
    before_glob = file_path[: match.start()]
    last_sep = max(before_glob.rfind("/"), before_glob.rfind("\\"))
    if last_sep == -1:
        return "."
    return before_glob[: last_sep + 1] or "/"


# ─── Core path check ──────────────────────────────────────────────────────────

def is_path_allowed(
    resolved_path: str,
    context: Any,
    operation_type: FileOperationType,
    precomputed_paths_to_check: Optional[List[str]] = None,
) -> PathCheckResult:
    """
    Checks if a resolved path is allowed for the given operation type.
    Mirrors the logic in BashTool/path_validation.py is_path_allowed.
    """
    permission_type = "read" if operation_type == "read" else "edit"

    # 1. Check deny rules first
    deny_rule = matching_rule_for_input(resolved_path, context, permission_type, "deny")
    if deny_rule is not None:
        return PathCheckResult(allowed=False, decision_reason={"type": "rule", "rule": deny_rule})

    # 2. For write/create operations, check internal editable paths
    if operation_type != "read":
        internal_edit_result = check_editable_internal_path(resolved_path, {})
        if getattr(internal_edit_result, "behavior", None) == "allow":
            return PathCheckResult(
                allowed=True,
                decision_reason=getattr(internal_edit_result, "decision_reason", None),
            )

    # 2.5. For write/create operations, check safety validations
    if operation_type != "read":
        safety_check = check_path_safety_for_auto_edit(resolved_path, precomputed_paths_to_check)
        if not getattr(safety_check, "safe", True):
            return PathCheckResult(
                allowed=False,
                decision_reason={
                    "type": "safetyCheck",
                    "reason": getattr(safety_check, "message", "Safety check failed"),
                    "classifier_approvable": getattr(safety_check, "classifier_approvable", False),
                },
            )

    # 3. Check if path is in allowed working directory
    is_in_working_dir = path_in_allowed_working_path(resolved_path, context, precomputed_paths_to_check)
    if is_in_working_dir:
        if operation_type == "read" or getattr(context, "mode", None) == "acceptEdits":
            return PathCheckResult(allowed=True)

    # 3.5. For read operations, check internal readable paths
    if operation_type == "read":
        internal_read_result = check_readable_internal_path(resolved_path, {})
        if getattr(internal_read_result, "behavior", None) == "allow":
            return PathCheckResult(
                allowed=True,
                decision_reason=getattr(internal_read_result, "decision_reason", None),
            )

    # 3.7. Sandbox write allowlist (outside working dir)
    if operation_type != "read" and not is_in_working_dir and is_path_in_sandbox_write_allowlist(resolved_path):
        return PathCheckResult(
            allowed=True,
            decision_reason={"type": "other", "reason": "Path is in sandbox write allowlist"},
        )

    # 4. Check allow rules
    allow_rule = matching_rule_for_input(resolved_path, context, permission_type, "allow")
    if allow_rule is not None:
        return PathCheckResult(allowed=True, decision_reason={"type": "rule", "rule": allow_rule})

    # 5. Not allowed
    return PathCheckResult(allowed=False)


def check_deny_rule_for_guessed_path(
    stripped_path: str,
    cwd: str,
    tool_permission_context: Any,
    operation_type: FileOperationType,
) -> Optional[Dict[str, Any]]:
    """
    Best-effort deny check for paths obscured by :: or backtick syntax.
    ONLY checks deny rules — never auto-allows.
    """
    if not stripped_path or "\0" in stripped_path:
        return None
    tilde_expanded = expand_tilde(stripped_path)
    if os.path.isabs(tilde_expanded):
        abs_path = tilde_expanded
    else:
        abs_path = os.path.join(cwd, tilde_expanded)
    result = safe_resolve_path(get_fs_implementation(), abs_path)
    resolved = getattr(result, "resolved_path", abs_path)
    permission_type = "read" if operation_type == "read" else "edit"
    deny_rule = matching_rule_for_input(resolved, tool_permission_context, permission_type, "deny")
    if deny_rule:
        return {"resolved_path": resolved, "rule": deny_rule}
    return None


def validate_path(
    file_path: str,
    cwd: str,
    tool_permission_context: Any,
    operation_type: FileOperationType,
) -> ResolvedPathCheckResult:
    """
    Validates a file system path, handling tilde expansion.
    Returns a ResolvedPathCheckResult with allowed, resolved_path, and decision_reason.
    """
    # Remove surrounding quotes
    clean_path = expand_tilde(re.sub(r"^['\"]|['\"]$", "", file_path))

    # Normalize backslashes to forward slashes
    normalized_path = clean_path.replace("\\", "/")

    # SECURITY: Backtick (`) is PowerShell's escape character
    if "`" in normalized_path:
        backtick_stripped = normalized_path.replace("`", "")
        deny_hit = check_deny_rule_for_guessed_path(
            backtick_stripped, cwd, tool_permission_context, operation_type
        )
        if deny_hit:
            return ResolvedPathCheckResult(
                allowed=False,
                resolved_path=deny_hit["resolved_path"],
                decision_reason={"type": "rule", "rule": deny_hit["rule"]},
            )
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=normalized_path,
            decision_reason={
                "type": "other",
                "reason": "Backtick escape characters in paths cannot be statically validated and require manual approval",
            },
        )

    # SECURITY: Block module-qualified provider paths (e.g., FileSystem::/path)
    if "::" in normalized_path:
        after_provider = normalized_path[normalized_path.index("::") + 2:]
        deny_hit = check_deny_rule_for_guessed_path(
            after_provider, cwd, tool_permission_context, operation_type
        )
        if deny_hit:
            return ResolvedPathCheckResult(
                allowed=False,
                resolved_path=deny_hit["resolved_path"],
                decision_reason={"type": "rule", "rule": deny_hit["rule"]},
            )
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=normalized_path,
            decision_reason={
                "type": "other",
                "reason": "Module-qualified provider paths (::) cannot be statically validated and require manual approval",
            },
        )

    # SECURITY: Block UNC paths
    if (
        normalized_path.startswith("//")
        or re.search(r"DavWWWRoot", normalized_path, re.IGNORECASE)
        or re.search(r"@SSL@", normalized_path, re.IGNORECASE)
    ):
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=normalized_path,
            decision_reason={
                "type": "other",
                "reason": "UNC paths are blocked because they can trigger network requests and credential leakage",
            },
        )

    # SECURITY: Reject paths containing shell expansion syntax
    if "$" in normalized_path or "%" in normalized_path:
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=normalized_path,
            decision_reason={
                "type": "other",
                "reason": "Variable expansion syntax in paths requires manual approval",
            },
        )

    # SECURITY: Block non-filesystem provider paths (env:, HKLM:, alias:, function:, etc.)
    if get_platform() == "windows":
        provider_path_regex = re.compile(r"^[a-z0-9]{2,}:", re.IGNORECASE)
    else:
        provider_path_regex = re.compile(r"^[a-z0-9]+:", re.IGNORECASE)

    if provider_path_regex.match(normalized_path):
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=normalized_path,
            decision_reason={
                "type": "other",
                "reason": f"Path '{normalized_path}' uses a non-filesystem provider and requires manual approval",
            },
        )

    # SECURITY: Block glob patterns in write/create operations
    if GLOB_PATTERN_REGEX.search(normalized_path):
        if operation_type in ("write", "create"):
            return ResolvedPathCheckResult(
                allowed=False,
                resolved_path=normalized_path,
                decision_reason={
                    "type": "other",
                    "reason": "Glob patterns are not allowed in write operations. Please specify an exact file path.",
                },
            )

        # For read operations with path traversal, resolve and validate
        if contains_path_traversal(normalized_path):
            if os.path.isabs(normalized_path):
                absolute_path = normalized_path
            else:
                absolute_path = os.path.join(cwd, normalized_path)
            resolve_result = safe_resolve_path(get_fs_implementation(), absolute_path)
            resolved_path = getattr(resolve_result, "resolved_path", absolute_path)
            is_canonical = getattr(resolve_result, "is_canonical", False)
            result = is_path_allowed(
                resolved_path,
                tool_permission_context,
                operation_type,
                [resolved_path] if is_canonical else None,
            )
            return ResolvedPathCheckResult(
                allowed=result.allowed,
                resolved_path=resolved_path,
                decision_reason=result.decision_reason,
            )

        # Glob in read operation — check deny rules on base dir, else force ask
        base_path = get_glob_base_directory(normalized_path)
        if os.path.isabs(base_path):
            absolute_base_path = base_path
        else:
            absolute_base_path = os.path.join(cwd, base_path)
        resolve_result = safe_resolve_path(get_fs_implementation(), absolute_base_path)
        resolved_path = getattr(resolve_result, "resolved_path", absolute_base_path)
        permission_type = "read" if operation_type == "read" else "edit"
        deny_rule = matching_rule_for_input(resolved_path, tool_permission_context, permission_type, "deny")
        if deny_rule is not None:
            return ResolvedPathCheckResult(
                allowed=False,
                resolved_path=resolved_path,
                decision_reason={"type": "rule", "rule": deny_rule},
            )
        return ResolvedPathCheckResult(
            allowed=False,
            resolved_path=resolved_path,
            decision_reason={
                "type": "other",
                "reason": "Glob patterns in paths cannot be statically validated — symlinks inside the glob expansion are not examined. Requires manual approval.",
            },
        )

    # Resolve path
    if os.path.isabs(normalized_path):
        absolute_path = normalized_path
    else:
        absolute_path = os.path.join(cwd, normalized_path)
    resolve_result = safe_resolve_path(get_fs_implementation(), absolute_path)
    resolved_path = getattr(resolve_result, "resolved_path", absolute_path)
    is_canonical = getattr(resolve_result, "is_canonical", False)

    result = is_path_allowed(
        resolved_path,
        tool_permission_context,
        operation_type,
        [resolved_path] if is_canonical else None,
    )
    return ResolvedPathCheckResult(
        allowed=result.allowed,
        resolved_path=resolved_path,
        decision_reason=result.decision_reason,
    )


# ─── Path extraction from parsed commands ─────────────────────────────────────

class ExtractPathsResult:
    def __init__(
        self,
        paths: List[str],
        operation_type: FileOperationType,
        has_unvalidatable_path_arg: bool,
        optional_write: bool,
    ):
        self.paths = paths
        self.operation_type = operation_type
        self.has_unvalidatable_path_arg = has_unvalidatable_path_arg
        self.optional_write = optional_write


def extract_paths_from_command(cmd: Any) -> ExtractPathsResult:
    """
    Extract file paths from a parsed PowerShell command element.
    Uses the AST args to find positional and named path parameters.
    """
    canonical = resolve_to_canonical(cmd.name)
    config = CMDLET_PATH_CONFIG.get(canonical)

    if not config:
        return ExtractPathsResult(
            paths=[],
            operation_type="read",
            has_unvalidatable_path_arg=False,
            optional_write=False,
        )

    # Build per-cmdlet known-param sets, merging in common parameters
    switch_params = list(config.known_switches) + list(COMMON_SWITCHES)
    value_params = list(config.known_value_params) + list(COMMON_VALUE_PARAMS)

    paths: List[str] = []
    args = cmd.args
    element_types = cmd.element_types  # elementTypes[0] = command name; [i+1] = args[i]
    has_unvalidatable_path_arg = False
    positionals_seen = 0
    positional_skip = config.positional_skip

    def check_arg_element_type(arg_idx: int) -> None:
        nonlocal has_unvalidatable_path_arg
        if not element_types:
            return
        et = element_types[arg_idx + 1] if arg_idx + 1 < len(element_types) else None
        if et and et not in SAFE_PATH_ELEMENT_TYPES:
            has_unvalidatable_path_arg = True

    i = 0
    while i < len(args):
        arg = args[i]
        if arg is None:
            i += 1
            continue

        arg_element_type = element_types[i + 1] if element_types and i + 1 < len(element_types) else None

        if is_powershell_parameter(arg, arg_element_type):
            # Normalize unicode dash to ASCII `-`
            normalized = "-" + arg[1:]
            colon_idx = normalized.find(":", 1)
            param_name = normalized[:colon_idx] if colon_idx > 0 else normalized
            param_lower = param_name.lower()

            if matches_param(param_lower, config.path_params):
                value: Optional[str] = None
                if colon_idx > 0:
                    raw_value = arg[colon_idx + 1:]
                    if has_complex_colon_value(raw_value):
                        has_unvalidatable_path_arg = True
                    else:
                        value = raw_value
                else:
                    if i + 1 < len(args):
                        next_val = args[i + 1]
                        next_type = element_types[i + 2] if element_types and i + 2 < len(element_types) else None
                        if next_val and not is_powershell_parameter(next_val, next_type):
                            value = next_val
                            check_arg_element_type(i + 1)
                            i += 1
                if value:
                    paths.append(value)

            elif config.leaf_only_path_params and matches_param(param_lower, config.leaf_only_path_params):
                value = None
                if colon_idx > 0:
                    raw_value = arg[colon_idx + 1:]
                    if has_complex_colon_value(raw_value):
                        has_unvalidatable_path_arg = True
                    else:
                        value = raw_value
                else:
                    if i + 1 < len(args):
                        next_val = args[i + 1]
                        next_type = element_types[i + 2] if element_types and i + 2 < len(element_types) else None
                        if next_val and not is_powershell_parameter(next_val, next_type):
                            value = next_val
                            check_arg_element_type(i + 1)
                            i += 1
                if value is not None:
                    if "/" in value or "\\" in value or value == "." or value == "..":
                        has_unvalidatable_path_arg = True
                    else:
                        paths.append(value)

            elif matches_param(param_lower, switch_params):
                # Known switch parameter — takes no value
                pass

            elif matches_param(param_lower, value_params):
                # Known value-taking non-path parameter
                if colon_idx > 0:
                    raw_value = arg[colon_idx + 1:]
                    if has_complex_colon_value(raw_value):
                        has_unvalidatable_path_arg = True
                else:
                    if i + 1 < len(args):
                        next_arg = args[i + 1]
                        next_arg_type = element_types[i + 2] if element_types and i + 2 < len(element_types) else None
                        if next_arg and not is_powershell_parameter(next_arg, next_arg_type):
                            check_arg_element_type(i + 1)
                            i += 1

            else:
                # Unknown parameter — flag as unvalidatable
                has_unvalidatable_path_arg = True
                # Defense-in-depth: try to extract colon-syntax path for deny-rule check
                if colon_idx > 0:
                    raw_value = arg[colon_idx + 1:]
                    if not has_complex_colon_value(raw_value):
                        paths.append(raw_value)

            i += 1
            continue

        # Positional argument
        if positionals_seen < positional_skip:
            positionals_seen += 1
            i += 1
            continue
        positionals_seen += 1
        check_arg_element_type(i)
        paths.append(arg)
        i += 1

    return ExtractPathsResult(
        paths=paths,
        operation_type=config.operation_type,
        has_unvalidatable_path_arg=has_unvalidatable_path_arg,
        optional_write=config.optional_write,
    )


# ─── Main permission checking functions ───────────────────────────────────────

def check_path_constraints(
    input_data: Dict[str, Any],
    parsed: Any,
    tool_permission_context: Any,
    compound_command_has_cd: bool = False,
) -> Dict[str, Any]:
    """
    Checks path constraints for PowerShell commands.
    Extracts file paths from the parsed AST and validates they are
    within allowed directories.

    Returns a PermissionResult dict:
      - 'ask'         if any path command tries to access outside allowed directories
      - 'deny'        if a deny rule explicitly blocks the path
      - 'passthrough' if no path commands were found or all paths are valid
    """
    if not getattr(parsed, "valid", False):
        return {
            "behavior": "passthrough",
            "message": "Cannot validate paths for unparsed command",
        }

    # Two-pass: check ALL statements so deny rules always take precedence over ask.
    first_ask: Optional[Dict[str, Any]] = None

    for statement in parsed.statements:
        result = _check_path_constraints_for_statement(
            statement, tool_permission_context, compound_command_has_cd
        )
        if result.get("behavior") == "deny":
            return result
        if result.get("behavior") == "ask" and first_ask is None:
            first_ask = result

    return first_ask or {
        "behavior": "passthrough",
        "message": "All path constraints validated successfully",
    }


def _check_path_constraints_for_statement(
    statement: Any,
    tool_permission_context: Any,
    compound_command_has_cd: bool = False,
) -> Dict[str, Any]:
    """Internal helper: validate a single parsed statement."""
    cwd = get_cwd()
    first_ask: Optional[Dict[str, Any]] = None

    # SECURITY: Block path operations in compound commands containing a cwd-changing cmdlet.
    if compound_command_has_cd:
        first_ask = {
            "behavior": "ask",
            "message": (
                "Compound command changes working directory (Set-Location/Push-Location/"
                "Pop-Location/New-PSDrive) — relative paths cannot be validated against "
                "the original cwd and require manual approval"
            ),
            "decision_reason": {
                "type": "other",
                "reason": "Compound command contains cd with path operation — manual approval required to prevent path resolution bypass",
            },
        }

    has_expression_pipeline_source = False
    pipeline_source_text: Optional[str] = None

    commands = getattr(statement, "commands", [])
    for cmd in commands:
        if getattr(cmd, "element_type", None) != "CommandAst":
            has_expression_pipeline_source = True
            pipeline_source_text = getattr(cmd, "text", None)
            continue

        extract = extract_paths_from_command(cmd)
        paths = extract.paths
        operation_type = extract.operation_type
        has_unvalidatable = extract.has_unvalidatable_path_arg
        optional_write = extract.optional_write

        # SECURITY: Cmdlet receiving piped path from expression source
        if has_expression_pipeline_source:
            canonical = resolve_to_canonical(cmd.name)
            if pipeline_source_text is not None:
                stripped = re.sub(r"^['\"]|['\"]$", "", pipeline_source_text)
                deny_hit = check_deny_rule_for_guessed_path(
                    stripped, cwd, tool_permission_context, operation_type
                )
                if deny_hit:
                    return {
                        "behavior": "deny",
                        "message": f"{canonical} targeting '{deny_hit['resolved_path']}' was blocked by a deny rule",
                        "decision_reason": {"type": "rule", "rule": deny_hit["rule"]},
                    }
            if first_ask is None:
                first_ask = {
                    "behavior": "ask",
                    "message": f"{canonical} receives its path from a pipeline expression source that cannot be statically validated and requires manual approval",
                }

        if has_unvalidatable:
            canonical = resolve_to_canonical(cmd.name)
            if first_ask is None:
                first_ask = {
                    "behavior": "ask",
                    "message": f"{canonical} uses a parameter or complex path expression (array literal, subexpression, unknown parameter, etc.) that cannot be statically validated and requires manual approval",
                }

        # SECURITY: Write cmdlet with zero extracted paths
        if (
            operation_type != "read"
            and not optional_write
            and len(paths) == 0
            and CMDLET_PATH_CONFIG.get(resolve_to_canonical(cmd.name))
        ):
            canonical = resolve_to_canonical(cmd.name)
            if first_ask is None:
                first_ask = {
                    "behavior": "ask",
                    "message": f"{canonical} is a write operation but no target path could be determined; requires manual approval",
                }
            continue

        is_removal = resolve_to_canonical(cmd.name) == "remove-item"

        for file_path in paths:
            # Hard-deny removal of dangerous system paths (check raw path first)
            if is_removal and is_dangerous_removal_raw_path(file_path):
                return dangerous_removal_deny(file_path)

            validated = validate_path(file_path, cwd, tool_permission_context, operation_type)

            if is_removal and is_dangerous_removal_path(validated.resolved_path):
                return dangerous_removal_deny(validated.resolved_path)

            if not validated.allowed:
                canonical = resolve_to_canonical(cmd.name)
                working_dirs = list(all_working_directories(tool_permission_context))
                dir_list_str = format_directory_list(working_dirs)
                dr = validated.decision_reason

                message = (
                    dr["reason"]
                    if dr and dr.get("type") in ("other", "safetyCheck")
                    else f"{canonical} targeting '{validated.resolved_path}' was blocked. For security, Claude Code may only access files in the allowed working directories for this session: {dir_list_str}."
                )

                if dr and dr.get("type") == "rule":
                    return {"behavior": "deny", "message": message, "decision_reason": dr}

                suggestions = []
                if validated.resolved_path:
                    if operation_type == "read":
                        suggestion = create_read_rule_suggestion(
                            get_directory_for_path(validated.resolved_path), "session"
                        )
                        if suggestion:
                            suggestions.append(suggestion)
                    else:
                        suggestions.append({
                            "type": "addDirectories",
                            "directories": [get_directory_for_path(validated.resolved_path)],
                            "destination": "session",
                        })

                if operation_type in ("write", "create"):
                    suggestions.append({"type": "setMode", "mode": "acceptEdits", "destination": "session"})

                if first_ask is None:
                    first_ask = {
                        "behavior": "ask",
                        "message": message,
                        "blocked_path": validated.resolved_path,
                        "decision_reason": dr,
                        "suggestions": suggestions,
                    }

    # Also check nested commands from control flow
    nested_commands = getattr(statement, "nested_commands", None)
    if nested_commands:
        for cmd in nested_commands:
            extract = extract_paths_from_command(cmd)
            paths = extract.paths
            operation_type = extract.operation_type
            has_unvalidatable = extract.has_unvalidatable_path_arg
            optional_write = extract.optional_write

            if has_unvalidatable:
                canonical = resolve_to_canonical(cmd.name)
                if first_ask is None:
                    first_ask = {
                        "behavior": "ask",
                        "message": f"{canonical} uses a parameter or complex path expression (array literal, subexpression, unknown parameter, etc.) that cannot be statically validated and requires manual approval",
                    }

            if (
                operation_type != "read"
                and not optional_write
                and len(paths) == 0
                and CMDLET_PATH_CONFIG.get(resolve_to_canonical(cmd.name))
            ):
                canonical = resolve_to_canonical(cmd.name)
                if first_ask is None:
                    first_ask = {
                        "behavior": "ask",
                        "message": f"{canonical} is a write operation but no target path could be determined; requires manual approval",
                    }
                continue

            is_removal = resolve_to_canonical(cmd.name) == "remove-item"

            for file_path in paths:
                if is_removal and is_dangerous_removal_raw_path(file_path):
                    return dangerous_removal_deny(file_path)

                validated = validate_path(file_path, cwd, tool_permission_context, operation_type)

                if is_removal and is_dangerous_removal_path(validated.resolved_path):
                    return dangerous_removal_deny(validated.resolved_path)

                if not validated.allowed:
                    canonical = resolve_to_canonical(cmd.name)
                    working_dirs = list(all_working_directories(tool_permission_context))
                    dir_list_str = format_directory_list(working_dirs)
                    dr = validated.decision_reason

                    message = (
                        dr["reason"]
                        if dr and dr.get("type") in ("other", "safetyCheck")
                        else f"{canonical} targeting '{validated.resolved_path}' was blocked. For security, Claude Code may only access files in the allowed working directories for this session: {dir_list_str}."
                    )

                    if dr and dr.get("type") == "rule":
                        return {"behavior": "deny", "message": message, "decision_reason": dr}

                    suggestions = []
                    if validated.resolved_path:
                        if operation_type == "read":
                            suggestion = create_read_rule_suggestion(
                                get_directory_for_path(validated.resolved_path), "session"
                            )
                            if suggestion:
                                suggestions.append(suggestion)
                        else:
                            suggestions.append({
                                "type": "addDirectories",
                                "directories": [get_directory_for_path(validated.resolved_path)],
                                "destination": "session",
                            })

                    if operation_type in ("write", "create"):
                        suggestions.append({"type": "setMode", "mode": "acceptEdits", "destination": "session"})

                    if first_ask is None:
                        first_ask = {
                            "behavior": "ask",
                            "message": message,
                            "blocked_path": validated.resolved_path,
                            "decision_reason": dr,
                            "suggestions": suggestions,
                        }

            if has_expression_pipeline_source and first_ask is None:
                first_ask = {
                    "behavior": "ask",
                    "message": f"{resolve_to_canonical(cmd.name)} appears inside a control-flow or chain statement where piped expression sources cannot be statically validated and requires manual approval",
                }

        # Check redirections on nested commands
        for cmd in nested_commands:
            redirections = getattr(cmd, "redirections", None)
            if not redirections:
                continue
            for redir in redirections:
                if getattr(redir, "is_merging", False):
                    continue
                target = getattr(redir, "target", None)
                if not target:
                    continue
                if is_null_redirection_target(target):
                    continue

                validated = validate_path(target, cwd, tool_permission_context, "create")

                if not validated.allowed:
                    working_dirs = list(all_working_directories(tool_permission_context))
                    dir_list_str = format_directory_list(working_dirs)
                    dr = validated.decision_reason

                    message = (
                        dr["reason"]
                        if dr and dr.get("type") in ("other", "safetyCheck")
                        else f"Output redirection to '{validated.resolved_path}' was blocked. For security, Claude Code may only write to files in the allowed working directories for this session: {dir_list_str}."
                    )

                    if dr and dr.get("type") == "rule":
                        return {"behavior": "deny", "message": message, "decision_reason": dr}

                    if first_ask is None:
                        first_ask = {
                            "behavior": "ask",
                            "message": message,
                            "blocked_path": validated.resolved_path,
                            "decision_reason": dr,
                            "suggestions": [{
                                "type": "addDirectories",
                                "directories": [get_directory_for_path(validated.resolved_path)],
                                "destination": "session",
                            }],
                        }

    # Check file redirections on the statement
    redirections = getattr(statement, "redirections", None)
    if redirections:
        for redir in redirections:
            if getattr(redir, "is_merging", False):
                continue
            target = getattr(redir, "target", None)
            if not target:
                continue
            if is_null_redirection_target(target):
                continue

            validated = validate_path(target, cwd, tool_permission_context, "create")

            if not validated.allowed:
                working_dirs = list(all_working_directories(tool_permission_context))
                dir_list_str = format_directory_list(working_dirs)
                dr = validated.decision_reason

                message = (
                    dr["reason"]
                    if dr and dr.get("type") in ("other", "safetyCheck")
                    else f"Output redirection to '{validated.resolved_path}' was blocked. For security, Claude Code may only write to files in the allowed working directories for this session: {dir_list_str}."
                )

                if dr and dr.get("type") == "rule":
                    return {"behavior": "deny", "message": message, "decision_reason": dr}

                if first_ask is None:
                    first_ask = {
                        "behavior": "ask",
                        "message": message,
                        "blocked_path": validated.resolved_path,
                        "decision_reason": dr,
                        "suggestions": [{
                            "type": "addDirectories",
                            "directories": [get_directory_for_path(validated.resolved_path)],
                            "destination": "session",
                        }],
                    }

    return first_ask or {
        "behavior": "passthrough",
        "message": "All path constraints validated successfully",
    }


# ─── Public exports ───────────────────────────────────────────────────────────

__all__ = [
    "CMDLET_PATH_CONFIG",
    "CmdletPathConfig",
    "FileOperationType",
    "check_path_constraints",
    "dangerous_removal_deny",
    "expand_tilde",
    "extract_paths_from_command",
    "format_directory_list",
    "get_glob_base_directory",
    "has_complex_colon_value",
    "is_dangerous_removal_raw_path",
    "is_path_allowed",
    "matches_param",
    "validate_path",
]
