"""JSON file persistence adapter and document writer for JobHunter MCP server.

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

OUTPUT_CATEGORIES = ("tailored", "cover-letters", "interview-prep", "reports")


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
        for cat in OUTPUT_CATEGORIES:
            (self.output_dir / cat).mkdir(parents=True, exist_ok=True)

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
                old = apps[idx]
                if record.get("status") and record.get("status") != old.get("status"):
                    hist = list(old.get("history", []))
                    hist.append({"status": record["status"], "timestamp": now, "notes": record.get("notes", "")})
                    record["history"] = hist
                apps[idx] = record
            else:
                apps.append(record)

            self._write_json_atomic(self.applications_path, apps)
            return record

    def get_application(self, app_id: str) -> Optional[dict[str, Any]]:
        apps = self.load_applications()
        return next((a for a in apps if str(a.get("id")) == str(app_id)), None)

    def update_application(self, app_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        with self._lock:
            apps = self._read_json(self.applications_path, default=[])
            if not isinstance(apps, list):
                return None
            idx = next((i for i, a in enumerate(apps) if str(a.get("id")) == str(app_id)), -1)
            if idx < 0:
                return None
            record = dict(apps[idx])
            record.update(updates)
            now = now_iso()
            record["updated_at"] = now
            new_status = updates.get("status")
            if new_status and (not record.get("history") or record["history"][-1].get("status") != new_status):
                hist = list(record.get("history", []))
                hist.append({"status": new_status, "timestamp": now, "notes": updates.get("notes", "")})
                record["history"] = hist
            apps[idx] = record
            self._write_json_atomic(self.applications_path, apps)
            return record

    def update_application_status(self, app_id: str, new_status: str, notes: str = "") -> Optional[dict[str, Any]]:
        return self.update_application(app_id, {"status": new_status, "notes": notes})

    # ------------------------------------------------------------ watchlist.json

    @property
    def watchlist_path(self) -> Path:
        return self.jh_dir / "watchlist.json"

    def load_watchlist(self) -> list[dict[str, Any]]:
        with self._lock:
            items = self._read_json(self.watchlist_path, default=[])
            if isinstance(items, dict):
                return items.get("companies", [])
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

    def add_to_watchlist(self, company: str, board_url: str = "", notes: str = "") -> dict[str, Any]:
        with self._lock:
            data = self._read_json(self.watchlist_path, default={"companies": [], "schema_version": self.SCHEMA_VERSION})
            companies = data.get("companies", []) if isinstance(data, dict) else []
            existing = next((c for c in companies if c.get("company", "").lower() == company.lower()), None)
            now = now_iso()
            if existing:
                if board_url:
                    existing["board_url"] = board_url
                if notes:
                    existing["notes"] = notes
                existing["updated_at"] = now
            else:
                entry = {
                    "company": company,
                    "board_url": board_url,
                    "notes": notes,
                    "added_at": now,
                    "updated_at": now,
                }
                companies.append(entry)
                existing = entry

            if isinstance(data, dict):
                data["companies"] = companies
                data["schema_version"] = self.SCHEMA_VERSION
                self._write_json_atomic(self.watchlist_path, data)
            else:
                self._write_json_atomic(self.watchlist_path, companies)
            return existing

    def remove_from_watchlist(self, company: str) -> bool:
        with self._lock:
            data = self._read_json(self.watchlist_path, default={"companies": []})
            if isinstance(data, dict):
                companies = data.get("companies", [])
                before = len(companies)
                companies = [c for c in companies if c.get("company", "").lower() != company.lower()]
                if len(companies) == before:
                    return False
                data["companies"] = companies
                self._write_json_atomic(self.watchlist_path, data)
                return True
            else:
                items = data if isinstance(data, list) else []
                before = len(items)
                items = [c for c in items if c.get("company", "").lower() != company.lower() and c.get("company_name", "").lower() != company.lower()]
                if len(items) == before:
                    return False
                self._write_json_atomic(self.watchlist_path, items)
                return True

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
            if len(cache) > 20:
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
        """Write ``data`` to ``output/<category>/<filename>`` and return the absolute path.

        Dicts and lists are written as JSON, everything else as text. A name that tries to
        leave the output folder is rejected.
        """
        cat_clean = category.strip().strip("/\\")
        target_dir = self.output_dir / cat_clean
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

    def export_all_data(self) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {}
            result["config"] = self._read_json(self.jh_dir / "config.json", default={})
            result["applications"] = self._read_json(self.jh_dir / "applications.json", default=[])
            result["watchlist"] = self._read_json(self.watchlist_path, default={})
            profiles = []
            if self.profiles_dir.is_dir():
                for pf in self.profiles_dir.glob("*.json"):
                    if pf.name != "index.json":
                        profiles.append(self._read_json(pf, default={}))
            result["profiles"] = profiles
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
        files = []
        for path in [self.jh_dir / "config.json", self.jh_dir / "applications.json", self.watchlist_path]:
            if path.is_file():
                files.append({"path": str(path), "type": "durable_data"})
        if self.profiles_dir.is_dir():
            for pf in self.profiles_dir.glob("*.json"):
                files.append({"path": str(pf), "type": "profile"})
        for subdir_name in OUTPUT_CATEGORIES:
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


# Alias for backward compatibility
OutputStore = FileStore
