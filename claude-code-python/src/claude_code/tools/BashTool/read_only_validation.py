"""
Read-only command validation for BashTool.

This module determines whether a bash command is read-only (safe to execute
without user permission) by checking:
1. Whether the command matches a known-safe command pattern
2. Whether all flags are safe

Ported from tools/BashTool/readOnlyValidation.ts (1990 lines)
"""

from __future__ import annotations

import os
import re
import sys
from typing import Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Types (mirrored from readOnlyCommandValidation)
# ---------------------------------------------------------------------------

FlagArgType = str  # 'none' | 'number' | 'string' | 'char' | '{}' | 'EOF'


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


CommandConfig = ExternalCommandConfig  # Alias used internally

# ---------------------------------------------------------------------------
# Imports from shared module (try/except for graceful degradation)
# ---------------------------------------------------------------------------

try:
    from claude_code.utils.shell.read_only_command_validation import (
        GIT_READ_ONLY_COMMANDS,
        GH_READ_ONLY_COMMANDS,
        DOCKER_READ_ONLY_COMMANDS,
        RIPGREP_READ_ONLY_COMMANDS,
        PYRIGHT_READ_ONLY_COMMANDS,
        ExternalCommandConfig as _ExternalCommandConfig,
        contains_vulnerable_unc_path,
    )
    ExternalCommandConfig = _ExternalCommandConfig
except ImportError:
    GIT_READ_ONLY_COMMANDS = {}
    GH_READ_ONLY_COMMANDS = {}
    DOCKER_READ_ONLY_COMMANDS = {}
    RIPGREP_READ_ONLY_COMMANDS = {}
    PYRIGHT_READ_ONLY_COMMANDS = {}

    def contains_vulnerable_unc_path(path: str) -> bool:
        return False


try:
    from claude_code.utils.bash.ast import (
        SimpleCommand,
        ParseForSecurityResult,
        ParseForSecuritySimple,
    )
except ImportError:
    SimpleCommand = None
    ParseForSecurityResult = None
    ParseForSecuritySimple = None


# ---------------------------------------------------------------------------
# Get platform
# ---------------------------------------------------------------------------

def _get_platform() -> str:
    if sys.platform == 'win32':
        return 'windows'
    elif sys.platform == 'darwin':
        return 'mac'
    return 'linux'


def _get_original_cwd() -> str:
    """Get the original working directory when the process started."""
    return os.environ.get('ORIGINAL_CWD', os.getcwd())


# ---------------------------------------------------------------------------
# Local command configurations for BashTool-specific commands
# ---------------------------------------------------------------------------

# grep flags
GREP_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-e': 'string',
    '--regexp': 'string',
    '-f': 'string',
    '--file': 'string',
    '-i': 'none',
    '--ignore-case': 'none',
    '-v': 'none',
    '--invert-match': 'none',
    '-w': 'none',
    '--word-regexp': 'none',
    '-x': 'none',
    '--line-regexp': 'none',
    '-c': 'none',
    '--count': 'none',
    '-l': 'none',
    '--files-with-matches': 'none',
    '-L': 'none',
    '--files-without-match': 'none',
    '-n': 'none',
    '--line-number': 'none',
    '-H': 'none',
    '--with-filename': 'none',
    '-h': 'none',
    '--no-filename': 'none',
    '-q': 'none',
    '--quiet': 'none',
    '--silent': 'none',
    '-s': 'none',
    '--no-messages': 'none',
    '-o': 'none',
    '--only-matching': 'none',
    '-A': 'number',
    '--after-context': 'number',
    '-B': 'number',
    '--before-context': 'number',
    '-C': 'number',
    '--context': 'number',
    '-m': 'number',
    '--max-count': 'number',
    '-r': 'none',
    '--recursive': 'none',
    '-R': 'none',
    '--dereference-recursive': 'none',
    '--include': 'string',
    '--exclude': 'string',
    '--exclude-dir': 'string',
    '--exclude-from': 'string',
    '--ignore-file': 'string',
    '-c': 'string',
    '--color': 'string',
    '--colour': 'string',
    '-P': 'none',
    '--perl-regexp': 'none',
    '-E': 'none',
    '--extended-regexp': 'none',
    '-G': 'none',
    '--basic-regexp': 'none',
    '-F': 'none',
    '--fixed-strings': 'none',
    '-z': 'none',
    '--null-data': 'none',
    '-Z': 'none',
    '--null': 'none',
    '-U': 'none',
    '--binary': 'none',
    '-a': 'none',
    '--text': 'none',
    '--no-buffer': 'none',
    '-n': 'none',
    '--preserve-date': 'none',
    '--mmap': 'none',
    '-T': 'none',
    '--initial-tab': 'none',
    '-I': 'none',
    '--binary-files': 'string',
    '--label': 'string',
    '-D': 'string',
    '--devices': 'string',
    '-d': 'string',
    '--directories': 'string',
}

# find safe flags
FIND_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-name': 'string',
    '-iname': 'string',
    '-type': 'string',
    '-size': 'string',
    '-maxdepth': 'number',
    '-mindepth': 'number',
    '-newer': 'string',
    '-newerXY': 'string',
    '-atime': 'string',
    '-mtime': 'string',
    '-ctime': 'string',
    '-amin': 'string',
    '-mmin': 'string',
    '-cmin': 'string',
    '-user': 'string',
    '-group': 'string',
    '-perm': 'string',
    '-path': 'string',
    '-ipath': 'string',
    '-regex': 'string',
    '-iregex': 'string',
    '-regextype': 'string',
    '-print': 'none',
    '-print0': 'none',
    '-ls': 'none',
    '-printf': 'string',
    '-readable': 'none',
    '-writable': 'none',
    '-executable': 'none',
    '-empty': 'none',
    '-and': 'none',
    '-or': 'none',
    '-not': 'none',
    '!': 'none',
    '-follow': 'none',
    '-L': 'none',
    '-P': 'none',
    '-H': 'none',
    '-D': 'string',
    '-O1': 'none',
    '-O2': 'none',
    '-O3': 'none',
    '-daystart': 'none',
    '-depth': 'none',
    '-d': 'none',
    '-mount': 'none',
    '-xdev': 'none',
    '-noleaf': 'none',
    '-links': 'number',
    '-inum': 'number',
}

# cat safe flags
CAT_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-n': 'none',
    '--number': 'none',
    '-b': 'none',
    '--number-nonblank': 'none',
    '-s': 'none',
    '--squeeze-blank': 'none',
    '-A': 'none',
    '--show-all': 'none',
    '-v': 'none',
    '--show-nonprinting': 'none',
    '-T': 'none',
    '--show-tabs': 'none',
    '-E': 'none',
    '--show-ends': 'none',
    '-e': 'none',
    '-t': 'none',
    '--help': 'none',
    '--version': 'none',
}

# head/tail safe flags
HEAD_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-n': 'number',
    '--lines': 'number',
    '-c': 'number',
    '--bytes': 'number',
    '-q': 'none',
    '--quiet': 'none',
    '--silent': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '-z': 'none',
    '--zero-terminated': 'none',
    '--help': 'none',
    '--version': 'none',
}

TAIL_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-n': 'string',  # can be +N or N
    '--lines': 'string',
    '-c': 'string',
    '--bytes': 'string',
    '-f': 'none',
    '--follow': 'none',
    '-F': 'none',
    '-q': 'none',
    '--quiet': 'none',
    '--silent': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '-z': 'none',
    '--zero-terminated': 'none',
    '--pid': 'number',
    '-s': 'number',
    '--sleep-interval': 'number',
    '--retry': 'none',
    '--help': 'none',
    '--version': 'none',
}

# wc safe flags
WC_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-l': 'none',
    '--lines': 'none',
    '-w': 'none',
    '--words': 'none',
    '-c': 'none',
    '--bytes': 'none',
    '-m': 'none',
    '--chars': 'none',
    '-L': 'none',
    '--max-line-length': 'none',
    '--help': 'none',
    '--version': 'none',
}

# ls safe flags
LS_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-l': 'none',
    '-a': 'none',
    '--all': 'none',
    '-A': 'none',
    '--almost-all': 'none',
    '-h': 'none',
    '--human-readable': 'none',
    '-r': 'none',
    '--reverse': 'none',
    '-S': 'none',
    '-t': 'none',
    '-u': 'none',
    '-c': 'none',
    '-R': 'none',
    '--recursive': 'none',
    '-1': 'none',
    '-C': 'none',
    '-m': 'none',
    '-x': 'none',
    '-n': 'none',
    '--numeric-uid-gid': 'none',
    '-g': 'none',
    '-G': 'none',
    '--no-group': 'none',
    '-o': 'none',
    '-p': 'none',
    '--indicator-style': 'string',
    '-F': 'none',
    '-b': 'none',
    '--escape': 'none',
    '-q': 'none',
    '--hide-control-chars': 'none',
    '-i': 'none',
    '--inode': 'none',
    '-s': 'none',
    '--size': 'none',
    '-d': 'none',
    '--directory': 'none',
    '-L': 'none',
    '--dereference': 'none',
    '-H': 'none',
    '--dereference-command-line': 'none',
    '-Z': 'none',
    '--context': 'none',
    '--color': 'string',
    '--colour': 'string',
    '--format': 'string',
    '--time': 'string',
    '--sort': 'string',
    '--quoting-style': 'string',
    '--block-size': 'string',
    '--time-style': 'string',
    '--hide': 'string',
    '--ignore': 'string',
    '--ignore-backups': 'none',
    '-B': 'none',
    '-k': 'none',
    '--kibibytes': 'none',
    '-Q': 'none',
    '--quote-name': 'none',
    '--si': 'none',
    '--author': 'none',
    '--full-time': 'none',
    '--dereference-command-line-symlink-to-dir': 'none',
    '--literal': 'none',
    '-N': 'none',
    '-v': 'none',
    '-w': 'number',
    '--width': 'number',
    '--help': 'none',
    '--version': 'none',
}

# diff safe flags
DIFF_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-u': 'none',
    '--unified': 'number',
    '-U': 'number',
    '-c': 'none',
    '--context': 'number',
    '-C': 'number',
    '-i': 'none',
    '--ignore-case': 'none',
    '-w': 'none',
    '--ignore-all-space': 'none',
    '-b': 'none',
    '--ignore-space-change': 'none',
    '-B': 'none',
    '--ignore-blank-lines': 'none',
    '-N': 'none',
    '--new-file': 'none',
    '-r': 'none',
    '--recursive': 'none',
    '-s': 'none',
    '--report-identical-files': 'none',
    '-q': 'none',
    '--brief': 'none',
    '-l': 'none',
    '--paginate': 'none',
    '-p': 'none',
    '--show-c-function': 'none',
    '-t': 'none',
    '--expand-tabs': 'none',
    '-T': 'none',
    '--initial-tab': 'none',
    '--color': 'string',
    '--colour': 'string',
    '--strip-trailing-cr': 'none',
    '-a': 'none',
    '--text': 'none',
    '-d': 'none',
    '--minimal': 'none',
    '--speed-large-files': 'none',
    '--normal': 'none',
    '-e': 'none',
    '--ed': 'none',
    '-n': 'none',
    '--rcs': 'none',
    '-y': 'none',
    '--side-by-side': 'none',
    '-W': 'number',
    '--width': 'number',
    '--left-column': 'none',
    '--suppress-common-lines': 'none',
    '-F': 'string',
    '--show-function-line': 'string',
    '-L': 'string',
    '--label': 'string',
    '--tabsize': 'number',
    '--horizon-lines': 'number',
    '-Z': 'none',
    '--ignore-trailing-space': 'none',
    '-E': 'none',
    '--ignore-tab-expansion': 'none',
    '-z': 'none',
    '--unidirectional-new-file': 'none',
    '--GTYPE-group-format': 'string',
    '--line-format': 'string',
    '--LTYPE-line-format': 'string',
    '--exclude': 'string',
    '-x': 'string',
    '--exclude-from': 'string',
    '-X': 'string',
    '-I': 'string',
    '--ignore-matching-lines': 'string',
    '--to-file': 'string',
    '--from-file': 'string',
    '--help': 'none',
    '--version': 'none',
}

