import json
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ["JH_DATA_DIR"] = tempfile.mkdtemp()
os.environ["JH_SEARCH_DEADLINE"] = "5"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jh import ats, db, dedup, exporters, pipeline, resume_parser as rp, scoring, skills, sources, refit, tracker, util  # noqa: E402
from jh.demo import DEMO_PROFILE  # noqa: E402

JOB = {"id": "j", "title": "Senior Backend Engineer", "company": "Acme",
       "description": "Requirements:\nPython, Postgres, Docker, Kubernetes. 4+ years of experience.\nNice to have: Go"}
RESUME = """JANE DOE
Austin, TX | jane@mail.com | (512) 555-0142

EXPERIENCE
Senior Engineer | Acme Corp | Jan 2021 - Present
- Built a Python and Postgres billing service for 2M requests per day.
- Reduced deploy time by 60% with Docker.
Software Engineer, Beta Systems
Jun 2018 - Dec 2020
- Developed REST APIs in Node.js.

EDUCATION
B.S. Computer Science, University of Texas at Austin, 2018

SKILLS
Python, Docker, Postgres
"""


class Base(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.purge_all()
        sources.reset_breakers()


class SkillTests(Base):
    def test_no_false_positives_from_common_words(self):
        text = "Our go-to-market team will go to the next quarter near the express lane at a spring event. Excel at teamwork."
        self.assertEqual(skills.extract(text), [])

    def test_real_mentions_found(self):
        self.assertEqual(skills.extract("Python, Go, Postgres and Next.js"), ["Go", "Next.js", "PostgreSQL", "Python"])

    def test_weights_split_required_and_preferred(self):
        w = skills.extract_weighted("Requirements:\nPython\nNice to have:\nKubernetes")
        self.assertGreater(w["Python"], w["Kubernetes"])


class DedupTests(Base):
    def test_different_roles_same_company_stay_separate(self):
        jobs = [{"title": t, "company": "Stripe", "source": "Greenhouse", "url": f"u{i}", "location": "Remote"}
                for i, t in enumerate(["Backend Engineer, Billing", "Frontend Engineer, Dashboard", "Data Scientist, Risk"])]
        self.assertEqual(len(dedup.merge_jobs(jobs)), 3)

    def test_true_duplicates_merge_and_prefer_ats_link(self):
        jobs = [{"title": "Senior Backend Engineer", "company": "Stripe Inc", "source": "Indeed", "url": "https://i/1", "location": "Remote, US"},
                {"title": "Senior Backend Engineer", "company": "Stripe", "source": "Greenhouse", "url": "https://g/1?utm_source=x", "location": "Remote"}]
        out = dedup.merge_jobs(jobs)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "Greenhouse")
        self.assertEqual(out[0]["url"], "https://g/1")
        self.assertEqual(len(out[0]["sources"]), 2)


class ScoreTests(Base):
    def test_unrelated_job_scores_low(self):
        r = scoring.score_job({"title": "Pastry Chef", "description": "bake bread"}, DEMO_PROFILE)
        self.assertLess(r["score"], 40)

    def test_matching_job_scores_high_and_explains(self):
        r = scoring.score_job({"title": "Senior Full-Stack Engineer", "location": "Remote",
                               "description": "Requirements:\nPython, React, PostgreSQL, Docker. 5+ years of experience."}, DEMO_PROFILE)
        self.assertGreaterEqual(r["score"], 85)
        self.assertIn("Python", r["matched_skills"])

    def test_thin_description_is_flagged(self):
        r = scoring.score_job({"title": "Software Engineer", "description": ""}, DEMO_PROFILE)
        self.assertEqual(r["confidence"], "low")


class ParserTests(Base):
    def test_structure_is_read_not_invented(self):
        p, rep = rp.parse_resume(RESUME)
        self.assertEqual(p["name"], "Jane Doe")
        self.assertEqual(p["email"], "jane@mail.com")
        self.assertEqual([e["company"] for e in p["experience"]], ["Acme Corp", "Beta Systems"])
        self.assertEqual(p["education"][0]["institution"], "University of Texas at Austin")
        self.assertIn("summary", rep["needs_review"])
        self.assertEqual(p["summary"], "")

    def test_garbage_input_yields_blanks(self):
        p, _ = rp.parse_resume("hello")
        self.assertEqual(p["email"], "")
        self.assertEqual(p["experience"], [])

    def test_docx_and_pdf_round_trip(self):
        p = dict(DEMO_PROFILE)
        self.assertIn("CloudScale", rp.extract_text("a.docx", exporters.to_docx(p)))
        self.assertIn("CloudScale", rp.extract_text("a.pdf", exporters.to_pdf(p)))


