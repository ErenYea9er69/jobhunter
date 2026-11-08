"""Tests for MCP auto-configurator and turnkey runners."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from jh import mcp_configurator


class TestMCPConfigurator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ws = Path(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_mcp_config_dict(self):
        cfg = mcp_configurator.get_mcp_config_dict(str(self.ws), python_exe="python3")
        self.assertEqual(cfg["command"], "python3")
        self.assertEqual(cfg["args"], [os.path.join(str(self.ws), "mcp_server.py")])
        self.assertEqual(cfg["env"]["JH_WORKSPACE"], str(self.ws))

    def test_register_with_cursor(self):
        res = mcp_configurator.register_with_cursor(str(self.ws), python_exe=sys.executable)
        self.assertTrue(res["success"])
        cursor_mcp = self.ws / ".cursor" / "mcp.json"
        self.assertTrue(cursor_mcp.exists())
        data = json.loads(cursor_mcp.read_text(encoding="utf-8"))
        self.assertIn("mcpServers", data)
        self.assertIn("jobhunter", data["mcpServers"])
        self.assertEqual(data["mcpServers"]["jobhunter"]["env"]["JH_WORKSPACE"], str(self.ws))

    def test_register_with_claude_desktop_custom_path(self):
        fake_claude_dir = self.ws / "fake_claude"
        fake_claude_dir.mkdir(parents=True)
        config_file = fake_claude_dir / "claude_desktop_config.json"
        # Pre-populate with another server
        config_file.write_text(json.dumps({"mcpServers": {"other_tool": {"command": "node"}}}), encoding="utf-8")

        res = mcp_configurator.register_with_claude_desktop(
            str(self.ws),
            python_exe=sys.executable,
            target_path=str(config_file),
        )
        self.assertTrue(res["success"])
        data = json.loads(config_file.read_text(encoding="utf-8"))
        # Both other_tool and jobhunter must be present (not clobbered)
        self.assertIn("other_tool", data["mcpServers"])
        self.assertIn("jobhunter", data["mcpServers"])


if __name__ == "__main__":
    unittest.main()