# sort safe flags
SORT_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-b': 'none',
    '--ignore-leading-blanks': 'none',
    '-d': 'none',
    '--dictionary-order': 'none',
    '-f': 'none',
    '--ignore-case': 'none',
    '-g': 'none',
    '--general-numeric-sort': 'none',
    '-i': 'none',
    '--ignore-nonprinting': 'none',
    '-M': 'none',
    '--month-sort': 'none',
    '-h': 'none',
    '--human-numeric-sort': 'none',
    '-n': 'none',
    '--numeric-sort': 'none',
    '-R': 'none',
    '--random-sort': 'none',
    '-r': 'none',
    '--reverse': 'none',
    '-V': 'none',
    '--version-sort': 'none',
    '-k': 'string',
    '--key': 'string',
    '-t': 'char',
    '--field-separator': 'char',
    '-u': 'none',
    '--unique': 'none',
    '-s': 'none',
    '--stable': 'none',
    '-z': 'none',
    '--zero-terminated': 'none',
    '--parallel': 'number',
    '-c': 'none',
    '--check': 'none',
    '-C': 'none',
    '-m': 'none',
    '--merge': 'none',
    '--output': 'string',
    '-o': 'string',
    '--compress-program': 'string',
    '--temporary-directory': 'string',
    '-T': 'string',
    '-S': 'string',
    '--buffer-size': 'string',
    '--batch-size': 'number',
    '--help': 'none',
    '--version': 'none',
}

# sed safe flags
SED_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-n': 'none',
    '--quiet': 'none',
    '--silent': 'none',
    '-e': 'string',
    '--expression': 'string',
    '-f': 'string',
    '--file': 'string',
    '-i': 'string',  # SECURITY: -i edits in-place — see callback
    '--in-place': 'string',
    '-r': 'none',
    '-E': 'none',
    '--regexp-extended': 'none',
    '-s': 'none',
    '--separate': 'none',
    '-z': 'none',
    '--null-data': 'none',
    '-l': 'number',
    '--line-length': 'number',
    '--debug': 'none',
    '--posix': 'none',
    '--sandbox': 'none',
    '--help': 'none',
    '--version': 'none',
}

# awk safe flags
AWK_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-F': 'string',
    '--field-separator': 'string',
    '-v': 'string',
    '--assign': 'string',
    '-f': 'string',
    '--file': 'string',
    '-e': 'string',  # gawk extension
    '-n': 'none',
    '--lint': 'none',
    '--lint-old': 'none',
    '-O': 'none',
    '--optimize': 'none',
    '-P': 'none',
    '--posix': 'none',
    '-s': 'none',
    '--sandbox': 'none',
    '-b': 'none',
    '--characters-as-bytes': 'none',
    '-c': 'none',
    '--traditional': 'none',
    '--re-interval': 'none',
    '--profile': 'string',
    '--copyleft': 'none',
    '--help': 'none',
    '--version': 'none',
}

# curl safe flags (read-only: GET only, no POST/PUT/DELETE)
CURL_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-s': 'none',
    '--silent': 'none',
    '-S': 'none',
    '--show-error': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '-L': 'none',
    '--location': 'none',
    '-I': 'none',
    '--head': 'none',
    '-G': 'none',
    '--get': 'none',
    '--get': 'none',
    '-o': 'string',
    '--output': 'string',
    '-O': 'none',
    '--remote-name': 'none',
    '-H': 'string',
    '--header': 'string',
    '--url': 'string',
    '-A': 'string',
    '--user-agent': 'string',
    '-m': 'number',
    '--max-time': 'number',
    '--connect-timeout': 'number',
    '-f': 'none',
    '--fail': 'none',
    '--fail-with-body': 'none',
    '-k': 'none',
    '--insecure': 'none',
    '-w': 'string',
    '--write-out': 'string',
    '--max-redirs': 'number',
    '-e': 'string',
    '--referer': 'string',
    '--compressed': 'none',
    '--no-compressed': 'none',
    '--http1.0': 'none',
    '--http1.1': 'none',
    '--http2': 'none',
    '--http3': 'none',
    '-4': 'none',
    '--ipv4': 'none',
    '-6': 'none',
    '--ipv6': 'none',
    '--no-keepalive': 'none',
    '--keepalive-time': 'number',
    '--limit-rate': 'string',
    '--retry': 'number',
    '--retry-delay': 'number',
    '--retry-max-time': 'number',
    '--noproxy': 'string',
    '--no-alpn': 'none',
    '--no-npn': 'none',
    '-Z': 'none',
    '--parallel': 'none',
    '--parallel-max': 'number',
    '--parallel-immediate': 'none',
    '--tlsv1': 'none',
    '--tlsv1.0': 'none',
    '--tlsv1.1': 'none',
    '--tlsv1.2': 'none',
    '--tlsv1.3': 'none',
    '--ssl': 'none',
    '--ssl-reqd': 'none',
    '--cacert': 'string',
    '--capath': 'string',
    '--cert': 'string',
    '--key': 'string',
    '--trace-time': 'none',
    '--trace': 'string',
    '--trace-ascii': 'string',
    '--help': 'none',
    '--version': 'none',
    '-V': 'none',
    '-#': 'none',
    '--progress-bar': 'none',
    '--no-progress-meter': 'none',
    '-i': 'none',
    '--include': 'none',
    '--dump-header': 'string',
    '-D': 'string',
    '-b': 'string',
    '--cookie': 'string',
    '-c': 'string',
    '--cookie-jar': 'string',
    '--junk-session-cookies': 'none',
    '-j': 'none',
    '--path-as-is': 'none',
    '--request-target': 'string',
    '--alt-svc': 'string',
    '--doh-url': 'string',
    '--doh-insecure': 'none',
    '--socks4': 'string',
    '--socks4a': 'string',
    '--socks5': 'string',
    '--socks5-hostname': 'string',
    '--socks5-basic': 'none',
    '--socks5-gssapi': 'none',
    '--proxy': 'string',
    '-x': 'string',
    '--proxy-user': 'string',
    '-U': 'string',
    '--proxy-cacert': 'string',
    '--proxy-capath': 'string',
    '--proxy-cert': 'string',
    '--proxy-key': 'string',
    '--proxy-insecure': 'none',
    '--proxy-tlsv1': 'none',
    '--proxy-ssl-allow-beast': 'none',
    '--proxy-header': 'string',
    '--proxy-service-name': 'string',
    '--proxy-negotiate': 'none',
    '--proxy-ntlm': 'none',
    '--proxy-basic': 'none',
    '--proxy-digest': 'none',
    '--preproxy': 'string',
    '--noproxy': 'string',
    '--haproxy-protocol': 'none',
    '--resolve': 'string',
    '--connect-to': 'string',
    '--interface': 'string',
    '--local-port': 'string',
}

# wget safe flags (GET only)
WGET_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-q': 'none',
    '--quiet': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '-nv': 'none',
    '--no-verbose': 'none',
    '-o': 'string',
    '--output-file': 'string',
    '-a': 'string',
    '--append-output': 'string',
    '-d': 'none',
    '--debug': 'none',
    '-i': 'string',
    '--input-file': 'string',
    '-F': 'none',
    '--force-html': 'none',
    '-B': 'string',
    '--base': 'string',
    '-t': 'number',
    '--tries': 'number',
    '--retry-connrefused': 'none',
    '--timeout': 'number',
    '-T': 'number',
    '--dns-timeout': 'number',
    '--connect-timeout': 'number',
    '--read-timeout': 'number',
    '-w': 'number',
    '--wait': 'number',
    '--waitretry': 'number',
    '--random-wait': 'none',
    '--limit-rate': 'string',
    '-O': 'string',
    '--output-document': 'string',
    '-P': 'string',
    '--directory-prefix': 'string',
    '-c': 'none',
    '--continue': 'none',
    '-N': 'none',
    '--timestamping': 'none',
    '--no-clobber': 'none',
    '--no-use-server-timestamps': 'none',
    '-nd': 'none',
    '--no-directories': 'none',
    '-x': 'none',
    '--force-directories': 'none',
    '-nH': 'none',
    '--no-host-directories': 'none',
    '--cut-dirs': 'number',
    '-r': 'none',
    '--recursive': 'none',
    '-l': 'number',
    '--level': 'number',
    '--delete-after': 'none',
    '-k': 'none',
    '--convert-links': 'none',
    '-K': 'none',
    '--backup-converted': 'none',
    '-p': 'none',
    '--page-requisites': 'none',
    '-H': 'none',
    '--span-hosts': 'none',
    '-L': 'none',
    '--relative': 'none',
    '-I': 'string',
    '--include-directories': 'string',
    '-X': 'string',
    '--exclude-directories': 'string',
    '--ignore-case': 'none',
    '-A': 'string',
    '--accept': 'string',
    '-R': 'string',
    '--reject': 'string',
    '--accept-regex': 'string',
    '--reject-regex': 'string',
    '--include-tags': 'string',
    '--exclude-tags': 'string',
    '-S': 'none',
    '--server-response': 'none',
    '--spider': 'none',
    '--no-check-certificate': 'none',
    '--certificate': 'string',
    '--certificate-type': 'string',
    '--private-key': 'string',
    '--private-key-type': 'string',
    '--ca-certificate': 'string',
    '--ca-directory': 'string',
    '--crl-file': 'string',
    '--secure-protocol': 'string',
    '--https-only': 'none',
    '--inet4-only': 'none',
    '-4': 'none',
    '--inet6-only': 'none',
    '-6': 'none',
    '--user': 'string',
    '--password': 'string',
    '--ask-password': 'none',
    '--user-agent': 'string',
    '-U': 'string',
    '--load-cookies': 'string',
    '--save-cookies': 'string',
    '--keep-session-cookies': 'none',
    '--no-cookies': 'none',
    '--header': 'string',
    '--referer': 'string',
    '--max-redirect': 'number',
    '--proxy-user': 'string',
    '--proxy-password': 'string',
    '--no-proxy': 'none',
    '-e': 'string',
    '--execute': 'string',
    '--help': 'none',
    '--version': 'none',
    '-V': 'none',
}

# ssh safe flags (safe = no -o ProxyCommand etc)
# SECURITY: ssh can be dangerous (execute commands on remote). Only allow
# limited read-only usages.
SSH_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-v': 'none',
    '-vv': 'none',
    '-vvv': 'none',
    '-q': 'none',
    '-4': 'none',
    '-6': 'none',
    '-n': 'none',
    '-N': 'none',
    '-T': 'none',
    '-p': 'number',
    '-l': 'string',
    '-i': 'string',
    '-F': 'string',
    '-c': 'string',
    '-m': 'string',
    '-e': 'string',
    '-b': 'string',
    '-x': 'none',
    '-X': 'none',
    '-Y': 'none',
    '-C': 'none',
    '-k': 'none',
    '-A': 'none',
    '-a': 'none',
    '-s': 'none',
    '-W': 'string',
    '-J': 'string',
    '-G': 'none',
}

# python safe flags
PYTHON_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-c': 'string',
    '-m': 'string',
    '-V': 'none',
    '--version': 'none',
    '-h': 'none',
    '--help': 'none',
    '-q': 'none',
    '-u': 'none',
    '-b': 'none',
    '-B': 'none',
    '-d': 'none',
    '-E': 'none',
    '-I': 'none',
    '-O': 'none',
    '-OO': 'none',
    '-R': 'none',
    '-s': 'none',
    '-S': 'none',
    '-t': 'none',
    '-v': 'none',
    '-W': 'string',
    '--check-hash-based-pycs': 'string',
    '-x': 'none',
    '-3': 'none',
}

