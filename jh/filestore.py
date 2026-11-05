"""Writes generated documents to ``.jobhunter/output/`` and imports old ``applications.json`` data.

Application tracking lives in SQLite (``jh.tracker``). That is the only application store.
Earlier versions also kept ``applications.json``; ``import_legacy_applications`` moves any
records from that file into SQLite once and then renames the file.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

OUTPUT_CATEGORIES = ("tailored", "cover-letters", "interview-prep", "reports")


class OutputStore:
    """Thread-safe, atomic writer for generated files."""

    def __init__(self, jobhunter_dir: str | Path):
        self.jh_dir = Path(jobhunter_dir).resolve()
        self.output_dir = self.jh_dir / "output"
        self._lock = threading.Lock()
        self.jh_dir.mkdir(parents=True, exist_ok=True)
        for cat in OUTPUT_CATEGORIES:
            (self.output_dir / cat).mkdir(parents=True, exist_ok=True)

    def save_output(self, category: str, filename: str, data: Any) -> str:
        """Write ``data`` to ``output/<category>/<filename>`` and return the absolute path.

        Dicts and lists are written as JSON, everything else as text. A name that tries to
        leave the output folder is rejected.
        """
        target_dir = self.output_dir / category.strip().strip("/\\")
        target_file = (target_dir / filename).resolve()
        try:
            target_file.relative_to(self.output_dir.resolve())
        except ValueError:
            raise ValueError(f"Access denied: '{category}/{filename}' escapes the output directory.")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, ensure_ascii=False) if isinstance(data, (dict, list)) else str(data)
        with self._lock:
            tmp = target_file.with_suffix(f"{target_file.suffix}.tmp.{os.getpid()}.{threading.get_ident()}")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, target_file)
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
        return str(target_file)

    def save_bytes(self, category: str, filename: str, blob: bytes) -> str:
        """Write binary output (DOCX, PDF) with the same path checks."""
        target_file = (self.output_dir / category.strip().strip("/\\") / filename).resolve()
        try:
            target_file.relative_to(self.output_dir.resolve())
        except ValueError:
            raise ValueError(f"Access denied: '{category}/{filename}' escapes the output directory.")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target_file.write_bytes(blob)
        return str(target_file)

    def import_legacy_applications(self) -> int:
        """Move records from the old ``applications.json`` into SQLite. Returns how many were imported."""
        legacy = self.jh_dir / "applications.json"
        if not legacy.is_file():
            return 0
        try:
            apps = json.loads(legacy.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 0
        from . import tracker
        count = 0
        for app in apps if isinstance(apps, list) else []:
            try:
                tracker.upsert_application(app)
                count += 1
            except Exception:
                continue
        try:
            legacy.rename(legacy.with_name("applications.json.imported"))
        except OSError:
            pass
        return count
