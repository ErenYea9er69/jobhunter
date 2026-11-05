"""Guards the code the owner asked never to change: the LinkedIn scraper and the LinkedIn radar.

If this test fails, someone edited LinkedIn code. Restore the original from version control. If the change
was intended, update tests/protected_hashes.json deliberately and say so in the commit message.
"""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
META = json.loads((ROOT / "tests" / "protected_hashes.json").read_text())


def block(file, start, end):
    text = (ROOT / file).read_text(encoding="utf-8").replace("\r\n", "\n")
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_linkedin_scraper_radar_and_getters_are_byte_identical():
    for name, m in META.items():
        digest = hashlib.sha256(block(m["file"], m["start"], m["end"]).encode()).hexdigest()
        assert digest == m["sha256"], f"{name} in {m['file']} was modified"