# node/npm safe flags
NODE_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--version': 'none',
    '-v': 'none',
    '--help': 'none',
    '-h': 'none',
    '-e': 'string',
    '--eval': 'string',
    '-p': 'string',
    '--print': 'string',
    '-i': 'none',
    '--interactive': 'none',
    '-r': 'string',
    '--require': 'string',
    '--inspect': 'none',
    '--inspect-brk': 'none',
    '--inspect-port': 'number',
    '--no-deprecation': 'none',
    '--throw-deprecation': 'none',
    '--trace-deprecation': 'none',
    '--trace-sync-io': 'none',
    '--no-warnings': 'none',
    '--node-memory-debug': 'none',
    '--expose-gc': 'none',
    '--harmony': 'none',
    '--max-old-space-size': 'number',
}

# ps safe flags
PS_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-e': 'none',
    '-f': 'none',
    '-l': 'none',
    '-a': 'none',
    '-u': 'none',
    '-x': 'none',
    '-r': 'none',
    '-A': 'none',
    '-j': 'none',
    '-p': 'string',
    '-o': 'string',
    '--no-headers': 'none',
    '--no-header': 'none',
    '-H': 'none',
    '--forest': 'none',
    '-T': 'none',
    '--no-wrap': 'none',
    'aux': 'none',  # not really a flag
    'axxx': 'none',
}

# netstat safe flags
NETSTAT_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-t': 'none',
    '--tcp': 'none',
    '-u': 'none',
    '--udp': 'none',
    '-n': 'none',
    '--numeric': 'none',
    '-l': 'none',
    '--listening': 'none',
    '-a': 'none',
    '--all': 'none',
    '-p': 'none',
    '--programs': 'none',
    '-r': 'none',
    '--route': 'none',
    '-s': 'none',
    '--statistics': 'none',
    '-i': 'none',
    '--interfaces': 'none',
    '-e': 'none',
    '--extend': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '-c': 'none',
    '--continuous': 'none',
    '-o': 'none',
    '--timers': 'none',
    '-4': 'none',
    '-6': 'none',
    '-W': 'none',
    '-Z': 'none',
    '--selinux': 'none',
    '--groups': 'none',
    '--masquerade': 'none',
    '--symbolic': 'none',
    '-N': 'none',
    '--numerical-hosts': 'none',
    '--numerical-ports': 'none',
    '--numerical-users': 'none',
    '-T': 'none',
    '--notrim': 'none',
    '-x': 'none',
    '-w': 'none',
    '-F': 'none',
    '-M': 'none',
    '--no-header': 'none',
    '-g': 'none',
}

# hostname safe flags
HOSTNAME_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-f': 'none',
    '--fqdn': 'none',
    '--long': 'none',
    '-s': 'none',
    '--short': 'none',
    '-i': 'none',
    '--ip-address': 'none',
    '-I': 'none',
    '--all-ip-addresses': 'none',
    '-A': 'none',
    '--all-fqdns': 'none',
    '-d': 'none',
    '--domain': 'none',
    '-y': 'none',
    '--nis': 'none',
    '--yp': 'none',
    '--help': 'none',
    '--version': 'none',
    '-V': 'none',
}

# du safe flags
DU_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-s': 'none',
    '--summarize': 'none',
    '-h': 'none',
    '--human-readable': 'none',
    '-k': 'none',
    '-m': 'none',
    '-b': 'none',
    '--bytes': 'none',
    '-c': 'none',
    '--total': 'none',
    '-a': 'none',
    '--all': 'none',
    '-d': 'number',
    '--max-depth': 'number',
    '--si': 'none',
    '--apparent-size': 'none',
    '-l': 'none',
    '--count-links': 'none',
    '-L': 'none',
    '--dereference': 'none',
    '-P': 'none',
    '--no-dereference': 'none',
    '-0': 'none',
    '--null': 'none',
    '-x': 'none',
    '--one-file-system': 'none',
    '--exclude': 'string',
    '-X': 'string',
    '--exclude-from': 'string',
    '--threshold': 'string',
    '-t': 'string',
    '--time': 'none',
    '--time-style': 'string',
    '--block-size': 'string',
    '-B': 'string',
    '--help': 'none',
    '--version': 'none',
}

# df safe flags
DF_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-h': 'none',
    '--human-readable': 'none',
    '-H': 'none',
    '--si': 'none',
    '-k': 'none',
    '-m': 'none',
    '-b': 'none',
    '--portability': 'none',
    '-P': 'none',
    '-T': 'none',
    '--print-type': 'none',
    '-t': 'string',
    '--type': 'string',
    '-x': 'string',
    '--exclude-type': 'string',
    '-l': 'none',
    '--local': 'none',
    '-a': 'none',
    '--all': 'none',
    '--total': 'none',
    '-i': 'none',
    '--inodes': 'none',
    '--sync': 'none',
    '--no-sync': 'none',
    '--output': 'string',
    '--block-size': 'string',
    '-B': 'string',
    '--help': 'none',
    '--version': 'none',
}

# tar safe flags (list/extract read-only modes)
TAR_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-t': 'none',
    '--list': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '-z': 'none',
    '--gzip': 'none',
    '--gunzip': 'none',
    '-j': 'none',
    '--bzip2': 'none',
    '-J': 'none',
    '--xz': 'none',
    '--lzma': 'none',
    '-a': 'none',
    '--auto-compress': 'none',
    '-I': 'string',
    '--use-compress-program': 'string',
    '-f': 'string',
    '--file': 'string',
    '-C': 'string',
    '--directory': 'string',
    '-p': 'none',
    '--preserve-permissions': 'none',
    '--same-permissions': 'none',
    '-o': 'none',
    '--no-same-owner': 'none',
    '--no-same-permissions': 'none',
    '-k': 'none',
    '--keep-old-files': 'none',
    '--no-overwrite-dir': 'none',
    '--one-top-level': 'none',
    '--strip-components': 'number',
    '--transform': 'string',
    '-s': 'string',
    '--wildcards': 'none',
    '--no-wildcards': 'none',
    '--wildcards-match-slash': 'none',
    '--no-wildcards-match-slash': 'none',
    '--anchored': 'none',
    '--no-anchored': 'none',
    '--ignore-case': 'none',
    '--no-ignore-case': 'none',
    '--exclude': 'string',
    '-X': 'string',
    '--exclude-from': 'string',
    '--exclude-caches': 'none',
    '--exclude-caches-all': 'none',
    '--exclude-caches-under': 'none',
    '--exclude-vcs': 'none',
    '--exclude-vcs-ignores': 'none',
    '--exclude-backups': 'none',
    '-H': 'string',
    '--format': 'string',
    '--old-archive': 'none',
    '--portability': 'none',
    '--ustar': 'none',
    '--posix': 'none',
    '--pax-option': 'string',
    '--totals': 'none',
    '--utc': 'none',
    '--show-transformed-names': 'none',
    '--index-file': 'string',
    '-R': 'none',
    '--block-number': 'none',
    '-T': 'string',
    '--files-from': 'string',
    '-h': 'none',
    '--dereference': 'none',
    '-L': 'number',
    '--tape-length': 'number',
    '--help': 'none',
    '--version': 'none',
}

# zip/unzip safe flags
UNZIP_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-l': 'none',
    '-v': 'none',
    '-t': 'none',
    '-Z': 'none',
    '-p': 'none',
    '-n': 'none',
    '-o': 'none',
    '-a': 'none',
    '-aa': 'none',
    '-b': 'none',
    '-q': 'none',
    '-qq': 'none',
    '-d': 'string',
    '-x': 'string',
    '-j': 'none',
    '--help': 'none',
    '-h': 'none',
    '-L': 'none',
    '-C': 'none',
    '-s': 'none',
    '-S': 'none',
    '-UU': 'none',
    '-W': 'none',
    '-P': 'string',
}

# which safe flags (no flags needed — just command name lookup)
WHICH_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-a': 'none',
    '--all': 'none',
    '--skip-alias': 'none',
    '--skip-functions': 'none',
    '--skip-dot': 'none',
    '--skip-tilde': 'none',
    '--show-tilde': 'none',
    '-s': 'none',
    '--tty-only': 'none',
    '--read-alias': 'none',
    '--no-aliases': 'none',
    '--read-functions': 'none',
    '--no-functions': 'none',
    '--help': 'none',
    '--version': 'none',
}

# make safe flags (list targets, dry-run)
MAKE_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-n': 'none',
    '--just-print': 'none',
    '--dry-run': 'none',
    '--recon': 'none',
    '-q': 'none',
    '--question': 'none',
    '-p': 'none',
    '--print-data-base': 'none',
    '-v': 'none',
    '--version': 'none',
    '-h': 'none',
    '--help': 'none',
    '-f': 'string',
    '--file': 'string',
    '--makefile': 'string',
    '-C': 'string',
    '--directory': 'string',
    '-e': 'none',
    '--environment-overrides': 'none',
    '-I': 'string',
    '--include-dir': 'string',
    '-j': 'number',
    '--jobs': 'number',
    '-k': 'none',
    '--keep-going': 'none',
    '-L': 'none',
    '--check-symlink-times': 'none',
    '--no-builtin-rules': 'none',
    '-r': 'none',
    '--no-builtin-variables': 'none',
    '-R': 'none',
    '-s': 'none',
    '--silent': 'none',
    '--quiet': 'none',
    '-S': 'none',
    '--no-keep-going': 'none',
    '--stop': 'none',
    '-t': 'none',
    '--touch': 'none',
    '--trace': 'none',
    '-w': 'none',
    '--print-directory': 'none',
    '--no-print-directory': 'none',
    '-W': 'string',
    '--what-if': 'string',
    '--new-file': 'string',
    '--assume-new': 'string',
    '-o': 'string',
    '--old-file': 'string',
    '--assume-old': 'string',
    '--warn-undefined-variables': 'none',
    '-d': 'none',
    '--debug': 'string',
}

# tree safe flags
TREE_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-a': 'none',
    '-d': 'none',
    '-f': 'none',
    '-l': 'none',
    '-L': 'number',
    '-i': 'none',
    '-q': 'none',
    '-N': 'none',
    '-Q': 'none',
    '-p': 'none',
    '-u': 'none',
    '-g': 'none',
    '-s': 'none',
    '-h': 'none',
    '--si': 'none',
    '-D': 'none',
    '-F': 'none',
    '-r': 'none',
    '-t': 'none',
    '-n': 'none',
    '-C': 'none',
    '-I': 'string',
    '-P': 'string',
    '-o': 'string',
    '--inodes': 'none',
    '--device': 'none',
    '--noreport': 'none',
    '--nolinks': 'none',
    '--dirsfirst': 'none',
    '--filesfirst': 'none',
    '--sort': 'string',
    '--prune': 'none',
    '--charset': 'string',
    '--filelimit': 'number',
    '--matchdirs': 'none',
    '--ignore-case': 'none',
    '--fromfile': 'none',
    '--du': 'none',
    '-X': 'none',
    '-J': 'none',
    '-H': 'string',
    '-T': 'string',
    '-R': 'none',
    '-v': 'none',
    '-x': 'none',
    '--version': 'none',
    '--help': 'none',
}

# lsof safe flags
LSOF_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-i': 'string',
    '-p': 'string',
    '-u': 'string',
    '-g': 'string',
    '-c': 'string',
    '-d': 'string',
    '-a': 'none',
    '-n': 'none',
    '-P': 'none',
    '-t': 'none',
    '-l': 'none',
    '-R': 'none',
    '-w': 'none',
    '-W': 'none',
    '-X': 'none',
    '-F': 'string',
    '+d': 'string',
    '+D': 'string',
    '-r': 'string',
    '-s': 'string',
    '+c': 'number',
    '-e': 'string',
    '-x': 'string',
    '+x': 'string',
    '-K': 'none',
    '+K': 'none',
    '-f': 'none',
    '+f': 'none',
    '-L': 'string',
    '-M': 'none',
    '-m': 'string',
    '+M': 'none',
    '-D': 'string',
    '-b': 'none',
    '-B': 'string',
    '-o': 'string',
    '-S': 'string',
    '-T': 'string',
    '-z': 'string',
    '-Z': 'string',
    '-v': 'none',
    '-V': 'none',
    '-h': 'none',
    '-?': 'none',
    '-O': 'none',
    '-q': 'none',
    '-0': 'none',
    '-E': 'none',
}

