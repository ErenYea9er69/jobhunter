"""DB-free JSON + in-memory persistence store for JobHunter.

Replaces SQLite (engine.db) with atomic per-workspace JSON persistence and thread-safe
in-memory tables. Zero .db files or sqlite3 locks are created anywhere on disk.
Includes a lightweight session facade so protected read-only SQL callers keep working
without modifying any protected LinkedIn regions.
"""

from __future__ import annotations

import copy
import datetime
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import config
from .util import now_iso

# Table schemas: column defaults applied on row insertion
TABLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "settings": {"key": "", "value": ""},
    "session_state": {"id": 1, "current_state": "idle", "last_tool": "", "updated_at": ""},
    "profile": {
        "id": 1,
        "data": "{}",
        "updated_at": "",
        "roles": "[]",
        "years": 0.0,
        "skills": "[]",
        "resume_path": "",
        "portfolio_url": "",
        "proof_points": "[]",
    },
    "resume_profiles": {
        "id": "",
        "name": "",
        "target_title": "",
        "target_roles_json": "[]",
        "tags_json": "[]",
        "data_json": "{}",
        "is_active": 0,
        "is_master": 0,
        "is_live": 1,
        "source_job_id": "",
        "source_job_title": "",
        "source_company": "",
        "created_at": "",
        "updated_at": "",
    },
    "jobs": {
        "id": "",
        "job_key": "",
        "title": "",
        "company": "",
        "location": "",
        "work_mode": "",
        "source": "",
        "url": "",
        "url_hash": "",
        "fingerprint": "",
        "description": "",
        "score": 0,
        "fit_score": 0,
        "opportunity_score": 0,
        "found_at": "",
        "first_seen_at": "",
        "last_seen_at": "",
        "is_new": 1,
        "seen_by_user": 0,
        "repost_count": 0,
        "possible_duplicate": 0,
        "freshness_state": "active",
        "delete_at": None,
        "keep_flag": 0,
        "closed_checked_at": None,
        "job_json": "{}",
        "created_at": "",
        "updated_at": "",
        "category": "",
        "job_type": "",
        "seniority": "",
        "country": "",
        "min_salary": 0.0,
        "max_salary": 0.0,
        "company_size": "",
        "industry": "",
        "visa_sponsor": 0,
        "skills_text": "",
        "saved_by": "",
    },
    "job_sources": {
        "id": None,
        "job_id": "",
        "source": "",
        "url": "",
        "url_hash": "",
        "first_seen_at": "",
        "last_seen_at": "",
    },
    "search_jobs": {
        "job_key": "",
        "query": "",
        "title": "",
        "company": "",
        "location": "",
        "work_mode": "",
        "score": 0,
        "opportunity_score": 0,
        "is_famous": 0,
        "source_kind": "",
        "source_names": "",
        "posted_at": "",
        "job_json": "{}",
        "created_at": "",
        "updated_at": "",
        "category": "",
        "job_type": "",
        "seniority": "",
        "country": "",
        "min_salary": 0.0,
        "max_salary": 0.0,
        "industry": "",
        "skills_text": "",
        "is_startup": 0,
        "h1b": 0,
        "is_active": 1,
        "best_profile_id": "",
        "best_profile_name": "",
    },
    "pending_search_jobs": {
        "job_key": "",
        "query": "",
        "title": "",
        "company": "",
        "location": "",
        "work_mode": "",
        "category": "",
        "job_type": "",
        "seniority": "",
        "country": "",
        "min_salary": 0.0,
        "max_salary": 0.0,
        "score": 0,
        "opportunity_score": 0,
        "is_famous": 0,
        "is_startup": 0,
        "industry": "",
        "h1b": 0,
        "source_kind": "",
        "source_names": "",
        "posted_at": "",
        "job_json": "{}",
        "discovered_at": "",
        "skills_text": "",
        "best_profile_id": "",
        "best_profile_name": "",
    },
    "search_meta": {
        "id": 1,
        "query": "",
        "location": "",
        "total_count": 0,
        "sources_json": "[]",
        "updated_at": "",
    },
    "seen_jobs": {
        "job_key": "",
        "title": "",
        "company": "",
        "url": "",
        "source_names": "",
        "first_seen": "",
        "last_seen": "",
        "best_score": 0,
        "digested": 0,
    },
    "applications": {
        "id": "",
        "job_id": "",
        "company": "",
        "title": "",
        "location": "",
        "salary": "",
        "status": "saved",
        "notes": "",
        "follow_up_date": "",
        "sources_json": "[]",
        "job_data_json": "{}",
        "tailored_resume_json": "null",
        "cover_letter": "",
        "resume_path": "",
        "cover_letter_path": "",
        "fit_score": 0,
        "grounding_result": "",
        "saved_by": "",
        "created_at": "",
        "updated_at": "",
    },
    "status_history": {"id": None, "app_id": "", "status": "", "changed_at": ""},
    "watchlist": {
        "id": "",
        "company_name": "",
        "slug": "",
        "board_type": "",
        "target_role": "",
        "added_at": "",
        "last_checked": "",
        "active_matches_count": 0,
    },
    "discovered_boards": {
        "board_type": "",
        "slug": "",
        "company_name": "",
        "first_seen": "",
        "last_fetched": 0.0,
        "last_ok": 0.0,
        "job_count": 0,
        "fail_count": 0,
        "found_via": "",
    },
    "source_cache": {"cache_key": "", "payload": "{}", "fetched_at": 0.0},
    "source_health": {
        "source": "",
        "ok_count": 0,
        "fail_count": 0,
        "last_error": "",
        "last_ok": "",
        "last_ms": 0,
    },
    "view_filters": {
        "id": None,
        "session_id": "default",
        "job_style": "",
        "roles": "[]",
        "work_mode": "any",
        "locations": "[]",
        "relocation": 0,
        "visa_need": 0,
        "visa_countries": "[]",
        "min_salary": 0.0,
        "currency": "USD",
        "period": "year",
        "contract_types": "[]",
        "seniority": "[]",
        "company_sizes": "[]",
        "industries": "[]",
        "excluded_companies": "[]",
        "excluded_keywords": "[]",
        "posting_age": 30,
        "show_unknown_salary": 1,
        "extra_filters": "{}",
        "updated_at": "",
    },
    "radar_state": {
        "id": 1,
        "last_poll_at": None,
        "next_poll_at": None,
        "interval_seconds": 600,
        "failure_count": 0,
        "status": "idle",
        "last_error": "",
    },
    "refresh_state": {
        "source": "",
        "last_run_at": None,
        "ttl_seconds": 43200,
        "last_new_ratio": 0.0,
        "last_total": 0,
        "last_new": 0,
    },
    "dismissals": {"id": None, "job_id": "", "reason": "", "created_at": ""},
    "tombstones": {"id": None, "url_hash": "", "fingerprint": "", "deleted_at": ""},
    "deletions_log": {"id": None, "count": 0, "deleted_at": "", "acknowledged": 0},
    "signals": {
        "id": "",
        "type": "hiring_post",
        "source": "radar",
        "url": "",
        "url_hash": "",
        "author_name": "",
        "author_url": "",
        "company": "",
        "company_domain": "",
        "text": "",
        "posted_at": "",
        "likes": 0,
        "comments": 0,
        "found_at": "",
        "is_new": 1,
        "status": "fresh",
        "score": 0,
        "role_guess": "",
        "stage": "any",
        "region": "any",
        "funding_amount": "",
        "funding_round": "",
        "signal_json": "{}",
        "created_at": "",
        "updated_at": "",
    },
    "company_briefs": {
        "id": "",
        "signal_id": "",
        "company": "",
        "company_domain": "",
        "stage": "",
        "funding_summary": "",
        "brief_json": "{}",
        "learning_pack_json": "{}",
        "created_at": "",
        "updated_at": "",
    },
    "contacts": {
        "id": "",
        "signal_id": "",
        "company": "",
        "company_domain": "",
        "name": "Contact",
        "role": "",
        "title": "",
        "role_category": "",
        "email": "",
        "confidence": "Guess",
        "email_confidence": "Guess",
        "provider": "",
        "source": "",
        "source_url": "",
        "linkedin_url": "",
        "x_handle": "",
        "phone": "",
        "notes": "",
        "last_contacted_at": "",
        "found_at": "",
        "status": "new",
        "created_at": "",
        "updated_at": "",
    },
    "outreach": {
        "id": "",
        "contact_id": "",
        "signal_id": "",
        "company": "",
        "recipient_name": "",
        "recipient_email": "",
        "recipient_title": "",
        "subject": "",
        "body": "",
        "status": "draft",
        "drafted_at": "",
        "sent_at": "",
        "follow_up_due": None,
        "follow_up_sent_at": None,
        "replied_at": None,
        "reply_received_at": None,
        "reply_sentiment": "",
        "notes": "",
        "resume_path": "",
        "attached": 1,
        "created_at": "",
        "updated_at": "",
    },
    "coach_state": {"session_id": "default", "coaching_enabled": 1, "opt_out": 0, "updated_at": ""},
    "coach_events": {"session_id": "default", "trigger_id": "", "ts": ""},
    "confirmed_facts": {"id": "", "session_id": "default", "fact": "", "category": "general", "label": "user_confirmed", "created_at": ""},
    "base_resumes": {"id": "", "session_id": "default", "role_family": "", "resume_data": "{}", "approved": 0, "created_at": "", "updated_at": ""},
    "audit_log": {"id": None, "session_id": "", "user_reply": "", "action": "", "details": "", "created_at": ""},
    "guesses": {"id": None, "session_id": "", "resume_id": "", "category": "", "value": "", "confidence": 0.0, "metadata": "{}", "created_at": ""},
    "answers": {"id": None, "session_id": "", "category": "", "value": "", "user_reply": "", "created_at": ""},
    "missions": {"id": "", "created_at": "", "updated_at": "", "request": "", "intents": "", "status": "", "data_json": "{}"},
}

