"""
Shared command validation maps for shell tools (BashTool, PowerShellTool, etc.).

Exports complete command configuration maps that any shell tool can import:
- GIT_READ_ONLY_COMMANDS: all git subcommands with safe flags and callbacks
- GH_READ_ONLY_COMMANDS: read-only gh CLI commands (network-dependent)
- EXTERNAL_READONLY_COMMANDS: cross-shell commands that work in both bash and PowerShell
- containsVulnerableUncPath: UNC path detection for credential leak prevention
- outputLimits are in outputLimits.py

Ported from utils/shell/readOnlyCommandValidation.ts
"""

from __future__ import annotations

import re
import sys
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# FlagArgType: no arg, integer, any string, single char, literal "{}", literal "EOF"
FlagArgType = str  # one of: 'none' | 'number' | 'string' | 'char' | '{}' | 'EOF'


class ExternalCommandConfig:
    """Configuration for an external command's safe flags."""

    def __init__(
        self,
        safe_flags: Dict[str, FlagArgType],
        additional_command_is_dangerous_callback: Optional[
            Callable[[str, List[str]], bool]
        ] = None,
        respects_double_dash: bool = True,
    ):
        self.safe_flags = safe_flags
        self.additional_command_is_dangerous_callback = (
            additional_command_is_dangerous_callback
        )
        self.respects_double_dash = respects_double_dash


# ---------------------------------------------------------------------------
# Shared git flag groups
# ---------------------------------------------------------------------------

GIT_REF_SELECTION_FLAGS: Dict[str, FlagArgType] = {
    '--all': 'none',
    '--branches': 'none',
    '--tags': 'none',
    '--remotes': 'none',
}

GIT_DATE_FILTER_FLAGS: Dict[str, FlagArgType] = {
    '--since': 'string',
    '--after': 'string',
    '--until': 'string',
    '--before': 'string',
}

GIT_LOG_DISPLAY_FLAGS: Dict[str, FlagArgType] = {
    '--oneline': 'none',
    '--graph': 'none',
    '--decorate': 'none',
    '--no-decorate': 'none',
    '--date': 'string',
    '--relative-date': 'none',
}

GIT_COUNT_FLAGS: Dict[str, FlagArgType] = {
    '--max-count': 'number',
    '-n': 'number',
}

# Stat output flags - used in git log, show, diff
GIT_STAT_FLAGS: Dict[str, FlagArgType] = {
    '--stat': 'none',
    '--numstat': 'none',
    '--shortstat': 'none',
    '--name-only': 'none',
    '--name-status': 'none',
}

# Color output flags
GIT_COLOR_FLAGS: Dict[str, FlagArgType] = {
    '--color': 'none',
    '--no-color': 'none',
}

# Patch display flags
GIT_PATCH_FLAGS: Dict[str, FlagArgType] = {
    '--patch': 'none',
    '-p': 'none',
    '--no-patch': 'none',
    '--no-ext-diff': 'none',
    '-s': 'none',
}

# Author/committer filter flags
GIT_AUTHOR_FILTER_FLAGS: Dict[str, FlagArgType] = {
    '--author': 'string',
    '--committer': 'string',
    '--grep': 'string',
}

# ---------------------------------------------------------------------------
# GIT_READ_ONLY_COMMANDS — complete map of all git subcommands
# ---------------------------------------------------------------------------


def _git_reflog_callback(_raw_command: str, args: List[str]) -> bool:
    """Block git reflog expire/delete/exists."""
    DANGEROUS_SUBCOMMANDS = {'expire', 'delete', 'exists'}
    for token in args:
        if not token or token.startswith('-'):
            continue
        if token in DANGEROUS_SUBCOMMANDS:
            return True  # Dangerous subcommand
        return False  # First positional is safe
    return False


def _git_remote_show_callback(_raw_command: str, args: List[str]) -> bool:
    """Only allow optional -n, then one alphanumeric remote name."""
    positional = [a for a in args if a != '-n']
    if len(positional) != 1:
        return True
    return not bool(re.match(r'^[a-zA-Z0-9_-]+$', positional[0]))


def _git_remote_callback(_raw_command: str, args: List[str]) -> bool:
    """Only allow bare 'git remote' or 'git remote -v/--verbose'."""
    return any(a != '-v' and a != '--verbose' for a in args)


def _git_tag_callback(_raw_command: str, args: List[str]) -> bool:
    """Block tag creation via positional arguments."""
    flags_with_args = {
        '--contains', '--no-contains', '--merged', '--no-merged',
        '--points-at', '--sort', '--format', '-n',
    }
    i = 0
    seen_list_flag = False
    seen_dash_dash = False
    while i < len(args):
        token = args[i]
        if not token:
            i += 1
            continue
        if token == '--' and not seen_dash_dash:
            seen_dash_dash = True
            i += 1
            continue
        if not seen_dash_dash and token.startswith('-'):
            if token == '--list' or token == '-l':
                seen_list_flag = True
            elif (token[0] == '-' and len(token) > 1 and token[1] != '-'
                  and len(token) > 2 and '=' not in token
                  and 'l' in token[1:]):
                seen_list_flag = True
            if '=' in token:
                i += 1
            elif token in flags_with_args:
                i += 2
            else:
                i += 1
        else:
            if not seen_list_flag:
                return True  # Positional arg without --list = tag creation
            i += 1
    return False