# pip/pip3 safe flags (list/show/check only)
PIP_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--version': 'none',
    '-V': 'none',
    '--verbose': 'none',
    '-v': 'none',
    '-q': 'none',
    '--quiet': 'none',
    '--isolated': 'none',
    '--no-color': 'none',
    '--no-python-version-warning': 'none',
    '--disable-pip-version-check': 'none',
    '--format': 'string',
    '-f': 'string',
    '-l': 'none',
    '--local': 'none',
    '--user': 'none',
    '--path': 'string',
    '--not-required': 'none',
    '--pre': 'none',
    '--outdated': 'none',
    '--uptodate': 'none',
    '-i': 'string',
    '--index-url': 'string',
    '--extra-index-url': 'string',
    '--no-index': 'none',
    '--find-links': 'string',
    '-f': 'string',
    '--files': 'none',
    '-F': 'none',
    '--include-editable': 'none',
    '-e': 'none',
    '--help': 'none',
    '-h': 'none',
    '--check': 'none',
    '--ignore-missing': 'none',
}

# npm safe flags
NPM_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--version': 'none',
    '-v': 'none',
    '--help': 'none',
    '-h': 'none',
    '--global': 'none',
    '-g': 'none',
    '--depth': 'number',
    '--json': 'none',
    '--long': 'none',
    '-l': 'none',
    '--parseable': 'none',
    '-p': 'none',
    '--color': 'string',
    '--no-color': 'none',
    '--unicode': 'none',
    '--no-unicode': 'none',
    '--progress': 'none',
    '--no-progress': 'none',
    '--loglevel': 'string',
    '--silent': 'none',
    '--quiet': 'none',
    '-q': 'none',
    '--prefer-offline': 'none',
    '--prefer-online': 'none',
    '--offline': 'none',
    '--dry-run': 'none',
    '--production': 'none',
    '--only': 'string',
    '--userconfig': 'string',
    '-a': 'none',
    '--all': 'none',
    '--diff': 'none',
    '--diff-name-only': 'none',
    '--diff-ignore-all-space': 'none',
    '--diff-unified': 'number',
    '--diff-stat': 'none',
    '--diff-src-prefix': 'string',
    '--diff-dst-prefix': 'string',
    '--prefix': 'string',
    '--workspaces': 'none',
    '-ws': 'none',
    '--workspace': 'string',
    '-w': 'string',
    '--include-workspace-root': 'none',
    '--ignore-scripts': 'none',
    '--tag': 'string',
}

# yarn safe flags
YARN_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--version': 'none',
    '-v': 'none',
    '--help': 'none',
    '-h': 'none',
    '--json': 'none',
    '--no-progress': 'none',
    '--verbose': 'none',
    '--offline': 'none',
    '--prefer-offline': 'none',
    '--cache-folder': 'string',
    '--mutex': 'string',
    '--cwd': 'string',
    '--silent': 'none',
    '--non-interactive': 'none',
    '--no-node-version-check': 'none',
    '--emoji': 'none',
    '--no-emoji': 'none',
    '--color': 'none',
    '--no-color': 'none',
    '--network-timeout': 'number',
    '--network-concurrency': 'number',
    '-D': 'none',
    '--dev': 'none',
    '-P': 'none',
    '--peer': 'none',
    '-O': 'none',
    '--optional': 'none',
    '-E': 'none',
    '--exact': 'none',
    '-T': 'none',
    '--tilde': 'none',
    '-A': 'none',
    '--audit': 'none',
    '-C': 'none',
    '--check-files': 'none',
    '--flat': 'none',
    '--ignore-optional': 'none',
    '--ignore-platform': 'none',
    '--ignore-scripts': 'none',
    '--no-bin-links': 'none',
    '--no-lockfile': 'none',
    '--production': 'none',
    '--pure-lockfile': 'none',
    '--focus': 'none',
    '--frozen-lockfile': 'none',
    '--link-duplicates': 'none',
}

# jq safe flags
JQ_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-c': 'none',
    '--compact-output': 'none',
    '-r': 'none',
    '--raw-output': 'none',
    '-R': 'none',
    '--raw-input': 'none',
    '-s': 'none',
    '--slurp': 'none',
    '-n': 'none',
    '--null-input': 'none',
    '-e': 'none',
    '--exit-status': 'none',
    '-f': 'string',
    '--from-file': 'string',
    '-L': 'string',
    '--rawfile': 'string',
    '--jsonargs': 'none',
    '--argjson': 'string',
    '--arg': 'string',
    '--args': 'none',
    '--sort-keys': 'none',
    '-S': 'none',
    '--tab': 'none',
    '--indent': 'number',
    '-j': 'none',
    '--join-output': 'none',
    '--raw-output0': 'none',
    '--stream': 'none',
    '--seq': 'none',
    '--unbuffered': 'none',
    '--monochrome-output': 'none',
    '-M': 'none',
    '--color-output': 'none',
    '-C': 'none',
    '--ascii-output': 'none',
    '-a': 'none',
    '--yaml-input': 'none',
    '--yaml-output': 'none',
    '--slurpfile': 'string',
    '--jsonargs': 'none',
    '--debug-trace': 'none',
    '-h': 'none',
    '--help': 'none',
    '--version': 'none',
    '-V': 'none',
}

# touch safe flags (commonly used to check/update timestamps)
TOUCH_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-a': 'none',
    '--time': 'string',
    '-c': 'none',
    '--no-create': 'none',
    '-d': 'string',
    '--date': 'string',
    '-f': 'none',
    '-h': 'none',
    '--no-dereference': 'none',
    '-m': 'none',
    '-r': 'string',
    '--reference': 'string',
    '-t': 'string',
    '--help': 'none',
    '--version': 'none',
}

# echo safe flags
ECHO_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-n': 'none',
    '-e': 'none',
    '-E': 'none',
    '--help': 'none',
    '--version': 'none',
}

# test/[ safe flags (file tests and string comparisons)
TEST_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-e': 'none',
    '-f': 'none',
    '-d': 'none',
    '-L': 'none',
    '-l': 'none',
    '-r': 'none',
    '-w': 'none',
    '-x': 'none',
    '-s': 'none',
    '-n': 'none',
    '-z': 'none',
    '-p': 'none',
    '-S': 'none',
    '-b': 'none',
    '-c': 'none',
    '-g': 'none',
    '-k': 'none',
    '-u': 'none',
    '-t': 'none',
    '-o': 'none',
    '-G': 'none',
    '-N': 'none',
    '-O': 'none',
    '-h': 'none',
    '--help': 'none',
}

# printenv/env safe flags
PRINTENV_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-0': 'none',
    '--null': 'none',
    '--help': 'none',
    '--version': 'none',
}

# uname safe flags
UNAME_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-a': 'none',
    '--all': 'none',
    '-s': 'none',
    '--kernel-name': 'none',
    '-n': 'none',
    '--nodename': 'none',
    '-r': 'none',
    '--kernel-release': 'none',
    '-v': 'none',
    '--kernel-version': 'none',
    '-m': 'none',
    '--machine': 'none',
    '-p': 'none',
    '--processor': 'none',
    '-i': 'none',
    '--hardware-platform': 'none',
    '-o': 'none',
    '--operating-system': 'none',
    '--help': 'none',
    '--version': 'none',
}

# date safe flags
DATE_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-d': 'string',
    '--date': 'string',
    '-f': 'string',
    '--file': 'string',
    '-r': 'string',
    '--reference': 'string',
    '-u': 'none',
    '--utc': 'none',
    '--universal': 'none',
    '-I': 'string',
    '--iso-8601': 'string',
    '-R': 'none',
    '--rfc-2822': 'none',
    '--rfc-email': 'none',
    '--rfc-3339': 'string',
    '-s': 'string',  # --set intentionally allowed (some read uses)
    '--set': 'string',
    '--help': 'none',
    '--version': 'none',
}

# basename/dirname safe flags
BASENAME_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-a': 'none',
    '--multiple': 'none',
    '-s': 'string',
    '--suffix': 'string',
    '-z': 'none',
    '--zero': 'none',
    '--help': 'none',
    '--version': 'none',
}

# realpath safe flags
REALPATH_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-e': 'none',
    '--canonicalize-existing': 'none',
    '-m': 'none',
    '--canonicalize-missing': 'none',
    '-L': 'none',
    '--logical': 'none',
    '-P': 'none',
    '--physical': 'none',
    '-q': 'none',
    '--quiet': 'none',
    '-s': 'none',
    '--strip': 'none',
    '--no-symlinks': 'none',
    '-z': 'none',
    '--zero': 'none',
    '--help': 'none',
    '--version': 'none',
}

# readlink safe flags
READLINK_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-f': 'none',
    '--canonicalize': 'none',
    '-e': 'none',
    '--canonicalize-existing': 'none',
    '-m': 'none',
    '--canonicalize-missing': 'none',
    '-n': 'none',
    '--no-newline': 'none',
    '-q': 'none',
    '--quiet': 'none',
    '-s': 'none',
    '--silent': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '-z': 'none',
    '--zero': 'none',
    '--help': 'none',
    '--version': 'none',
}

# printf safe flags
PRINTF_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--help': 'none',
    '--version': 'none',
}

# id safe flags
ID_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-a': 'none',
    '-g': 'none',
    '--group': 'none',
    '-G': 'none',
    '--groups': 'none',
    '-n': 'none',
    '--name': 'none',
    '-r': 'none',
    '--real': 'none',
    '-u': 'none',
    '--user': 'none',
    '-z': 'none',
    '--zero': 'none',
    '--help': 'none',
    '--version': 'none',
}

# whoami safe flags
WHOAMI_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--help': 'none',
    '--version': 'none',
}

# groups safe flags
GROUPS_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--help': 'none',
    '--version': 'none',
}

# stdbuf safe flags
STDBUF_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-i': 'string',
    '--input': 'string',
    '-o': 'string',
    '--output': 'string',
    '-e': 'string',
    '--error': 'string',
    '--help': 'none',
    '--version': 'none',
}

# timeout safe flags
TIMEOUT_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-s': 'string',
    '--signal': 'string',
    '--foreground': 'none',
    '-k': 'string',
    '--kill-after': 'string',
    '-p': 'none',
    '--preserve-status': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '--help': 'none',
    '--version': 'none',
}

# env safe flags (read-only mode: no modification)
ENV_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-0': 'none',
    '--null': 'none',
    '-u': 'string',
    '--unset': 'string',
    '--ignore-environment': 'none',
    '-i': 'none',
    '--help': 'none',
    '--version': 'none',
    '-v': 'none',
    '--debug': 'none',
    '-S': 'string',
    '--split-string': 'string',
    '-C': 'string',
    '--chdir': 'string',
}

# xargs safe flags
XARGS_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-n': 'number',
    '--max-args': 'number',
    '-P': 'number',
    '--max-procs': 'number',
    '-L': 'number',
    '--max-lines': 'number',
    '-s': 'number',
    '--max-chars': 'number',
    '-x': 'none',
    '--exit': 'none',
    '-r': 'none',
    '--no-run-if-empty': 'none',
    '-0': 'none',
    '--null': 'none',
    '-d': 'char',
    '--delimiter': 'char',
    '-t': 'none',
    '--verbose': 'none',
    '-I': 'string',
    '--replace': 'string',
    '-i': 'string',  # deprecated form of -I
    '-a': 'string',
    '--arg-file': 'string',
    '-E': 'string',
    '--eof': 'string',
    '-e': 'string',  # deprecated form of -E
    '--process-slot-var': 'string',
    '--open-tty': 'none',
    '-o': 'none',
    '-p': 'none',
    '--interactive': 'none',
    '--show-limits': 'none',
    '--help': 'none',
    '--version': 'none',
}

