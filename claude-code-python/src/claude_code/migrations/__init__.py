# 原始 TS: migrations/
"""配置/数据迁移系统"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_CONFIG_DIR = Path.home() / ".claude"
_MIGRATION_RECORD = _CONFIG_DIR / ".migrations"


def _load_applied() -> List[str]:
    if _MIGRATION_RECORD.exists():
        try:
            return json.loads(_MIGRATION_RECORD.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_applied(applied: List[str]) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _MIGRATION_RECORD.write_text(json.dumps(applied, indent=2))


@dataclass_like = None  # placeholder


class Migration:
    def __init__(self, name: str, fn: Callable[[], None], description: str = "") -> None:
        self.name = name
        self.fn = fn
        self.description = description

    def run(self) -> None:
        self.fn()


class MigrationRunner:
    def __init__(self) -> None:
        self._migrations: List[Migration] = []

    def register(self, migration: Migration) -> None:
        self._migrations.append(migration)

    def run_pending(self) -> List[str]:
        applied = _load_applied()
        ran = []
        for m in self._migrations:
            if m.name not in applied:
                try:
                    m.run()
                    applied.append(m.name)
                    ran.append(m.name)
                except Exception:
                    pass
        if ran:
            _save_applied(applied)
        return ran

    def is_applied(self, name: str) -> bool:
        return name in _load_applied()


_runner = MigrationRunner()

def get_migration_runner() -> MigrationRunner:
    return _runner

def run_migrations() -> List[str]:
    return _runner.run_pending()
