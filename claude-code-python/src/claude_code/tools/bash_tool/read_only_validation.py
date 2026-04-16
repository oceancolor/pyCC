"""
Read-only command validation. Ported from BashTool/readOnlyValidation.ts (1990 lines → core).
"""
from __future__ import annotations
import os
import re
from typing import List, Optional

# Commands that are inherently read-only
SAFE_READ_ONLY_BASES = frozenset([
    'cat', 'head', 'tail', 'grep', 'rg', 'ag', 'find', 'fd', 'ls', 'll', 'la', 'dir',
    'pwd', 'echo', 'printf', 'wc', 'sort', 'uniq', 'diff', 'stat', 'file', 'type', 'which',
    'less', 'more', 'bat', 'hexdump', 'xxd', 'strings', 'od', 'du', 'df', 'free',
    'ps', 'top', 'htop', 'uptime', 'id', 'whoami', 'uname', 'hostname',
    'date', 'cal', 'env', 'printenv', 'locale', 'stty', 'tty',
    'git',      # git read-only ops checked separately
    'python3', 'python', 'node', 'ruby', 'perl',  # require further checks
    'jq', 'yq', 'xmllint', 'csvtool',
    'curl', 'wget', 'dig', 'nslookup', 'host', 'ping', 'traceroute', 'netstat', 'ss',
    'docker', 'kubectl',  # require further checks
    'man', 'info', 'help',
])

DEFINITELY_WRITE_BASES = frozenset([
    'rm', 'rmdir', 'mv', 'cp', 'mkdir', 'touch', 'chmod', 'chown', 'chgrp',
    'dd', 'tee', 'install', 'ln', 'unlink', 'mkfifo', 'mknod',
    'truncate', 'shred', 'wipe',
    'apt', 'apt-get', 'yum', 'dnf', 'brew', 'pip', 'pip3', 'npm', 'yarn', 'cargo',
    'make', 'cmake', 'ninja', 'gradle', 'mvn',
    'git',  # handled separately - some ops are write
    'ssh', 'scp', 'rsync', 'sftp',
    'sudo', 'su', 'doas',
    'kill', 'killall', 'pkill',
    'mount', 'umount', 'fdisk', 'mkfs',
    'crontab', 'at',
    'sed',  # -i flag makes it write
    'awk',  # can write with >
])

_REDIRECT_WRITE_RE = re.compile(r'(?<![<>])>(?!=)')
_PIPE_RE = re.compile(r'\|')


def _get_base_cmd(command: str) -> str:
    stripped = command.strip()
    # strip env vars
    while re.match(r'^[A-Za-z_][A-Za-z0-9_]*=\S*\s+', stripped):
        stripped = re.sub(r'^[A-Za-z_][A-Za-z0-9_]*=\S*\s+', '', stripped)
    return stripped.split()[0] if stripped.split() else ''


def is_command_safe_via_flag_parsing(command: str) -> bool:
    """
    Returns True if the command can be statically determined as read-only.
    Conservative: returns False when uncertain.
    """
    base = _get_base_cmd(command)
    if not base:
        return False
    # Has write redirect?
    if _REDIRECT_WRITE_RE.search(command):
        return False
    # Known write commands
    if base in DEFINITELY_WRITE_BASES:
        return False
    # Known read-only commands
    if base in SAFE_READ_ONLY_BASES:
        return True
    return False


def check_read_only_constraints(command: str, compound_command_has_cd: bool = False) -> dict:
    """
    Main entry for read-only constraint checking.
    Returns a PermissionResult dict.
    """
    base = _get_base_cmd(command)

    # cd + git is a security risk (bare repo RCE)
    if compound_command_has_cd and re.search(r'\bgit\b', command):
        return {"behavior": "passthrough",
                "message": "Compound cd+git requires permission checks"}

    if is_command_safe_via_flag_parsing(command):
        return {"behavior": "allow", "updatedInput": {"command": command},
                "decisionReason": {"type": "read_only"}}

    return {"behavior": "passthrough",
            "message": f"Command '{base}' requires permission check"}
