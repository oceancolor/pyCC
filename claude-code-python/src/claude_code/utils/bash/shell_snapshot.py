"""
shell_snapshot.py - Shell environment snapshot creation.

Port of TypeScript ShellSnapshot.ts.
"""

import asyncio
import os
import subprocess
import time
import random
import string
from pathlib import Path
from typing import Optional

SNAPSHOT_CREATION_TIMEOUT = 10  # seconds
LITERAL_BACKSLASH = '\\'


def _get_config_file(shell_path: str) -> str:
    """Get the shell config file path for the given shell."""
    home = Path.home()
    if 'zsh' in shell_path:
        return str(home / '.zshrc')
    elif 'bash' in shell_path:
        return str(home / '.bashrc')
    else:
        return str(home / '.profile')


def create_ripgrep_shell_integration() -> dict:
    """Creates ripgrep shell integration (alias or function)."""
    # Try to find ripgrep
    import shutil
    rg_path = shutil.which('rg')
    if rg_path:
        return {'type': 'alias', 'snippet': rg_path}
    return {'type': 'alias', 'snippet': 'rg'}


def _get_user_snapshot_content(config_file: str) -> str:
    """Generates user-specific snapshot content."""
    is_zsh = config_file.endswith('.zshrc')

    content = ''

    if is_zsh:
        content += '''
      echo "# Functions" >> "$SNAPSHOT_FILE"
      typeset -f > /dev/null 2>&1
      typeset +f | grep -vE '^_[^_]' | while read func; do
        typeset -f "$func" >> "$SNAPSHOT_FILE"
      done
'''
    else:
        content += f'''
      echo "# Functions" >> "$SNAPSHOT_FILE"
      declare -f > /dev/null 2>&1
      declare -F | cut -d' ' -f3 | grep -vE '^_[^_]' | while read func; do
        encoded_func=$(declare -f "$func" | base64 )
        echo "eval {LITERAL_BACKSLASH}"{LITERAL_BACKSLASH}$(echo '$encoded_func' | base64 -d){LITERAL_BACKSLASH}" > /dev/null 2>&1" >> "$SNAPSHOT_FILE"
      done
'''

    if is_zsh:
        content += '''
      echo "# Shell Options" >> "$SNAPSHOT_FILE"
      setopt | sed 's/^/setopt /' | head -n 1000 >> "$SNAPSHOT_FILE"
'''
    else:
        content += '''
      echo "# Shell Options" >> "$SNAPSHOT_FILE"
      shopt -p | head -n 1000 >> "$SNAPSHOT_FILE"
      set -o | grep "on" | awk '{print "set -o " $1}' | head -n 1000 >> "$SNAPSHOT_FILE"
      echo "shopt -s expand_aliases" >> "$SNAPSHOT_FILE"
'''

    content += '''
      echo "# Aliases" >> "$SNAPSHOT_FILE"
      if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        alias | grep -v "='winpty " | sed 's/^alias //g' | sed 's/^/alias -- /' | head -n 1000 >> "$SNAPSHOT_FILE"
      else
        alias | sed 's/^alias //g' | sed 's/^/alias -- /' | head -n 1000 >> "$SNAPSHOT_FILE"
      fi
'''

    return content


async def _get_claude_code_snapshot_content() -> str:
    """Generates Claude Code specific snapshot content."""
    from .shell_quote import quote

    path_value = os.environ.get('PATH', '')

    rg_integration = create_ripgrep_shell_integration()

    content = '''
      echo "# Check for rg availability" >> "$SNAPSHOT_FILE"
      echo "if ! (unalias rg 2>/dev/null; command -v rg) >/dev/null 2>&1; then" >> "$SNAPSHOT_FILE"
'''

    if rg_integration['type'] == 'function':
        content += f'''
      cat >> "$SNAPSHOT_FILE" << 'RIPGREP_FUNC_END'
  {rg_integration['snippet']}
RIPGREP_FUNC_END
'''
    else:
        escaped_snippet = rg_integration['snippet'].replace("'", "'\\''")
        content += f'''
      echo '  alias rg='"'{escaped_snippet}'" >> "$SNAPSHOT_FILE"
'''

    content += '''
      echo "fi" >> "$SNAPSHOT_FILE"
'''

    content += f'''
      echo "export PATH={quote([path_value])}" >> "$SNAPSHOT_FILE"
'''

    return content


async def _get_snapshot_script(
    shell_path: str,
    snapshot_file_path: str,
    config_file_exists: bool,
) -> str:
    """Creates the appropriate shell script for capturing environment."""
    from .shell_quote import quote

    config_file = _get_config_file(shell_path)
    is_zsh = config_file.endswith('.zshrc')

    if config_file_exists:
        user_content = _get_user_snapshot_content(config_file)
    elif not is_zsh:
        user_content = 'echo "shopt -s expand_aliases" >> "$SNAPSHOT_FILE"'
    else:
        user_content = ''

    claude_code_content = await _get_claude_code_snapshot_content()

    script = f'''SNAPSHOT_FILE={quote([snapshot_file_path])}
      {f'source "{config_file}" < /dev/null' if config_file_exists else '# No user config file to source'}

      echo "# Snapshot file" >| "$SNAPSHOT_FILE"

      echo "# Unset all aliases to avoid conflicts with functions" >> "$SNAPSHOT_FILE"
      echo "unalias -a 2>/dev/null || true" >> "$SNAPSHOT_FILE"

      {user_content}

      {claude_code_content}

      if [ ! -f "$SNAPSHOT_FILE" ]; then
        echo "Error: Snapshot file was not created at $SNAPSHOT_FILE" >&2
        exit 1
      fi
    '''

    return script


async def create_and_save_snapshot(bin_shell: str) -> Optional[str]:
    """
    Creates and saves the shell environment snapshot.

    Returns:
        Path to the snapshot file, or None if creation failed.
    """
    from ...utils.env_utils import get_claude_config_home_dir

    shell_type = (
        'zsh' if 'zsh' in bin_shell
        else 'bash' if 'bash' in bin_shell
        else 'sh'
    )

    try:
        config_file = _get_config_file(bin_shell)
        config_file_exists = Path(config_file).exists()

        timestamp = int(time.time() * 1000)
        random_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

        snapshots_dir = Path(get_claude_config_home_dir()) / 'shell-snapshots'
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        snapshot_path = str(snapshots_dir / f"snapshot-{shell_type}-{timestamp}-{random_id}.sh")

        snapshot_script = await _get_snapshot_script(
            bin_shell,
            snapshot_path,
            config_file_exists,
        )

        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    [bin_shell, '-c', '-l', snapshot_script],
                    capture_output=True,
                    text=True,
                    timeout=SNAPSHOT_CREATION_TIMEOUT,
                    env={
                        **os.environ,
                        'SHELL': bin_shell,
                        'GIT_EDITOR': 'true',
                        'CLAUDECODE': '1',
                    },
                )
            ),
            timeout=SNAPSHOT_CREATION_TIMEOUT + 2,
        )

        if result.returncode != 0:
            return None

        if Path(snapshot_path).exists():
            return snapshot_path

        return None

    except Exception:
        return None
