"""Mission log in JSON store. One entry per client request, so work can be resumed, shown and re-checked."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from .. import db

_MAX_JSON = 400_000
KEEP = 200            # missions kept; older ones are deleted


def new_id() -> str:
    return "m-" + uuid.uuid4().hex[:8]


def save(mission_id: str, request: str, intents: list[str], status: str, data: dict[str, Any]) -> None:
    blob = json.dumps(data, default=str, ensure_ascii=False)
    if len(blob) > _MAX_JSON:
        blob = json.dumps({"truncated": True, "summary": data.get("summary", "")}, ensure_ascii=False)
    db.upsert_mission(mission_id, request, intents, status, blob, keep=KEEP)


def load(mission_id: str) -> Optional[dict[str, Any]]:
    r = db.load_mission(mission_id)
    if not r:
        return None
    return {
        "id": r["id"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "request": r["request"],
        "intents": r["intents"].split(",") if r["intents"] else [],
        "status": r["status"],
        "data": json.loads(r["data_json"]),
    }


def recent(limit: int = 10) -> list[dict[str, Any]]:
    rows = db.recent_missions(limit=limit)
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "request": r["request"][:140],
            "intents": r["intents"].split(",") if r["intents"] else [],
            "status": r["status"],
        }
        for r in rows
    ]


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
    for r in db.all_missions():
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
    return db.delete_missions(mission_id)
