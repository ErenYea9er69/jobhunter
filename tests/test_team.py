"""The CEO team: roster, router, Reviewer checks, delegation, and the anti-hallucination gates."""

import asyncio
import datetime

import pytest

import mcp_server
from jh import db, util
from jh.team import directives, qa, roles, router
from jh.team.surface import TEAM_TOOLS


@pytest.fixture
def market(net):
    net.fixture("boards-api.greenhouse.io/v1/boards/adyen/jobs", "greenhouse_adyen.json")
    net.fixture("workingnomads.com/api/exposed_jobs", "workingnomads.json")
    return net


def run(tools, request, **hints):
    res = tools.call("ceo_run", request=request, hints=hints or None)
    assert res["status"] in ("ok", "partial"), res
    return res["data"]


def first_job(tools):
    return tools.call("search_jobs", query="backend engineer", limit=5)["data"]["jobs"][0]["job_id"]


# ------------------------------------------------------------------ roster and surface

def test_every_tool_has_exactly_one_owner(server):
    names = {t.name for t in asyncio.run(server.list_tools())}
    specialist = {n for n in names if n not in TEAM_TOOLS}
    owned = {t for r in roles.ROSTER.values() for t in r.tools}
    assert specialist == owned
    all_tools = [t for r in roles.ROSTER.values() for t in r.tools]
    assert len(all_tools) == len(set(all_tools))


def test_team_surface_shows_only_ceo_tools(ws, net):
    server = mcp_server.create_server(str(ws), surface="team")
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == set(TEAM_TOOLS)


def test_full_surface_shows_everything(server):
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert set(TEAM_TOOLS) <= names and "search_jobs" in names and len(names) >= 45


def test_hidden_tools_still_work_through_the_ceo(ws, net):
    server = mcp_server.create_server(str(ws), surface="team")
    from conftest import ToolClient
    t = ToolClient(server)
    res = t.call("ceo_delegate", tool="list_resumes")
    assert res["success"] and res["data"]["employee"] == "ops" and res["data"]["result"]["count"] == 1


def test_every_role_has_a_prompt_and_workspace_can_override(ws):
    for key in roles.ROSTER:
        assert len(roles.role_prompt(key, ws)) > 40
    (ws / "prompts" / "team").mkdir(parents=True)
    (ws / "prompts" / "team" / "scout.md").write_text("Custom scout prompt for tests.", encoding="utf-8")
    assert roles.role_prompt("scout", ws) == "Custom scout prompt for tests."


def test_directive_carries_limits_and_a_prompt(ws):
    d = directives.make("writer", "Write a letter.", inputs={"job_id": "abc", "empty": ""}, with_prompt=True, workspace=str(ws))
    assert "empty" not in d["inputs"] and any("Do not guess" in x for x in d["limits"])
    assert "Document Writer" in d["prompt"] and "Write a letter." in d["prompt"]


# ------------------------------------------------------------------ router

@pytest.mark.parametrize("text,intents,role,place", [
    ("Find me backend engineer jobs in Tunisia", ["hunt"], "backend engineer", "Tunisia"),
    ("find small companies hiring python developers in Sfax", ["hunt"], "python developer", "Sfax"),
    ("cherche des offres de développeur à Tunis", ["hunt"], "développeur", "Tunis"),
    ("prepare an application for job 0123456789abcdef", ["apply"], "", ""),
    ("what's my status today?", ["status"], "", ""),
    ("set me up", ["setup"], "", ""),
    ("recheck 0123456789abcdef", ["recheck"], "", ""),
    ("find me a job and apply", ["hunt", "apply"], "", ""),
    ("hello there", ["help"], "", ""),
])
def test_router_understands_requests(text, intents, role, place):
    p = router.parse(text)
    assert p.intents == intents and p.role == role and p.location == place


def test_router_marks_small_employers_and_takes_job_id():
    p = router.parse("find small local companies hiring")
    assert p.small and "hunt" in p.intents
    assert router.parse("cover letter for 0123456789abcdef").job_id == "0123456789abcdef"


def test_router_makes_plural_titles_singular_but_keeps_sales_and_devops():
    assert router.parse("find backend engineers jobs").role == "backend engineer"
    assert router.parse("find sales jobs").role == "sales"
    assert router.parse("find devops jobs").role == "devops"
    assert router.parse("find data analysts jobs").role == "data analyst"


def test_router_never_invents_a_job_id():
    assert router.parse("write a cover letter").job_id == ""


