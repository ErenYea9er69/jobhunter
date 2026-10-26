"""JSON file persistence adapter for JobHunter MCP server.

Provides thread-safe, atomic read/write operations for user data stored in .jobhunter/:
- applications.json (tracked job applications)
- watchlist.json (companies/queries to watch)
- config.json (user preferences and active profile selection)
- cache/jobs.json (TTL-cached search results)
- cache/sources.json (job board health state)
- output/ (tailored resumes, cover letters, gap reports)
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .util import now_iso


class FileStore:
    """Thread-safe JSON file storage for .jobhunter workspace data."""

    def __init__(self, jobhunter_dir: str | Path):
        self.jh_dir = Path(jobhunter_dir).resolve()
        self.cache_dir = self.jh_dir / "cache"
        self.output_dir = self.jh_dir / "output"
        self._lock = threading.Lock()

        # Ensure base directories exist
        self.jh_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "tailored").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "cover-letters").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "reports").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ atomic file IO

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _write_json_atomic(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------ config.json

    @property
    def config_path(self) -> Path:
        return self.jh_dir / "config.json"

    def load_config(self) -> dict[str, Any]:
        with self._lock:
            return self._read_json(self.config_path, default={})

    def save_config(self, key_or_dict: str | dict[str, Any], value: Any = None) -> dict[str, Any]:
        with self._lock:
            cfg = self._read_json(self.config_path, default={})
            if isinstance(key_or_dict, dict):
                cfg.update(key_or_dict)
            else:
                cfg[str(key_or_dict)] = value
            self._write_json_atomic(self.config_path, cfg)
            return cfg

    def get_active_resume(self) -> Optional[str]:
        cfg = self.load_config()
        return cfg.get("active_resume")

    def set_active_resume(self, name: str) -> None:
        self.save_config("active_resume", name)

    # ------------------------------------------------------------ applications.json

    @property
    def applications_path(self) -> Path:
        return self.jh_dir / "applications.json"

    def load_applications(self) -> list[dict[str, Any]]:
        with self._lock:
            apps = self._read_json(self.applications_path, default=[])
            return apps if isinstance(apps, list) else []

    def save_application(self, app_data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update an application record by 'id'."""
        with self._lock:
            apps = self._read_json(self.applications_path, default=[])
            if not isinstance(apps, list):
                apps = []

            app_id = str(app_data.get("id") or uuid.uuid4())
            record = dict(app_data)
            record["id"] = app_id
            now = now_iso()
            if "created_at" not in record:
                record["created_at"] = now
            record["updated_at"] = now

            if "history" not in record:
                status = record.get("status", "saved")
                record["history"] = [{"status": status, "timestamp": now, "notes": record.get("notes", "")}]

            # Check if exists
            idx = next((i for i, a in enumerate(apps) if str(a.get("id")) == app_id), -1)
            if idx >= 0:
                # Merge updates, preserving existing fields if not overwritten
                existing = apps[idx]
                history = list(existing.get("history", []))
                if record.get("status") and record.get("status") != existing.get("status"):
                    history.append({
                        "status": record["status"],
                        "timestamp": now,
                        "notes": record.get("notes", ""),
                    })
                record["history"] = history
                apps[idx] = record
            else:
                apps.append(record)

            self._write_json_atomic(self.applications_path, apps)
            return record

    def update_application(self, app_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        with self._lock:
            apps = self._read_json(self.applications_path, default=[])
            if not isinstance(apps, list):
                return None

            idx = next((i for i, a in enumerate(apps) if str(a.get("id")) == str(app_id)), -1)
            if idx < 0:
                return None

            app = apps[idx]
            now = now_iso()
            old_status = app.get("status")
            new_status = updates.get("status")

            app.update(updates)
            app["updated_at"] = now

            if new_status and new_status != old_status:
                history = list(app.get("history", []))
                history.append({
                    "status": new_status,
                    "timestamp": now,
                    "notes": updates.get("notes", ""),
                })
                app["history"] = history

            apps[idx] = app
            self._write_json_atomic(self.applications_path, apps)
            return app

    # ------------------------------------------------------------ watchlist.json

    @property
    def watchlist_path(self) -> Path:
        return self.jh_dir / "watchlist.json"

    def load_watchlist(self) -> list[dict[str, Any]]:
        with self._lock:
            items = self._read_json(self.watchlist_path, default=[])
            return items if isinstance(items, list) else []

    def save_watch(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        with self._lock:
            items = self._read_json(self.watchlist_path, default=[])
            if not isinstance(items, list):
                items = []
            watch_id = str(item.get("id") or uuid.uuid4())
            record = dict(item)
            record["id"] = watch_id
            record.setdefault("created_at", now_iso())

            idx = next((i for i, w in enumerate(items) if str(w.get("id")) == watch_id), -1)
            if idx >= 0:
                items[idx] = record
            else:
                items.append(record)

            self._write_json_atomic(self.watchlist_path, items)
            return items

    # ------------------------------------------------------------ cache/jobs.json

    @property
    def jobs_cache_path(self) -> Path:
        return self.cache_dir / "jobs.json"

    def cache_jobs(self, jobs: list[dict[str, Any]], query_key: str = "latest") -> None:
        with self._lock:
            cache = self._read_json(self.jobs_cache_path, default={})
            if not isinstance(cache, dict):
                cache = {}
            cache[query_key] = {
                "timestamp": time.time(),
                "created_at": now_iso(),
                "count": len(jobs),
                "jobs": jobs,
            }
            # Limit cache entries to keep file reasonable
            if len(cache) > 20:
                # Remove oldest keys
                sorted_keys = sorted(cache.keys(), key=lambda k: cache[k].get("timestamp", 0))
                for old_key in sorted_keys[:-15]:
                    del cache[old_key]
            self._write_json_atomic(self.jobs_cache_path, cache)

    def get_cached_jobs(self, query_key: str = "latest", max_age_seconds: int = 900) -> Optional[list[dict[str, Any]]]:
        with self._lock:
            cache = self._read_json(self.jobs_cache_path, default={})
            if not isinstance(cache, dict) or query_key not in cache:
                return None
            entry = cache[query_key]
            entry_time = entry.get("timestamp", 0)
            if time.time() - entry_time > max_age_seconds:
                return None
            return entry.get("jobs")

    def get_latest_cached_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            cache = self._read_json(self.jobs_cache_path, default={})
            if not isinstance(cache, dict) or not cache:
                return []
            latest_entry = max(cache.values(), key=lambda v: v.get("timestamp", 0), default=None)
            if latest_entry and isinstance(latest_entry, dict):
                return latest_entry.get("jobs", [])
            return []

    # ------------------------------------------------------------ cache/sources.json

    @property
    def sources_cache_path(self) -> Path:
        return self.cache_dir / "sources.json"

    def save_sources_health(self, health_data: dict[str, Any]) -> None:
        with self._lock:
            self._write_json_atomic(self.sources_cache_path, health_data)

    def load_sources_health(self) -> dict[str, Any]:
        with self._lock:
            return self._read_json(self.sources_cache_path, default={})

    # ------------------------------------------------------------ output/ saving

    def save_output(self, category: str, filename: str, data: Any) -> str:
        """Write generated output to .jobhunter/output/<category>/<filename>.

        Categories: 'tailored', 'cover-letters', 'reports'
        If data is dict/list, written as JSON. If str, written as text.
        Returns absolute path string.
        """
        cat_clean = category.strip().strip("/\\")
        target_dir = self.output_dir / cat_clean
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / filename
        with self._lock:
            if isinstance(data, (dict, list)):
                self._write_json_atomic(target_file, data)
            else:
                tmp_path = target_file.with_suffix(f".tmp.{os.getpid()}.{threading.get_ident()}")
                try:
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        f.write(str(data))
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp_path, target_file)
                finally:
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except OSError:
                            pass
        return str(target_file.resolve())
