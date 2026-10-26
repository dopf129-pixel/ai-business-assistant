"""Bounded subprocess worker for a single SQLite online backup."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys


def main(arguments: list[str]) -> int:
    if len(arguments) != 2:
        return 2
    source = destination = None
    try:
        source_uri = Path(arguments[0]).resolve(strict=True).as_uri()
        source = sqlite3.connect(source_uri + "?mode=ro", uri=True, timeout=1.0)
        source.execute("PRAGMA query_only = ON")
        destination = sqlite3.connect(arguments[1], timeout=1.0)
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            return 3
        user_version = destination.execute("PRAGMA user_version").fetchone()[0]
        table_count = destination.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        sys.stdout.write(json.dumps({
            "integrity_check": "ok",
            "user_version": int(user_version),
            "table_count": int(table_count),
        }, separators=(",", ":")))
        return 0
    except Exception:
        return 4
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
