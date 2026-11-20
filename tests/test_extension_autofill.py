"""Test ATS Autofill Extension Logic (Phase F2)."""
import json
import re
from pathlib import Path


def test_extension_manifest_valid_and_has_permissions():
    manifest_path = Path("extension/manifest.json")
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["manifest_version"] == 3
    assert "content_scripts" in data
    # Permissions include host permissions
    perms = data.get("host_permissions", [])
    assert any("127.0.0.1" in p for p in perms)


def test_extension_content_js_eeo_and_unknown_handling():
    content_js = Path("extension/content.js").read_text(encoding="utf-8")

    # 1. EEO classification and answer
    assert 'return "eeo";' in content_js
    assert 'case "eeo": return "decline";' in content_js

    # 2. Decline matching in select and radio
    assert "(decline|prefer not|do not wish|choose not|not disclose)" in content_js

    # 3. Orange highlight for unknown questions
    assert "highlightOrange" in content_js
    assert "#f97316" in content_js
    assert "#fff7ed" in content_js

    # 4. Never auto-submit; badge shows 'fields filled, ... needs you'
    assert "fields filled," in content_js
    assert "needs you" in content_js
    assert "startCountdown" not in content_js
    assert "setTimeout(() => { btn.click() }, 10000)" not in content_js


def test_extension_content_js_ats_coverage():
    manifest = json.loads(Path("extension/manifest.json").read_text(encoding="utf-8"))
    matches = manifest["content_scripts"][0]["matches"]
    known_ats = ["greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "smartrecruiters.com", "bamboohr.com"]
    for ats in known_ats:
        assert any(ats in m for m in matches), f"Missing ATS portal pattern: {ats}"