class TailorTests(Base):
    def test_never_adds_skills_or_numbers(self):
        out = refit.refine_resume_for_job(JOB, DEMO_PROFILE, use_llm=False)
        text = out["tailored_summary"] + " ".join(b for e in out["tailored_experience"] for b in e["bullets"])
        self.assertEqual(refit.ungrounded(DEMO_PROFILE, text), {"numbers": [], "skills": []})
        self.assertNotIn("Kubernetes", out["tailored_skills"])
        self.assertEqual(sorted(out["tailored_skills"]), sorted(DEMO_PROFILE["skills"]))

    def test_term_alignment_uses_job_spelling(self):
        p = json.loads(json.dumps(DEMO_PROFILE))
        p["experience"][0]["bullets"] = ["Tuned Postgres queries for the billing service."]
        out = refit.refine_resume_for_job({"title": "Engineer", "description": "Requirements:\nPostgreSQL"}, p, use_llm=False)
        self.assertIn("PostgreSQL", out["tailored_experience"][0]["bullets"][0])

    def test_llm_fabrications_are_rejected(self):
        bad = json.dumps({"summary": "Cut downtime 99.9% using Kubernetes.", "bullets": {"0.0": "Saved $5M with Rust."}})
        _, diffs, _, engine = refit.refit_llm(JOB, DEMO_PROFILE, llm=lambda s, u: bad)
        self.assertIn("rejected", engine)
        self.assertFalse(any(d["id"].startswith("diff_llm") for d in diffs))

    def test_llm_failure_falls_back(self):
        def boom(s, u):
            raise RuntimeError("down")
        _, _, _, engine = refit.refit_llm(JOB, DEMO_PROFILE, llm=boom)
        self.assertIn("deterministic", engine)

    def test_cover_letter_has_no_invented_claims(self):
        letter = refit.generate_cover_letter(JOB, DEMO_PROFILE)
        self.assertNotIn("led initiatives", letter)
        self.assertIn("have not used", letter)  # honest about the Kubernetes gap

    def test_gap_report_separates_real_gaps(self):
        g = refit.generate_gap_report(JOB, DEMO_PROFILE)
        self.assertIn("Kubernetes", [x["skill"] for x in g["real_gaps"]])


class AtsTests(Base):
    def test_empty_resume_is_not_given_a_floor(self):
        self.assertLess(ats.compute_ats_audit({}, JOB)["ats_score"], 30)

    def test_tailoring_does_not_inflate_by_stuffing(self):
        before = ats.compute_ats_audit(DEMO_PROFILE, JOB)["ats_score"]
        t = refit.refine_resume_for_job(JOB, DEMO_PROFILE, use_llm=False)["tailored_resume"]
        self.assertLessEqual(ats.compute_ats_audit(t, JOB)["ats_score"] - before, 8)


class ExportTests(Base):
    def test_html_is_escaped(self):
        r = dict(DEMO_PROFILE, summary="<script>alert(1)</script>")
        self.assertNotIn("<script>", exporters.to_html(r))


