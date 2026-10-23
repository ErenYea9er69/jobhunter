"""Tests for Standalone Manifest V3 Chrome Extension Files and Structure."""
import json
import pathlib


def test_extension_manifest_and_files():
    ext_dir = pathlib.Path("extension")
    assert ext_dir.exists(), "extension directory must exist"

    manifest_path = ext_dir / "manifest.json"
    assert manifest_path.exists(), "manifest.json must exist"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Manifest V3 validations
    assert manifest.get("manifest_version") == 3
    assert manifest.get("name")
    assert manifest.get("version")
    assert "activeTab" in manifest.get("permissions", [])
    assert "storage" in manifest.get("permissions", [])

    host_perms = manifest.get("host_permissions", [])
    assert any("localhost" in p or "<all_urls>" in p for p in host_perms)

    # Core required extension assets
    assert (ext_dir / "content.js").exists(), "content.js must exist"
    assert (ext_dir / "flyout.css").exists(), "flyout.css must exist"
    assert (ext_dir / "popup.html").exists(), "popup.html must exist"
    assert (ext_dir / "popup.js").exists(), "popup.js must exist"
    assert (ext_dir / "background.js").exists(), "background.js must exist"
    assert (ext_dir / "README.md").exists(), "README.md setup instructions must exist"