# wsl safe flags (Windows Subsystem for Linux)
WSL_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-e': 'none',
    '--exec': 'none',
    '-l': 'none',
    '--list': 'none',
    '-v': 'none',
    '--verbose': 'none',
    '--help': 'none',
    '--version': 'none',
    '--status': 'none',
    '--system': 'none',
    '--user': 'string',
    '-u': 'string',
    '-d': 'string',
    '--distribution': 'string',
    '--running': 'none',
    '--quiet': 'none',
    '-q': 'none',
    '--set-default-version': 'string',
}

# openssl safe flags (info/digest only)
OPENSSL_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-help': 'none',
    '-version': 'none',
    '-md': 'string',
    '-dgst': 'string',
    '-r': 'none',
    '-hex': 'none',
    '-binary': 'none',
    '-out': 'string',
    '-in': 'string',
    '-noout': 'none',
    '-text': 'none',
    '-inform': 'string',
    '-outform': 'string',
    '-passin': 'string',
    '-passout': 'string',
    '-engine': 'string',
    '-rand': 'string',
    '-writerand': 'string',
    '-list': 'none',
    '-v': 'none',
    '-quiet': 'none',
}

# nmap safe flags (network discovery — restricted)
NMAP_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-sn': 'none',
    '-Pn': 'none',
    '-n': 'none',
    '-v': 'none',
    '-vv': 'none',
    '-vvv': 'none',
    '-p': 'string',
    '-p-': 'none',
    '--top-ports': 'number',
    '-oN': 'string',
    '-oX': 'string',
    '-oG': 'string',
    '-oA': 'string',
    '-T': 'string',
    '--open': 'none',
    '-F': 'none',
    '--version': 'none',
    '-V': 'none',
    '-h': 'none',
    '--help': 'none',
    '--reason': 'none',
    '--iflist': 'none',
    '--traceroute': 'none',
    '-6': 'none',
    '-A': 'none',
    '-iL': 'string',
    '-iR': 'number',
    '--excludefile': 'string',
    '--exclude': 'string',
    '--randomize-hosts': 'none',
    '-sV': 'none',
    '--version-intensity': 'number',
    '--version-light': 'none',
    '--version-all': 'none',
    '--version-trace': 'none',
    '-O': 'none',
    '--osscan-limit': 'none',
    '--osscan-guess': 'none',
    '--max-os-tries': 'number',
    '--fuzzy': 'none',
    '--disable-arp-ping': 'none',
    '--privileged': 'none',
    '--unprivileged': 'none',
    '--servicedb': 'string',
    '--versiondb': 'string',
    '--send-eth': 'none',
    '--send-ip': 'none',
    '--allports': 'none',
    '--min-rtt-timeout': 'string',
    '--max-rtt-timeout': 'string',
    '--initial-rtt-timeout': 'string',
    '--max-retries': 'number',
    '--host-timeout': 'string',
    '--scan-delay': 'string',
    '--max-scan-delay': 'string',
    '--min-rate': 'number',
    '--max-rate': 'number',
    '--min-parallelism': 'number',
    '--max-parallelism': 'number',
    '--min-hostgroup': 'number',
    '--max-hostgroup': 'number',
}

# pnpm safe flags
PNPM_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--version': 'none',
    '-v': 'none',
    '--help': 'none',
    '-h': 'none',
    '-r': 'none',
    '--recursive': 'none',
    '--filter': 'string',
    '-F': 'string',
    '--workspace-root': 'none',
    '-w': 'none',
    '--json': 'none',
    '--long': 'none',
    '-l': 'none',
    '--parseable': 'none',
    '-p': 'none',
    '--global': 'none',
    '-g': 'none',
    '--color': 'none',
    '--no-color': 'none',
    '--depth': 'number',
    '--dev': 'none',
    '-D': 'none',
    '--prod': 'none',
    '-P': 'none',
    '--optional': 'none',
    '--production': 'none',
    '--only': 'string',
    '--silent': 'none',
    '--reporter': 'string',
    '--aggregate-output': 'none',
    '--stream': 'none',
    '--parallel': 'none',
    '--no-bail': 'none',
    '--sort': 'none',
    '--no-sort': 'none',
}

# bun safe flags
BUN_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--version': 'none',
    '-v': 'none',
    '--help': 'none',
    '-h': 'none',
    '--revision': 'none',
    '-r': 'none',
    '--json': 'none',
    '--no-progress': 'none',
    '--verbose': 'none',
    '--silent': 'none',
    '--global': 'none',
    '-g': 'none',
    '--cwd': 'string',
    '--env-file': 'string',
    '--extension-order': 'string',
    '--jsx-factory': 'string',
    '--jsx-fragment': 'string',
    '--jsx-import-source': 'string',
    '--jsx-runtime': 'string',
    '--conditions': 'string',
    '-e': 'string',
    '--eval': 'string',
    '--main-fields': 'string',
    '--no-install': 'none',
    '--prefer-offline': 'none',
    '--prefer-latest': 'none',
    '--production': 'none',
    '--frozen-lockfile': 'none',
    '--exact': 'none',
    '--no-save': 'none',
    '--hot': 'none',
    '--watch': 'none',
    '--smol': 'none',
    '--logLevel': 'string',
    '--log-level': 'string',
    '-p': 'none',
    '--print': 'none',
}

# cargo safe flags
CARGO_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-v': 'none',
    '--verbose': 'none',
    '-q': 'none',
    '--quiet': 'none',
    '--color': 'string',
    '--frozen': 'none',
    '--locked': 'none',
    '--offline': 'none',
    '--config': 'string',
    '-Z': 'string',
    '-h': 'none',
    '--help': 'none',
    '--version': 'none',
    '-V': 'none',
    '--list': 'none',
    '--explain': 'string',
    '--message-format': 'string',
    '--manifest-path': 'string',
    '--workspace': 'none',
    '-p': 'string',
    '--package': 'string',
    '--exclude': 'string',
    '--all': 'none',
    '--all-targets': 'none',
    '--lib': 'none',
    '--bin': 'string',
    '--bins': 'none',
    '--example': 'string',
    '--examples': 'none',
    '--test': 'string',
    '--tests': 'none',
    '--bench': 'string',
    '--benches': 'none',
    '--target': 'string',
    '--target-dir': 'string',
    '--features': 'string',
    '-F': 'string',
    '--all-features': 'none',
    '--no-default-features': 'none',
    '--profile': 'string',
    '--release': 'none',
    '-r': 'none',
    '--jobs': 'number',
    '-j': 'number',
    '--keep-going': 'none',
    '--no-run': 'none',
    '--no-fail-fast': 'none',
    '--future-incompat-report': 'none',
    '--depth': 'number',
    '--prefix': 'string',
    '--invert': 'none',
    '--duplicates': 'none',
    '--charset': 'string',
    '--format': 'string',
    '--graph-features': 'none',
    '--normal': 'none',
    '--build': 'none',
    '--dev': 'none',
    '--no-dedupe': 'none',
    '--sort': 'none',
    '--ignore-rust-version': 'none',
    '--unit-graph': 'none',
    '--timings': 'none',
}

# go safe flags
GO_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-v': 'none',
    '-n': 'none',
    '-x': 'none',
    '-work': 'none',
    '-race': 'none',
    '-msan': 'none',
    '-asan': 'none',
    '-o': 'string',
    '-p': 'number',
    '-buildmode': 'string',
    '-mod': 'string',
    '-modfile': 'string',
    '-modcacherw': 'none',
    '-buildvcs': 'string',
    '-toolexec': 'string',
    '-json': 'none',
    '-u': 'none',
    '-t': 'none',
    '-e': 'none',
    '-f': 'string',
    '-test.v': 'none',
    '-test.bench': 'string',
    '-test.benchtime': 'string',
    '-test.benchmem': 'none',
    '-test.count': 'number',
    '-test.run': 'string',
    '-test.timeout': 'string',
    '-test.parallel': 'number',
    '-test.cpu': 'string',
    '-test.short': 'none',
    '-test.shuffle': 'string',
    '-cpuprofile': 'string',
    '-memprofile': 'string',
    '-blockprofile': 'string',
    '-mutexprofile': 'string',
    '-trace': 'string',
    '-coverprofile': 'string',
    '-coverpkg': 'string',
    '-covermode': 'string',
    '-tags': 'string',
    '-ldflags': 'string',
    '-gcflags': 'string',
    '-asmflags': 'string',
    '-overlay': 'string',
    '-trimpath': 'none',
    '-vet': 'string',
    '-short': 'none',
    '-timeout': 'string',
    '-all': 'none',
    '-m': 'none',
    '-explain': 'string',
    '-reuse': 'string',
    '-retract': 'string',
    '-why': 'none',
    '-d': 'none',
}

# java safe flags
JAVA_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-version': 'none',
    '--version': 'none',
    '-showversion': 'none',
    '--show-version': 'none',
    '-XshowSettings': 'none',
    '--show-module-resolution': 'none',
    '-verbose': 'string',
    '-cp': 'string',
    '--class-path': 'string',
    '-classpath': 'string',
    '--module-path': 'string',
    '-p': 'string',
    '--upgrade-module-path': 'string',
    '--add-modules': 'string',
    '--list-modules': 'none',
    '--describe-module': 'string',
    '-d': 'string',
    '--add-reads': 'string',
    '--add-exports': 'string',
    '--add-opens': 'string',
    '--permit-illegal-access': 'none',
    '--illegal-access': 'string',
    '-ea': 'none',
    '--enable-assertions': 'none',
    '-da': 'none',
    '--disable-assertions': 'none',
    '-esa': 'none',
    '--enable-system-assertions': 'none',
    '-dsa': 'none',
    '--disable-system-assertions': 'none',
    '-help': 'none',
    '-?': 'none',
    '-X': 'none',
    '-Xmx': 'string',
    '-Xms': 'string',
    '-Xss': 'string',
    '-jar': 'string',
    '-noverify': 'none',
    '-verify': 'none',
    '-server': 'none',
    '-client': 'none',
    '-D': 'string',  # system property -Dkey=value
}

# php safe flags
PHP_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-v': 'none',
    '--version': 'none',
    '-i': 'none',
    '--info': 'none',
    '-m': 'none',
    '--modules': 'none',
    '-r': 'string',
    '--run': 'string',
    '-f': 'string',
    '--file': 'string',
    '-l': 'none',
    '--syntax-check': 'none',
    '-c': 'string',
    '--php-ini': 'string',
    '-n': 'none',
    '--no-php-ini': 'none',
    '-d': 'string',
    '--define': 'string',
    '-e': 'none',
    '--profile-info': 'none',
    '-h': 'none',
    '--help': 'none',
    '-s': 'none',
    '--syntax-highlight': 'none',
    '-z': 'string',
    '--zend-extension': 'string',
    '-T': 'number',
    '--timing': 'number',
    '-R': 'string',
    '--process-code': 'string',
    '-B': 'string',
    '--process-begin': 'string',
    '-E': 'string',
    '--process-end': 'string',
    '-H': 'none',
    '--hide-args': 'none',
    '-w': 'none',
    '--strip': 'none',
    '-a': 'none',
    '--interactive': 'none',
    '-S': 'string',
    '--server': 'string',
    '-t': 'string',
    '--docroot': 'string',
    '-F': 'string',
    '--process-file': 'string',
    '-q': 'none',
    '--no-header': 'none',
}