DURABLE_TABLES = {
    "settings", "session_state", "profile", "resume_profiles", "applications",
    "status_history", "watchlist", "discovered_boards", "outreach", "contacts",
    "company_briefs", "confirmed_facts", "base_resumes", "coach_state",
    "coach_events", "dismissals", "tombstones", "deletions_log", "missions",
    "view_filters", "radar_state", "refresh_state", "audit_log", "guesses",
    "answers", "source_health",
}
CACHE_TABLES = {
    "jobs", "job_sources", "search_jobs", "pending_search_jobs",
    "search_meta", "seen_jobs", "signals", "source_cache",
}
ALL_TABLES = DURABLE_TABLES | CACHE_TABLES

DEFAULT_SETTINGS = {
    "cleanup_grace_hours": "24",
    "method": "hybrid",
    "daily_cap": "20",
    "follow_up_days": "4",
    "first_touch_attachment": "1",
    "send_mode": "one_at_a_time",
    "resume_max_kb": "200",
    "coach_lang": "en",
}


class StoreRow(dict):
    """Dict row that also supports integer indexing and .keys()."""

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _store_dir() -> Path:
    db_path = getattr(config, "DB_PATH", "") or ""
    if db_path:
        p = Path(db_path)
        return (p.parent / f".{p.stem}_store").resolve()
    data_dir = getattr(config, "DATA_DIR", "") or ""
    if data_dir:
        return (Path(data_dir) / "store").resolve()
    return (Path.cwd() / ".jobhunter" / "store").resolve()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(payload, default=str, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class WorkspaceStore:
    """Thread-safe JSON-backed in-memory state for one workspace/store directory."""

    def __init__(self, store_dir: Path) -> None:
        self.store_dir = store_dir
        self.durable_path = store_dir / "durable.json"
        self.cache_path = store_dir / "cache.json"
        self.lock = threading.RLock()
        self.tables: dict[str, list[dict[str, Any]]] = {t: [] for t in ALL_TABLES}
        self.auto_ids: dict[str, int] = {}
        self.initialized = False
        self._load()

    def _seed_defaults(self) -> None:
        existing_keys = {r.get("key") for r in self.tables["settings"]}
        for k, v in DEFAULT_SETTINGS.items():
            if k not in existing_keys:
                self.tables["settings"].append({"key": k, "value": v})
        if not self.tables["session_state"]:
            self.tables["session_state"].append(
                {"id": 1, "current_state": "idle", "last_tool": "", "updated_at": now_iso()}
            )
        if not self.tables["radar_state"]:
            self.tables["radar_state"].append(
                {
                    "id": 1,
                    "last_poll_at": None,
                    "next_poll_at": None,
                    "interval_seconds": 600,
                    "failure_count": 0,
                    "status": "idle",
                    "last_error": "",
                }
            )

    def _load(self) -> None:
        with self.lock:
            for path, group in ((self.durable_path, DURABLE_TABLES), (self.cache_path, CACHE_TABLES)):
                if path.is_file():
                    try:
                        raw = json.loads(path.read_text(encoding="utf-8"))
                        if isinstance(raw, dict):
                            raw_tables = raw.get("tables") or {}
                            for t in group:
                                rows = raw_tables.get(t)
                                if isinstance(rows, list):
                                    self.tables[t] = [self._normalize_row(t, r) for r in rows if isinstance(r, dict)]
                            for k, v in (raw.get("auto_ids") or {}).items():
                                if k in group:
                                    self.auto_ids[k] = int(v)
                    except Exception:
                        pass
            self._seed_defaults()

    def _normalize_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        defaults = TABLE_DEFAULTS.get(table, {})
        out = copy.deepcopy(defaults)
        out.update(row)
        return out

    def ensure_initialized(self) -> None:
        with self.lock:
            self._seed_defaults()
            if not self.initialized:
                self.flush_durable()
                self.initialized = True

    def flush_durable(self) -> None:
        with self.lock:
            payload = {
                "tables": {t: self.tables[t] for t in sorted(DURABLE_TABLES)},
                "auto_ids": {k: v for k, v in self.auto_ids.items() if k in DURABLE_TABLES},
            }
            _atomic_write_json(self.durable_path, payload)

    def flush_cache(self) -> None:
        with self.lock:
            payload = {
                "tables": {t: self.tables[t] for t in sorted(CACHE_TABLES)},
                "auto_ids": {k: v for k, v in self.auto_ids.items() if k in CACHE_TABLES},
            }
            _atomic_write_json(self.cache_path, payload)

    def flush_tables(self, touched: set[str]) -> None:
        if touched & DURABLE_TABLES:
            self.flush_durable()
        if touched & CACHE_TABLES:
            self.flush_cache()

    def next_id(self, table: str) -> int:
        with self.lock:
            curr = self.auto_ids.get(table, 0)
            for r in self.tables.get(table, []):
                rv = r.get("id")
                if isinstance(rv, int) and rv > curr:
                    curr = rv
            nxt = curr + 1
            self.auto_ids[table] = nxt
            return nxt

    def reset(self) -> None:
        with self.lock:
            self.tables = {t: [] for t in ALL_TABLES}
            self.auto_ids = {}
            self._seed_defaults()
            self.flush_durable()
            self.flush_cache()


_REGISTRY_LOCK = threading.RLock()
_WORKSPACES: dict[str, WorkspaceStore] = {}


def get_store(ensure_dirs: bool = False) -> WorkspaceStore:
    sdir = _store_dir()
    key = os.path.normcase(os.path.abspath(str(sdir)))
    with _REGISTRY_LOCK:
        ws = _WORKSPACES.get(key)
        if ws is None:
            ws = WorkspaceStore(sdir)
            _WORKSPACES[key] = ws
        if ensure_dirs:
            ws.ensure_initialized()
        return ws


# ------------------------------------------------------------------ Pure-Python SQL compatibility session

class _MemCursor:
    def __init__(self, rows: list[StoreRow] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self._idx = 0
        self.rowcount = rowcount

    def fetchone(self) -> StoreRow | None:
        if self._idx < len(self._rows):
            r = self._rows[self._idx]
            self._idx += 1
            return r
        return None

    def fetchall(self) -> list[StoreRow]:
        rem = self._rows[self._idx:]
        self._idx = len(self._rows)
        return rem

    def __iter__(self) -> Iterator[StoreRow]:
        return iter(self.fetchall())


def _like_match(val: Any, pattern: Any) -> bool:
    if val is None:
        return False
    pat = str(pattern or "")
    regex = "^" + ".*".join(re.escape(part) for part in pat.split("%")) + "$"
    regex = regex.replace("_", ".")
    return bool(re.match(regex, str(val), re.I | re.S))


def _eval_expr(row: dict[str, Any], expr: str, params_iter: Iterator[Any]) -> Any:
    e = expr.strip()
    while e.startswith("(") and e.endswith(")") and _balanced_parens(e[1:-1]):
        e = e[1:-1].strip()
    if e == "?":
        return next(params_iter)
    low = e.lower()
    if low == "null":
        return None
    if low in ("datetime('now')", 'datetime("now")'):
        return now_iso()
    if low.startswith("coalesce(") and e.endswith(")"):
        inner = _split_top_level(e[9:-1], ",")
        for part in inner:
            v = _eval_expr(row, part, params_iter)
            if v is not None and v != "":
                return v
        return ""
    if low.startswith("lower(") and e.endswith(")"):
        v = _eval_expr(row, e[6:-1], params_iter)
        return "" if v is None else str(v).lower()
    if (e.startswith("'") and e.endswith("'")) or (e.startswith('"') and e.endswith('"')):
        return e[1:-1].replace("''", "'")
    try:
        if "." in e:
            return float(e)
        return int(e)
    except ValueError:
        pass
    return row.get(e)


def _balanced_parens(s: str) -> bool:
    depth = 0
    in_sq = in_dq = False
    for ch in s:
        if ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
        elif not in_sq and not in_dq:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth < 0:
                    return False
    return depth == 0


def _split_top_level(s: str, sep: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    in_sq = in_dq = False
    i = 0
    upper_s = s.upper()
    sep_u = sep.upper()
    sep_len = len(sep)
    while i < len(s):
        ch = s[i]
        if ch == "'" and not in_dq:
            if in_sq and i + 1 < len(s) and s[i + 1] == "'":
                cur.append("''")
                i += 2
                continue
            in_sq = not in_sq
            cur.append(ch)
            i += 1
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
            cur.append(ch)
            i += 1
        elif not in_sq and not in_dq:
            if ch == "(":
                depth += 1
                cur.append(ch)
                i += 1
            elif ch == ")":
                depth -= 1
                cur.append(ch)
                i += 1
            elif depth == 0 and upper_s[i:i + sep_len] == sep_u:
                if sep.isalpha() or " " in sep:
                    prev_ok = i == 0 or s[i - 1].isspace() or s[i - 1] in "()"
                    next_ok = i + sep_len >= len(s) or s[i + sep_len].isspace() or s[i + sep_len] in "()"
                    if not (prev_ok and next_ok):
                        cur.append(ch)
                        i += 1
                        continue
                parts.append("".join(cur).strip())
                cur = []
                i += sep_len
            else:
                cur.append(ch)
                i += 1
        else:
            cur.append(ch)
            i += 1
    parts.append("".join(cur).strip())
    return [p for p in parts if p]


def _consume_params(expr: str, params_iter: Iterator[Any]) -> list[Any]:
    # Consume '?' placeholders in left-to-right order respecting string literals.
    out: list[Any] = []
    in_sq = in_dq = False
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
        elif ch == "?" and not in_sq and not in_dq:
            out.append(next(params_iter))
        i += 1
    return out


def _eval_where(row: dict[str, Any], clause: str, params: tuple[Any, ...]) -> bool:
    if not clause or clause.strip() == "1=1":
        return True
    p_iter = iter(params)
    return _eval_where_node(row, clause.strip(), p_iter)


def _eval_where_node(row: dict[str, Any], node: str, p_iter: Iterator[Any]) -> bool:
    n = node.strip()
    while n.startswith("(") and n.endswith(")") and _balanced_parens(n[1:-1]):
        n = n[1:-1].strip()

    or_parts = _split_top_level(n, " OR ")
    if len(or_parts) > 1:
        res = False
        for part in or_parts:
            sub_params = tuple(_consume_params(part, p_iter))
            if not res and _eval_where(row, part, sub_params):
                res = True
        return res

    and_parts = _split_top_level(n, " AND ")
    if len(and_parts) > 1:
        res = True
        for part in and_parts:
            sub_params = tuple(_consume_params(part, p_iter))
            if res and not _eval_where(row, part, sub_params):
                res = False
        return res

    # Single predicate
    m_not_null = re.match(r"^(.+?)\s+IS\s+NOT\s+NULL$", n, re.I)
    if m_not_null:
        return _eval_expr(row, m_not_null.group(1), p_iter) is not None

    m_null = re.match(r"^(.+?)\s+IS\s+NULL$", n, re.I)
    if m_null:
        return _eval_expr(row, m_null.group(1), p_iter) is None

    m_in = re.match(r"^(.+?)\s+(NOT\s+)?IN\s*\((.+)\)$", n, re.I | re.S)
    if m_in:
        lhs = _eval_expr(row, m_in.group(1), p_iter)
        neg = bool(m_in.group(2))
        rhs_items = [_eval_expr(row, x, p_iter) for x in _split_top_level(m_in.group(3), ",")]
        hit = lhs in rhs_items
        return (not hit) if neg else hit

    m_like = re.match(r"^(.+?)\s+LIKE\s+(.+)$", n, re.I | re.S)
    if m_like:
        lhs = _eval_expr(row, m_like.group(1), p_iter)
        rhs = _eval_expr(row, m_like.group(2), p_iter)
        return _like_match(lhs, rhs)

    for op in ("!=", "<>", ">=", "<=", "=", ">", "<"):
        parts = _split_top_level(n, op)
        if len(parts) == 2:
            lhs = _eval_expr(row, parts[0], p_iter)
            rhs = _eval_expr(row, parts[1], p_iter)
            if op == "=":
                return lhs == rhs
            if op in ("!=", "<>"):
                return lhs != rhs
            if lhs is None or rhs is None:
                return False
            try:
                if op == ">=":
                    return lhs >= rhs
                if op == "<=":
                    return lhs <= rhs
                if op == ">":
                    return lhs > rhs
                if op == "<":
                    return lhs < rhs
            except TypeError:
                return str(lhs) >= str(rhs) if op == ">=" else str(lhs) <= str(rhs)
    return True


def _apply_order_by(rows: list[dict[str, Any]], order_clause: str) -> list[dict[str, Any]]:
    if not order_clause:
        return list(rows)
    specs = _split_top_level(order_clause, ",")
    out = list(rows)
    for spec in reversed(specs):
        tokens = spec.strip().split()
        col = tokens[0]
        desc = len(tokens) > 1 and tokens[1].upper() == "DESC"

        def _key(r: dict[str, Any], c: str = col) -> tuple[int, Any]:
            v = r.get(c)
            if v is None:
                return (0, "")
            if isinstance(v, (int, float)):
                return (1, v)
            return (1, str(v))

        out.sort(key=_key, reverse=desc)
    return out


class MemSession:
    """In-memory session adapter supporting protected LinkedIn SQL & legacy tests without SQLite."""

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self._last_changes = 0
        self._touched: set[str] = set()

    def _split_top_where_order_limit(self, tail: str) -> tuple[str, str, int | None]:
        where_clause = ""
        order_clause = ""
        limit_val: int | None = None
        m_lim = re.search(r"\bLIMIT\s+(\?|\d+)\s*$", tail, re.I)
        if m_lim:
            raw_l = m_lim.group(1)
            limit_val = -1 if raw_l == "?" else int(raw_l)
            tail = tail[:m_lim.start()].strip()
        m_ord = re.search(r"\bORDER\s+BY\s+(.+)$", tail, re.I | re.S)
        if m_ord:
            order_clause = m_ord.group(1).strip()
            tail = tail[:m_ord.start()].strip()
        m_wh = re.search(r"\bWHERE\s+(.+)$", tail, re.I | re.S)
        if m_wh:
            where_clause = m_wh.group(1).strip()
        return where_clause, order_clause, limit_val

    def execute(self, sql: str, params: Any = ()) -> _MemCursor:
        stmt = re.sub(r"\s+", " ", (sql or "").strip()).strip(";")
        params_tuple = tuple(params) if isinstance(params, (list, tuple)) else (params,)
        low = stmt.lower()

        if low.startswith(("create ", "alter ", "pragma ")):
            if low == "pragma journal_mode":
                return _MemCursor([StoreRow({"journal_mode": "memory"})])
            if low == "pragma busy_timeout":
                return _MemCursor([StoreRow({"busy_timeout": 5000})])
            return _MemCursor([])

        if low in ("select changes()", "select changes() as c"):
            return _MemCursor([StoreRow({"changes": self._last_changes})])

        if low.startswith("select "):
            return self._exec_select(stmt, params_tuple)
        if low.startswith("insert "):
            return self._exec_insert(stmt, params_tuple)
        if low.startswith("update "):
            return self._exec_update(stmt, params_tuple)
        if low.startswith("delete "):
            return self._exec_delete(stmt, params_tuple)
        return _MemCursor([])

    def executemany(self, sql: str, seq_of_params: list[Any]) -> _MemCursor:
        total = 0
        for p in seq_of_params:
            total += self.execute(sql, p).rowcount
        self._last_changes = total
        return _MemCursor([], rowcount=total)

    def _exec_select(self, stmt: str, params: tuple[Any, ...]) -> _MemCursor:
        m = re.match(r"^SELECT\s+(.+?)\s+FROM\s+([a-zA-Z_0-9]+)(?:\s+(.*))?$", stmt, re.I | re.S)
        if not m:
            return _MemCursor([])
        cols_expr, table, tail = m.group(1).strip(), m.group(2).lower(), (m.group(3) or "").strip()
        where_clause, order_clause, limit_val = self._split_top_where_order_limit(tail)
        if limit_val == -1 and params:
            limit_val = int(params[-1])
            where_params = params[:-1]
        else:
            where_params = params

        with self.store.lock:
            rows = [r for r in self.store.tables.get(table, []) if _eval_where(r, where_clause, where_params)]
        rows = _apply_order_by(rows, order_clause)

        m_cnt = re.match(r"^COUNT\(\*\)(?:\s+as\s+([a-zA-Z_0-9]+))?$", cols_expr, re.I)
        if m_cnt:
            alias = m_cnt.group(1) or "count"
            return _MemCursor([StoreRow({alias: len(rows)})])

        if limit_val is not None:
            rows = rows[:max(0, limit_val)]

        if cols_expr.strip() == "1":
            return _MemCursor([StoreRow({"1": 1}) for _ in rows])
        if cols_expr.strip() == "*":
            return _MemCursor([StoreRow(r) for r in rows])

        col_list = [c.strip().split()[-1] for c in cols_expr.split(",")]
        out_rows = [StoreRow({col: r.get(col) for col in col_list}) for r in rows]
        return _MemCursor(out_rows)

    def _key_columns(self, table: str) -> tuple[str, ...]:
        pk_map = {
            "settings": ("key",),
            "session_state": ("id",),
            "radar_state": ("id",),
            "search_meta": ("id",),
            "profile": ("id",),
            "resume_profiles": ("id",),
            "jobs": ("id",),
            "search_jobs": ("job_key",),
            "pending_search_jobs": ("job_key",),
            "seen_jobs": ("job_key",),
            "applications": ("id",),
            "watchlist": ("id",),
            "discovered_boards": ("board_type", "slug"),
            "source_cache": ("cache_key",),
            "source_health": ("source",),
            "refresh_state": ("source",),
            "view_filters": ("session_id",),
            "signals": ("id",),
            "company_briefs": ("id",),
            "contacts": ("id",),
            "outreach": ("id",),
            "coach_state": ("session_id",),
            "coach_events": ("session_id", "trigger_id"),
            "confirmed_facts": ("id",),
            "base_resumes": ("id",),
            "missions": ("id",),
        }
        return pk_map.get(table, ())

    def _exec_insert(self, stmt: str, params: tuple[Any, ...]) -> _MemCursor:
        or_ignore = bool(re.match(r"^INSERT\s+OR\s+IGNORE\s+", stmt, re.I))
        or_replace = bool(re.match(r"^INSERT\s+OR\s+REPLACE\s+", stmt, re.I))
        clean_stmt = re.sub(r"^INSERT(?:\s+OR\s+(?:IGNORE|REPLACE))?\s+INTO\s+", "", stmt, flags=re.I)

        m_conflict = re.search(r"\bON\s+CONFLICT\b.*?\bDO\s+UPDATE\s+SET\s+(.+)$", clean_stmt, re.I | re.S)
        conflict_set = ""
        if m_conflict:
            conflict_set = m_conflict.group(1).strip()
            clean_stmt = clean_stmt[:m_conflict.start()].strip()

        m = re.match(r"^([a-zA-Z_0-9]+)\s*\(([^)]+)\)\s*VALUES\s*(.+)$", clean_stmt, re.I | re.S)
        if not m:
            return _MemCursor([], rowcount=0)
        table = m.group(1).lower()
        cols = [c.strip() for c in m.group(2).split(",")]
        tuples_raw = _split_value_tuples(m.group(3).strip())

        p_iter = iter(params)
        inserted = 0
        with self.store.lock:
            tbl = self.store.tables.setdefault(table, [])
            pks = self._key_columns(table)
            for tup in tuples_raw:
                exprs = _split_top_level(tup, ",")
                row_vals = {c: _eval_expr({}, ex, p_iter) for c, ex in zip(cols, exprs)}
                row = self.store._normalize_row(table, row_vals)
                if table in ("status_history", "dismissals", "tombstones", "deletions_log", "audit_log", "guesses", "answers", "job_sources") and row.get("id") is None:
                    row["id"] = self.store.next_id(table)

                # Unique checks
                if table == "job_sources" and row.get("url_hash"):
                    dup_idx = next((i for i, x in enumerate(tbl) if x.get("url_hash") == row["url_hash"]), None)
                    if dup_idx is not None:
                        if or_ignore:
                            continue
                        if m_conflict or or_replace:
                            tbl[dup_idx].update({k: v for k, v in row.items() if k != "id"})
                            inserted += 1
                            continue
                        raise ValueError(f"Duplicate url_hash in job_sources: {row['url_hash']}")

                existing_idx = None
                if pks:
                    for i, existing in enumerate(tbl):
                        if all(existing.get(k) == row.get(k) for k in pks):
                            existing_idx = i
                            break

                if existing_idx is not None:
                    if or_ignore:
                        continue
                    if or_replace or m_conflict:
                        if conflict_set:
                            for assign in _split_top_level(conflict_set, ","):
                                ak, av = assign.split("=", 1)
                                ak = ak.strip()
                                av = av.strip()
                                if av.lower().startswith("excluded."):
                                    tbl[existing_idx][ak] = row.get(av.split(".", 1)[1])
                        else:
                            tbl[existing_idx] = row
                        inserted += 1
                    else:
                        raise ValueError(f"Duplicate primary key in {table}")
                else:
                    tbl.append(row)
                    inserted += 1
            self._touched.add(table)
        self._last_changes = inserted
        return _MemCursor([], rowcount=inserted)

    def _exec_update(self, stmt: str, params: tuple[Any, ...]) -> _MemCursor:
        m = re.match(r"^UPDATE\s+([a-zA-Z_0-9]+)\s+SET\s+(.+?)(?:\s+WHERE\s+(.+))?$", stmt, re.I | re.S)
        if not m:
            return _MemCursor([], rowcount=0)
        table, set_clause, where_clause = m.group(1).lower(), m.group(2).strip(), (m.group(3) or "").strip()
        assigns = _split_top_level(set_clause, ",")

        p_iter = iter(params)
        set_pairs: list[tuple[str, Any]] = []
        for assign in assigns:
            k, vexpr = assign.split("=", 1)
            set_pairs.append((k.strip(), _eval_expr({}, vexpr.strip(), p_iter)))
        where_params = tuple(p_iter)

        changed = 0
        with self.store.lock:
            for r in self.store.tables.get(table, []):
                if _eval_where(r, where_clause, where_params):
                    for k, v in set_pairs:
                        r[k] = v
                    changed += 1
            self._touched.add(table)
        self._last_changes = changed
        return _MemCursor([], rowcount=changed)

    def _exec_delete(self, stmt: str, params: tuple[Any, ...]) -> _MemCursor:
        m = re.match(r"^DELETE\s+FROM\s+([a-zA-Z_0-9]+)(?:\s+WHERE\s+(.+))?$", stmt, re.I | re.S)
        if not m:
            return _MemCursor([], rowcount=0)
        table, where_clause = m.group(1).lower(), (m.group(2) or "").strip()
        with self.store.lock:
            tbl = self.store.tables.get(table, [])
            kept = [r for r in tbl if not _eval_where(r, where_clause, params)]
            deleted = len(tbl) - len(kept)
            self.store.tables[table] = kept
            self._touched.add(table)
        self._last_changes = deleted
        return _MemCursor([], rowcount=deleted)


def _split_value_tuples(raw: str) -> list[str]:
    tuples: list[str] = []
    depth = 0
    in_sq = in_dq = False
    start = -1
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "'" and not in_dq:
            if in_sq and i + 1 < len(raw) and raw[i + 1] == "'":
                i += 2
                continue
            in_sq = not in_sq
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
        elif not in_sq and not in_dq:
            if ch == "(":
                if depth == 0:
                    start = i + 1
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and start != -1:
                    tuples.append(raw[start:i])
                    start = -1
        i += 1
    return tuples


@contextmanager
def open_session(ensure_dirs: bool = True) -> Iterator[MemSession]:
    ws = get_store(ensure_dirs=ensure_dirs)
    sess = MemSession(ws)
    with ws.lock:
        yield sess
        ws.flush_tables(sess._touched)
