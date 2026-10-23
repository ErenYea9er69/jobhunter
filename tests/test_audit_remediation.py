"""Regression tests for audit remediation and security hardening."""
import base64
import gzip
import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch, MagicMock

from jh import dedup, httpd, util, autofill, refit, resume_parser


class TestAuditRemediation(unittest.TestCase):
    def test_find_static_file_path_traversal_blocked(self):
        """Verify that directory traversal sequences cannot escape the public static folder."""
        bad_paths = [
            "../../jobhunter.db",
            "../server.py",
            "/../../server.py",
            "..\\..\\server.py",
            "....//....//server.py",
            "/etc/passwd",
            "c:/windows/win.ini",
            "../../data/jobhunter.db",
            "index.html/../../server.py",
        ]
        for bad in bad_paths:
            with self.subTest(bad=bad):
                res = httpd._find_static_file(bad)
                self.assertIsNone(res, f"Path traversal succeeded for: {bad} -> {res}")

    def test_find_static_file_legitimate_assets_allowed(self):
        """Verify legitimate static files still resolve correctly."""
        index_path = httpd._find_static_file("index.html")
        self.assertIsNotNone(index_path)
        self.assertTrue(index_path.endswith("index.html"))
        self.assertTrue(os.path.isfile(index_path))

        css_path = httpd._find_static_file("styles.css")
        self.assertIsNotNone(css_path)
        self.assertTrue(css_path.endswith("styles.css"))
        self.assertTrue(os.path.isfile(css_path))

    def test_http_get_scheme_validation(self):
        """Verify that http_get enforces http and https schemes and blocks file:// or other protocols."""
        with self.assertRaises(util.HttpError) as ctx:
            util.http_get("file:///c:/windows/win.ini")
        self.assertIn("Unsupported URL scheme", str(ctx.exception))

        with self.assertRaises(util.HttpError) as ctx2:
            util.http_get("ftp://ftp.example.com/file")
        self.assertIn("Unsupported URL scheme", str(ctx2.exception))

        with self.assertRaises(util.HttpError) as ctx3:
            util.http_get("javascript:alert(1)")
        self.assertIn("Unsupported URL scheme", str(ctx3.exception))

    def test_autofill_bookmarklet_safe_dom_construction(self):
        """Verify autofill bookmarklet uses safe programmatic DOM nodes with zero innerHTML sinks."""
        payload = {
            "full_name": "<script>alert(1)</script>",
            "email": "test@example.com",
            "detected_platform": "<img src=x onerror=alert(1)>",
            "cover_letter": "Pitch",
        }
        code = autofill.generate_bookmarklet_code(payload)
        # Verify no innerHTML injection sink
        self.assertNotIn("toast.innerHTML", code)
        self.assertIn("badgeSpan.textContent", code)
        self.assertIn("titleSpan.textContent", code)
        self.assertIn("document.createElement", code)

    def test_job_key_sha256_format_and_stability(self):
        """Verify that job_key produces a 16-character hex digest and is stable."""
        job = {"title": "Senior Backend Engineer", "company": "Stripe, Inc."}
        k1 = dedup.job_key(job)
        k2 = dedup.job_key(job)
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 16)
        int(k1, 16)

        other = {"title": "Frontend Engineer", "company": "Stripe, Inc."}
        self.assertNotEqual(k1, dedup.job_key(other))

    def test_http_get_gzip_bomb_protection(self):
        """Verify that decompressed response size is capped to max_bytes to protect against gzip bombs."""
        # Create a compressed payload that inflates beyond max_bytes
        large_uncompressed = b"A" * 50_000
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(large_uncompressed)
        compressed_data = buf.getvalue()

        # Mock urllib.request.urlopen returning this compressed response
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Encoding": "gzip"}
        mock_resp.read.return_value = compressed_data
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(util.HttpError) as ctx:
                util.http_get("https://example.com/api/jobs", max_bytes=10_000)
            self.assertIn("decompressed response too large", str(ctx.exception))

    def test_httpd_content_length_validation(self):
        """Verify that malformed or negative Content-Length headers are rejected with 400 Bad Request."""
        handler = MagicMock()
        handler.headers = {"Host": "127.0.0.1", "X-JH-Token": httpd.TOKEN, "Content-Length": "-5"}
        handler.path = "/api/profile"
        handler._host_ok.return_value = True

        res = httpd.Handler._dispatch(handler, "POST")
        handler._json.assert_called_with({"error": "Invalid Content-Length header"}, 400)

        # Non-numeric Content-Length
        handler.headers["Content-Length"] = "invalid_number"
        res = httpd.Handler._dispatch(handler, "POST")
        handler._json.assert_called_with({"error": "Invalid Content-Length header"}, 400)

    def test_httpd_token_exact_query_validation(self):
        """Verify that loose substring tokens in query string are rejected."""
        handler = MagicMock()
        handler.headers = {"Host": "127.0.0.1"}
        # Substring prefix match attempt: not_token=... should fail
        handler.path = f"/api/profile?not_token={httpd.TOKEN}&other=1"
        handler._host_ok.return_value = True

        res = httpd.Handler._dispatch(handler, "GET")
        handler._json.assert_called_with({"error": "Missing or invalid session token. Reload the page."}, 401)

    def test_llm_api_error_response_handling(self):
        """Verify that API errors in LLM provider responses raise informative RuntimeError instead of KeyError."""
        error_payload = json.dumps({"error": {"message": "Invalid API key provided", "type": "auth_error"}})

        with patch("jh.refit.http_get", return_value=error_payload):
            with self.assertRaises(RuntimeError) as ctx:
                refit._call_llm("sys", "user", cfg={"provider": "gemini", "key": "bad_key", "model": "gemini-2.5-flash"})
            self.assertIn("Gemini API error: Invalid API key provided", str(ctx.exception))

            with self.assertRaises(RuntimeError) as ctx2:
                refit._call_llm("sys", "user", cfg={"provider": "openai", "key": "bad_key", "model": "gpt-4o-mini"})
            self.assertIn("Openai API error: Invalid API key provided", str(ctx2.exception))

    def test_resume_parser_oversized_upload_rejected(self):
        """Verify that raw resume upload exceeding 20MB is rejected early."""
        oversized_b64 = base64.b64encode(b"X" * (20_000_001)).decode("ascii")
        with self.assertRaises(resume_parser.ParseError) as ctx:
            resume_parser.decode_upload({"content_base64": oversized_b64, "filename": "resume.pdf"})
        self.assertIn("Uploaded file exceeds 20MB limit", str(ctx.exception))

    def test_resume_parser_docx_uncompressed_limit(self):
        """Verify that .docx files with oversized document.xml (>10MB) are rejected to prevent zip bombs."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", b"<xml>" + (b"A" * 10_000_005) + b"</xml>")
        docx_raw = buf.getvalue()

        with self.assertRaises(resume_parser.ParseError) as ctx:
            resume_parser._docx_text(docx_raw)
        self.assertIn("too large to process", str(ctx.exception))


    def test_pdf_builtin_stream_inflation(self):
        """Verify that _pdf_text_builtin decompresses streams and extracts text correctly."""
        import zlib
        stream_content = b"BT /F1 12 Tf (Jane Doe Software Engineer) Tj ET"
        compressed = zlib.compress(stream_content)
        mock_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nstream\n" + compressed + b"\nendstream\nendobj\n%%EOF"
        text = resume_parser._pdf_text_builtin(mock_pdf)
        self.assertIn("Jane Doe Software Engineer", text)


if __name__ == "__main__":
    unittest.main()
