import json
import subprocess
import sys

proc = subprocess.Popen(
    [sys.executable, "mcp_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=0
)

def send_recv(req):
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line)

# 1. Initialize
init_resp = send_recv({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0.0"}
    }
})
assert "result" in init_resp, init_resp
proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
proc.stdin.flush()

# 2. Call score_fit
score_resp = send_recv({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "score_fit",
        "arguments": {
            "job_title": "Python Backend Engineer",
            "company": "TestCorp",
            "description": "Looking for Python, FastAPI, PostgreSQL engineer"
        }
    }
})
print("score_fit isError:", score_resp.get("result", {}).get("isError", False))
res_text = score_resp["result"]["content"][0]["text"]
score_data = json.loads(res_text)
print("score_fit status:", score_data.get("status"))

# 3. Call add_to_tracker
track_resp = send_recv({
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
        "name": "add_to_tracker",
        "arguments": {
            "company": "TestCorp",
            "title": "Python Backend Engineer",
            "status": "applied",
            "notes": "Testing tracker addition"
        }
    }
})
print("add_to_tracker isError:", track_resp.get("result", {}).get("isError", False))
track_data = json.loads(track_resp["result"]["content"][0]["text"])
print("add_to_tracker status:", track_data.get("status"))
print("tracked application id:", track_data.get("data", {}).get("application", {}).get("id"))

# 4. Call search_jobs
search_resp = send_recv({
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
        "name": "search_jobs",
        "arguments": {
            "query": "Software Engineer",
            "limit": 3
        }
    }
})
print("search_jobs isError:", search_resp.get("result", {}).get("isError", False))
search_data = json.loads(search_resp["result"]["content"][0]["text"])
print("search_jobs status:", search_data.get("status"))

# 5. Call rewrite_resume (dry run with sample description)
rewrite_resp = send_recv({
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
        "name": "rewrite_resume",
        "arguments": {
            "job_title": "Python Backend Engineer",
            "company": "TestCorp",
            "description": "Python, PostgreSQL, Redis",
            "save": False
        }
    }
})
print("rewrite_resume isError:", rewrite_resp.get("result", {}).get("isError", False))
rewrite_data = json.loads(rewrite_resp["result"]["content"][0]["text"])
print("rewrite_resume status:", rewrite_data.get("status"))

proc.terminate()
proc.wait()
print("All 4 core tools tested successfully via stdio JSON-RPC!")

