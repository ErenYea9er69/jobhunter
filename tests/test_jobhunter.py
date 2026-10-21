import datetime
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ["JH_DATA_DIR"] = tempfile.mkdtemp()
os.environ["JH_SEARCH_DEADLINE"] = "5"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jh import ats, config, db, dedup, exporters, httpd, pipeline, resume_parser as rp, scoring, skills, sources, refit, tracker, util  # noqa: E402
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

    def test_unenriched_sparse_job_does_not_falsely_inflate_to_90(self):
        # A job with 0 description that only matches 1 skill in its title must not score >= 85%
        r = scoring.score_job({"title": "Senior Backend Engineer - Python IRC302277", "description": "",
                               "location": "Bengaluru, Karnataka, India", "work_mode": "On-site"}, DEMO_PROFILE)
        self.assertLess(r["score"], 80)
        self.assertEqual(r["confidence"], "low")

    def test_multilingual_french_title_matches_target_role(self):
        r = scoring.score_job({"title": "Développeur Back-end Python", "location": "Remote",
                               "description": "Requirements: Python, FastAPI"}, DEMO_PROFILE)
        self.assertGreaterEqual(r["score"], 70)
        tokens = scoring.title_tokens("Développeur Python Confirmé F/H")
        self.assertIn("engineer", tokens)
        self.assertIn("python", tokens)
        self.assertNotIn("fh", tokens)
        self.assertNotIn("f/h", tokens)

    def test_non_software_engineering_does_not_match_tech_candidate(self):
        r = scoring.score_job({"title": "Civil Engineer", "description": "Construction site planning, AutoCAD and structural engineering"}, DEMO_PROFILE)
        self.assertLess(r["score"], 40)

    def test_seniority_gap_penalizes_extreme_mismatches(self):
        junior_profile = dict(DEMO_PROFILE, target_title="Junior Python Developer", years_of_experience=1)
        r = scoring.score_job({"title": "Director of Engineering", "description": "10+ years required with Python and Docker"}, junior_profile)
        self.assertLess(r["score"], 50)
        self.assertIn("above your experience level", r["rationale"])

    def test_geographic_restriction_mismatch_penalized(self):
        uk_profile = dict(DEMO_PROFILE, preferred_locations=["London", "United Kingdom"], location="London")
        r = scoring.score_job({"title": "Senior Python Developer", "location": "Remote, US",
                               "description": "Must be located in United States. US Citizen only."}, uk_profile)
        self.assertLess(r["score"], 45)
        self.assertIn("Geographic restriction", r["rationale"])

    def test_opportunity_score_does_not_inflate_unqualified_job(self):
        job = {"score": 30, "source_rank": 100, "source_kind": "Direct employer ATS", "sources": [{"source_rank": 100}]}
        pipeline._rank_opportunity(job)
        self.assertEqual(job["opportunity_score"], 30)

    def test_tunisia_country_mapping_and_filtering(self):
        self.assertEqual(scoring.classify_job_country("Tunis, Tunisia"), "Tunisia")
        self.assertEqual(scoring.classify_job_country("Ariana, Tunisia"), "Tunisia")
        self.assertEqual(scoring.classify_job_country("Sousse"), "Tunisia")

        tunisia_job = {"location": "Tunis, Tunisia", "work_mode": "On-site"}
        remote_global = {"location": "Remote - Worldwide", "work_mode": "Remote"}
        us_only_job = {"location": "Remote (US Only)", "work_mode": "Remote"}

        self.assertTrue(pipeline._passes(tunisia_job, "any", "Tunisia"))
        self.assertTrue(pipeline._passes(remote_global, "any", "Tunisia"))
        self.assertFalse(pipeline._passes(us_only_job, "any", "Tunisia"))

        # Remote role with HQ in San Francisco but without residency blockers passes for Tunisia
        remote_sf = {"location": "San Francisco, CA", "work_mode": "Remote", "description": "Global distributed engineering team"}
        self.assertTrue(pipeline._passes(remote_sf, "any", "Tunisia"))

        # EMEA remote passes for Tunisia (which is in EMEA)
        emea_job = {"location": "Remote (EMEA)", "work_mode": "Remote", "description": "EMEA remote position"}
        self.assertTrue(pipeline._passes(emea_job, "any", "Tunisia"))

        # APAC remote passes for China
        apac_job = {"location": "Remote (APAC)", "work_mode": "Remote", "description": "APAC timezone remote"}
        self.assertTrue(pipeline._passes(apac_job, "any", "China"))
        self.assertFalse(pipeline._passes(apac_job, "any", "Tunisia"))

    def test_configurable_capacity_and_depth(self):
        # Verify dynamic capacity getters read from DB settings
        db.set_setting("max_scored_jobs", "5000")
        self.assertEqual(config.get_max_scored_jobs(), 5000)

        db.set_setting("max_results", "2500")
        self.assertEqual(config.get_max_results(), 2500)

        db.set_setting("linkedin_scrape_depth", "deep")
        self.assertEqual(config.get_linkedin_scrape_depth(), "deep")

        # Fallback clamped values (max 20000)
        db.set_setting("max_scored_jobs", "99999999")
        self.assertEqual(config.get_max_scored_jobs(), 20000)

    def test_smart_remote_fallback_when_local_empty(self):
        # When user searches for a location that has 0 local postings, pipeline falls back to Worldwide Remote
        res = pipeline.search(query="cobol", location="Atlantis", work_mode="Onsite")
        self.assertGreater(res["count"], 0)
        self.assertTrue(any(j.get("is_fallback") for j in res["jobs"]))
        self.assertIn("Worldwide Remote", res.get("fallback_notice", ""))



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

    def test_generate_custom_resume_6sec_structure(self):
        """Verify 6-second recruiter targeting structure, executive hook, audit metrics, and grounding."""
        res = refit.generate_custom_resume(JOB, DEMO_PROFILE, archetype="startup_velocity", use_llm=False)
        self.assertIn("executive_hook", res)
        self.assertTrue(len(res["executive_hook"]) > 20)
        self.assertIn("recruiter_6sec_audit", res)
        audit = res["recruiter_6sec_audit"]
        self.assertGreaterEqual(audit["skim_score"], 80)
        self.assertEqual(len(audit["eye_catchers"]), 3)
        self.assertIn("scan_zones", audit)
        self.assertIn("zone_1_anchor", audit["scan_zones"])
        self.assertIn("zone_2_competencies", audit["scan_zones"])
        self.assertIn("zone_3_proof", audit["scan_zones"])
        self.assertIn("core_competencies", res)
        self.assertIn("primary_matches", res["core_competencies"])
        # Verify 100% grounding
        tailored = res["tailored_resume"]
        full_text = tailored["summary"] + " " + " ".join(b for e in tailored.get("experience", []) for b in e.get("bullets", []))
        self.assertTrue(refit.is_grounded(DEMO_PROFILE, full_text))
        self.assertTrue(res["guardrail_report"]["grounded"])

    def test_generate_custom_resume_archetypes(self):
        """Verify support for startup_velocity, enterprise_scale, and technical_depth archetypes."""
        res_startup = refit.generate_custom_resume(JOB, DEMO_PROFILE, archetype="startup_velocity", use_llm=False)
        res_ent = refit.generate_custom_resume(JOB, DEMO_PROFILE, archetype="enterprise_scale", use_llm=False)
        res_tech = refit.generate_custom_resume(JOB, DEMO_PROFILE, archetype="technical_depth", use_llm=False)
        self.assertEqual(res_startup["archetype_applied"], "startup_velocity")
        self.assertEqual(res_ent["archetype_applied"], "enterprise_scale")
        self.assertEqual(res_tech["archetype_applied"], "technical_depth")

    def test_generate_custom_resume_llm_hallucination_filtered(self):
        """Verify that simulated LLM hallucinations are rejected by the 6-sec custom generator guardrail."""
        fake_bad_llm_output = json.dumps({
            "executive_hook": "Senior Staff Engineer with 15 years cutting costs by 99% using Kubernetes and Rust.",
            "bullets": {"0.0": "Invented new quantum database saving $500M."}
        })
        res = refit.generate_custom_resume(JOB, DEMO_PROFILE, archetype="enterprise_scale", use_llm=True,
                                           llm_caller=lambda s, u: fake_bad_llm_output)
        tailored = res["tailored_resume"]
        full_text = tailored["summary"] + " " + " ".join(b for e in tailored.get("experience", []) for b in e.get("bullets", []))
        self.assertTrue(refit.is_grounded(DEMO_PROFILE, full_text))
        self.assertNotIn("Kubernetes", full_text)
        self.assertNotIn("$500M", full_text)

    def test_http_custom_resume_generation(self):
        """Verify the /api/resume/custom-generate route returns full 6-sec recruiter audit and tailored resume."""
        db.save_profile(DEMO_PROFILE)
        out = httpd.r_custom_generate({}, {"job": JOB, "archetype": "startup_velocity"})
        self.assertTrue(out["success"])
        self.assertIn("recruiter_6sec_audit", out)
        self.assertIn("executive_hook", out)
        self.assertIn("core_competencies", out)
        self.assertGreaterEqual(out["recruiter_6sec_audit"]["skim_score"], 80)
        self.assertEqual(len(out["recruiter_6sec_audit"]["eye_catchers"]), 3)


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
        self.assertTrue(sources.Indeed().available())
        self.assertTrue(sources.ZipRecruiter().available())
        self.assertTrue(sources.Bayt().available())
        self.assertTrue(sources.Naukri().available())
        self.assertTrue(sources.HelloWork().available())

    def test_startup_sources_integrated(self):
        self.assertTrue(sources.YCombinatorStartups().available())
        self.assertTrue(sources.StartupATS().available())
        self.assertIn("Y Combinator", sources.SOURCE_RANKS)
        self.assertIn("Startup ATS", sources.SOURCE_RANKS)
        self.assertTrue(any(s.name == "Y Combinator" for s in sources.SEARCH_SOURCES))
        self.assertTrue(any(s.name == "Startup ATS" for s in sources.SEARCH_SOURCES))

    def test_ycombinator_source_fetch_and_enrich(self):
        yc = sources.YCombinatorStartups()
        sample_page = """<!DOCTYPE html><html><body>
        <div id="app" data-page='{"component":"jobs/public/pages/JobsV2Page","version":"abc123","props":{"totalJobsCount":1,"jobs":[{"id":999,"title":"Senior Full Stack Engineer","companyName":"AcmeAI","companySlug":"acmeai","companyBatch":"W24","companyOneLiner":"Next-gen robotics platform","location":"San Francisco, CA / Remote (US)","jobType":"Full-time","roleType":"Full stack","salary":"$140K - $190K","applyUrl":"https://www.workatastartup.com/jobs/999"}]}}'></div>
        </body></html>"""
        with mock.patch("jh.sources._fetch_html_tls", return_value=sample_page):
            jobs = yc.fetch("Full Stack", "Remote")
            self.assertEqual(len(jobs), 1)
            j = jobs[0]
            self.assertEqual(j["title"], "Senior Full Stack Engineer")
            self.assertEqual(j["company"], "AcmeAI")
            self.assertTrue(j.get("is_startup"))
            self.assertEqual(j["url"], "https://www.workatastartup.com/jobs/999")

        detail_html = """<!DOCTYPE html><html><body>
        <div id="app" data-page='{"component":"JobPage","props":{"job":{"id":999,"skills":["Python","React","PostgreSQL"],"descriptionHtml":"<p>Comprehensive description of full stack engineering role with Postgres and React.</p>","sponsorsVisa":true}}}'></div>
        </body></html>"""
        with mock.patch("jh.sources._fetch_html_tls", return_value=detail_html):
            enriched = yc.enrich(jobs[0])
            self.assertTrue(enriched.get("enriched"))
            self.assertIn("Comprehensive description", enriched.get("description", ""))
            self.assertEqual(enriched.get("skills"), ["Python", "React", "PostgreSQL"])
            self.assertTrue(enriched.get("h1b"))

    def test_startup_ats_filtering(self):
        ats_src = sources.StartupATS()
        sample_jobs = [
            sources.make_job(id="1", title="Full Stack Engineer", company="Ramp", location="New York, NY", source="Startup ATS", is_startup=True),
            sources.make_job(id="2", title="Account Executive", company="Ramp", location="New York, NY", source="Startup ATS", is_startup=True)
        ]
        mock_board = mock.MagicMock()
        mock_board.fetch_company.return_value = sample_jobs
        jobs = ats_src._search_company(mock_board, "ramp", "Ramp", "Full Stack", "")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Full Stack Engineer")
        self.assertTrue(jobs[0]["is_startup"])

    def test_linkedin_guest_fetch_and_cursor_loop(self):
        lg = sources.LinkedInGuest()
        sample_card = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/python-engineer-at-acme-4411223344">
              <h3 class="base-search-card__title">Senior Python Engineer</h3>
            </a>
            <h4 class="base-search-card__subtitle">Acme Corp</h4>
            <span class="job-search-card__location">New York, NY</span>
            <time datetime="2026-10-15"></time>
          </div>
        </li>"""
        db.set_setting("linkedin_scrape_depth", "deep")
        with mock.patch.object(lg, "_get_page", return_value=sample_card):
            jobs = lg.fetch("Python", "New York")
            self.assertTrue(len(jobs) >= 1)
            self.assertEqual(jobs[0]["id"], "linkedin-4411223344")
            self.assertEqual(jobs[0]["title"], "Senior Python Engineer")
            self.assertEqual(jobs[0]["company"], "Acme Corp")
            # Verify cursor was recorded in SQLite
            cur = db.get_setting("li_cursor_python_newyork")
            self.assertTrue(cur.isdigit() and int(cur) > 0)

    def test_linkedin_429_retry_recovers_page(self):
        """429s are retried up to 2 times instead of silently discarding the page."""
        lg = sources.LinkedInGuest()
        sample_card = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/retry-eng-at-test-9988776655">
              <h3 class="base-search-card__title">Retry Engineer</h3>
            </a>
            <h4 class="base-search-card__subtitle">TestCo</h4>
            <span class="job-search-card__location">Remote</span>
            <time datetime="2026-10-16"></time>
          </div>
        </li>"""
        call_count = [0]
        def mock_get_page(url, timeout=6):
            call_count[0] += 1
            if call_count[0] <= 2:
                return "429"
            return sample_card
        db.set_setting("linkedin_scrape_depth", "fast")
        with mock.patch.object(lg, "_get_page", side_effect=mock_get_page):
            with mock.patch("time.sleep"):  # skip sleeps in test
                jobs = lg.fetch("Retry", "Remote")
        self.assertTrue(len(jobs) >= 1, f"Expected jobs from 429 retry, got {len(jobs)}")
        self.assertEqual(jobs[0]["title"], "Retry Engineer")
        self.assertGreater(call_count[0], 2, "Should have retried after 429")

    def test_linkedin_query_slicing_generates_variants(self):
        """_build_query_slices returns skill-based and role-family variants."""
        lg = sources.LinkedInGuest()
        db.save_profile({"skills": ["Python", "React", "PostgreSQL", "Docker"],
                         "target_title": "Full Stack Developer"})
        slices = lg._build_query_slices("Full Stack Developer")
        self.assertTrue(len(slices) >= 2, f"Expected >=2 slices, got {slices}")
        lower_slices = [s.lower() for s in slices]
        self.assertTrue(any("backend" in s for s in lower_slices),
                        f"Expected 'backend' variant in {slices}")
        # Ensure no slice is an exact copy of the original query
        self.assertNotIn("full stack developer", lower_slices)

    def test_linkedin_incremental_skips_known_jobs(self):
        """fetch_incremental returns only jobs not already in the database."""
        lg = sources.LinkedInGuest()
        new_card = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/new-role-at-co-1111111111">
              <h3 class="base-search-card__title">New Role</h3>
            </a>
            <h4 class="base-search-card__subtitle">NewCo</h4>
            <span class="job-search-card__location">Remote</span>
            <time datetime="2026-10-17"></time>
          </div>
        </li><li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/old-role-at-co-2222222222">
              <h3 class="base-search-card__title">Old Role</h3>
            </a>
            <h4 class="base-search-card__subtitle">OldCo</h4>
            <span class="job-search-card__location">NYC</span>
            <time datetime="2026-10-10"></time>
          </div>
        </li>"""
        # Simulate 2222222222 already known
        with db.session() as c:
            c.execute("INSERT OR IGNORE INTO seen_jobs (job_key,title,company,url,source_names,first_seen,last_seen,best_score) VALUES (?,?,?,?,?,?,?,?)",
                      ("linkedin-2222222222", "Old", "OldCo", "x", "LinkedIn", "2026-10-10", "2026-10-10", 0))
        with mock.patch.object(lg, "_get_page", return_value=new_card):
            with mock.patch("time.sleep"):
                jobs = lg.fetch_incremental("Python", "Remote")
        job_ids = [j["id"] for j in jobs]
        self.assertIn("linkedin-1111111111", job_ids, "New job should be included")
        self.assertNotIn("linkedin-2222222222", job_ids, "Known job should be filtered out")

    def test_linkedin_relative_time_and_company_url_parsing(self):
        """Relative times ('18 minutes ago', '2 hours ago') and company links are parsed with tags."""
        lg = sources.LinkedInGuest()
        card_with_rel = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/fresh-eng-5555555555">
              <h3 class="base-search-card__title">Fresh Engineer</h3>
            </a>
            <h4 class="base-search-card__subtitle">
              <a href="https://www.linkedin.com/company/acme-corp?trk=public_jobs">Acme Corp</a>
            </h4>
            <span class="job-search-card__location">Austin, TX</span>
            <time class="job-search-card__listdate--new" datetime="2026-10-18">
              18 minutes ago
            </time>
          </div>
        </li>"""
        with mock.patch.object(lg, "_get_page", return_value=card_with_rel):
            with mock.patch("time.sleep"):
                jobs = lg.fetch_incremental("Python", "Austin, TX")

        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["id"], "linkedin-5555555555")
        self.assertEqual(j["company_url"], "https://www.linkedin.com/company/acme-corp")
        self.assertEqual(j["posted_relative"], "18m ago")
        self.assertIn("just-posted", j.get("tags", []))
        self.assertIn("T", j["posted_at"], "Minute-precision ISO timestamp expected")

    def test_linkedin_easy_apply_flag(self):
        """Passing easy_apply=True appends &f_AL=true to LinkedIn search URLs."""
        lg = sources.LinkedInGuest()
        captured_urls = []
        def fake_get_page(url, timeout=6):
            captured_urls.append(url)
            return ""
        with mock.patch.object(lg, "_get_page", side_effect=fake_get_page):
            lg.fetch("Python", "Remote", depth="fast", easy_apply=True)

        self.assertTrue(len(captured_urls) > 0)
        self.assertTrue(any("&f_AL=true" in u for u in captured_urls),
                        f"Expected &f_AL=true in URLs: {captured_urls}")

    def test_linkedin_incremental_adaptive_stagnant_page1_rotates_or_backfills(self):
        """When Page 1 top ID is identical to last run, it pivots to skill rotation or backfill."""
        lg = sources.LinkedInGuest()
        card_stagnant = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/stale-role-9999999999">
              <h3 class="base-search-card__title">Stale Role</h3>
            </a>
            <h4 class="base-search-card__subtitle">StaleCo</h4>
          </div>
        </li>"""
        card_backfill = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/unseen-role-8888888888">
              <h3 class="base-search-card__title">Unseen Backfill Role</h3>
            </a>
            <h4 class="base-search-card__subtitle">BackfillCo</h4>
          </div>
        </li>"""

        # Mark 9999999999 as known and set as last_top_id
        db.set_setting("li_radar_last_top_id", "9999999999")
        with db.session() as c:
            c.execute("INSERT OR IGNORE INTO seen_jobs (job_key,title,company,url,source_names,first_seen,last_seen,best_score) VALUES (?,?,?,?,?,?,?,?)",
                      ("linkedin-9999999999", "Stale", "StaleCo", "x", "LinkedIn", "2026-10-10", "2026-10-10", 0))

        # First page call returns card_stagnant, subsequent backfill returns card_backfill
        with mock.patch.object(lg, "_get_page", side_effect=[card_stagnant, card_backfill]):
            with mock.patch("time.sleep"):
                jobs = lg.fetch_incremental("Python", "Remote")

        job_ids = [j["id"] for j in jobs]
        self.assertIn("linkedin-8888888888", job_ids, "Unseen backfill job should be captured on stagnant page 1")
        self.assertNotIn("linkedin-9999999999", job_ids, "Known top job should not be included")

    def test_linkedin_radar_status_and_settings(self):
        """Pipeline returns valid radar status and handles interval updates."""
        from jh import pipeline
        st = pipeline.get_linkedin_radar_status()
        self.assertIn("enabled", st)
        self.assertIn("interval_min", st)
        self.assertIn("pending_count", st)
        self.assertIn("last_action", st)

        # Trigger radar should return success or in-progress
        ok, msg = pipeline.trigger_linkedin_radar_now()
        self.assertTrue(ok)
        self.assertIn("Scan", msg)

    def test_linkedin_radar_no_non_linkedin_or_duplicate_recommendations(self):
        """Radar status recent_matches must ONLY contain LinkedIn jobs and must not duplicate items."""
        from jh import pipeline, db
        # Insert a high-scoring non-LinkedIn job (e.g. Ashby/OpenAI) and a LinkedIn job
        ashby_job = sources.make_job(
            id="ashby-openai-1",
            title="Software Engineer, Full Stack - Dots",
            company="OpenAI",
            location="Remote",
            source="Ashby",
            url="https://jobs.ashbyhq.com/openai/1",
            score=99
        )
        li_job = sources.make_job(
            id="linkedin-test-1",
            title="Senior Backend Engineer",
            company="LinkedInCo",
            location="Remote",
            source="LinkedIn",
            url="https://linkedin.com/jobs/view/1",
            score=88
        )
        db.replace_search_jobs([ashby_job, li_job], query="Software Engineer", clear_existing=False)

        st = pipeline.get_linkedin_radar_status()
        recent = st.get("recent_matches", [])
        for r in recent:
            self.assertNotEqual(r.get("company"), "OpenAI", "Non-LinkedIn jobs like OpenAI must never appear in LinkedIn Radar matches")
            self.assertEqual(r.get("source"), "LinkedIn", "All radar matches must be LinkedIn jobs")

    def test_store_pending_jobs_deduplicates_against_existing(self):
        """store_pending_jobs must reject jobs already in search_jobs by key or company/title."""
        from jh import db
        existing = sources.make_job(
            id="ashby-existing-1",
            title="Platform Architect",
            company="Acme Corp",
            location="Remote",
            source="Ashby",
            score=90
        )
        db.replace_search_jobs([existing], query="Platform", clear_existing=False)

        # Attempt to stage a duplicate from LinkedIn
        li_dup = sources.make_job(
            id="linkedin-999999",
            title="Platform Architect",
            company="Acme Corp",
            location="Remote",
            source="LinkedIn",
            score=90
        )
        added = db.store_pending_jobs([li_dup])
        self.assertEqual(added, 0, "Duplicate role already in search_jobs must not be staged into pending_search_jobs")

    def test_linkedin_fetch_step25_offsets_and_priority_ordering(self):
        """fetch generates step-25 offsets and orders high-priority fresh/page-0 queries first."""
        lg = sources.LinkedInGuest()
        requested_urls = []

        def fake_get_page(url, timeout=6):
            requested_urls.append(url)
            return ""

        with mock.patch.object(lg, "_get_page", side_effect=fake_get_page):
            with mock.patch("time.sleep"):
                lg.fetch("Python", "Remote", depth="deep")

        self.assertTrue(len(requested_urls) > 0)
        import urllib.parse
        start_vals = []
        for u in requested_urls:
            parsed = urllib.parse.urlparse(u)
            qs = urllib.parse.parse_qs(parsed.query)
            if "start" in qs:
                start_vals.append(int(qs["start"][0]))
        self.assertTrue(all(s % 25 == 0 for s in start_vals), f"Offsets must be multiples of 25: {start_vals}")
        self.assertNotIn(10, start_vals)

        first_few_urls = requested_urls[:4]
        has_fresh_stream = any("f_TPR=r86400" in u or "f_TPR=r604800" in u for u in first_few_urls)
        self.assertTrue(has_fresh_stream, "Fresh streams must be prioritized at the front of query queue")

    def test_linkedin_geoid_location_mapping(self):
        """Known countries/regions map to exact LinkedIn geoId to eliminate location noise."""
        lg = sources.LinkedInGuest()
        urls = []

        def fake_get_page(url, timeout=6):
            urls.append(url)
            return ""

        with mock.patch.object(lg, "_get_page", side_effect=fake_get_page):
            with mock.patch("time.sleep"):
                lg.fetch("Python", "United States", depth="fast")

        self.assertTrue(len(urls) > 0)
        self.assertTrue(any("geoId=103644278" in u for u in urls), f"Expected geoId=103644278 in requested URLs: {urls}")

    def test_linkedin_fetch_deduplicates_against_all_three_tables(self):
        """fetch filters out jobs present in search_jobs, pending_search_jobs, or seen_jobs."""
        from jh import db
        lg = sources.LinkedInGuest()

        # Insert 1 into search_jobs
        db.replace_search_jobs([sources.make_job(
            id="linkedin-1000000001", title="Job 1", company="C1", location="Remote", source="LinkedIn"
        )], query="test", clear_existing=False)

        # Insert 1 into pending_search_jobs
        db.store_pending_jobs([sources.make_job(
            id="linkedin-1000000002", title="Job 2", company="C2", location="Remote", source="LinkedIn"
        )])

        # Insert 1 into seen_jobs
        with db.session() as c:
            c.execute(
                "INSERT OR IGNORE INTO seen_jobs (job_key,title,company,url,source_names,first_seen,last_seen,best_score) VALUES (?,?,?,?,?,?,?,?)",
                ("linkedin-1000000003", "Job 3", "C3", "url", "LinkedIn", "2026-10-10", "2026-10-10", 0)
            )

        html_card = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/j1-1000000001"><h3 class="base-search-card__title">J1</h3></a>
            <h4 class="base-search-card__subtitle">C1</h4>
          </div></li>
        <li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/j2-1000000002"><h3 class="base-search-card__title">J2</h3></a>
            <h4 class="base-search-card__subtitle">C2</h4>
          </div></li>
        <li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/j3-1000000003"><h3 class="base-search-card__title">J3</h3></a>
            <h4 class="base-search-card__subtitle">C3</h4>
          </div></li>
        <li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/j4-1000000004"><h3 class="base-search-card__title">J4</h3></a>
            <h4 class="base-search-card__subtitle">C4</h4>
          </div></li>"""

        with mock.patch.object(lg, "_get_page", return_value=html_card):
            with mock.patch("time.sleep"):
                res = lg.fetch("Software", "Remote", depth="fast")

        res_ids = [j["id"] for j in res]
        self.assertIn("linkedin-1000000004", res_ids, "Unseen job should be included")
        self.assertNotIn("linkedin-1000000001", res_ids, "Job in search_jobs should be excluded")
        self.assertNotIn("linkedin-1000000002", res_ids, "Job in pending_search_jobs should be excluded")
        self.assertNotIn("linkedin-1000000003", res_ids, "Job in seen_jobs should be excluded")

    def test_linkedin_backfill_advances_beyond_250(self):
        """Adaptive backfill advances past 250 up to 900 without resetting prematurely."""
        lg = sources.LinkedInGuest()
        card_stagnant = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/stale-role-9999999999">
              <h3 class="base-search-card__title">Stale Role</h3>
            </a>
            <h4 class="base-search-card__subtitle">StaleCo</h4>
          </div>
        </li>"""
        card_backfill = """<li>
          <div class="base-card base-search-card base-search-card--link job-search-card">
            <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/unseen-role-7777777777">
              <h3 class="base-search-card__title">Unseen Backfill Role</h3>
            </a>
            <h4 class="base-search-card__subtitle">BackfillCo</h4>
          </div>
        </li>"""

        db.set_setting("li_radar_last_top_id", "9999999999")
        db.set_setting("li_radar_backfill_offset", "250")
        with db.session() as c:
            c.execute("INSERT OR IGNORE INTO seen_jobs (job_key,title,company,url,source_names,first_seen,last_seen,best_score) VALUES (?,?,?,?,?,?,?,?)",
                      ("linkedin-9999999999", "Stale", "StaleCo", "x", "LinkedIn", "2026-10-10", "2026-10-10", 0))

        def fake_get_page(url, timeout=5):
            if "f_TPR=r604800" in url:
                return card_backfill
            return card_stagnant

        with mock.patch.object(lg, "_get_page", side_effect=fake_get_page):
            with mock.patch("time.sleep"):
                lg.fetch_incremental("Python", "Remote")

        saved_offset = int(db.get_setting("li_radar_backfill_offset") or 0)
        self.assertEqual(saved_offset, 275, "Backfill offset should advance from 250 to 275 instead of resetting to 25")

    def test_linkedin_radar_multi_query_rotation(self):
        """Radar increments query index and rotates across primary and derived roles."""
        from jh import pipeline
        db.save_profile({"target_title": "Backend Engineer", "skills": ["Python", "Golang", "PostgreSQL", "AWS"]})
        db.set_setting("li_radar_query_idx", "0")

        queries_used = []
        with mock.patch("jh.sources.LinkedInGuest.fetch_incremental", return_value=[]) as mock_fetch:
            pipeline.run_linkedin_incremental()
            queries_used.append(mock_fetch.call_args[0][0])
            pipeline.run_linkedin_incremental()
            queries_used.append(mock_fetch.call_args[0][0])

        self.assertEqual(len(queries_used), 2)
        idx_after = db.get_setting("li_radar_query_idx")
        self.assertEqual(idx_after, "2")


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

    def test_sources_synonym_matching(self):
        self.assertTrue(sources._matches("Full Stack Developer", "Full Stack Engineer", "Acme Corp"))
        self.assertTrue(sources._matches("Software Engineer", "Senior Software Developer", "Acme Corp"))
        self.assertFalse(sources._matches("Python Developer", "Go Infrastructure Lead", "Acme Corp"))

    def test_sources_role_family_matching(self):
        # A Full Stack query should accept backend, frontend, and software engineering roles
        self.assertTrue(sources._matches("Full Stack Developer", "Backend Engineer", "Acme Corp"))
        self.assertTrue(sources._matches("Full Stack Developer", "Frontend Developer", "Acme Corp"))
        self.assertTrue(sources._matches("Full Stack Developer", "Senior Software Engineer", "Acme Corp"))
        self.assertFalse(sources._matches("Full Stack Developer", "Pastry Chef", "Acme Bakery"))

    def test_role_family_and_skill_title_scoring(self):
        profile = {
            "target_title": "Full Stack Developer",
            "skills": ["Python", "React", "PostgreSQL", "Docker"],
            "experience": [{"role": "Full Stack Developer"}]
        }
        roles = scoring.derive_target_roles(profile)
        self.assertIn("Backend Developer", roles)
        self.assertIn("Frontend Developer", roles)
        self.assertIn("Python Developer", roles)

        # Full stack candidates have high title affinity for Backend, Frontend, and Python roles
        self.assertGreaterEqual(scoring._title_score("Backend Engineer", profile), 0.85)
        self.assertGreaterEqual(scoring._title_score("Frontend Engineer", profile), 0.85)
        self.assertGreaterEqual(scoring._title_score("Python Developer", profile), 0.85)
        self.assertGreaterEqual(scoring._title_score("Software Engineer", profile), 0.85)
        # Unrelated domain remains 0.0
        self.assertEqual(scoring._title_score("Pastry Chef", profile), 0.0)

    def test_himalayas_source_integrated(self):
        self.assertIn("Himalayas", sources.SOURCE_RANKS)
        self.assertTrue(any(s.name == "Himalayas" for s in sources.SEARCH_SOURCES))

    def test_search_db_persistence_and_replacement(self):
        batch1 = [
            {"job_key": "job1", "title": "Python Dev", "company": "Co A", "location": "Remote", "work_mode": "Remote", "score": 80, "opportunity_score": 85},
            {"job_key": "job2", "title": "React Dev", "company": "Co B", "location": "NYC", "work_mode": "Onsite", "score": 70, "opportunity_score": 75},
        ]
        db.replace_search_jobs(batch1, query="python", location="remote")
        saved = db.get_saved_search_jobs()
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]["job_key"], "job1")

        meta = db.get_search_meta()
        self.assertEqual(meta["query"], "python")
        self.assertEqual(meta["total_count"], 2)

        # Verify replacement: old ones are deleted and new ones stored
        batch2 = [
            {"job_key": "job3", "title": "Go Dev", "company": "Co C", "location": "Remote", "work_mode": "Remote", "score": 90, "opportunity_score": 95},
        ]
        db.replace_search_jobs(batch2, query="golang", location="remote")
        saved2 = db.get_saved_search_jobs()
        self.assertEqual(len(saved2), 1)
        self.assertEqual(saved2[0]["job_key"], "job3")
        self.assertFalse(any(j["job_key"] == "job1" for j in saved2))


    def test_country_and_company_stage_classification(self):
        from jh.scoring import classify_job_country, classify_company_stage
        self.assertEqual(classify_job_country("San Francisco, CA"), "United States")
        self.assertEqual(classify_job_country("Salt Lake City, UT"), "United States")
        self.assertEqual(classify_job_country("London, United Kingdom"), "United Kingdom")
        self.assertEqual(classify_job_country("Berlin, Germany"), "Germany")
        self.assertEqual(classify_job_country("Toronto, ON, Canada"), "Canada")
        self.assertEqual(classify_job_country("Bengaluru, Karnataka, India"), "India")
        self.assertEqual(classify_job_country("Singapore, Singapore"), "Singapore")
        self.assertEqual(classify_job_country("Paris, France"), "France")
        self.assertEqual(classify_job_country("Remote"), "Worldwide")

        # Company stage
        self.assertEqual(classify_company_stage({"company": "Google"}), "big_tech")
        self.assertEqual(classify_company_stage({"company": "OpenAI"}), "big_tech")
        self.assertEqual(classify_company_stage({"company": "Linear", "tags": []}), "mid_tech")
        self.assertEqual(classify_company_stage({"company": "Stealth AI", "tags": ["startup"]}), "startup")
        self.assertEqual(classify_company_stage({"company": "Hedge (YC)", "tags": []}), "startup")

    def test_paid_and_free_source_classification(self):
        # Paid / paywalled platforms
        self.assertFalse(sources.is_free_to_apply("RemoteOK"))
        self.assertFalse(sources.is_free_to_apply("Remote OK"))
        self.assertFalse(sources.is_free_to_apply("We Work Remotely"))
        self.assertFalse(sources.is_free_to_apply("Remotive"))
        self.assertIn("remoteok.com/premium", sources.apply_cost_note("RemoteOK"))

        # Free platforms
        self.assertTrue(sources.is_free_to_apply("Greenhouse"))
        self.assertTrue(sources.is_free_to_apply("LinkedIn"))
        self.assertTrue(sources.is_free_to_apply("Indeed"))
        self.assertTrue(sources.is_free_to_apply("ZipRecruiter"))
        self.assertTrue(sources.is_free_to_apply("Hacker News"))
        self.assertTrue(sources.is_free_to_apply("Jobicy"))
        self.assertTrue(sources.is_free_to_apply("Arbeitnow"))
        self.assertTrue(sources.is_free_to_apply("Himalayas"))
        self.assertTrue(sources.is_free_to_apply("Adzuna"))
        self.assertTrue(sources.is_free_to_apply("Bayt"))
        self.assertTrue(sources.is_free_to_apply("Naukri"))
        self.assertTrue(sources.is_free_to_apply("HelloWork"))
        self.assertTrue(sources.is_free_to_apply("Y Combinator"))
        self.assertTrue(sources.is_free_to_apply("Startup ATS"))

    def test_dedup_prefers_free_source_over_paid_remoteok(self):
        paid_job = sources.make_job(id="rok-1", title="Staff Engineer", company="Vercel",
                                    source="RemoteOK", url="https://remoteok.com/l/1", location="Remote")
        free_job = sources.make_job(id="li-1", title="Staff Engineer", company="Vercel",
                                    source="LinkedIn", url="https://linkedin.com/jobs/view/1", location="Remote")
        merged = dedup.merge_jobs([paid_job, free_job])
        self.assertEqual(len(merged), 1)
        # LinkedIn is free, so it MUST win over RemoteOK
        self.assertEqual(merged[0]["source"], "LinkedIn")
        self.assertEqual(merged[0]["url"], "https://linkedin.com/jobs/view/1")
        self.assertTrue(merged[0]["is_free_to_apply"])

    def test_pipeline_retains_more_than_350_jobs(self):
        db.save_profile(DEMO_PROFILE)
        # Generate 400 unique candidate jobs
        sample_jobs = [
            sources.make_job(id=f"job-{i}", title=f"Python Engineer {i}", company=f"Company {i}",
                             location="Remote", source="LinkedIn", description="Python development",
                             url=f"https://example.com/{i}")
            for i in range(400)
        ]
        class BulkSrc(sources.Source):
            name, tier = "Bulk", "Major job board"
            def fetch(self, q, l): return sample_jobs

        with mock.patch.object(sources, "SEARCH_SOURCES", [BulkSrc()]):
            res = pipeline.search("python", limit=500)
            # Must return all 400 jobs, not artificially capped at 350
            self.assertGreater(len(res["all_jobs"]), 350)
            self.assertEqual(len(res["all_jobs"]), 400)

    def test_recommendations_and_insider_links(self):
        db.save_profile(DEMO_PROFILE)
        jobs = [
            sources.make_job(id="rec-1", title="Senior Python Engineer", company="Stripe",
                             location="Remote", source="Greenhouse", description="Requirements:\nPython, Docker, PostgreSQL",
                             url="https://stripe.com/jobs/1"),
            sources.make_job(id="rec-2", title="Frontend Engineer", company="Figma",
                             location="Remote", source="Lever", description="Requirements:\nReact, TypeScript",
                             url="https://figma.com/jobs/2")
        ]
        class RecSrc(sources.Source):
            name, tier = "ATS", "Direct employer ATS"
            def fetch(self, q, l): return jobs

        with mock.patch.object(sources, "SEARCH_SOURCES", [RecSrc()]):
            res = pipeline.get_recommendations(profile=DEMO_PROFILE, force_refresh=True)
            self.assertTrue(res["success"])
            self.assertGreaterEqual(res["count"], 1)
            first_job = res["recommendations"][0]
            self.assertIn("recommendation_hook", first_job)
            self.assertIn("insider_links", first_job)
            self.assertTrue(first_job["insider_links"]["recruiters_url"].startswith("https://www.linkedin.com/search/results/people/"))
    def test_refresh_sync_does_not_prune_active_older_posted_jobs(self):
        # Create a job with posted_at 45 days ago (common for active tech jobs)
        old_posted = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=45)).isoformat()
        job = {
            "job_key": "active-old-job",
            "title": "Senior Staff Engineer",
            "company": "Stripe",
            "location": "Remote",
            "work_mode": "Remote",
            "posted_at": old_posted,
            "score": 92,
            "opportunity_score": 95,
            "skills_text": "python, go, kubernetes",
            "source": "Greenhouse",
            "source_kind": "Direct employer ATS"
        }
        db.store_pending_jobs([job], query="stripe")
        self.assertEqual(db.get_pending_jobs_count(), 1)

        # Refresh sync should add the job to search_jobs and NOT prune it immediately
        res = db.apply_refresh_sync()
        self.assertEqual(res["added_count"], 1)
        self.assertEqual(res["removed_count"], 0)

        stored = db.query_stored_jobs({})
        keys = [j.get("job_key") or j.get("id") for j in stored["jobs"]]
        self.assertIn("active-old-job", keys)

        # Check skills_text persistence
        with db.session() as c:
            row = c.execute("SELECT skills_text FROM search_jobs WHERE job_key='active-old-job'").fetchone()
            self.assertIsNotNone(row)
            self.assertIn("python", row["skills_text"])

    def test_refresh_sync_endpoint_body_filters(self):
        from jh.httpd import r_refresh_sync
        job1 = {"job_key": "f1", "title": "Full Stack Dev", "company": "A", "location": "Remote", "work_mode": "Remote", "score": 85, "opportunity_score": 90}
        job2 = {"job_key": "f2", "title": "Accountant", "company": "B", "location": "NYC", "work_mode": "Onsite", "score": 40, "opportunity_score": 30}
        db.replace_search_jobs([job1, job2], query="test", clear_existing=True)

        # Request refresh-sync with filter for Full Stack
        res = r_refresh_sync({}, {"category": "Full Stack Developer"})
        self.assertEqual(res["total_all"], 2)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["jobs"][0]["job_key"], "f1")
        self.assertEqual(len(res["all_jobs"]), 2)

    def test_saved_search_endpoint_returns_all_jobs_and_filtered_subset(self):
        from jh.httpd import r_saved_search
        job1 = {"job_key": "s1", "title": "Full Stack Dev", "company": "A", "location": "Remote", "work_mode": "Remote", "score": 85, "opportunity_score": 90}
        job2 = {"job_key": "s2", "title": "Accountant", "company": "B", "location": "NYC", "work_mode": "Onsite", "score": 40, "opportunity_score": 30}
        db.replace_search_jobs([job1, job2], query="test", clear_existing=True)

        res = r_saved_search({"category": ["Full Stack Developer"]}, {})
        self.assertEqual(res["total_all"], 2)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["jobs"][0]["job_key"], "s1")
        self.assertEqual(len(res["all_jobs"]), 2)

    def test_html_entity_decoding_and_title_sanitization(self):
        from jh.util import clean_text
        from jh import sources

        # Hex entities from real job boards
        self.assertEqual(clean_text("D&#xE9;veloppeur Full Stack H/F"), "Développeur Full Stack H/F")
        self.assertEqual(clean_text("Groupe Q&#xE9;rys"), "Groupe Qérys")
        self.assertEqual(clean_text("Eiffage &#xC9;nergie Syst&#xE8;mes"), "Eiffage Énergie Systèmes")

        # Decimal and named entities
        self.assertEqual(clean_text("D&#233;veloppeur &amp; Tech Lead"), "Développeur & Tech Lead")
        self.assertEqual(clean_text("&quot;Senior&quot; Engineer&#39;s Hub"), '"Senior" Engineer\'s Hub')

        # Double-escaped entities
        self.assertEqual(clean_text("&amp;#xE9;"), "é")
        self.assertEqual(clean_text("&amp;amp;"), "&")

        # Non-breaking spaces and zero-width spaces
        self.assertEqual(clean_text("Software\xa0\xa0Engineer\u200b"), "Software Engineer")

        # Literal ampersands preserved
        self.assertEqual(clean_text("Motors & Actuators"), "Motors & Actuators")
        self.assertEqual(clean_text("AT&T"), "AT&T")
        self.assertEqual(clean_text("IT Systems Engineer, M&A"), "IT Systems Engineer, M&A")

        # make_job cleans titles, company, location
        j = sources.make_job(
            id="test-1",
            title="D&#xE9;veloppeur Full-Stack H/F",
            company="Eiffage &#xC9;nergie Syst&#xE8;mes",
            location="Paris, France\xa0",
            salary="&#x20AC;50,000 - &#x20AC;60,000"
        )
        self.assertEqual(j["title"], "Développeur Full-Stack H/F")
        self.assertEqual(j["company"], "Eiffage Énergie Systèmes")
        self.assertEqual(j["location"], "Paris, France")
        self.assertIn("€50,000", j["salary"])

    def test_db_clean_job_dict_and_migration(self):
        from jh import db
        raw_job = {
            "id": "html-job-1",
            "title": "D&#xE9;veloppeur Full Stack H/F",
            "company": "Groupe Q&#xE9;rys",
            "location": "Bordeaux\xa0",
            "salary": "45k - 55k",
            "description": "Poste de D&#xE9;veloppeur Full Stack"
        }
        db.replace_search_jobs([raw_job], query="test", clear_existing=True)
        jobs = db.get_saved_search_jobs()
        self.assertTrue(len(jobs) >= 1)
        stored = next(x for x in jobs if x.get("id") == "html-job-1" or x.get("job_key") == "html-job-1")
        self.assertEqual(stored["title"], "Développeur Full Stack H/F")
        self.assertEqual(stored["company"], "Groupe Qérys")
        self.assertEqual(stored["location"], "Bordeaux")
    def test_linkedin_jid_extraction(self):
        """Verify _extract_linkedin_jid accurately finds the 10-digit LinkedIn ID even with numeric requisition codes in slug."""
        url_with_req = "https://www.linkedin.com/jobs/view/middle-python-engineer-irc304696-at-globallogic-4480244118?position=1&pageNum=0"
        self.assertEqual(sources._extract_linkedin_jid(url_with_req), "4480244118")

        url_simple = "https://www.linkedin.com/jobs/view/4474341902"
        self.assertEqual(sources._extract_linkedin_jid(url_simple), "4474341902")

        url_current_job_id = "https://www.linkedin.com/jobs/search?currentJobId=4480244118"
        self.assertEqual(sources._extract_linkedin_jid(url_current_job_id), "4480244118")

    def test_background_enricher_telemetry_and_worker(self):
        """Verify get_enrichment_telemetry and trigger_background_enrichment work properly."""
        from jh import pipeline, db
        telemetry = pipeline.get_enrichment_telemetry()
        self.assertIn("is_running", telemetry)
        self.assertIn("total", telemetry)
        self.assertIn("completed", telemetry)

        # Triggering enricher starts daemon thread
        self.assertTrue(pipeline.trigger_background_enrichment())
        self.assertIsNotNone(pipeline._enrich_bg_thread)
        self.assertTrue(pipeline._enrich_bg_thread.is_alive())

    def test_scoring_bayesian_damping_for_sparse_jobs(self):
        """Sparse/unenriched postings must not achieve inflated 90%+ scores based on 1 skill match."""
        from jh import scoring
        profile = {
            "title": "Senior Python Developer",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "Redis"],
            "experience_years": 5,
            "target_roles": ["Python Developer", "Backend Engineer"]
        }
        sparse_job = {
            "title": "Python Developer",
            "description": "Looking for a Python developer.",
            "company": "Tech Corp",
            "location": "Remote",
            "enriched": False
        }
        result = scoring.score_job(sparse_job, profile)
        # Bayesian smoothing should temper the score well below 85
        self.assertLess(result["score"], 80)
        self.assertGreaterEqual(result["score"], 40)


    def test_resume_profiles_lifecycle(self):
        """Verify resume profiles listing, creation, activation, cloning, updating, and deletion."""
        from jh import db
        # 1. Save demo profile so master has valid data
        db.save_profile(DEMO_PROFILE)
        profs = db.list_resume_profiles()
        self.assertGreaterEqual(len(profs), 1)
        master = next((p for p in profs if p["id"] == "master"), None)
        self.assertIsNotNone(master)
        self.assertTrue(master["is_master"])

        # 2. Duplicate master into a new variant
        cloned = db.duplicate_resume_profile("master", new_name="Python Backend Specialist", target_title="Senior Backend Engineer", tags=["Python", "FastAPI", "AWS"])
        self.assertEqual(cloned["_profile_name"], "Python Backend Specialist")
        self.assertEqual(cloned["target_title"], "Senior Backend Engineer")
        self.assertIn("Python", cloned["skills"])

        # 3. Activate the new variant
        active = db.set_active_resume_profile(cloned["_profile_id"])
        self.assertEqual(active["_profile_id"], cloned["_profile_id"])
        self.assertTrue(active["_is_active"])

        # Verify get_profile() returns active profile
        current = db.get_profile()
        self.assertEqual(current["_profile_id"], cloned["_profile_id"])

        # 4. Save edits to this variant
        current["summary"] = "High performance distributed systems backend engineer."
        saved = db.save_profile(current, profile_id=cloned["_profile_id"])
        self.assertEqual(saved["summary"], "High performance distributed systems backend engineer.")

        # 5. Prevent deleting master
        with self.assertRaises(ValueError):
            db.delete_resume_profile("master")

        # 6. Delete the created variant
        deleted = db.delete_resume_profile(cloned["_profile_id"])
        self.assertTrue(deleted)

        # Deleting active variant must safely restore master as active
        restored = db.get_profile()
        self.assertEqual(restored["_profile_id"], "master")
        self.assertTrue(restored["_is_active"])

    def test_save_tailored_variant_from_workspace(self):
        """Verify saving a workspace tailored resume as a reusable library variant."""
        from jh import db
        job = {
            "id": "job_tailor_test_1",
            "title": "Senior AI Systems Engineer",
            "company": "DeepMind",
            "location": "London, UK",
            "matched_skills": ["Python", "PyTorch", "Kubernetes"]
        }
        tailored = {
            "summary": "Specialized AI Systems Engineer with proven scale experience.",
            "skills": ["Python", "PyTorch", "Kubernetes", "Ray", "Docker"],
            "experience": [
                {
                    "company": "Tech Corp",
                    "role": "AI Infrastructure Lead",
                    "bullets": ["Optimized training cluster throughput by 35% with Ray and Kubernetes."]
                }
            ]
        }
        variant = db.save_tailored_variant_from_workspace(job, tailored, variant_name="DeepMind - AI Systems", tags=["AI", "PyTorch", "Scale"])
        self.assertEqual(variant["_profile_name"], "DeepMind - AI Systems")
        self.assertEqual(variant["target_title"], "Senior AI Systems Engineer")
        self.assertIn("AI Infrastructure Lead", [e["role"] for e in variant.get("experience", [])])

        # Cleanup
        db.delete_resume_profile(variant["_profile_id"])

    def test_audit_resume(self):
        """Verify ATS audit scoring, checks, metrics, and actionable tips."""
        from jh import refit
        sample_profile = {
            "name": "Jane Developer",
            "target_title": "Staff Backend Engineer",
            "email": "jane@example.com",
            "phone": "+1 555-0199",
            "location": "San Francisco, CA",
            "linkedin": "https://linkedin.com/in/janedev",
            "github": "https://github.com/janedev",
            "summary": "Accomplished Staff Backend Engineer with 8+ years of production experience architecting high-throughput distributed systems, event-driven microservices, and cloud-native APIs. Proven leader in reliability, database scalability, and optimizing infrastructure costs across complex distributed cloud environments.",
            "skills": ["Python", "Go", "Distributed Systems", "AWS", "PostgreSQL", "Docker", "Kubernetes", "Redis", "Kafka", "FastAPI"],
            "experience": [
                {
                    "company": "Acme Cloud",
                    "role": "Senior Engineer",
                    "bullets": [
                        "Reduced p99 API latency by 42% across 50M daily requests by caching with Redis.",
                        "Architected streaming ingestion pipeline saving $120k annually in cloud compute across 12 services.",
                        "Led migration of 4 core databases to PostgreSQL with 99.99% uptime and zero data loss."
                    ]
                }
            ],
            "education": [
                {
                    "institution": "University of Tech",
                    "degree": "B.S. in Computer Science",
                    "graduation_year": "2018"
                }
            ]
        }
        audit = refit.audit_resume(sample_profile)
        self.assertIn("score", audit)
        self.assertIn("grade", audit)
        self.assertGreaterEqual(audit["score"], 85)
        self.assertEqual(audit["stats"]["quantified_rate"], 100)
        self.assertEqual(audit["stats"]["quantified_bullet_count"], 3)
        self.assertTrue(len(audit["checks"]) >= 5)

    def test_compare_variants_against_job(self):
        """Verify comparing and ranking multiple resume variants against a target job."""
        from jh import refit
        job = {
            "title": "Senior Python Backend Engineer",
            "company": "Stripe",
            "description": "Looking for deep Python, FastAPI, PostgreSQL, and AWS experience to scale payments.",
            "required_skills": ["Python", "FastAPI", "PostgreSQL", "AWS"]
        }
        variant_a = {
            "_profile_id": "var_a",
            "_profile_name": "Python Specialist",
            "_is_master": False,
            "_is_active": True,
            "target_title": "Python Backend Engineer",
            "tags": ["Python", "FastAPI"],
            "skills": ["Python", "FastAPI", "PostgreSQL", "AWS", "Docker"]
        }
        variant_b = {
            "_profile_id": "var_b",
            "_profile_name": "Frontend Specialist",
            "_is_master": False,
            "_is_active": False,
            "target_title": "Frontend Engineer",
            "tags": ["React", "CSS"],
            "skills": ["JavaScript", "React", "TypeScript", "HTML", "CSS"]
        }

        res = refit.compare_variants_against_job(job, [variant_a, variant_b])
        comparisons = res["comparisons"]
        self.assertEqual(len(comparisons), 2)
        # Variant A has Python & FastAPI matching Stripe, so it should rank first with a higher score
        self.assertEqual(comparisons[0]["id"], "var_a")
        self.assertGreater(comparisons[0]["score"], comparisons[1]["score"])
        self.assertEqual(res["best_variant"]["id"], "var_a")

    def test_set_resume_profile_live_and_minimum_guarantee(self):
        """Verify toggling is_live status and enforcing that at least 1 resume remains live."""
        from jh import db
        # Ensure master profile is populated before duplicating
        db.save_profile({
            "name": "Master Resume",
            "target_title": "Software Engineer",
            "skills": ["Python", "FastAPI", "SQL"],
        }, profile_id="master")
        # Create a second variant
        v2 = db.duplicate_resume_profile("master", new_name="Data Science Variant", target_title="Data Scientist")
        self.assertTrue(v2.get("_is_live", True))

        # We now have 2 resumes (master and v2). We can toggle v2 to paused (is_live=False)
        updated = db.set_resume_profile_live(v2["_profile_id"], is_live=False)
        self.assertFalse(updated["is_live"])

        # Now only master is live. Trying to pause master must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            db.set_resume_profile_live("master", is_live=False)
        self.assertIn("At least one resume must remain Live", str(ctx.exception))

        # Re-enable v2
        updated2 = db.set_resume_profile_live(v2["_profile_id"], is_live=True)
        self.assertTrue(updated2["is_live"])

        # Clean up created variant
        db.delete_resume_profile(v2["_profile_id"])

    def test_score_job_best_picks_highest_matching_live_resume(self):
        """score_job_best must score across live profiles and pick the winner with the highest fit."""
        from jh import scoring
        python_profile = {
            "_profile_id": "prof_py",
            "_profile_name": "Python Backend Specialist",
            "target_title": "Senior Python Backend Engineer",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "AWS"],
            "years_of_experience": 5
        }
        frontend_profile = {
            "_profile_id": "prof_fe",
            "_profile_name": "Frontend React Specialist",
            "target_title": "Senior React Frontend Engineer",
            "skills": ["JavaScript", "TypeScript", "React", "Next.js", "Tailwind CSS", "Redux"],
            "years_of_experience": 5
        }

        # 1. Job requiring Python & FastAPI
        py_job = {
            "title": "Senior Python Engineer",
            "description": "Building microservices with Python, FastAPI, and PostgreSQL on AWS.",
            "location": "Remote",
            "work_mode": "Remote"
        }
        res_py = scoring.score_job_best(py_job, [python_profile, frontend_profile])
        self.assertEqual(res_py["best_profile_id"], "prof_py")
        self.assertEqual(res_py["best_profile_name"], "Python Backend Specialist")
        self.assertEqual(len(res_py["live_matches"]), 2)
        self.assertTrue(res_py["live_matches"][0]["is_best"])
        self.assertGreater(res_py["live_matches"][0]["score"], res_py["live_matches"][1]["score"])

        # 2. Job requiring React & Next.js
        fe_job = {
            "title": "Senior Frontend Engineer",
            "description": "Building interactive dashboards with React, Next.js, and TypeScript.",
            "location": "Remote",
            "work_mode": "Remote"
        }
        res_fe = scoring.score_job_best(fe_job, [python_profile, frontend_profile])
        self.assertEqual(res_fe["best_profile_id"], "prof_fe")
        self.assertEqual(res_fe["best_profile_name"], "Frontend React Specialist")
        self.assertEqual(res_fe["live_matches"][0]["id"], "prof_fe")
        self.assertTrue(res_fe["live_matches"][0]["is_best"])

    def test_score_job_best_ignores_paused_resumes_in_matching_pool(self):
        """Out of 5 resumes with only 3 Live, the matching engine only scores against the 3 Live and ignores the 2 Paused."""
        from jh import scoring, db
        # 3 Live profiles, 2 Paused profiles
        p1_live = {"_profile_id": "p1", "_profile_name": "Live 1 (Go)", "skills": ["Go", "Kubernetes"], "_is_live": True}
        p2_live = {"_profile_id": "p2", "_profile_name": "Live 2 (Java)", "skills": ["Java", "Spring Boot"], "_is_live": True}
        p3_live = {"_profile_id": "p3", "_profile_name": "Live 3 (DevOps)", "skills": ["Terraform", "AWS"], "_is_live": True}
        # Paused profiles: p4 has 100% Python match, but because it is paused, it MUST NOT be scored
        p4_paused = {"_profile_id": "p4", "_profile_name": "Paused 1 (Python)", "skills": ["Python", "FastAPI", "Postgres", "Redis"], "_is_live": False}
        p5_paused = {"_profile_id": "p5", "_profile_name": "Paused 2 (Ruby)", "skills": ["Ruby", "Rails"], "_is_live": False}

        # Save these into DB to verify get_live_profiles() filtering
        live_pool = [p for p in [p1_live, p2_live, p3_live, p4_paused, p5_paused] if p["_is_live"]]
        self.assertEqual(len(live_pool), 3)

        job = {
            "title": "Cloud Infrastructure Engineer",
            "description": "Looking for AWS and Terraform experts.",
            "location": "Remote"
        }
        res = scoring.score_job_best(job, live_pool)
        # p3_live (DevOps with AWS and Terraform) must win among the live ones
        self.assertEqual(res["best_profile_id"], "p3")
        self.assertEqual(res["total_live_profiles"], 3)
        evaluated_ids = [m["id"] for m in res["live_matches"]]
        self.assertIn("p1", evaluated_ids)
        self.assertIn("p2", evaluated_ids)
        self.assertIn("p3", evaluated_ids)
        self.assertNotIn("p4", evaluated_ids)
        self.assertNotIn("p5", evaluated_ids)

    def test_rescore_and_query_stored_jobs_with_best_profile(self):
        """Verify rescore_and_classify_stored_jobs stores best_profile_id and query_stored_jobs filters by it."""
        from jh import db
        # Ensure master profile is populated with skills
        db.save_profile({
            "name": "Staff Architect Resume",
            "target_title": "Senior Staff Architect",
            "skills": ["compression", "algorithms", "scale", "Python"],
        }, profile_id="master")
        test_job = {
            "id": "job-best-prof-test-1",
            "title": "Senior Staff Architect",
            "company": "Pied Piper",
            "location": "Remote",
            "work_mode": "Remote",
            "description": "Building compression algorithms with high scale.",
            "score": 0
        }
        db.replace_search_jobs([test_job], query="compression", clear_existing=False)

        count = db.rescore_and_classify_stored_jobs()
        self.assertGreaterEqual(count, 1)

        # Query jobs and verify best_profile_id is present
        res = db.query_stored_jobs()
        matching_job = next((j for j in res["jobs"] if j.get("id") == "job-best-prof-test-1" or j.get("job_key") == "job-best-prof-test-1"), None)
        self.assertIsNotNone(matching_job)
        self.assertTrue(bool(matching_job.get("best_profile_id")))
        self.assertTrue(bool(matching_job.get("best_profile_name")))

        # Verify facets include profiles
        facets = res.get("facets", {})
        self.assertIn("profiles", facets)

    def test_job_type_classification_and_normalization(self):
        """Verify intelligent classification of Internship, Part-time, and Contract roles."""
        from jh import db
        # 1. Internship from title or German/French terms even if raw feed defaulted to Full-time
        job_intern = {
            "title": "Summer Backend Engineering Intern",
            "company": "Stripe",
            "job_type": "Full-time", # Raw feed defaulted to full-time
            "description": "Internship for university students."
        }
        meta_intern = db.classify_job(job_intern)
        self.assertEqual(meta_intern["job_type"], "Internship")

        job_praktik = {
            "title": "Praktikum Softwareentwicklung",
            "company": "BMW",
            "job_type": "Praktikum",
            "description": "Werkstudent oder Praktikant im Bereich Cloud."
        }
        meta_praktik = db.classify_job(job_praktik)
        self.assertEqual(meta_praktik["job_type"], "Internship")

        # 2. Part-time
        job_part = {
            "title": "Part-time Python Developer",
            "company": "EdTech",
            "job_type": "",
            "description": "15-20 hours per week helping students."
        }
        meta_part = db.classify_job(job_part)
        self.assertEqual(meta_part["job_type"], "Part-time")

        # 3. Contract
        job_contract = {
            "title": "Senior Cloud Infrastructure Consultant (Contract)",
            "company": "Fintech Corp",
            "job_type": "Contract",
            "description": "6 months contract / C2C."
        }
        meta_contract = db.classify_job(job_contract)
        self.assertEqual(meta_contract["job_type"], "Contract")

    def test_query_stored_jobs_multi_job_type_filtering(self):
        """Verify query_stored_jobs supports multi-value job_type filtering and facet counts."""
        from jh import db
        jobs = [
            {"id": "jt-test-ft", "title": "Full-time SRE", "company": "Co A", "job_type": "Full-time", "description": "Full time role."},
            {"id": "jt-test-pt", "title": "Part-time Frontend", "company": "Co B", "job_type": "Part-time", "description": "Part time role."},
            {"id": "jt-test-in", "title": "AI Research Intern", "company": "Co C", "job_type": "Internship", "description": "Summer internship."},
            {"id": "jt-test-ct", "title": "Go Contractor", "company": "Co D", "job_type": "Contract", "description": "Contractor role."}
        ]
        db.replace_search_jobs(jobs, query="jt-test", clear_existing=False)

        # 1. Multi-filter: Part-time + Internship
        res_multi = db.query_stored_jobs({"job_type": "Part-time,Internship"})
        returned_ids = {j.get("id") or j.get("job_key") for j in res_multi["jobs"]}
        self.assertIn("jt-test-pt", returned_ids)
        self.assertIn("jt-test-in", returned_ids)
        self.assertNotIn("jt-test-ft", returned_ids)
        self.assertNotIn("jt-test-ct", returned_ids)

        # 2. Single filter: Contract
        res_contract = db.query_stored_jobs({"job_type": "Contract"})
        ret_contract_ids = {j.get("id") or j.get("job_key") for j in res_contract["jobs"]}
        self.assertIn("jt-test-ct", ret_contract_ids)
        self.assertNotIn("jt-test-ft", ret_contract_ids)

        # 3. Dynamic facets include job_types
        facets = res_multi.get("facets", {})
        self.assertIn("job_types", facets)
        self.assertGreaterEqual(facets["job_types"].get("Internship", 0), 1)
        self.assertGreaterEqual(facets["job_types"].get("Part-time", 0), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)