# ruby safe flags
RUBY_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-v': 'none',
    '--version': 'none',
    '--verbose': 'none',
    '-c': 'none',
    '--check': 'none',
    '-d': 'none',
    '--debug': 'none',
    '-h': 'none',
    '--help': 'none',
    '-i': 'string',
    '-I': 'string',
    '-K': 'string',
    '-l': 'none',
    '-n': 'none',
    '-p': 'none',
    '-r': 'string',
    '--require': 'string',
    '-s': 'none',
    '-S': 'none',
    '-T': 'string',
    '-u': 'none',
    '-w': 'none',
    '-W': 'string',
    '-x': 'string',
    '-X': 'string',
    '-e': 'string',
    '--external-encoding': 'string',
    '--internal-encoding': 'string',
    '--encoding': 'string',
    '-E': 'string',
    '--enable': 'string',
    '--disable': 'string',
    '--jit': 'none',
    '--jit-warnings': 'none',
    '--jit-debug': 'none',
    '--jit-wait': 'none',
    '--jit-save-temps': 'none',
    '--jit-verbose': 'number',
    '--jit-max-cache': 'number',
    '--jit-min-calls': 'number',
    '--dump': 'string',
    '--parser': 'string',
    '--profile': 'string',
    '--parser-options': 'string',
}

# swift safe flags
SWIFT_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-v': 'none',
    '--version': 'none',
    '-version': 'none',
    '-help': 'none',
    '--help': 'none',
    '-h': 'none',
    '--show-bin-path': 'none',
    '--package-path': 'string',
    '-c': 'string',
    '--configuration': 'string',
    '--triple': 'string',
    '--sdk': 'string',
    '--toolchain': 'string',
    '--jobs': 'number',
    '-j': 'number',
    '--enable-code-coverage': 'none',
    '--enable-test-discovery': 'none',
    '--sanitize': 'string',
    '--build-tests': 'none',
    '--verbose': 'none',
    '--quiet': 'none',
    '-q': 'none',
    '--disable-package-manifest-caching': 'none',
    '--disable-automatic-resolution': 'none',
    '--skip-update': 'none',
    '--arch': 'string',
    '-Xswiftc': 'string',
    '-Xcc': 'string',
    '-Xlinker': 'string',
    '--show-bin-path': 'none',
    '--build-path': 'string',
    '--manifest-path': 'string',
    '--scratch-path': 'string',
}

# mvn safe flags
MVN_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-v': 'none',
    '--version': 'none',
    '-h': 'none',
    '--help': 'none',
    '-q': 'none',
    '--quiet': 'none',
    '-X': 'none',
    '--debug': 'none',
    '-N': 'none',
    '--non-recursive': 'none',
    '-T': 'string',
    '--threads': 'string',
    '-o': 'none',
    '--offline': 'none',
    '-U': 'none',
    '--update-snapshots': 'none',
    '-pl': 'string',
    '--projects': 'string',
    '-am': 'none',
    '--also-make': 'none',
    '-amd': 'none',
    '--also-make-dependents': 'none',
    '-f': 'string',
    '--file': 'string',
    '-P': 'string',
    '--activate-profiles': 'string',
    '-D': 'string',
    '-fae': 'none',
    '--fail-at-end': 'none',
    '-ff': 'none',
    '--fail-fast': 'none',
    '-fn': 'none',
    '--fail-never': 'none',
    '-ntp': 'none',
    '--no-transfer-progress': 'none',
    '-B': 'none',
    '--batch-mode': 'none',
    '--errors': 'none',
    '-e': 'none',
    '--no-plugin-registry': 'none',
    '--non-recursive': 'none',
    '--resume-from': 'string',
    '-rf': 'string',
    '--strict-checksums': 'none',
    '-C': 'none',
    '--lax-checksums': 'none',
    '-c': 'none',
    '--settings': 'string',
    '-s': 'string',
    '--toolchains': 'string',
    '-t': 'string',
    '--global-settings': 'string',
    '-gs': 'string',
    '--global-toolchains': 'string',
    '-gt': 'string',
    '--log-file': 'string',
    '-l': 'string',
    '--encrypt-master-password': 'string',
    '--encrypt-password': 'string',
    '--legacy-local-repository': 'none',
    '--llr': 'none',
    '-nsu': 'none',
    '--no-snapshot-updates': 'none',
}

# gradle safe flags
GRADLE_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-v': 'none',
    '--version': 'none',
    '-h': 'none',
    '--help': 'none',
    '-q': 'none',
    '--quiet': 'none',
    '-w': 'none',
    '--warn': 'none',
    '-i': 'none',
    '--info': 'none',
    '-d': 'none',
    '--debug': 'none',
    '-s': 'none',
    '--stacktrace': 'none',
    '-S': 'none',
    '--full-stacktrace': 'none',
    '-p': 'string',
    '--project-dir': 'string',
    '-b': 'string',
    '--build-file': 'string',
    '-c': 'string',
    '--settings-file': 'string',
    '-g': 'string',
    '--gradle-user-home': 'string',
    '-x': 'string',
    '--exclude-task': 'string',
    '-a': 'none',
    '--no-rebuild': 'none',
    '-m': 'none',
    '--dry-run': 'none',
    '-n': 'none',
    '--dependency-verification': 'string',
    '-F': 'string',
    '-r': 'none',
    '--rerun-tasks': 'none',
    '--continue': 'none',
    '--parallel': 'none',
    '--max-workers': 'number',
    '--priority': 'string',
    '-P': 'string',
    '--project-prop': 'string',
    '--console': 'string',
    '--no-color': 'none',
    '--color': 'none',
    '--no-daemon': 'none',
    '--daemon': 'none',
    '--foreground': 'none',
    '--status': 'none',
    '--stop': 'none',
    '--write-locks': 'none',
    '--update-locks': 'string',
    '--no-build-cache': 'none',
    '--build-cache': 'none',
    '--tasks': 'none',
    '--properties': 'none',
    '--dependencies': 'none',
    '--dependency-insight': 'none',
    '--configuration': 'string',
    '--scan': 'none',
    '--no-scan': 'none',
    '--watch-fs': 'none',
    '--no-watch-fs': 'none',
    '--configure-on-demand': 'none',
    '--no-configure-on-demand': 'none',
    '--init-script': 'string',
    '-I': 'string',
    '--export-keys': 'none',
    '--keyring': 'string',
    '-t': 'none',
    '--continuous': 'none',
}

# cmake safe flags
CMAKE_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '--version': 'none',
    '-version': 'none',
    '--help': 'none',
    '-help': 'none',
    '-h': 'none',
    '-H': 'none',
    '-L': 'none',
    '-LA': 'none',
    '-LH': 'none',
    '-LAH': 'none',
    '-N': 'none',
    '-U': 'string',
    '--graphviz': 'string',
    '--system-information': 'string',
    '-Q': 'none',
    '--log-level': 'string',
    '--log-context': 'none',
    '--debug-trycompile': 'none',
    '--debug-output': 'none',
    '--trace': 'none',
    '--trace-expand': 'none',
    '--trace-format': 'string',
    '--trace-source': 'string',
    '--trace-redirect': 'string',
    '--warn-uninitialized': 'none',
    '--warn-unused-vars': 'none',
    '--no-warn-unused-cli': 'none',
    '--check-system-vars': 'none',
    '--profiling-output': 'string',
    '--profiling-format': 'string',
    '-P': 'string',
    '-E': 'string',
    '-G': 'string',
    '-T': 'string',
    '-A': 'string',
    '-D': 'string',
    '-B': 'string',
    '-S': 'string',
    '-C': 'string',
}

# env/set/export (pure listing)
ENV_LIST_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-0': 'none',
    '--null': 'none',
    '--help': 'none',
    '--version': 'none',
}

# shasum / md5sum / sha256sum safe flags
CHECKSUM_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-a': 'string',
    '--algorithm': 'string',
    '-b': 'none',
    '--binary': 'none',
    '-c': 'none',
    '--check': 'none',
    '--ignore-missing': 'none',
    '--quiet': 'none',
    '-q': 'none',
    '--status': 'none',
    '--strict': 'none',
    '-t': 'none',
    '--text': 'none',
    '-w': 'none',
    '--warn': 'none',
    '-0': 'none',
    '--zero': 'none',
    '--tag': 'none',
    '-p': 'none',
    '--portable': 'none',
    '-U': 'none',
    '--universal': 'none',
    '--help': 'none',
    '--version': 'none',
    '-v': 'none',
}

# file safe flags
FILE_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-b': 'none',
    '--brief': 'none',
    '-i': 'none',
    '--mime': 'none',
    '--mime-type': 'none',
    '--mime-encoding': 'none',
    '-e': 'string',
    '--exclude': 'string',
    '--exclude-quiet': 'none',
    '-f': 'string',
    '--files-from': 'string',
    '-F': 'string',
    '--separator': 'string',
    '-k': 'none',
    '--keep-going': 'none',
    '-L': 'none',
    '--dereference': 'none',
    '-m': 'string',
    '--magic-file': 'string',
    '-M': 'none',
    '-n': 'none',
    '--no-buffer': 'none',
    '-N': 'none',
    '-0': 'none',
    '--print0': 'none',
    '-p': 'none',
    '--preserve-date': 'none',
    '-r': 'none',
    '--raw': 'none',
    '-s': 'none',
    '--special-files': 'none',
    '-v': 'none',
    '--version': 'none',
    '-z': 'none',
    '--uncompress': 'none',
    '-Z': 'none',
    '--uncompress-noreport': 'none',
    '-d': 'none',
    '--debug': 'none',
    '-c': 'none',
    '--checking-printout': 'none',
    '-I': 'none',
    '-h': 'none',
    '--help': 'none',
}

# stat safe flags
STAT_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-L': 'none',
    '--dereference': 'none',
    '-f': 'none',
    '--file-system': 'none',
    '-c': 'string',
    '--format': 'string',
    '-t': 'none',
    '--terse': 'none',
    '--printf': 'string',
    '-x': 'none',
    '--extended': 'none',
    '--help': 'none',
    '--version': 'none',
}

# cut safe flags
CUT_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-b': 'string',
    '--bytes': 'string',
    '-c': 'string',
    '--characters': 'string',
    '-d': 'char',
    '--delimiter': 'char',
    '-f': 'string',
    '--fields': 'string',
    '-n': 'none',
    '--complement': 'none',
    '--output-delimiter': 'string',
    '-s': 'none',
    '--only-delimited': 'none',
    '-z': 'none',
    '--zero-terminated': 'none',
    '--help': 'none',
    '--version': 'none',
}

# tr safe flags
TR_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-c': 'none',
    '--complement': 'none',
    '-C': 'none',
    '-d': 'none',
    '--delete': 'none',
    '-s': 'none',
    '--squeeze-repeats': 'none',
    '-t': 'none',
    '--truncate-set1': 'none',
    '--help': 'none',
    '--version': 'none',
}

# uniq safe flags
UNIQ_SAFE_FLAGS: Dict[str, FlagArgType] = {
    '-c': 'none',
    '--count': 'none',
    '-d': 'none',
    '--repeated': 'none',
    '-D': 'none',
    '-f': 'number',
    '--skip-fields': 'number',
    '-i': 'none',
    '--ignore-case': 'none',
    '-s': 'number',
    '--skip-chars': 'number',
    '-u': 'none',
    '--unique': 'none',
    '-w': 'number',
    '--check-chars': 'number',
    '-z': 'none',
    '--zero-terminated': 'none',
    '--group': 'string',
    '--all-repeated': 'string',
    '--help': 'none',
    '--version': 'none',
}

# env safe flags alias
PRINTENV_SAFE_FLAGS.update(ENV_LIST_SAFE_FLAGS)

# ---------------------------------------------------------------------------
# Command allowlist builder
# ---------------------------------------------------------------------------

# Sed callback: block -i (in-place edit) when not empty-suffix dry-run
def _sed_is_dangerous(_raw_command: str, args: List[str]) -> bool:
    """Block sed -i (in-place edit without suffix = data mutation)."""
    for i, arg in enumerate(args):
        if arg in ('-i', '--in-place') or (arg.startswith('-i') and arg != '-i'):
            # -i with empty suffix is destructive
            if arg == '-i':
                # Check if next arg is the suffix (an expression would start with /)
                next_arg = args[i + 1] if i + 1 < len(args) else None
                if next_arg and not next_arg.startswith('-') and not next_arg.startswith('/'):
                    continue  # has a backup suffix — still read
                return True  # no suffix = in-place edit = destructive
    return False


