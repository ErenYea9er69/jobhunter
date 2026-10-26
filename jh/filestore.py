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

    SCHEMA_VERSION = "1.0"
    MAX_BACKUPS = 5

    def __init__(self, jobhunter_dir: str | Path):
        self.jh_dir = Path(jobhunter_dir).resolve()
        self.cache_dir = self.jh_dir / "cache"
        self.output_dir = self.jh_dir / "output"
        self.profiles_dir = self.jh_dir / "profiles"
        self.backups_dir = self.jh_dir / "backups"
        self._lock = threading.Lock()

        # Ensure base directories exist
        self.jh_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "tailored").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "cover-letters").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "interview-prep").mkdir(parents=True, exist_ok=True)
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

    # ------------------------------------------------------------ profiles/

    @property
    def profiles_index_path(self) -> Path:
        return self.profiles_dir / "index.json"

    def save_profile(self, profile_id: str, profile_data: dict[str, Any]) -> None:
        """Save a normalized profile and update the profile index."""
        with self._lock:
            # Save individual profile file
            profile_file = self.profiles_dir / f"{profile_id}.json"
            record = dict(profile_data)
            record["schema_version"] = self.SCHEMA_VERSION
            record["profile_id"] = profile_id
            record["updated_at"] = now_iso()
            self._write_json_atomic(profile_file, record)

            # Update index
            index = self._read_json(self.profiles_index_path, default={"profiles": [], "schema_version": self.SCHEMA_VERSION})
            entries = index.get("profiles", [])
            existing_idx = next((i for i, e in enumerate(entries) if e.get("profile_id") == profile_id), -1)
            entry = {
                "profile_id": profile_id,
                "variant_name": profile_data.get("_profile_name", profile_data.get("variant_name", "")),
                "source_file": profile_data.get("_source_file", ""),
                "skills_count": len(profile_data.get("skills", [])),
                "updated_at": now_iso(),
            }
            if existing_idx >= 0:
                entries[existing_idx] = entry
            else:
                entries.append(entry)
            index["profiles"] = entries
            index["schema_version"] = self.SCHEMA_VERSION
            self._write_json_atomic(self.profiles_index_path, index)

    def load_profile(self, profile_id: str) -> Optional[dict[str, Any]]:
        """Load a profile by ID."""
        with self._lock:
            profile_file = self.profiles_dir / f"{profile_id}.json"
            data = self._read_json(profile_file, default=None)
            return data

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return the profile index entries."""
        with self._lock:
            index = self._read_json(self.profiles_index_path, default={"profiles": []})
            return index.get("profiles", [])

    # ------------------------------------------------------------ backups/

    def create_backup(self, file_path: Path, reason: str = "") -> Optional[str]:
        """Create a backup of a durable file in .jobhunter/backups/.

        Keeps a bounded rotation of MAX_BACKUPS per source file.
        Returns the backup path or None on failure.
        """
        if not file_path.is_file():
            return None
        try:
            import shutil
            stem = file_path.stem
            suffix = file_path.suffix
            timestamp = now_iso().replace(":", "-").replace("+", "_")
            backup_name = f"{stem}_{timestamp}{suffix}"
            backup_path = self.backups_dir / backup_name
            shutil.copy2(file_path, backup_path)

            # Rotate old backups for this file
            existing = sorted(
                [f for f in self.backups_dir.iterdir() if f.name.startswith(stem) and f.suffix == suffix],
                key=lambda f: f.stat().st_mtime,
            )
            while len(existing) > self.MAX_BACKUPS:
                oldest = existing.pop(0)
                try:
                    oldest.unlink()
                except OSError:
                    pass

            return str(backup_path)
        except Exception:
            return None

    # ------------------------------------------------------------ schema versioning

    def validate_schema_version(self, data: dict[str, Any], expected: str = "") -> bool:
        """Check if data has a compatible schema version."""
        expected = expected or self.SCHEMA_VERSION
        return data.get("schema_version", "1.0") == expected

    # ------------------------------------------------------------ watchlist.json

    @property
    def watchlist_path(self) -> Path:
        return self.jh_dir / "watchlist.json"

    def load_watchlist(self) -> list[dict[str, Any]]:
        """Load the target company watchlist."""
        with self._lock:
            data = self._read_json(self.watchlist_path, default={"companies": [], "schema_version": self.SCHEMA_VERSION})
            return data.get("companies", [])

    def add_to_watchlist(self, company: str, board_url: str = "", notes: str = "") -> dict[str, Any]:
        """Add a target company to the watchlist."""
        with self._lock:
            data = self._read_json(self.watchlist_path, default={"companies": [], "schema_version": self.SCHEMA_VERSION})
            companies = data.get("companies", [])

            # Check for duplicate
            existing = next((c for c in companies if c.get("company", "").lower() == company.lower()), None)
            if existing:
                if board_url:
                    existing["board_url"] = board_url
                if notes:
                    existing["notes"] = notes
                existing["updated_at"] = now_iso()
            else:
                entry = {
                    "company": company,
                    "board_url": board_url,
                    "notes": notes,
                    "added_at": now_iso(),
                    "updated_at": now_iso(),
                }
                companies.append(entry)
                existing = entry

            data["companies"] = companies
            data["schema_version"] = self.SCHEMA_VERSION
            self._write_json_atomic(self.watchlist_path, data)
            return existing

    def remove_from_watchlist(self, company: str) -> bool:
        """Remove a company from the watchlist. Returns True if found and removed."""
        with self._lock:
            data = self._read_json(self.watchlist_path, default={"companies": []})
            companies = data.get("companies", [])
            before = len(companies)
            companies = [c for c in companies if c.get("company", "").lower() != company.lower()]
            if len(companies) == before:
                return False
            data["companies"] = companies
            self._write_json_atomic(self.watchlist_path, data)
            return True

    # ------------------------------------------------------------ data export / deletion

    def export_all_data(self) -> dict[str, Any]:
        """Export all durable data for the candidate. Returns a dict of all stored data."""
        with self._lock:
            result: dict[str, Any] = {}
            result["config"] = self._read_json(self.jh_dir / "config.json", default={})
            result["applications"] = self._read_json(self.jh_dir / "applications.json", default=[])
            result["watchlist"] = self._read_json(self.watchlist_path, default={})

            # Profiles
            profiles = []
            if self.profiles_dir.is_dir():
                for pf in self.profiles_dir.glob("*.json"):
                    if pf.name != "index.json":
                        profiles.append(self._read_json(pf, default={}))
            result["profiles"] = profiles

            # Output manifest (filenames only, not full content)
            outputs: dict[str, list[str]] = {}
            if self.output_dir.is_dir():
                for subdir in self.output_dir.iterdir():
                    if subdir.is_dir():
                        outputs[subdir.name] = [f.name for f in subdir.iterdir() if f.is_file()]
            result["generated_outputs"] = outputs
            result["exported_at"] = now_iso()
            result["schema_version"] = self.SCHEMA_VERSION
            return result

    def list_deletable_files(self) -> list[dict[str, str]]:
        """Preview files that would be deleted by a full data deletion."""
        files = []
        for path in [
            self.jh_dir / "config.json",
            self.jh_dir / "applications.json",
            self.watchlist_path,
        ]:
            if path.is_file():
                files.append({"path": str(path), "type": "durable_data"})

        if self.profiles_dir.is_dir():
            for pf in self.profiles_dir.glob("*.json"):
                files.append({"path": str(pf), "type": "profile"})

        for subdir_name in ("tailored", "cover-letters", "interview-prep", "reports"):
            subdir = self.output_dir / subdir_name
            if subdir.is_dir():
                for f in subdir.iterdir():
                    if f.is_file():
                        files.append({"path": str(f), "type": f"output/{subdir_name}"})

        if self.cache_dir.is_dir():
            for f in self.cache_dir.iterdir():
                if f.is_file():
                    files.append({"path": str(f), "type": "cache"})

        return files