def _git_branch_callback(_raw_command: str, args: List[str]) -> bool:
    """Block branch creation via positional arguments."""
    flags_with_args = {
        '--contains', '--no-contains', '--points-at', '--sort',
        # --abbrev REMOVED (git uses PARSE_OPT_OPTARG)
    }
    flags_with_optional_args = {'--merged', '--no-merged'}
    i = 0
    last_flag = ''
    seen_list_flag = False
    seen_dash_dash = False
    while i < len(args):
        token = args[i]
        if not token:
            i += 1
            continue
        if token == '--' and not seen_dash_dash:
            seen_dash_dash = True
            last_flag = ''
            i += 1
            continue
        if not seen_dash_dash and token.startswith('-'):
            if token == '--list' or token == '-l':
                seen_list_flag = True
            elif (token[0] == '-' and len(token) > 1 and token[1] != '-'
                  and len(token) > 2 and '=' not in token
                  and 'l' in token[1:]):
                seen_list_flag = True
            if '=' in token:
                last_flag = token.split('=')[0]
                i += 1
            elif token in flags_with_args:
                last_flag = token
                i += 2
            else:
                last_flag = token
                i += 1
        else:
            last_flag_has_optional_arg = last_flag in flags_with_optional_args
            if not seen_list_flag and not last_flag_has_optional_arg:
                return True  # branch creation
            i += 1
    return False