# ------------------------------------------------------------------ Reviewer: jobs

PROFILE = {"skills": ["Python", "Docker"], "name": "Ahmed Ben Salah"}


def test_job_review_blocks_junk_and_unsafe_links():
    assert qa.review_job({"title": "N/A", "company": "X", "url": "https://x.org/1"}).blocked
    assert qa.review_job({"title": "Dev", "company": "X", "url": ""}).blocked
    assert qa.review_job({"title": "Developer", "company": "X", "url": "http://127.0.0.1/admin"}).blocked
    ok = qa.review_job({"title": "Backend Developer", "company": "Acme", "url": "https://acme.com/jobs/1"})
    assert ok.verdict == "pass"


def test_job_review_flags_old_future_and_foreign_jobs():
    old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=90)).isoformat()
    fut = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat()
    base = {"title": "Backend Developer", "company": "Acme", "url": "https://acme.com/jobs/1"}
    assert "older_than_limit" in [f["code"] for f in qa.review_job({**base, "posted_at": old}, prefs={"max_age_days": 30}).findings]
    assert "future_date" in [f["code"] for f in qa.review_job({**base, "posted_at": fut}).findings]
    foreign = qa.review_job({**base, "location": "Paris, France", "work_mode": "Onsite"}, prefs={"target_countries": ["Tunisia"]})
    assert "outside_targets" in [f["code"] for f in foreign.findings]
    remote = qa.review_job({**base, "location": "Paris, France", "work_mode": "Remote"}, prefs={"target_countries": ["Tunisia"]})
    assert "outside_targets" not in [f["code"] for f in remote.findings]


def test_skill_claims_are_audited_against_resume_and_posting():
    job = {"title": "Backend Developer", "company": "Acme", "url": "https://acme.com/1", "description": "We use Python and Kubernetes.",
           "matched_skills": ["Python", "Kubernetes", "Docker"]}
    rev = qa.review_job(job, profile=PROFILE)
    assert rev.adjusted["matched_skills"] == ["Python"]      # Kubernetes not on resume, Docker not in posting
    assert "skill_claim_removed" in [f["code"] for f in rev.findings]


def test_high_score_without_evidence_is_flagged():
    rev = qa.review_job({"title": "Backend Developer", "company": "Acme", "url": "https://acme.com/1", "score": 92, "matched_skills": []})
    assert "score_without_evidence" in [f["code"] for f in rev.findings]


def test_duplicates_are_blocked():
    j = {"title": "Backend Developer", "company": "Acme", "url": "https://acme.com/1"}
    pairs = qa.review_jobs([j, dict(j)])
    assert [r.blocked for _, r in pairs] == [False, True]


# ------------------------------------------------------------------ Reviewer: live links

def _http_error(status):
    e = util.HttpError(f"HTTP {status}")
    e.status = status
    return e


def _fetch_raising(err):
    def f(url):
        raise err
    return f


JOB = {"title": "Backend Engineer", "company": "Acme"}


def test_live_check_dead_on_404_and_410():
    for code in (404, 410):
        assert qa.live_check("https://acme.com/j/1", JOB, fetch=_fetch_raising(_http_error(code)))["state"] == "dead"


def test_live_check_does_not_call_blocking_sites_dead():
    for code in (403, 429, 999):
        assert qa.live_check("https://acme.com/j/1", JOB, fetch=_fetch_raising(_http_error(code)))["state"] == "unconfirmed"
    assert qa.live_check("https://acme.com/j/1", JOB, fetch=_fetch_raising(util.HttpError("network error")))["state"] == "unreachable"


def test_live_check_reads_visible_text_not_scripts():
    spa = "<html><script>var t='This job is no longer available';</script><body><h1>Backend Engineer</h1><p>Acme builds APIs.</p></body></html>"
    assert qa.live_check("https://acme.com/j/1", JOB, fetch=lambda u: spa)["state"] == "live"
    closed = "<html><body><h1>Backend Engineer</h1><p>Sorry, this position has been filled.</p></body></html>"
    assert qa.live_check("https://acme.com/j/1", JOB, fetch=lambda u: closed)["state"] == "dead"
    fr = "<html><body><p>Cette offre n'est plus disponible.</p></body></html>"
    assert qa.live_check("https://acme.com/j/1", JOB, fetch=lambda u: fr)["state"] == "dead"