class PipelineTests(Base):
    def _fake(self, behaviour):
        class Fake(sources.Source):
            name, tier = "Fake", "Free feed"
            def fetch(self, q, l):
                return behaviour()
        return Fake()

    def test_search_scores_dedups_and_remembers(self):
        db.save_profile(DEMO_PROFILE)
        jobs = [sources.make_job(id="1", title="Senior Python Engineer", company="Acme", location="Remote", source="Fake",
                                 description="Requirements:\nPython, Docker", url="https://x/1"),
                sources.make_job(id="2", title="Senior Python Engineer", company="Acme Inc", location="Remote", source="Other",
                                 description="Python", url="https://y/1")]
        with mock.patch.object(sources, "SEARCH_SOURCES", [self._fake(lambda: jobs)]):
            r = pipeline.search("python")
        self.assertEqual(r["count"], 1)
        self.assertEqual(len(r["jobs"][0]["sources"]), 2)
        self.assertTrue(r["jobs"][0]["is_new"])

    def test_failed_source_serves_stale_cache_and_reports(self):
        db.save_profile(DEMO_PROFILE)
        good = [sources.make_job(id="1", title="Python Engineer", company="Acme", location="Remote", source="Fake", url="https://x/1", description="Python")]
        state = {"fail": False}
        def behaviour():
            if state["fail"]:
                raise util.HttpError("boom")
            return good
        with mock.patch.object(sources, "SEARCH_SOURCES", [self._fake(behaviour)]):
            pipeline.search("python")
            state["fail"] = True
            r = pipeline.search("python", force_refresh=True)
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["sources"][0]["state"], "stale")
        self.assertTrue(r["partial"])

    def test_circuit_breaker_pauses_a_dead_source(self):
        for _ in range(sources.BREAKER_FAILS):
            sources.breaker_record("Dead", False)
        self.assertTrue(sources.breaker_open("Dead"))


class SourceParserTests(Base):
    def test_major_boards_are_always_attempted(self):
        self.assertTrue(sources.LinkedInGuest().available())
        self.assertTrue(sources.IndeedJobSpy().available())

    def test_source_hierarchy_prefers_direct_employer_application(self):
        jobs = [
            sources.make_job(id="li-1", title="Senior Backend Engineer", company="Acme", location="Remote",
                             source="LinkedIn", url="https://linkedin.example/1"),
            sources.make_job(id="gh-1", title="Senior Backend Engineer", company="Acme", location="Remote",
                             source="Greenhouse", source_tier="Direct company ATS", url="https://boards.greenhouse.io/acme/jobs/1"),
        ]
        out = dedup.merge_jobs(jobs)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "Greenhouse")
        self.assertEqual(out[0]["source_rank"], 100)
        self.assertEqual(out[0]["sources"][0]["source"], "Greenhouse")

    def test_greenhouse_lever_ashby_parse(self):
        gh = {"jobs": [{"id": 1, "title": "Engineer", "absolute_url": "https://g/1", "location": {"name": "Remote"},
                        "content": "&lt;p&gt;Python and Docker&lt;/p&gt;", "updated_at": "2026-10-01T00:00:00Z"}]}
        lv = [{"id": "a", "text": "Designer", "hostedUrl": "https://l/1", "categories": {"location": "Paris"},
               "descriptionPlain": "Figma", "createdAt": 1760000000000, "lists": []}]
        ab = {"jobs": [{"id": "z", "title": "PM", "jobUrl": "https://a/1", "location": "NYC", "isRemote": False,
                        "descriptionHtml": "<p>Roadmapping</p>", "publishedAt": "2026-10-02T00:00:00Z"}]}
        with mock.patch.object(sources, "http_get_json", side_effect=[gh, lv, ab]):
            g = sources.Greenhouse().fetch_company("acme")
            l = sources.Lever().fetch_company("acme")
            a = sources.Ashby().fetch_company("acme")
        self.assertIn("Python and Docker", g[0]["description"])
        self.assertEqual(l[0]["posted_at"][:4], "2025")
        self.assertEqual(a[0]["title"], "PM")

    def test_placeholder_salaries_are_dropped(self):
        j = sources.make_job(id="1", title="x", company="y", salary="Competitive", source="S")
        self.assertEqual(j["salary"], "")


class TrackerTests(Base):
    def test_history_and_follow_up(self):
        i = tracker.upsert_application({"company": "A", "title": "T", "status": "saved"})
        tracker.upsert_application({"id": i, "company": "A", "title": "T", "status": "applied"})
        a = tracker.list_applications()[0]
        self.assertEqual([h["status"] for h in a["history"]], ["saved", "applied"])
        self.assertTrue(a["follow_up_date"])
        self.assertEqual(tracker.funnel_stats()["reached"]["applied"], 1)

    def test_prepare_application_saves_not_applies(self):
        db.save_profile(DEMO_PROFILE)
        out = tracker.prepare_application(JOB, DEMO_PROFILE)
        self.assertEqual(tracker.list_applications()[0]["status"], "saved")
        self.assertIn("Applied", out["next_step"])

    def test_purge_empties_everything(self):
        db.save_profile(DEMO_PROFILE)
        tracker.upsert_application({"company": "A", "title": "T"})
        db.purge_all()
        self.assertTrue(db.get_profile()["_is_empty"])
        self.assertEqual(tracker.list_applications(), [])