# curl callback: block write-mode flags (POST, PUT, DELETE, UPLOAD)
def _curl_is_dangerous(_raw_command: str, args: List[str]) -> bool:
    """Block curl in write-mode (POST/PUT/DELETE/upload)."""
    WRITE_FLAGS = {
        '-X', '--request',
        '-d', '--data', '--data-raw', '--data-binary', '--data-urlencode', '--data-ascii',
        '-T', '--upload-file',
        '-F', '--form', '--form-string',
        '--json',
        '--oauth2-bearer',  # modifies request type
        '--ntlm',           # triggers auth handshake
        '--digest',
        '--negotiate',
        '--anyauth',
        '-u', '--user',     # credentials for potentially mutating requests
        '--netrc', '--netrc-file', '--netrc-optional',
        '--krb',
        '--proxy-header',
        '--proxy-user', '-U',
    }
    for arg in args:
        flag = arg.split('=')[0] if '=' in arg else arg
        if flag in WRITE_FLAGS:
            return True
        # -X POST / -XPOST
        if flag == '-X' or arg.startswith('-X'):
            method = arg[2:] if arg.startswith('-X') and len(arg) > 2 else (args[args.index(arg) + 1] if args.index(arg) + 1 < len(args) else '')
            if method.upper() in ('POST', 'PUT', 'DELETE', 'PATCH'):
                return True
    return False


# find callback: block exec/execdir/delete actions
def _find_is_dangerous(_raw_command: str, args: List[str]) -> bool:
    """Block find -exec, -execdir, -delete (mutating actions)."""
    DANGEROUS_ACTIONS = {'-exec', '-execdir', '-delete', '-ok', '-okdir'}
    return any(arg in DANGEROUS_ACTIONS for arg in args)


# xargs callback: check target command is safe
def _xargs_is_dangerous(_raw_command: str, args: List[str]) -> bool:
    """
    Block xargs from calling dangerous commands.
    xargs can only call commands from a limited safe list.
    """
    # Find the target command (first non-flag arg after xargs flags)
    SAFE_XARGS_TARGETS = {
        'echo', 'cat', 'head', 'tail', 'wc', 'grep', 'ls', 'find', 'file',
        'stat', 'du', 'df', 'cut', 'sort', 'uniq', 'tr', 'printf', 'basename',
        'dirname', 'realpath', 'readlink', 'diff', 'git', 'python', 'python3',
        'node', 'jq', 'rg', 'md5sum', 'sha256sum', 'shasum',
    }
    i = 0
    while i < len(args):
        arg = args[i]
        if not arg:
            i += 1
            continue
        if arg == '--':
            i += 1
            if i < len(args):
                target = args[i]
                return target not in SAFE_XARGS_TARGETS
            return True  # nothing after --

        if arg.startswith('-'):
            # Skip known xargs flags that take arguments
            if arg in ('-n', '--max-args', '-P', '--max-procs', '-L', '--max-lines',
                       '-s', '--max-chars', '-d', '--delimiter', '-I', '--replace',
                       '-i', '-a', '--arg-file', '-E', '--eof', '-e',
                       '--process-slot-var'):
                i += 2
            else:
                i += 1
        else:
            # Found target command
            return arg not in SAFE_XARGS_TARGETS
    return False  # No target command found — xargs with no command reads stdin


def _get_command_allowlist() -> Dict[str, ExternalCommandConfig]:
    """Build the complete command allowlist for BashTool."""
    allowlist: Dict[str, ExternalCommandConfig] = {}

    # Add git commands from shared module
    allowlist.update(GIT_READ_ONLY_COMMANDS)

    # Add gh commands
    allowlist.update(GH_READ_ONLY_COMMANDS)

    # Add docker commands
    allowlist.update(DOCKER_READ_ONLY_COMMANDS)

    # Add ripgrep
    allowlist.update(RIPGREP_READ_ONLY_COMMANDS)

    # Add pyright
    allowlist.update(PYRIGHT_READ_ONLY_COMMANDS)

    # Add local BashTool-specific commands
    local_commands: Dict[str, ExternalCommandConfig] = {
        'cat': ExternalCommandConfig(safe_flags=CAT_SAFE_FLAGS),
        'head': ExternalCommandConfig(safe_flags=HEAD_SAFE_FLAGS),
        'tail': ExternalCommandConfig(safe_flags=TAIL_SAFE_FLAGS),
        'ls': ExternalCommandConfig(safe_flags=LS_SAFE_FLAGS),
        'wc': ExternalCommandConfig(safe_flags=WC_SAFE_FLAGS),
        'echo': ExternalCommandConfig(safe_flags=ECHO_SAFE_FLAGS),
        'grep': ExternalCommandConfig(
            safe_flags=GREP_SAFE_FLAGS,
            respects_double_dash=True,
        ),
        'egrep': ExternalCommandConfig(safe_flags=GREP_SAFE_FLAGS),
        'fgrep': ExternalCommandConfig(safe_flags=GREP_SAFE_FLAGS),
        'find': ExternalCommandConfig(
            safe_flags=FIND_SAFE_FLAGS,
            additional_command_is_dangerous_callback=_find_is_dangerous,
        ),
        'diff': ExternalCommandConfig(safe_flags=DIFF_SAFE_FLAGS),
        'sort': ExternalCommandConfig(safe_flags=SORT_SAFE_FLAGS),
        'sed': ExternalCommandConfig(
            safe_flags=SED_SAFE_FLAGS,
            additional_command_is_dangerous_callback=_sed_is_dangerous,
        ),
        'awk': ExternalCommandConfig(safe_flags=AWK_SAFE_FLAGS),
        'gawk': ExternalCommandConfig(safe_flags=AWK_SAFE_FLAGS),
        'nawk': ExternalCommandConfig(safe_flags=AWK_SAFE_FLAGS),
        'mawk': ExternalCommandConfig(safe_flags=AWK_SAFE_FLAGS),
        'curl': ExternalCommandConfig(
            safe_flags=CURL_SAFE_FLAGS,
            additional_command_is_dangerous_callback=_curl_is_dangerous,
        ),
        'wget': ExternalCommandConfig(safe_flags=WGET_SAFE_FLAGS),
        'ps': ExternalCommandConfig(safe_flags=PS_SAFE_FLAGS),
        'netstat': ExternalCommandConfig(safe_flags=NETSTAT_SAFE_FLAGS),
        'hostname': ExternalCommandConfig(safe_flags=HOSTNAME_SAFE_FLAGS),
        'du': ExternalCommandConfig(safe_flags=DU_SAFE_FLAGS),
        'df': ExternalCommandConfig(safe_flags=DF_SAFE_FLAGS),
        'tar': ExternalCommandConfig(safe_flags=TAR_SAFE_FLAGS),
        'unzip': ExternalCommandConfig(safe_flags=UNZIP_SAFE_FLAGS),
        'which': ExternalCommandConfig(safe_flags=WHICH_SAFE_FLAGS),
        'make': ExternalCommandConfig(safe_flags=MAKE_SAFE_FLAGS),
        'tree': ExternalCommandConfig(safe_flags=TREE_SAFE_FLAGS),
        'lsof': ExternalCommandConfig(safe_flags=LSOF_SAFE_FLAGS),
        'pip': ExternalCommandConfig(safe_flags=PIP_SAFE_FLAGS),
        'pip3': ExternalCommandConfig(safe_flags=PIP_SAFE_FLAGS),
        'npm': ExternalCommandConfig(safe_flags=NPM_SAFE_FLAGS),
        'yarn': ExternalCommandConfig(safe_flags=YARN_SAFE_FLAGS),
        'pnpm': ExternalCommandConfig(safe_flags=PNPM_SAFE_FLAGS),
        'bun': ExternalCommandConfig(safe_flags=BUN_SAFE_FLAGS),
        'jq': ExternalCommandConfig(safe_flags=JQ_SAFE_FLAGS),
        'touch': ExternalCommandConfig(safe_flags=TOUCH_SAFE_FLAGS),
        'date': ExternalCommandConfig(safe_flags=DATE_SAFE_FLAGS),
        'basename': ExternalCommandConfig(safe_flags=BASENAME_SAFE_FLAGS),
        'dirname': ExternalCommandConfig(safe_flags=BASENAME_SAFE_FLAGS),
        'realpath': ExternalCommandConfig(safe_flags=REALPATH_SAFE_FLAGS),
        'readlink': ExternalCommandConfig(safe_flags=READLINK_SAFE_FLAGS),
        'printf': ExternalCommandConfig(safe_flags=PRINTF_SAFE_FLAGS),
        'id': ExternalCommandConfig(safe_flags=ID_SAFE_FLAGS),
        'whoami': ExternalCommandConfig(safe_flags=WHOAMI_SAFE_FLAGS),
        'groups': ExternalCommandConfig(safe_flags=GROUPS_SAFE_FLAGS),
        'uname': ExternalCommandConfig(safe_flags=UNAME_SAFE_FLAGS),
        'stat': ExternalCommandConfig(safe_flags=STAT_SAFE_FLAGS),
        'file': ExternalCommandConfig(safe_flags=FILE_SAFE_FLAGS),
        'cut': ExternalCommandConfig(safe_flags=CUT_SAFE_FLAGS),
        'tr': ExternalCommandConfig(safe_flags=TR_SAFE_FLAGS),
        'uniq': ExternalCommandConfig(safe_flags=UNIQ_SAFE_FLAGS),
        'printenv': ExternalCommandConfig(safe_flags=PRINTENV_SAFE_FLAGS),
        'env': ExternalCommandConfig(safe_flags=ENV_SAFE_FLAGS),
        'python': ExternalCommandConfig(safe_flags=PYTHON_SAFE_FLAGS),
        'python3': ExternalCommandConfig(safe_flags=PYTHON_SAFE_FLAGS),
        'node': ExternalCommandConfig(safe_flags=NODE_SAFE_FLAGS),
        'ssh': ExternalCommandConfig(safe_flags=SSH_SAFE_FLAGS),
        'md5sum': ExternalCommandConfig(safe_flags=CHECKSUM_SAFE_FLAGS),
        'sha256sum': ExternalCommandConfig(safe_flags=CHECKSUM_SAFE_FLAGS),
        'sha1sum': ExternalCommandConfig(safe_flags=CHECKSUM_SAFE_FLAGS),
        'sha512sum': ExternalCommandConfig(safe_flags=CHECKSUM_SAFE_FLAGS),
        'shasum': ExternalCommandConfig(safe_flags=CHECKSUM_SAFE_FLAGS),
        'openssl': ExternalCommandConfig(safe_flags=OPENSSL_SAFE_FLAGS),
        'cargo': ExternalCommandConfig(safe_flags=CARGO_SAFE_FLAGS),
        'go': ExternalCommandConfig(safe_flags=GO_SAFE_FLAGS),
        'java': ExternalCommandConfig(safe_flags=JAVA_SAFE_FLAGS),
        'php': ExternalCommandConfig(safe_flags=PHP_SAFE_FLAGS),
        'ruby': ExternalCommandConfig(safe_flags=RUBY_SAFE_FLAGS),
        'mvn': ExternalCommandConfig(safe_flags=MVN_SAFE_FLAGS),
        'gradle': ExternalCommandConfig(safe_flags=GRADLE_SAFE_FLAGS),
        'cmake': ExternalCommandConfig(safe_flags=CMAKE_SAFE_FLAGS),
        'swift': ExternalCommandConfig(safe_flags=SWIFT_SAFE_FLAGS),
        'stdbuf': ExternalCommandConfig(safe_flags=STDBUF_SAFE_FLAGS),
        'timeout': ExternalCommandConfig(safe_flags=TIMEOUT_SAFE_FLAGS),
        'xargs': ExternalCommandConfig(
            safe_flags=XARGS_SAFE_FLAGS,
            additional_command_is_dangerous_callback=_xargs_is_dangerous,
        ),
        'nmap': ExternalCommandConfig(safe_flags=NMAP_SAFE_FLAGS),
        'test': ExternalCommandConfig(safe_flags=TEST_SAFE_FLAGS),
        '[': ExternalCommandConfig(safe_flags=TEST_SAFE_FLAGS),
        '[[': ExternalCommandConfig(safe_flags=TEST_SAFE_FLAGS),
        'true': ExternalCommandConfig(safe_flags={}),
        'false': ExternalCommandConfig(safe_flags={}),
        ':': ExternalCommandConfig(safe_flags={}),
        'read': ExternalCommandConfig(
            safe_flags={
                '-r': 'none',
                '-n': 'number',
                '-N': 'number',
                '-d': 'char',
                '-s': 'none',
                '-t': 'number',
                '-u': 'number',
                '-p': 'string',
                '-a': 'none',
                '-e': 'none',
                '-i': 'string',
            }
        ),
        'cd': ExternalCommandConfig(safe_flags={'-L': 'none', '-P': 'none', '-e': 'none', '-@': 'none'}),
        'pwd': ExternalCommandConfig(safe_flags={'-L': 'none', '-P': 'none'}),
        'exit': ExternalCommandConfig(safe_flags={}),
        'return': ExternalCommandConfig(safe_flags={}),
        'set': ExternalCommandConfig(safe_flags={}),
        'unset': ExternalCommandConfig(safe_flags={'-f': 'none', '-v': 'none', '-n': 'none'}),
        'export': ExternalCommandConfig(safe_flags={'-f': 'none', '-n': 'none', '-p': 'none'}),
        'local': ExternalCommandConfig(safe_flags={'-a': 'none', '-A': 'none', '-f': 'none', '-i': 'none', '-n': 'none', '-r': 'none', '-t': 'none', '-u': 'none', '-x': 'none'}),
        'declare': ExternalCommandConfig(safe_flags={'-a': 'none', '-A': 'none', '-f': 'none', '-i': 'none', '-l': 'none', '-n': 'none', '-p': 'none', '-r': 'none', '-t': 'none', '-u': 'none', '-x': 'none', '-g': 'none'}),
        'source': ExternalCommandConfig(safe_flags={}),  # source is controlled separately
        'less': ExternalCommandConfig(safe_flags={'-N': 'none', '-n': 'none', '-F': 'none', '-R': 'none', '-r': 'none', '-X': 'none', '-S': 'none', '-i': 'none', '-I': 'none', '-q': 'none', '-Q': 'none', '-m': 'none', '-M': 'none', '-e': 'none', '-E': 'none', '-c': 'none', '-C': 'none', '--help': 'none', '--version': 'none', '-+': 'none', '-J': 'none', '-K': 'none', '-y': 'number', '-x': 'number'}),
        'more': ExternalCommandConfig(safe_flags={'-d': 'none', '-l': 'none', '-f': 'none', '-p': 'none', '-c': 'none', '-s': 'none', '-u': 'none', '-n': 'number', '--help': 'none', '--version': 'none'}),
    }

    allowlist.update(local_commands)

    return allowlist