def test_live_check_uses_valid_through_and_jobposting_data():
    def page(valid):
        return ('<script type="application/ld+json">{"@type":"JobPosting","title":"Backend Engineer","validThrough":"%s",'
                '"hiringOrganization":{"name":"Acme"}}</script>' % valid)
    assert qa.live_check("https://acme.com/j/1", JOB, fetch=lambda u: page("2020-01-01"))["state"] == "dead"
    assert qa.live_check("https://acme.com/j/1", JOB, fetch=lambda u: page("2099-01-01"))["state"] == "live"


def test_live_check_unconfirmed_when_page_shows_nothing_and_skips_unsafe_urls():
    assert qa.live_check("https://acme.com/j/1", JOB, fetch=lambda u: "<html><div id=app></div></html>")["state"] == "unconfirmed"
    assert qa.live_check("http://127.0.0.1/x", JOB)["state"] == "skipped"


# ------------------------------------------------------------------ Reviewer: documents

@pytest.fixture
def profile(server):
    """The active resume profile, loaded by the engine at start-up."""
    return db.get_profile()


def test_contact_lines_are_not_treated_as_claims(profile):
    text = ("Ahmed Ben Salah\nahmed@example.com | +216 20 000 000 | Tunis, Tunisia\n\n"
            "I build REST APIs in Python and FastAPI. At Vermeg I reduced PostgreSQL query latency by 45%.\n\nBest regards,\nAhmed Ben Salah")
    rev = qa.review_document(text, kind="cover_letter", profile=profile, job={"company": "Acme"})
    assert not rev.blocked, rev.findings


def test_invented_numbers_and_employers_are_blocked_and_removed(profile):
    text = ("I build REST APIs in Python and FastAPI at Vermeg.\n"
            "At Google I led a team of 40 engineers and cut latency by 93%.\n"
            "I reduced PostgreSQL query latency by 45%.")
    rev = qa.review_document(text, kind="other", profile=profile)
    assert rev.blocked and "unsupported_claims" in [f["code"] for f in rev.findings]
    cleaned, removed = qa.remove_unsupported(text, rev)
    assert any("Google" in r for r in removed) and "Google" not in cleaned and "45%" in cleaned
    assert not qa.review_document(cleaned, kind="other", profile=profile).blocked


RESUME_OK = """AHMED BEN SALAH
ahmed@example.com | +216 20 000 000 | Tunis, Tunisia

PROFESSIONAL EXPERIENCE
Software Engineer - Vermeg, Tunis, Tunisia  [2022-01 - Present]
  * Reduced PostgreSQL query latency by 45% by redesigning indexes and caching hot paths in Redis.
Junior Developer - Sofrecom, Tunis, Tunisia  [2020-06 - 2021-12]
  * Developed Django REST endpoints used by 3 internal teams.

EDUCATION
Bachelor of Engineering in Computer Science (2020)
"""


def test_real_resume_headers_pass_the_structure_check(profile):
    rev = qa.review_document(RESUME_OK, kind="resume", profile=profile)
    assert not rev.blocked, rev.findings


def test_date_ranges_are_not_mistaken_for_phone_numbers():
    text = "Staff Engineer - Google [2018-01 - 2020-05]\n+216 20 000 000 | Tunis\nI write code."
    out = qa.strip_contact_lines(text, {})
    assert "Google" in out and "+216" not in out


def test_invented_employer_header_is_blocked_and_removed(profile):
    fake = RESUME_OK.replace("Junior Developer - Sofrecom, Tunis, Tunisia  [2020-06 - 2021-12]",
                             "Staff Engineer - Google, Mountain View, USA  [2018-01 - 2020-05]")
    rev = qa.review_document(fake, kind="resume", profile=profile)
    assert rev.blocked and "unsupported_header" in [f["code"] for f in rev.findings]
    cleaned, removed = qa.remove_unsupported(fake, rev)
    assert any("Google" in r for r in removed) and "Google" not in cleaned and "Vermeg" in cleaned


def test_right_employer_with_wrong_dates_is_blocked(profile):
    wrong = RESUME_OK.replace("[2022-01 - Present]", "[2015-01 - Present]")
    assert "unsupported_header" in [f["code"] for f in qa.review_document(wrong, kind="resume", profile=profile).findings]


def test_invented_degree_is_blocked(profile):
    fake = RESUME_OK.replace("Bachelor of Engineering in Computer Science (2020)", "PhD in Machine Learning, MIT (2019)")
    assert "unsupported_header" in [f["code"] for f in qa.review_document(fake, kind="resume", profile=profile).findings]


