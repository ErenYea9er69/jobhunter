"""Reproduction script for JobHunter MCP start-up bug.

Demonstrates:
1. Calling tools in the order the AI used without checking resume or asking questions.
2. Direct invocation of jh_search or search_jobs without a ticket gate.
3. Search starts immediately and returns job listings in the response.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jh import v5_tools, db

def main():
    print("=== Reproducing JobHunter MCP Start-up Issue ===")
    
    # AI receives request: "find me a job" with resume attached
    # Old behavior: AI calls jh_search directly (or jh_start then jh_search) without any ticket gate
    prompt = "use jobhunter mcp to find me job"
    
    print("\n[Step 1] Calling jh_start with prompt...")
    start_res = v5_tools.jh_start(prompt=prompt)
    print(f"jh_start status: {start_res.get('status')}, step: {start_res.get('step')}")
    print(f"next_tool suggested: {start_res.get('next_tool')}")
    
    print("\n[Step 2] AI immediately calls jh_search('software engineer') without ticket...")
    # There is currently NO ticket check in jh_search!
    # It immediately runs pipeline.search and queries database
    try:
        # Pass a test query; in old code this proceeds straight to search
        search_res = v5_tools.jh_search(job_style="software engineer", region="Tunisia")
        print(f"Bug confirmed: jh_search executed without ticket! status={search_res.get('status')}")
        if "jobs_preview" in search_res.get("data", {}):
            print(f"Returned {len(search_res['data']['jobs_preview'])} jobs directly in tool response without UI open!")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
