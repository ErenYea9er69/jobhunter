"""Mission log in SQLite. One row per client request, so work can be resumed, shown and re-checked."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from .. import db
from ..util import now_iso

_MAX_JSON = 400_000
KEEP = 200            # missions kept; older ones are deleted


def _ensure(c) -> None:
    c.execute("""CREATE TABLE IF NOT EXISTS missions (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, request TEXT NOT NULL,
        intents TEXT NOT NULL, status TEXT NOT NULL, data_json TEXT NOT NULL)""")


def new_id() -> str:
    return "m-" + uuid.uuid4().hex[:8]


def save(mission_id: str, request: str, intents: list[str], status: str, data: dict[str, Any]) -> None:
    blob = json.dumps(data, default=str, ensure_ascii=False)
    if len(blob) > _MAX_JSON:
        blob = json.dumps({"truncated": True, "summary": data.get("summary", "")}, ensure_ascii=False)
    now = now_iso()
    with db.session() as c:
        _ensure(c)
        row = c.execute("SELECT created_at FROM missions WHERE id=?", (mission_id,)).fetchone()
        c.execute("INSERT OR REPLACE INTO missions (id, created_at, updated_at, request, intents, status, data_json) VALUES (?,?,?,?,?,?,?)",
                  (mission_id, row["created_at"] if row else now, now, request[:1000], ",".join(intents), status, blob))
        c.execute("DELETE FROM missions WHERE id NOT IN (SELECT id FROM missions ORDER BY created_at DESC LIMIT ?)", (KEEP,))


def load(mission_id: str) -> Optional[dict[str, Any]]:
    with db.session() as c:
        _ensure(c)
        r = c.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
    if not r:
        return None
    return {"id": r["id"], "created_at": r["created_at"], "updated_at": r["updated_at"], "request": r["request"],
            "intents": r["intents"].split(",") if r["intents"] else [], "status": r["status"], "data": json.loads(r["data_json"])}


def recent(limit: int = 10) -> list[dict[str, Any]]:
    with db.session() as c:
        _ensure(c)
        rows = c.execute("SELECT id, created_at, request, intents, status FROM missions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": r["id"], "created_at": r["created_at"], "request": r["request"][:140],
             "intents": r["intents"].split(",") if r["intents"] else [], "status": r["status"]} for r in rows]


def update_data(mission_id: str, patch: dict[str, Any]) -> bool:
    m = load(mission_id)
    if not m:
        return False
    data = {**m["data"], **patch}
    save(mission_id, m["request"], m["intents"], m["status"], data)
    return True


def review_totals() -> dict[str, Any]:
    """What the Reviewer has done across all kept missions. It is the team's track record."""
    totals: dict[str, int] = {}
    n = 0
    with db.session() as c:
        _ensure(c)
        rows = c.execute("SELECT data_json FROM missions").fetchall()
    for r in rows:
        try:
            stats = (json.loads(r["data_json"]).get("summary") or {}).get("review_stats") or {}
        except ValueError:
            continue
        n += 1
        for k, v in stats.items():
            if isinstance(v, int):
                totals[k] = totals.get(k, 0) + v
    return {"missions": n, **totals}


def forget(mission_id: str) -> int:
    """Delete one mission, or every mission with ``"all"``. Returns how many were deleted."""
    with db.session() as c:
        _ensure(c)
        cur = c.execute("DELETE FROM missions") if mission_id == "all" else c.execute("DELETE FROM missions WHERE id=?", (mission_id,))
        return cur.rowcount