def test_placeholders_and_empty_drafts_are_blocked(profile):
    assert qa.review_document("Dear [Company Name], I am a Python developer with experience in many things.", profile=profile).blocked
    assert qa.review_document("", profile=profile).blocked


def test_letter_must_name_the_employer(profile):
    text = "I build REST APIs in Python and FastAPI at Vermeg. I reduced PostgreSQL query latency by 45% using Redis. " * 4
    rev = qa.review_document(text, kind="cover_letter", profile=profile, job={"company": "Globex"})
    assert "company_not_named" in [f["code"] for f in rev.findings]


def test_envelope_review_maps_status():
    assert qa.review_envelope({"status": "error", "error": {"code": "x", "message": "bad"}}).blocked
    assert qa.review_envelope({"status": "partial", "warnings": ["a source failed"]}).verdict == "warn"
    assert qa.review_envelope({"status": "ok"}).verdict == "pass"


# ------------------------------------------------------------------ CEO: hunting

def test_hunt_returns_reviewed_jobs_with_provenance(tools, market):
    d = run(tools, "find backend engineer jobs", limit=5)
    assert d["status"] in ("done", "partial") and d["jobs"], d["report"]
    j = d["jobs"][0]
    assert j["verification"]["review"] in ("pass", "warn") and j["verification"]["link"]
    assert j["provenance"]["tool"] == "search_jobs" and j["provenance"]["correlation_id"]
    tools_used = [s["tool"] for s in d["team"]]
    assert "search_jobs" in tools_used and "review_jobs" in tools_used
    assert "Jobs that passed review" in d["report"] and j["job_id"] in d["report"]
    assert d["relay_rules"] and d["mission_id"].startswith("m-")


def test_unread_links_are_reported_as_not_verified(tools, market):
    d = run(tools, "find backend engineer jobs", limit=25, verify_live=False)
    assert any("Live link checks were turned off" in x for x in d["not_verified"])
    assert all(j["verification"]["link"] == "not_checked" for j in d["jobs"])


def test_dead_posting_is_removed_before_the_client_sees_it(tools, market, monkeypatch):
    seen = {}

    def fake_live(url, job, fetch=None, timeout=10):
        seen.setdefault("first", job.get("title"))
        return {"state": "dead", "detail": "The page returns HTTP 404."} if job.get("title") == seen["first"] else {"state": "live", "detail": "ok"}
    monkeypatch.setattr(qa, "live_check", fake_live)
    d = run(tools, "find backend engineer jobs", limit=10)
    assert d["removed_by_reviewer"] and "HTTP 404" in d["removed_by_reviewer"][0]["reasons"][0]
    assert all(j["title"] != seen["first"] for j in d["jobs"])
    assert "Removed by the Reviewer" in d["report"]


def test_empty_search_widens_in_steps_and_never_invents_jobs(tools, net):
    d = run(tools, "find quantum basket weaving jobs in Atlantis")
    searches = [s for s in d["team"] if s["tool"] == "search_jobs"]
    assert len(searches) == 4 and "fresh read" in searches[-1]["objective"]      # as asked, relaxed, any location, then a fresh read
    assert d["jobs"] == [] and d["status"] in ("blocked", "needs_input", "partial")
    assert any("No job came back" in b for b in d["blocked"])


def test_small_employer_mode_reports_the_split_and_a_next_step(tools, market):
    d = run(tools, "find small companies hiring backend engineers", small_employers=True)
    assert d["understood"]["small_employers"] is True
    assert "small_employer_jobs" in d["summary"]
    assert any("Regional Boards" in n or "JOOBLE" in n for n in d["next_steps"])


def test_hunt_asks_for_a_country_when_none_is_known(tools, market, monkeypatch):
    from jh import regions
    monkeypatch.setattr(regions, "resolve_targets", lambda *a, **k: [])
    d = run(tools, "find backend engineer jobs")
    assert any("Where do you want to work" in x for x in d["decisions_needed"])


# ------------------------------------------------------------------ CEO: applying and writing

def test_apply_flow_reviews_every_document_and_saves_approved_files(tools, market):
    jid = first_job(tools)
    d = run(tools, f"prepare an application for job {jid}", job_id=jid)
    kinds = {x["kind"] for x in d["documents"]}
    assert "cover letter" in kinds and "tailored resume" in kinds
    for doc in d["documents"]:
        assert doc["review"]["verdict"] in ("pass", "warn", "block")
        assert doc["provenance"]["correlation_id"]
    letter = next(x for x in d["documents"] if x["kind"] == "cover letter")
    assert letter["review"]["verdict"] != "block", letter["review"]
    import pathlib
    assert pathlib.Path(letter["approved_file"]).read_text(encoding="utf-8").strip()
    resume = next(x for x in d["documents"] if x["kind"] == "tailored resume")
    assert resume["review"]["verdict"] != "block" and not resume.get("removed_lines")   # real headers are not removed
    assert any("never submit" in n for n in d["next_steps"])
    assert any("employer" in x for x in d["not_verified"])