GIT_READ_ONLY_COMMANDS: Dict[str, ExternalCommandConfig] = {
    'git diff': ExternalCommandConfig(
        safe_flags={
            **GIT_STAT_FLAGS,
            **GIT_COLOR_FLAGS,
            '--dirstat': 'none',
            '--summary': 'none',
            '--patch-with-stat': 'none',
            '--word-diff': 'none',
            '--word-diff-regex': 'string',
            '--color-words': 'none',
            '--no-renames': 'none',
            '--no-ext-diff': 'none',
            '--check': 'none',
            '--ws-error-highlight': 'string',
            '--full-index': 'none',
            '--binary': 'none',
            '--abbrev': 'number',
            '--break-rewrites': 'none',
            '--find-renames': 'none',
            '--find-copies': 'none',
            '--find-copies-harder': 'none',
            '--irreversible-delete': 'none',
            '--diff-algorithm': 'string',
            '--histogram': 'none',
            '--patience': 'none',
            '--minimal': 'none',
            '--ignore-space-at-eol': 'none',
            '--ignore-space-change': 'none',
            '--ignore-all-space': 'none',
            '--ignore-blank-lines': 'none',
            '--inter-hunk-context': 'number',
            '--function-context': 'none',
            '--exit-code': 'none',
            '--quiet': 'none',
            '--cached': 'none',
            '--staged': 'none',
            '--pickaxe-regex': 'none',
            '--pickaxe-all': 'none',
            '--no-index': 'none',
            '--relative': 'string',
            '--diff-filter': 'string',
            '-p': 'none',
            '-u': 'none',
            '-s': 'none',
            '-M': 'none',
            '-C': 'none',
            '-B': 'none',
            '-D': 'none',
            '-l': 'none',
            # SECURITY: -S/-G/-O take REQUIRED string arguments
            '-S': 'string',
            '-G': 'string',
            '-O': 'string',
            '-R': 'none',
        }
    ),
    'git log': ExternalCommandConfig(
        safe_flags={
            **GIT_LOG_DISPLAY_FLAGS,
            **GIT_REF_SELECTION_FLAGS,
            **GIT_DATE_FILTER_FLAGS,
            **GIT_COUNT_FLAGS,
            **GIT_STAT_FLAGS,
            **GIT_COLOR_FLAGS,
            **GIT_PATCH_FLAGS,
            **GIT_AUTHOR_FILTER_FLAGS,
            '--abbrev-commit': 'none',
            '--full-history': 'none',
            '--dense': 'none',
            '--sparse': 'none',
            '--simplify-merges': 'none',
            '--ancestry-path': 'none',
            '--source': 'none',
            '--first-parent': 'none',
            '--merges': 'none',
            '--no-merges': 'none',
            '--reverse': 'none',
            '--walk-reflogs': 'none',
            '--skip': 'number',
            '--max-age': 'number',
            '--min-age': 'number',
            '--no-min-parents': 'none',
            '--no-max-parents': 'none',
            '--follow': 'none',
            '--no-walk': 'none',
            '--left-right': 'none',
            '--cherry-mark': 'none',
            '--cherry-pick': 'none',
            '--boundary': 'none',
            '--topo-order': 'none',
            '--date-order': 'none',
            '--author-date-order': 'none',
            '--pretty': 'string',
            '--format': 'string',
            '--diff-filter': 'string',
            '-S': 'string',
            '-G': 'string',
            '--pickaxe-regex': 'none',
            '--pickaxe-all': 'none',
        }
    ),
    'git show': ExternalCommandConfig(
        safe_flags={
            **GIT_LOG_DISPLAY_FLAGS,
            **GIT_STAT_FLAGS,
            **GIT_COLOR_FLAGS,
            **GIT_PATCH_FLAGS,
            '--abbrev-commit': 'none',
            '--word-diff': 'none',
            '--word-diff-regex': 'string',
            '--color-words': 'none',
            '--pretty': 'string',
            '--format': 'string',
            '--first-parent': 'none',
            '--raw': 'none',
            '--diff-filter': 'string',
            '-m': 'none',
            '--quiet': 'none',
        }
    ),
    'git shortlog': ExternalCommandConfig(
        safe_flags={
            **GIT_REF_SELECTION_FLAGS,
            **GIT_DATE_FILTER_FLAGS,
            '-s': 'none',
            '--summary': 'none',
            '-n': 'none',
            '--numbered': 'none',
            '-e': 'none',
            '--email': 'none',
            '-c': 'none',
            '--committer': 'none',
            '--group': 'string',
            '--format': 'string',
            '--no-merges': 'none',
            '--author': 'string',
        }
    ),
    'git reflog': ExternalCommandConfig(
        safe_flags={
            **GIT_LOG_DISPLAY_FLAGS,
            **GIT_REF_SELECTION_FLAGS,
            **GIT_DATE_FILTER_FLAGS,
            **GIT_COUNT_FLAGS,
            **GIT_AUTHOR_FILTER_FLAGS,
        },
        additional_command_is_dangerous_callback=_git_reflog_callback,
    ),
    'git stash list': ExternalCommandConfig(
        safe_flags={
            **GIT_LOG_DISPLAY_FLAGS,
            **GIT_REF_SELECTION_FLAGS,
            **GIT_COUNT_FLAGS,
        }
    ),
    'git ls-remote': ExternalCommandConfig(
        safe_flags={
            '--branches': 'none',
            '-b': 'none',
            '--tags': 'none',
            '-t': 'none',
            '--heads': 'none',
            '-h': 'none',
            '--refs': 'none',
            '--quiet': 'none',
            '-q': 'none',
            '--exit-code': 'none',
            '--get-url': 'none',
            '--symref': 'none',
            '--sort': 'string',
            # SECURITY: --server-option intentionally excluded
        }
    ),
    'git status': ExternalCommandConfig(
        safe_flags={
            '--short': 'none',
            '-s': 'none',
            '--branch': 'none',
            '-b': 'none',
            '--porcelain': 'none',
            '--long': 'none',
            '--verbose': 'none',
            '-v': 'none',
            '--untracked-files': 'string',
            '-u': 'string',
            '--ignored': 'none',
            '--ignore-submodules': 'string',
            '--column': 'none',
            '--no-column': 'none',
            '--ahead-behind': 'none',
            '--no-ahead-behind': 'none',
            '--renames': 'none',
            '--no-renames': 'none',
            '--find-renames': 'string',
            '-M': 'string',
        }
    ),
    'git blame': ExternalCommandConfig(
        safe_flags={
            **GIT_COLOR_FLAGS,
            '-L': 'string',
            '--porcelain': 'none',
            '-p': 'none',
            '--line-porcelain': 'none',
            '--incremental': 'none',
            '--root': 'none',
            '--show-stats': 'none',
            '--show-name': 'none',
            '--show-number': 'none',
            '-n': 'none',
            '--show-email': 'none',
            '-e': 'none',
            '-f': 'none',
            '--date': 'string',
            '-w': 'none',
            '--ignore-rev': 'string',
            '--ignore-revs-file': 'string',
            '-M': 'none',
            '-C': 'none',
            '--score-debug': 'none',
            '--abbrev': 'number',
            '-s': 'none',
            '-l': 'none',
            '-t': 'none',
        }
    ),
    'git ls-files': ExternalCommandConfig(
        safe_flags={
            '--cached': 'none',
            '-c': 'none',
            '--deleted': 'none',
            '-d': 'none',
            '--modified': 'none',
            '-m': 'none',
            '--others': 'none',
            '-o': 'none',
            '--ignored': 'none',
            '-i': 'none',
            '--stage': 'none',
            '-s': 'none',
            '--killed': 'none',
            '-k': 'none',
            '--unmerged': 'none',
            '-u': 'none',
            '--directory': 'none',
            '--no-empty-directory': 'none',
            '--eol': 'none',
            '--full-name': 'none',
            '--abbrev': 'number',
            '--debug': 'none',
            '-z': 'none',
            '-t': 'none',
            '-v': 'none',
            '-f': 'none',
            '--exclude': 'string',
            '-x': 'string',
            '--exclude-from': 'string',
            '-X': 'string',
            '--exclude-per-directory': 'string',
            '--exclude-standard': 'none',
            '--error-unmatch': 'none',
            '--recurse-submodules': 'none',
        }
    ),
    'git config --get': ExternalCommandConfig(
        safe_flags={
            '--local': 'none',
            '--global': 'none',
            '--system': 'none',
            '--worktree': 'none',
            '--default': 'string',
            '--type': 'string',
            '--bool': 'none',
            '--int': 'none',
            '--bool-or-int': 'none',
            '--path': 'none',
            '--expiry-date': 'none',
            '-z': 'none',
            '--null': 'none',
            '--name-only': 'none',
            '--show-origin': 'none',
            '--show-scope': 'none',
        }
    ),
    # NOTE: 'git remote show' must come BEFORE 'git remote' so longer patterns are matched first
    'git remote show': ExternalCommandConfig(
        safe_flags={'-n': 'none'},
        additional_command_is_dangerous_callback=_git_remote_show_callback,
    ),
    'git remote': ExternalCommandConfig(
        safe_flags={
            '-v': 'none',
            '--verbose': 'none',
        },
        additional_command_is_dangerous_callback=_git_remote_callback,
    ),
    'git merge-base': ExternalCommandConfig(
        safe_flags={
            '--is-ancestor': 'none',
            '--fork-point': 'none',
            '--octopus': 'none',
            '--independent': 'none',
            '--all': 'none',
        }
    ),
    'git rev-parse': ExternalCommandConfig(
        safe_flags={
            '--verify': 'none',
            '--short': 'string',
            '--abbrev-ref': 'none',
            '--symbolic': 'none',
            '--symbolic-full-name': 'none',
            '--show-toplevel': 'none',
            '--show-cdup': 'none',
            '--show-prefix': 'none',
            '--git-dir': 'none',
            '--git-common-dir': 'none',
            '--absolute-git-dir': 'none',
            '--show-superproject-working-tree': 'none',
            '--is-inside-work-tree': 'none',
            '--is-inside-git-dir': 'none',
            '--is-bare-repository': 'none',
            '--is-shallow-repository': 'none',
            '--is-shallow-update': 'none',
            '--path-prefix': 'none',
        }
    ),
    'git rev-list': ExternalCommandConfig(
        safe_flags={
            **GIT_REF_SELECTION_FLAGS,
            **GIT_DATE_FILTER_FLAGS,
            **GIT_COUNT_FLAGS,
            **GIT_AUTHOR_FILTER_FLAGS,
            '--count': 'none',
            '--reverse': 'none',
            '--first-parent': 'none',
            '--ancestry-path': 'none',
            '--merges': 'none',
            '--no-merges': 'none',
            '--min-parents': 'number',
            '--max-parents': 'number',
            '--no-min-parents': 'none',
            '--no-max-parents': 'none',
            '--skip': 'number',
            '--max-age': 'number',
            '--min-age': 'number',
            '--walk-reflogs': 'none',
            '--oneline': 'none',
            '--abbrev-commit': 'none',
            '--pretty': 'string',
            '--format': 'string',
            '--abbrev': 'number',
            '--full-history': 'none',
            '--dense': 'none',
            '--sparse': 'none',
            '--source': 'none',
            '--graph': 'none',
        }
    ),
    'git describe': ExternalCommandConfig(
        safe_flags={
            '--tags': 'none',
            '--match': 'string',
            '--exclude': 'string',
            '--long': 'none',
            '--abbrev': 'number',
            '--always': 'none',
            '--contains': 'none',
            '--first-match': 'none',
            '--exact-match': 'none',
            '--candidates': 'number',
            '--dirty': 'none',
            '--broken': 'none',
        }
    ),
    'git cat-file': ExternalCommandConfig(
        safe_flags={
            '-t': 'none',
            '-s': 'none',
            '-p': 'none',
            '-e': 'none',
            '--batch-check': 'none',
            '--allow-undetermined-type': 'none',
        }
    ),
    'git for-each-ref': ExternalCommandConfig(
        safe_flags={
            '--format': 'string',
            '--sort': 'string',
            '--count': 'number',
            '--contains': 'string',
            '--no-contains': 'string',
            '--merged': 'string',
            '--no-merged': 'string',
            '--points-at': 'string',
        }
    ),
    'git grep': ExternalCommandConfig(
        safe_flags={
            '-e': 'string',
            '-E': 'none',
            '--extended-regexp': 'none',
            '-G': 'none',
            '--basic-regexp': 'none',
            '-F': 'none',
            '--fixed-strings': 'none',
            '-P': 'none',
            '--perl-regexp': 'none',
            '-i': 'none',
            '--ignore-case': 'none',
            '-v': 'none',
            '--invert-match': 'none',
            '-w': 'none',
            '--word-regexp': 'none',
            '-n': 'none',
            '--line-number': 'none',
            '-c': 'none',
            '--count': 'none',
            '-l': 'none',
            '--files-with-matches': 'none',
            '-L': 'none',
            '--files-without-match': 'none',
            '-h': 'none',
            '-H': 'none',
            '--heading': 'none',
            '--break': 'none',
            '--full-name': 'none',
            '--color': 'none',
            '--no-color': 'none',
            '-o': 'none',
            '--only-matching': 'none',
            '-A': 'number',
            '--after-context': 'number',
            '-B': 'number',
            '--before-context': 'number',
            '-C': 'number',
            '--context': 'number',
            '--and': 'none',
            '--or': 'none',
            '--not': 'none',
            '--max-depth': 'number',
            '--untracked': 'none',
            '--no-index': 'none',
            '--recurse-submodules': 'none',
            '--cached': 'none',
            '--threads': 'number',
            '-q': 'none',
            '--quiet': 'none',
        }
    ),
    'git stash show': ExternalCommandConfig(
        safe_flags={
            **GIT_STAT_FLAGS,
            **GIT_COLOR_FLAGS,
            **GIT_PATCH_FLAGS,
            '--word-diff': 'none',
            '--word-diff-regex': 'string',
            '--diff-filter': 'string',
            '--abbrev': 'number',
        }
    ),
    'git worktree list': ExternalCommandConfig(
        safe_flags={
            '--porcelain': 'none',
            '-v': 'none',
            '--verbose': 'none',
            '--expire': 'string',
        }
    ),
    'git tag': ExternalCommandConfig(
        safe_flags={
            '-l': 'none',
            '--list': 'none',
            '-n': 'number',
            '--contains': 'string',
            '--no-contains': 'string',
            '--merged': 'string',
            '--no-merged': 'string',
            '--sort': 'string',
            '--format': 'string',
            '--points-at': 'string',
            '--column': 'none',
            '--no-column': 'none',
            '-i': 'none',
            '--ignore-case': 'none',
        },
        additional_command_is_dangerous_callback=_git_tag_callback,
    ),
    'git branch': ExternalCommandConfig(
        safe_flags={
            '-l': 'none',
            '--list': 'none',
            '-a': 'none',
            '--all': 'none',
            '-r': 'none',
            '--remotes': 'none',
            '-v': 'none',
            '-vv': 'none',
            '--verbose': 'none',
            '--color': 'none',
            '--no-color': 'none',
            '--column': 'none',
            '--no-column': 'none',
            '--abbrev': 'number',
            '--no-abbrev': 'none',
            '--contains': 'string',
            '--no-contains': 'string',
            '--merged': 'none',
            '--no-merged': 'none',
            '--points-at': 'string',
            '--sort': 'string',
            '--show-current': 'none',
            '-i': 'none',
            '--ignore-case': 'none',
        },
        additional_command_is_dangerous_callback=_git_branch_callback,
    ),
}

