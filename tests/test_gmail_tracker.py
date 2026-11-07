"""Tests for the automatic Gmail job application tracker and synchronization engine."""

import json
import unittest
from unittest.mock import patch

from jh import db, gmail_tracker, tracker


class TestGmailTracker(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_classify_applied_email(self):
        subject = "Thank you for applying to Stripe!"
        sender = "Stripe Recruiting <jobs@stripe.com>"
        body = "Hi there, We have received your application for the Backend Software Engineer role at Stripe. Our team is reviewing it."
        res = gmail_tracker.classify_job_email(subject, sender, body)

        self.assertTrue(res["is_job_email"])
        self.assertEqual(res["status"], "applied")
        self.assertEqual(res["company"], "Stripe")
        self.assertIn("Backend", res["job_title"])

    def test_classify_interview_email_with_links(self):
        subject = "Invitation to interview with Vermeg"
        sender = "talent@vermeg.com"
        body = "We were impressed with your profile and would like to invite you to an interview! Please pick a slot here: https://calendly.com/vermeg-recruiting/30min"
        res = gmail_tracker.classify_job_email(subject, sender, body)

        self.assertTrue(res["is_job_email"])
        self.assertEqual(res["status"], "interview")
        self.assertEqual(res["company"], "Vermeg")
        self.assertEqual(len(res["meeting_links"]), 1)
        self.assertIn("calendly.com", res["meeting_links"][0])

    def test_classify_rejection_email(self):
        subject = "Update regarding your application at Datadog"
        sender = "no-reply@greenhouse.io"
        body = "Thank you for taking the time to speak with Datadog. While your background is impressive, after careful review we have decided to pursue other candidates at this time."
        res = gmail_tracker.classify_job_email(subject, sender, body)

        self.assertTrue(res["is_job_email"])
        self.assertEqual(res["status"], "rejected")
        self.assertEqual(res["company"], "Datadog")

    def test_classify_offer_email(self):
        subject = "Formal Offer of Employment - Harvey"
        sender = "careers@harvey.ai"
        body = "We are pleased to offer you the position of Senior Systems Engineer at Harvey! Attached is your formal offer letter."
        res = gmail_tracker.classify_job_email(subject, sender, body)

        self.assertTrue(res["is_job_email"])
        self.assertEqual(res["status"], "offer")
        self.assertEqual(res["company"], "Harvey")

    def test_sync_gmail_advances_existing_application(self):
        import uuid
        unique_comp = f"TestCo{uuid.uuid4().hex[:6]}"
        # Create an existing application in 'applied' stage
        app_id = tracker.upsert_application(
            {
                "company": unique_comp,
                "title": "Full Stack Engineer",
                "status": "applied",
            }
        )

        mock_email = {
            "subject": f"Invitation to interview for Full Stack Engineer at {unique_comp}",
            "sender": f"karri@{unique_comp.lower()}.app",
            "body": "Hi, we loved your application and would like to invite you to interview with our engineering team next week.",
            "date": "2026-11-07T12:00:00Z",
        }

        outcome = gmail_tracker.fetch_gmail_and_sync(mock_messages=[mock_email])
        self.assertTrue(outcome["success"])
        self.assertGreaterEqual(outcome["applications_updated"], 1)

        # Verify application status advanced in SQLite
        apps = tracker.list_applications()
        matched = next((a for a in apps if a["id"] == app_id), None)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["status"], "interview")
        self.assertIn("Gmail Sync", matched["notes"])

    def test_sync_gmail_auto_creates_discovered_application(self):
        import uuid
        unique_comp = f"DiscoveredCo{uuid.uuid4().hex[:6]}"
        mock_email = {
            "subject": f"Thank you for applying to {unique_comp}",
            "sender": f"{unique_comp} Recruiting <no-reply@ashbyhq.com>",
            "body": f"We have received your application for Backend Engineer at {unique_comp}. Thank you for your interest!",
            "date": "2026-11-07T14:30:00Z",
        }

        outcome = gmail_tracker.fetch_gmail_and_sync(mock_messages=[mock_email])
        self.assertTrue(outcome["success"])
        self.assertGreaterEqual(outcome["applications_created"], 1)

        apps = tracker.list_applications()
        found = next((a for a in apps if unique_comp.lower() in a["company"].lower()), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["status"], "applied")

    def test_gmail_config_save_and_retrieve(self):
        ok = gmail_tracker.save_gmail_config("testuser@gmail.com", "abcd efgh ijkl mnop")
        self.assertTrue(ok)

        cfg = gmail_tracker.get_gmail_config()
        self.assertTrue(cfg["configured"])
        self.assertEqual(cfg["email"], "testuser@gmail.com")
        # App password is never returned in status
        self.assertNotIn("app_password", cfg)


if __name__ == "__main__":
    unittest.main()