def test_apply_makes_a_writing_work_order_with_a_briefed_prompt(tools, market):
    jid = first_job(tools)
    d = run(tools, f"write a cover letter for {jid}", job_id=jid, polish=True)
    wo = d["work_orders"][0]
    assert wo["task"] == "cover_letter" and wo["submit_with"]["tool"] == "ceo_submit_work"
    assert "Document Writer" in wo["prompt"] and "TASK" in wo["prompt"] and "LIMITS" in wo["prompt"]


def test_apply_stops_when_the_posting_is_dead(tools, market, monkeypatch):
    jid = first_job(tools)
    monkeypatch.setattr(qa, "live_check", lambda url, job, **k: {"state": "dead", "detail": "The page returns HTTP 404."})
    d = run(tools, f"prepare an application for job {jid}", job_id=jid)
    assert d["documents"] == [] and any("blocked" in b.lower() for b in d["blocked"])
    assert "writer" not in [s["employee"] for s in d["team"]]


def test_apply_without_a_job_asks_instead_of_guessing(tools, market):
    d = run(tools, "write me a cover letter")
    assert d["status"] == "needs_input" and any("Which job" in x for x in d["decisions_needed"]) and d["documents"] == []


def test_unknown_job_id_is_reported_not_invented(tools, market):
    d = run(tools, "prepare an application", job_id="ffffffffffffffff")
    assert d["documents"] == [] and any("could not be opened" in b for b in d["blocked"])


def test_interview_prep_is_marked_as_only_error_checked(tools, market):
    jid = first_job(tools)
    d = run(tools, f"interview prep for {jid}", job_id=jid)
    assert any(x["kind"] == "interview prep" for x in d["documents"])
    assert any("Interview stories were not checked" in x for x in d["not_verified"])


# ------------------------------------------------------------------ submitting model-written drafts

def test_good_draft_is_approved_and_saved(tools, market):
    jid = first_job(tools)
    mission = run(tools, f"write a cover letter for {jid}", job_id=jid, polish=True)
    draft = ("I build REST APIs in Python and FastAPI. At Vermeg I reduced PostgreSQL query latency by 45% with Redis caching, "
             "and I containerized 6 services with Docker. I would bring that work to the team. " * 2)
    res = tools.call("ceo_submit_work", mission_id=mission["mission_id"], task="cover_letter", text=draft, job_id=jid)["data"]
    assert res["approved"] is True and res["approved_file"]
    saved = tools.call("ceo_status", mission_id=mission["mission_id"])["data"]
    assert any("written by the CEO's model" in d["kind"] for d in saved["data"]["documents"])


def test_fabricated_lines_are_removed_from_a_draft(tools, market):
    jid = first_job(tools)
    draft = ("I build REST APIs in Python and FastAPI at Vermeg.\n"
             "At Google I led 40 engineers and cut latency by 93%.\n"
             "I reduced PostgreSQL query latency by 45% using Redis.")
    res = tools.call("ceo_submit_work", mission_id="", task="cover_letter", text=draft, job_id=jid, kind="other")["data"]
    assert res["approved"] is True and any("Google" in r for r in res["removed_lines"]) and "Google" not in res["text"]
    assert res["verdict"] == "warn"


def test_fully_fabricated_draft_is_rejected(tools, market):
    jid = first_job(tools)
    draft = "At Google I led 40 engineers and cut latency by 93%.\nAt Amazon I managed a 12 million dollar budget and 300 staff."
    res = tools.call("ceo_submit_work", mission_id="", task="cover_letter", text=draft, job_id=jid, kind="other")["data"]
    assert res["approved"] is False and res["verdict"] == "block" and "Do not show" in res["what_to_do"]


def test_unknown_mission_is_an_error(tools):
    res = tools.call("ceo_submit_work", mission_id="m-nope", task="cover_letter", text="x" * 80)
    assert res["status"] == "error" and res["error"]["code"] == "not_found"


# ------------------------------------------------------------------ recheck, delegate, status, setup