# ---------------------------------------------------------------------------
# GH_READ_ONLY_COMMANDS — read-only gh CLI commands (network-dependent)
# ---------------------------------------------------------------------------

# SECURITY: Shared callback for all gh commands to prevent network exfil.
def _gh_is_dangerous_callback(_raw_command: str, args: List[str]) -> bool:
    """Check if any gh argument could exfiltrate data via a custom host."""
    for token in args:
        if not token:
            continue
        # For flag tokens, extract the value after `=` for inspection.
        value = token
        if token.startswith('-'):
            eq_idx = token.find('=')
            if eq_idx == -1:
                continue  # flag without inline value
            value = token[eq_idx + 1:]
            if not value:
                continue
        # Skip values that are clearly not repo specs
        if '/' not in value and '://' not in value and '@' not in value:
            continue
        # URL schemes
        if '://' in value:
            return True
        # SSH-style
        if '@' in value:
            return True
        # 3+ segments = HOST/OWNER/REPO
        slash_count = value.count('/')
        if slash_count >= 2:
            return True
    return False


GH_READ_ONLY_COMMANDS: Dict[str, ExternalCommandConfig] = {
    'gh pr view': ExternalCommandConfig(
        safe_flags={
            '--json': 'string',
            '--comments': 'none',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh pr list': ExternalCommandConfig(
        safe_flags={
            '--state': 'string',
            '-s': 'string',
            '--author': 'string',
            '--assignee': 'string',
            '--label': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--base': 'string',
            '--head': 'string',
            '--search': 'string',
            '--json': 'string',
            '--draft': 'none',
            '--app': 'string',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh pr diff': ExternalCommandConfig(
        safe_flags={
            '--color': 'string',
            '--name-only': 'none',
            '--patch': 'none',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh pr checks': ExternalCommandConfig(
        safe_flags={
            '--watch': 'none',
            '--required': 'none',
            '--fail-fast': 'none',
            '--json': 'string',
            '--interval': 'number',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh issue view': ExternalCommandConfig(
        safe_flags={
            '--json': 'string',
            '--comments': 'none',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh issue list': ExternalCommandConfig(
        safe_flags={
            '--state': 'string',
            '-s': 'string',
            '--assignee': 'string',
            '--author': 'string',
            '--label': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--milestone': 'string',
            '--search': 'string',
            '--json': 'string',
            '--app': 'string',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh repo view': ExternalCommandConfig(
        safe_flags={'--json': 'string'},
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh run list': ExternalCommandConfig(
        safe_flags={
            '--branch': 'string',
            '-b': 'string',
            '--status': 'string',
            '-s': 'string',
            '--workflow': 'string',
            '-w': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--json': 'string',
            '--repo': 'string',
            '-R': 'string',
            '--event': 'string',
            '-e': 'string',
            '--user': 'string',
            '-u': 'string',
            '--created': 'string',
            '--commit': 'string',
            '-c': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh run view': ExternalCommandConfig(
        safe_flags={
            '--log': 'none',
            '--log-failed': 'none',
            '--exit-status': 'none',
            '--verbose': 'none',
            '-v': 'none',
            '--json': 'string',
            '--repo': 'string',
            '-R': 'string',
            '--job': 'string',
            '-j': 'string',
            '--attempt': 'number',
            '-a': 'number',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh auth status': ExternalCommandConfig(
        safe_flags={
            '--active': 'none',
            '-a': 'none',
            '--hostname': 'string',
            '-h': 'string',
            '--json': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh pr status': ExternalCommandConfig(
        safe_flags={
            '--conflict-status': 'none',
            '-c': 'none',
            '--json': 'string',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh issue status': ExternalCommandConfig(
        safe_flags={
            '--json': 'string',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh release list': ExternalCommandConfig(
        safe_flags={
            '--exclude-drafts': 'none',
            '--exclude-pre-releases': 'none',
            '--json': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--order': 'string',
            '-O': 'string',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh release view': ExternalCommandConfig(
        safe_flags={
            '--json': 'string',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh workflow list': ExternalCommandConfig(
        safe_flags={
            '--all': 'none',
            '-a': 'none',
            '--json': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh workflow view': ExternalCommandConfig(
        safe_flags={
            '--ref': 'string',
            '-r': 'string',
            '--yaml': 'none',
            '-y': 'none',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh label list': ExternalCommandConfig(
        safe_flags={
            '--json': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--order': 'string',
            '--search': 'string',
            '-S': 'string',
            '--sort': 'string',
            '--repo': 'string',
            '-R': 'string',
        },
        additional_command_is_dangerous_callback=_gh_is_dangerous_callback,
    ),
    'gh search repos': ExternalCommandConfig(
        safe_flags={
            '--archived': 'none',
            '--created': 'string',
            '--followers': 'string',
            '--forks': 'string',
            '--good-first-issues': 'string',
            '--help-wanted-issues': 'string',
            '--include-forks': 'string',
            '--json': 'string',
            '--language': 'string',
            '--license': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--match': 'string',
            '--number-topics': 'string',
            '--order': 'string',
            '--owner': 'string',
            '--size': 'string',
            '--sort': 'string',
            '--stars': 'string',
            '--topic': 'string',
            '--updated': 'string',
            '--visibility': 'string',
        }
    ),
    'gh search issues': ExternalCommandConfig(
        safe_flags={
            '--app': 'string',
            '--assignee': 'string',
            '--author': 'string',
            '--closed': 'string',
            '--commenter': 'string',
            '--comments': 'string',
            '--created': 'string',
            '--include-prs': 'none',
            '--interactions': 'string',
            '--involves': 'string',
            '--json': 'string',
            '--label': 'string',
            '--language': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--locked': 'none',
            '--match': 'string',
            '--mentions': 'string',
            '--milestone': 'string',
            '--no-assignee': 'none',
            '--no-label': 'none',
            '--no-milestone': 'none',
            '--no-project': 'none',
            '--order': 'string',
            '--owner': 'string',
            '--project': 'string',
            '--reactions': 'string',
            '--repo': 'string',
            '-R': 'string',
            '--sort': 'string',
            '--state': 'string',
            '--team-mentions': 'string',
            '--updated': 'string',
            '--visibility': 'string',
        }
    ),
    'gh search prs': ExternalCommandConfig(
        safe_flags={
            '--app': 'string',
            '--assignee': 'string',
            '--author': 'string',
            '--base': 'string',
            '-B': 'string',
            '--checks': 'string',
            '--closed': 'string',
            '--commenter': 'string',
            '--comments': 'string',
            '--created': 'string',
            '--draft': 'none',
            '--head': 'string',
            '-H': 'string',
            '--interactions': 'string',
            '--involves': 'string',
            '--json': 'string',
            '--label': 'string',
            '--language': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--locked': 'none',
            '--match': 'string',
            '--mentions': 'string',
            '--merged': 'none',
            '--merged-at': 'string',
            '--milestone': 'string',
            '--no-assignee': 'none',
            '--no-label': 'none',
            '--no-milestone': 'none',
            '--no-project': 'none',
            '--order': 'string',
            '--owner': 'string',
            '--project': 'string',
            '--reactions': 'string',
            '--repo': 'string',
            '-R': 'string',
            '--review': 'string',
            '--review-requested': 'string',
            '--reviewed-by': 'string',
            '--sort': 'string',
            '--state': 'string',
            '--team-mentions': 'string',
            '--updated': 'string',
            '--visibility': 'string',
        }
    ),
    'gh search commits': ExternalCommandConfig(
        safe_flags={
            '--author': 'string',
            '--author-date': 'string',
            '--author-email': 'string',
            '--author-name': 'string',
            '--committer': 'string',
            '--committer-date': 'string',
            '--committer-email': 'string',
            '--committer-name': 'string',
            '--hash': 'string',
            '--json': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--merge': 'none',
            '--order': 'string',
            '--owner': 'string',
            '--parent': 'string',
            '--repo': 'string',
            '-R': 'string',
            '--sort': 'string',
            '--tree': 'string',
            '--visibility': 'string',
        }
    ),
    'gh search code': ExternalCommandConfig(
        safe_flags={
            '--extension': 'string',
            '--filename': 'string',
            '--json': 'string',
            '--language': 'string',
            '--limit': 'number',
            '-L': 'number',
            '--match': 'string',
            '--owner': 'string',
            '--repo': 'string',
            '-R': 'string',
            '--size': 'string',
        }
    ),
}

# ---------------------------------------------------------------------------
# DOCKER_READ_ONLY_COMMANDS
# ---------------------------------------------------------------------------

DOCKER_READ_ONLY_COMMANDS: Dict[str, ExternalCommandConfig] = {
    'docker logs': ExternalCommandConfig(
        safe_flags={
            '--follow': 'none',
            '-f': 'none',
            '--tail': 'string',
            '-n': 'string',
            '--timestamps': 'none',
            '-t': 'none',
            '--since': 'string',
            '--until': 'string',
            '--details': 'none',
        }
    ),
    'docker inspect': ExternalCommandConfig(
        safe_flags={
            '--format': 'string',
            '-f': 'string',
            '--type': 'string',
            '--size': 'none',
            '-s': 'none',
        }
    ),
}

# ---------------------------------------------------------------------------
# RIPGREP_READ_ONLY_COMMANDS
# ---------------------------------------------------------------------------

RIPGREP_READ_ONLY_COMMANDS: Dict[str, ExternalCommandConfig] = {
    'rg': ExternalCommandConfig(
        safe_flags={
            '-e': 'string',
            '--regexp': 'string',
            '-f': 'string',
            '-i': 'none',
            '--ignore-case': 'none',
            '-S': 'none',
            '--smart-case': 'none',
            '-F': 'none',
            '--fixed-strings': 'none',
            '-w': 'none',
            '--word-regexp': 'none',
            '-v': 'none',
            '--invert-match': 'none',
            '-c': 'none',
            '--count': 'none',
            '-l': 'none',
            '--files-with-matches': 'none',
            '--files-without-match': 'none',
            '-n': 'none',
            '--line-number': 'none',
            '-o': 'none',
            '--only-matching': 'none',
            '-A': 'number',
            '--after-context': 'number',
            '-B': 'number',
            '--before-context': 'number',
            '-C': 'number',
            '--context': 'number',
            '-H': 'none',
            '-h': 'none',
            '--heading': 'none',
            '--no-heading': 'none',
            '-q': 'none',
            '--quiet': 'none',
            '--column': 'none',
            '-g': 'string',
            '--glob': 'string',
            '-t': 'string',
            '--type': 'string',
            '-T': 'string',
            '--type-not': 'string',
            '--type-list': 'none',
            '--hidden': 'none',
            '--no-ignore': 'none',
            '-u': 'none',
            '-m': 'number',
            '--max-count': 'number',
            '-d': 'number',
            '--max-depth': 'number',
            '-a': 'none',
            '--text': 'none',
            '-z': 'none',
            '-L': 'none',
            '--follow': 'none',
            '--color': 'string',
            '--json': 'none',
            '--stats': 'none',
            '--help': 'none',
            '--version': 'none',
            '--debug': 'none',
            '--': 'none',
        }
    ),
}

# ---------------------------------------------------------------------------
# PYRIGHT_READ_ONLY_COMMANDS
# ---------------------------------------------------------------------------


def _pyright_callback(_raw_command: str, args: List[str]) -> bool:
    """Check if --watch or -w appears as a standalone flag."""
    return any(t == '--watch' or t == '-w' for t in args)


PYRIGHT_READ_ONLY_COMMANDS: Dict[str, ExternalCommandConfig] = {
    'pyright': ExternalCommandConfig(
        safe_flags={
            '--outputjson': 'none',
            '--project': 'string',
            '-p': 'string',
            '--pythonversion': 'string',
            '--pythonplatform': 'string',
            '--typeshedpath': 'string',
            '--venvpath': 'string',
            '--level': 'string',
            '--stats': 'none',
            '--verbose': 'none',
            '--version': 'none',
            '--dependencies': 'none',
            '--warnings': 'none',
        },
        additional_command_is_dangerous_callback=_pyright_callback,
        respects_double_dash=False,
    ),
}

# ---------------------------------------------------------------------------
# EXTERNAL_READONLY_COMMANDS — cross-shell read-only commands
# ---------------------------------------------------------------------------

EXTERNAL_READONLY_COMMANDS: Tuple[str, ...] = (
    'docker ps',
    'docker images',
)

# ---------------------------------------------------------------------------
# UNC path detection (shared across Bash and PowerShell)
# ---------------------------------------------------------------------------


def get_platform() -> str:
    """Return platform string: 'windows', 'mac', or 'linux'."""
    if sys.platform == 'win32':
        return 'windows'
    elif sys.platform == 'darwin':
        return 'mac'
    return 'linux'


def contains_vulnerable_unc_path(path_or_command: str) -> bool:
    """
    Check if a path or command contains a UNC path that could trigger network
    requests (NTLM/Kerberos credential leakage, WebDAV attacks).

    Only relevant on Windows; always returns False on other platforms.
    """
    if get_platform() != 'windows':
        return False

    # 1. Backslash UNC paths: \\server, \\server\share
    if re.search(r'\\\\[^\s\\/]+(?:@(?:\d+|ssl))?(?:[\\/]|$|\s)', path_or_command, re.IGNORECASE):
        return True

    # 2. Forward-slash UNC paths: //server/share
    # Negative lookbehind for : to exclude http:// etc
    if re.search(r'(?<!:)\/\/[^\s\\/]+(?:@(?:\d+|ssl))?(?:[\\/]|$|\s)', path_or_command, re.IGNORECASE):
        return True

    # 3. Mixed: /\\server
    if re.search(r'\/\\{2,}[^\s\\/]', path_or_command):
        return True

    # 4. Mixed: \\\/server
    if re.search(r'\\{2,}\/[^\s\\/]', path_or_command):
        return True

    # 5. WebDAV SSL/port patterns
    if re.search(r'@SSL@\d+', path_or_command, re.IGNORECASE) or re.search(r'@\d+@SSL', path_or_command, re.IGNORECASE):
        return True

    # 6. DavWWWRoot marker
    if re.search(r'DavWWWRoot', path_or_command, re.IGNORECASE):
        return True

    # 7. IPv4 UNC
    if re.search(r'^\\\\(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[\\/]', path_or_command):
        return True
    if re.search(r'^\/\/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[\\/]', path_or_command):
        return True

    # 8. IPv6 UNC
    if re.search(r'^\\\\(\[[\da-fA-F:]+\])[\\/]', path_or_command):
        return True
    if re.search(r'^\/\/(\[[\da-fA-F:]+\])[\\/]', path_or_command):
        return True

    return False


# ---------------------------------------------------------------------------
# Flag validation utilities
# ---------------------------------------------------------------------------

# Regex pattern to match valid flag names
FLAG_PATTERN = re.compile(r'^-[a-zA-Z0-9_-]')


def validate_flag_argument(value: str, arg_type: FlagArgType) -> bool:
    """Validate a flag argument based on its expected type."""
    if arg_type == 'none':
        return False  # Should not have been called for 'none' type
    elif arg_type == 'number':
        return bool(re.match(r'^\d+$', value))
    elif arg_type == 'string':
        return True  # Any string including empty is valid
    elif arg_type == 'char':
        return len(value) == 1
    elif arg_type == '{}':
        return value == '{}'
    elif arg_type == 'EOF':
        return value == 'EOF'
    return False


def validate_flags(
    tokens: List[str],
    start_index: int,
    config: ExternalCommandConfig,
    command_name: Optional[str] = None,
    raw_command: Optional[str] = None,
    xargs_target_commands: Optional[List[str]] = None,
) -> bool:
    """
    Validates the flags/arguments portion of a tokenized command against a config.

    Args:
        tokens: Pre-tokenized args
        start_index: Where to start validating (after command tokens)
        config: The safe flags config
        command_name: For command-specific handling (git numeric shorthand, grep/rg attached numeric)
        raw_command: For additionalCommandIsDangerousCallback
        xargs_target_commands: If provided, enables xargs-style target command detection

    Returns:
        True if all flags are valid, False otherwise
    """
    i = start_index

    while i < len(tokens):
        token = tokens[i]
        if not token:
            i += 1
            continue

        # Special handling for xargs
        if xargs_target_commands is not None and command_name == 'xargs':
            if not token.startswith('-') or token == '--':
                if token == '--' and i + 1 < len(tokens):
                    i += 1
                    token = tokens[i]
                if token and token in xargs_target_commands:
                    break
                return False

        if token == '--':
            if config.respects_double_dash is not False:
                i += 1
                break  # Everything after -- is arguments
            i += 1
            continue

        if token.startswith('-') and len(token) > 1 and FLAG_PATTERN.match(token):
            # SECURITY: Track hasEquals separately from inlineValue truthiness
            has_equals = '=' in token
            parts = token.split('=', 1)
            flag = parts[0]
            inline_value = parts[1] if has_equals else ''

            if not flag:
                return False

            flag_arg_type = config.safe_flags.get(flag)

            if flag_arg_type is None:
                # Special case: git commands support -<number> as shorthand for -n
                if command_name == 'git' and re.match(r'^-\d+$', flag):
                    i += 1
                    continue

                # Handle flags with directly attached numeric arguments (e.g., -A20, -B10)
                # Only for grep and rg
                if command_name in ('grep', 'rg') and flag.startswith('-') and not flag.startswith('--') and len(flag) > 2:
                    potential_flag = flag[:2]
                    potential_value = flag[2:]
                    potential_type = config.safe_flags.get(potential_flag)
                    if potential_type and re.match(r'^\d+$', potential_value):
                        if potential_type in ('number', 'string'):
                            if validate_flag_argument(potential_value, potential_type):
                                i += 1
                                continue
                            else:
                                return False

                # Handle combined single-letter flags like -nr
                # SECURITY: ALL bundled flags must be 'none' type
                if flag.startswith('-') and not flag.startswith('--') and len(flag) > 2:
                    all_safe = True
                    for j in range(1, len(flag)):
                        single_flag = '-' + flag[j]
                        ft = config.safe_flags.get(single_flag)
                        if not ft:
                            all_safe = False
                            break
                        if ft != 'none':
                            all_safe = False
                            break
                    if all_safe:
                        i += 1
                        continue
                    else:
                        return False
                else:
                    return False  # Unknown flag

            # Validate flag arguments
            if flag_arg_type == 'none':
                if has_equals:
                    return False  # Flag should not have a value
                i += 1
            else:
                if has_equals:
                    arg_value = inline_value
                    i += 1
                else:
                    # Check if next token is the argument
                    next_token = tokens[i + 1] if i + 1 < len(tokens) else None
                    if (next_token is None or
                            (next_token.startswith('-') and len(next_token) > 1
                             and FLAG_PATTERN.match(next_token))):
                        return False  # Missing required argument
                    arg_value = next_token or ''
                    i += 2

                # Defense-in-depth: reject string args that start with '-'
                if flag_arg_type == 'string' and arg_value.startswith('-'):
                    # Special case: git's --sort flag allows - prefix for reverse sorting
                    if flag == '--sort' and command_name == 'git' and re.match(r'^-[a-zA-Z]', arg_value):
                        pass  # Allow reverse sort
                    else:
                        return False

                if not validate_flag_argument(arg_value, flag_arg_type):
                    return False
        else:
            # Non-flag argument — allowed
            i += 1

    return True