class AiStrategyTests(Base):
    def test_ai_strategy_generation(self):
        strat = refit.generate_ai_strategy(JOB, DEMO_PROFILE)
        self.assertIn("fit_score", strat)
        self.assertIn("executive_summary", strat)
        self.assertIn("posting_health_flags", strat)
        self.assertIn("action_plan", strat)
        self.assertTrue(strat["guardrail_verified"])
        self.assertGreater(len(strat["action_plan"]), 0)

    def test_guardrail_report_grounded(self):
        rep = refit.generate_guardrail_report(DEMO_PROFILE, DEMO_PROFILE)
        self.assertTrue(rep["grounded"])
        self.assertEqual(rep["safety_score"], 100)

    def test_guardrail_report_flags_unearned_claims(self):
        bad_resume = dict(DEMO_PROFILE, summary="Earned $10M scaling Rust to 100M users with Kubernetes.")
        rep = refit.generate_guardrail_report(DEMO_PROFILE, bad_resume)
        self.assertFalse(rep["grounded"])
        self.assertEqual(rep["safety_score"], 50)

    def test_ai_config_resolution(self):
        db.set_setting("ai_provider", "gemini")
        db.set_setting("gemini_api_key", "test-key-123")
        cfg = refit.get_active_ai_config()
        self.assertEqual(cfg["provider"], "gemini")
        self.assertEqual(cfg["key"], "test-key-123")


class FamousFilterTests(Base):
    def test_famous_company_detection(self):
        self.assertTrue(pipeline.is_famous_company("OpenAI"))
        self.assertTrue(pipeline.is_famous_company("open ai"))
        self.assertTrue(pipeline.is_famous_company("Vercel"))
        self.assertTrue(pipeline.is_famous_company("Meta"))
        self.assertTrue(pipeline.is_famous_company("Meta Platforms, Inc."))
        self.assertTrue(pipeline.is_famous_company("Grok"))
        self.assertTrue(pipeline.is_famous_company("xAI"))
        self.assertTrue(pipeline.is_famous_company("Anthropic"))
        self.assertTrue(pipeline.is_famous_company("Stripe"))
        self.assertTrue(pipeline.is_famous_company("Google"))
        # Non-famous companies should not match
        self.assertFalse(pipeline.is_famous_company("Acme Labs"))
        self.assertFalse(pipeline.is_famous_company("Metadata Systems"))
        self.assertFalse(pipeline.is_famous_company("Local Startup LLC"))

    def test_search_famous_filtering(self):
        db.save_profile(DEMO_PROFILE)
        jobs = [
            sources.make_job(id="1", title="Python Engineer", company="OpenAI", location="Remote", source="Fake",
                             description="Python", url="https://x/1"),
            sources.make_job(id="2", title="Python Engineer", company="Acme Startup", location="Remote", source="Fake",
                             description="Python", url="https://x/2"),
        ]
        class FakeSrc(sources.Source):
            name, tier = "Fake", "Free feed"
            def fetch(self, q, l): return jobs

        with mock.patch.object(sources, "SEARCH_SOURCES", [FakeSrc()]):
            # 1. Default / "all": both appear
            r_all = pipeline.search("python", famous_mode="all")
            self.assertEqual(len(r_all["jobs"]), 2)
            companies_all = {j["company"] for j in r_all["jobs"]}
            self.assertEqual(companies_all, {"OpenAI", "Acme Startup"})

            # 2. "hide": OpenAI is excluded
            r_hide = pipeline.search("python", famous_mode="hide")
            self.assertEqual(len(r_hide["jobs"]), 1)
            self.assertEqual(r_hide["jobs"][0]["company"], "Acme Startup")

            # 3. "only": Only OpenAI appears
            r_only = pipeline.search("python", famous_mode="only")
            self.assertEqual(len(r_only["jobs"]), 1)
            self.assertEqual(r_only["jobs"][0]["company"], "OpenAI")


if __name__ == "__main__":
    unittest.main(verbosity=1)