def test_recheck_job_reads_the_live_page(tools, market, monkeypatch):
    jid = first_job(tools)
    monkeypatch.setattr(qa, "live_check", lambda url, job, **k: {"state": "dead", "detail": "The page returns HTTP 410."})
    res = tools.call("ceo_recheck", job_id=jid)["data"]
    assert res["job"]["link"]["state"] == "dead"


def test_recheck_text_catches_fabrication(tools, market):
    res = tools.call("ceo_recheck", text="At Google I led 40 engineers and cut latency by 93%. I also hold a PhD from MIT.")["data"]
    assert res["document"]["verdict"] == "block"


def test_recheck_mission_reports_what_changed(tools, market, monkeypatch):
    d = run(tools, "find backend engineer jobs", limit=3, verify_live=False)
    monkeypatch.setattr(qa, "live_check", lambda url, job, **k: {"state": "dead", "detail": "The page returns HTTP 404."})
    res = tools.call("ceo_recheck", mission_id=d["mission_id"])["data"]
    assert res["checked"] >= 1 and res["changes"] and "no longer passes" in res["changes"][0]


def test_recheck_needs_something_to_check(tools):
    assert tools.call("ceo_recheck")["error"]["code"] == "invalid_input"
    assert tools.call("ceo_recheck", job_id="ffffffffffffffff")["error"]["code"] == "not_found"


def test_delegate_checks_ownership_and_reviews_job_results(tools, market):
    bad = tools.call("ceo_delegate", tool="search_jobs", employee="writer", arguments={"query": "x"})
    assert bad["status"] == "error"
    assert tools.call("ceo_delegate", tool="ceo_run")["status"] == "error"
    res = tools.call("ceo_delegate", tool="search_jobs", employee="scout", arguments={"query": "backend engineer", "limit": 5})["data"]
    assert res["employee"] == "scout" and res["job_review"] and res["provenance"]["correlation_id"]


def test_delegate_keeps_the_error_when_the_employee_fails(tools):
    res = tools.call("ceo_delegate", tool="discover_job_source", arguments={"url": "ftp://x"})
    assert res["status"] == "partial" and res["data"]["error"]["code"] == "invalid_input" and res["data"]["review"]["verdict"] == "block"


def test_delegate_reviews_generated_letters(tools, market):
    jid = first_job(tools)
    res = tools.call("ceo_delegate", tool="cover_letter", arguments={"job_id": jid})["data"]
    assert "document_review" in res and res["employee"] == "writer"


def test_plan_previews_without_running(tools, market):
    res = tools.call("ceo_plan", request="find small companies hiring python developers in Sfax")["data"]
    assert res["understood"]["intents"] == ["hunt"] and any(o["tool"] == "search_jobs" for o in res["outline"])
    assert not any("search_jobs" in c for c in market.calls)
    need = tools.call("ceo_plan", request="write a cover letter")["data"]
    assert need["needs"]


def test_setup_applies_preferences_and_adds_sources(tools, market):
    d = run(tools, "set me up", preferences={"target_countries": ["Tunisia"], "work_mode": "Any"})
    assert any("Preferences saved" in f for f in d["report"].splitlines()) or "target_countries" in d["report"]
    assert any("Tunisia" in line for line in d["report"].splitlines())
    bad = run(tools, "set me up", preferences={"work_mode": "Spaceship"})
    assert any("not saved" in b.lower() for b in bad["blocked"])


def test_status_and_help_work_on_an_empty_tracker(tools):
    d = run(tools, "what is my status today")
    assert d["status"] in ("done", "partial") and "Tracked applications: 0" in d["report"]
    h = run(tools, "hello")
    assert h["understood"]["intents"] == ["help"] and h["next_steps"]


def test_missions_are_saved_and_listed(tools, market):
    d = run(tools, "find backend engineer jobs", limit=3)
    listing = tools.call("ceo_status")["data"]
    assert listing["recent_missions"][0]["id"] == d["mission_id"] and listing["has_resume"]
    assert tools.call("ceo_status", mission_id=d["mission_id"])["data"]["data"]["report"] == d["report"]


def test_team_roster_tool(tools):
    res = tools.call("ceo_team", with_prompts=True)["data"]
    assert [e["key"] for e in res["employees"]][:1] == ["ceo"] and all(e["prompt"] for e in res["employees"])


def test_empty_request_is_rejected(tools):
    assert tools.call("ceo_run", request="  ")["error"]["code"] == "invalid_input"
