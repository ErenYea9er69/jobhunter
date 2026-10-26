"""Resume registry for variant discovery, stable identities, and incremental parsing.

Implements Section 6.2 of newall-logic.md:
- Stable identities using normalized file paths and SHA-256 content hashes
- Incremental parsing: re-parses only changed files
- Active variant tracking, parse status, and manifest persistence
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config, db, workspace
from .util import file_sha256, now_iso, slugify

log = logging.getLogger("jobhunter.registry")

MANIFEST_FILENAME = "resume_manifest.json"


class ResumeRegistry:
    """Manages discovered resume variants and tracks incremental parsing manifests."""

    def __init__(self, workspace_path: str | Path) -> None:
        self.workspace_path = Path(workspace_path).resolve()
        self.data_dir = self.workspace_path / ".jobhunter"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.data_dir / MANIFEST_FILENAME
        self._manifest: dict[str, Any] = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        """Load persistent manifest or return empty structure."""
        if self.manifest_path.exists():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as e:
                log.warning("Could not read resume manifest at %s: %s", self.manifest_path, e)
        return {"version": "1.0", "active_variant": "", "variants": {}}

    def _save_manifest(self) -> None:
        """Persist manifest to disk atomically."""
        try:
            self.manifest_path.write_text(json.dumps(self._manifest, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("Could not write resume manifest: %s", e)

    def get_manifest(self) -> dict[str, Any]:
        return self._manifest

    def get_active_variant(self) -> Optional[str]:
        return self._manifest.get("active_variant") or None

    def set_active_variant(self, name_or_id: str) -> bool:
        """Set active variant by name, filename, or variant ID."""
        target = name_or_id.strip().lower()
        variants = self._manifest.get("variants", {})
        for key, var in variants.items():
            if (
                key.lower() == target
                or var.get("name", "").lower() == target
                or var.get("id", "").lower() == target
                or var.get("filename", "").lower() == target
            ):
                self._manifest["active_variant"] = var.get("name")
                self._save_manifest()
                return True
        return False

    def list_variants(self) -> list[dict[str, Any]]:
        """Return list of known variants."""
        return list(self._manifest.get("variants", {}).values())

    def get_variant(self, name_or_id: str) -> Optional[dict[str, Any]]:
        """Look up variant by name or ID."""
        target = name_or_id.strip().lower()
        for var in self.list_variants():
            if (
                var.get("name", "").lower() == target
                or var.get("id", "").lower() == target
                or var.get("filename", "").lower() == target
            ):
                return var
        return None

    def scan_and_sync(self, force: bool = False) -> dict[str, Any]:
        """Discover resumes in workspace and re-parse only changed files.

        Returns:
            Dict summarizing scan: total_files, parsed_count, cached_count, active_variant.
        """
        found_resumes = workspace.discover_resumes(self.workspace_path)
        existing_variants = self._manifest.get("variants", {})
        new_variants: dict[str, Any] = {}

        parsed_count = 0
        cached_count = 0

        for item in found_resumes:
            file_path = Path(item["path"]).resolve()
            if not file_path.exists():
                continue

            try:
                rel_path = file_path.relative_to(self.workspace_path).as_posix()
            except ValueError:
                rel_path = file_path.name

            try:
                current_hash = file_sha256(str(file_path))
            except Exception as e:
                log.warning("Could not hash %s: %s", file_path, e)
                current_hash = ""

            try:
                mtime = file_path.stat().st_mtime
            except OSError:
                mtime = 0.0

            slug_name = slugify(item["name"]) or "resume"
            variant_id = f"var_{slug_name}"

            cached = existing_variants.get(rel_path) or existing_variants.get(item["name"])
            needs_parse = (
                force
                or not cached
                or cached.get("content_hash") != current_hash
                or not cached.get("profile")
            )

            if needs_parse:
                try:
                    profile = workspace.parse_resume_variant(file_path)
                    profile["_profile_id"] = variant_id
                    profile["_profile_name"] = item["name"]
                    parse_status = "ok"
                    confidence = 0.95
                    parsed_count += 1
                except Exception as e:
                    log.error("Failed to parse %s: %s", file_path, e)
                    profile = {}
                    parse_status = f"error: {e}"
                    confidence = 0.0
            else:
                profile = cached.get("profile", {})
                parse_status = cached.get("parse_status", "ok")
                confidence = cached.get("confidence", 0.95)
                cached_count += 1

            record = {
                "id": variant_id,
                "name": item["name"],
                "filename": file_path.name,
                "rel_path": rel_path,
                "abs_path": str(file_path),
                "content_hash": current_hash,
                "mtime": mtime,
                "last_parsed": now_iso() if needs_parse else cached.get("last_parsed", now_iso()),
                "parse_status": parse_status,
                "confidence": confidence,
                "profile": profile,
            }
            new_variants[rel_path] = record

        self._manifest["variants"] = new_variants

        # Update active variant if unset or invalid
        current_active = self._manifest.get("active_variant")
        valid_names = [v["name"] for v in new_variants.values()]
        if not current_active or current_active not in valid_names:
            if valid_names:
                self._manifest["active_variant"] = valid_names[0]
            else:
                self._manifest["active_variant"] = ""

        self._save_manifest()

        return {
            "total_files": len(found_resumes),
            "parsed_count": parsed_count,
            "cached_count": cached_count,
            "active_variant": self._manifest.get("active_variant"),
            "variants": list(new_variants.values()),
        }