# Lazy-initialized singleton
_COMMAND_ALLOWLIST: Optional[Dict[str, ExternalCommandConfig]] = None


def get_command_allowlist() -> Dict[str, ExternalCommandConfig]:
    """Get the command allowlist (singleton)."""
    global _COMMAND_ALLOWLIST
    if _COMMAND_ALLOWLIST is None:
        _COMMAND_ALLOWLIST = _get_command_allowlist()
    return _COMMAND_ALLOWLIST


# ---------------------------------------------------------------------------
# Flag validation
# ---------------------------------------------------------------------------

FLAG_PATTERN = re.compile(r'^-[a-zA-Z0-9_-]')


def _validate_flag_argument(value: str, arg_type: FlagArgType) -> bool:
    """Validate a flag argument based on its expected type."""
    if arg_type == 'none':
        return False
    elif arg_type == 'number':
        return bool(re.match(r'^-?\d+$', value))
    elif arg_type == 'string':
        return True
    elif arg_type == 'char':
        return len(value) == 1
    elif arg_type == '{}':
        return value == '{}'
    elif arg_type == 'EOF':
        return value == 'EOF'
    return False


def _validate_flags(
    tokens: List[str],
    start_index: int,
    config: ExternalCommandConfig,
    command_base: Optional[str] = None,
) -> bool:
    """
    Validate flags in a tokenized command from start_index onward.

    Returns True if all flags are valid.
    """
    i = start_index
    respects_double_dash = config.respects_double_dash

    while i < len(tokens):
        token = tokens[i]
        if not token:
            i += 1
            continue

        # End-of-options marker
        if token == '--':
            if respects_double_dash is not False:
                # Everything after -- is positional args, not flags
                break
            i += 1
            continue

        # Is it a flag?
        if token.startswith('-') and len(token) > 1:
            has_equals = '=' in token
            parts = token.split('=', 1)
            flag = parts[0]
            inline_value = parts[1] if has_equals else ''

            if not flag:
                return False

            flag_arg_type = config.safe_flags.get(flag)

            if flag_arg_type is None:
                # Special case: git commands accept -<number> as -n shorthand
                if command_base == 'git' and re.match(r'^-\d+$', flag):
                    i += 1
                    continue

                # Handle attached numeric args for grep/rg: -A20 → -A with value 20
                if command_base in ('grep', 'egrep', 'fgrep', 'rg') and not flag.startswith('--') and len(flag) > 2:
                    short_flag = flag[:2]
                    attached_val = flag[2:]
                    short_type = config.safe_flags.get(short_flag)
                    if short_type in ('number', 'string') and re.match(r'^\d+$', attached_val):
                        i += 1
                        continue

                # Try short-flag bundling: -rn treated as -r -n if all are 'none'
                if not flag.startswith('--') and len(flag) > 2 and not has_equals:
                    all_safe = True
                    for ch in flag[1:]:
                        ft = config.safe_flags.get('-' + ch)
                        if ft != 'none':
                            all_safe = False
                            break
                    if all_safe:
                        i += 1
                        continue

                return False  # Unknown flag

            if flag_arg_type == 'none':
                if has_equals:
                    return False  # 'none'-type flag should not take a value
                i += 1
            else:
                if has_equals:
                    arg_value = inline_value
                    i += 1
                else:
                    # Consume next token as the value
                    if i + 1 >= len(tokens):
                        return False  # No value available
                    arg_value = tokens[i + 1] or ''
                    i += 2

                # Block flag-looking values for 'string' args (possible flag confusion)
                if flag_arg_type == 'string' and arg_value.startswith('-'):
                    # Exception: git --sort accepts `-refname` etc. for reverse-sort
                    if flag == '--sort' and command_base == 'git':
                        pass  # Allow
                    else:
                        return False

                if not _validate_flag_argument(arg_value, flag_arg_type):
                    return False
        else:
            # Non-flag positional argument — allowed
            i += 1

    return True


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def tokenize_command(command: str) -> List[str]:
    """
    Tokenize a shell command string into argv tokens.

    This is a simplified tokenizer for read-only validation — it handles
    basic quoting but does not process complex shell constructs.
    """
    tokens: List[str] = []
    current: List[str] = []
    i = 0
    n = len(command)
    in_single_quote = False
    in_double_quote = False

    while i < n:
        c = command[i]

        if in_single_quote:
            if c == "'":
                in_single_quote = False
            else:
                current.append(c)
            i += 1
        elif in_double_quote:
            if c == '\\' and i + 1 < n and command[i + 1] in ('"', '\\', '$', '`', '\n'):
                current.append(command[i + 1])
                i += 2
            elif c == '"':
                in_double_quote = False
                i += 1
            else:
                current.append(c)
                i += 1
        else:
            if c == "'":
                in_single_quote = True
                i += 1
            elif c == '"':
                in_double_quote = True
                i += 1
            elif c == '\\' and i + 1 < n:
                if command[i + 1] == '\n':
                    i += 2  # line continuation
                else:
                    current.append(command[i + 1])
                    i += 2
            elif c in (' ', '\t', '\n'):
                if current:
                    tokens.append(''.join(current))
                    current = []
                i += 1
            else:
                current.append(c)
                i += 1

    if current:
        tokens.append(''.join(current))

    return tokens


# ---------------------------------------------------------------------------
# URL validation (for git ls-remote etc.)
# ---------------------------------------------------------------------------

# Patterns that indicate a URL is a network URL (not a local path)
URL_PATTERN = re.compile(r'^(?:https?|git|ssh|ftp)://')
SSH_URL_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+:[a-zA-Z0-9._/-]+')


def is_local_path(arg: str) -> bool:
    """Check if an argument looks like a local filesystem path."""
    if arg.startswith('/') or arg.startswith('./') or arg.startswith('../'):
        return True
    if arg.startswith('~'):
        return True
    return not (URL_PATTERN.match(arg) or SSH_URL_PATTERN.match(arg))


# ---------------------------------------------------------------------------
# Main validation function
# ---------------------------------------------------------------------------


def is_read_only_command(command: str) -> bool:
    """
    Determine if a shell command is read-only (safe to execute without user permission).

    This function:
    1. Tokenizes the command
    2. Finds the longest matching command in the allowlist
    3. Validates all flags against the config
    4. Runs any command-specific safety callback

    Returns True if the command is read-only (safe), False otherwise.
    """
    if not command or not command.strip():
        return False

    tokens = tokenize_command(command.strip())
    if not tokens:
        return False

    allowlist = get_command_allowlist()

    # Try to find the longest matching command pattern
    # Commands can be multi-word: "git log", "git remote show", etc.
    matched_config: Optional[ExternalCommandConfig] = None
    matched_command_tokens: int = 0
    command_base: Optional[str] = None

    # Try up to 4 tokens as the command name (e.g. "git remote show")
    for length in range(min(4, len(tokens)), 0, -1):
        candidate = ' '.join(tokens[:length])
        if candidate in allowlist:
            matched_config = allowlist[candidate]
            matched_command_tokens = length
            command_base = tokens[0]
            break

    if matched_config is None:
        return False

    # Validate flags from position matched_command_tokens onwards
    if not _validate_flags(
        tokens, matched_command_tokens, matched_config, command_base
    ):
        return False

    # Run the additional safety callback if present
    if matched_config.additional_command_is_dangerous_callback is not None:
        args_after_command = tokens[matched_command_tokens:]
        raw_command = command.strip()
        if matched_config.additional_command_is_dangerous_callback(raw_command, args_after_command):
            return False

    return True


def get_read_only_command_config(
    command: str,
) -> Optional[Tuple[str, ExternalCommandConfig, List[str]]]:
    """
    Look up a command in the allowlist and return (matched_name, config, remaining_args).

    Returns None if the command is not in the allowlist.
    """
    tokens = tokenize_command(command.strip())
    if not tokens:
        return None

    allowlist = get_command_allowlist()

    for length in range(min(4, len(tokens)), 0, -1):
        candidate = ' '.join(tokens[:length])
        if candidate in allowlist:
            config = allowlist[candidate]
            remaining = tokens[length:]
            return candidate, config, remaining

    return None


# ---------------------------------------------------------------------------
# Validate a list of SimpleCommand objects
# ---------------------------------------------------------------------------


def validate_simple_commands(
    commands: list,  # List[SimpleCommand]
    raw_command: str,
) -> bool:
    """
    Validate a list of SimpleCommand objects against the read-only allowlist.

    Returns True if all commands are read-only safe, False otherwise.
    """
    for cmd in commands:
        argv = getattr(cmd, 'argv', [])
        if not argv:
            continue

        cmd_str = ' '.join(argv)
        if not is_read_only_command(cmd_str):
            return False

    return True
