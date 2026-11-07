import subprocess
import sys
import json

args_json = json.dumps({"job_title": "Software Engineer", "company": "TechCorp", "description": "Python developer needed"})
cmd = [
    "npx.cmd", "--yes", "@modelcontextprotocol/inspector",
    "--cli",
    "--method", "tools/call",
    "--tool-name", "score_fit",
    "--tool-args", args_json,
    sys.executable, "mcp_server.py"
]
res = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", res.returncode)
print("STDOUT:\n", res.stdout)
if res.stderr:
    print("STDERR:\n", res.stderr[:500])
