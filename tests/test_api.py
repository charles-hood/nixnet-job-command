#!/usr/bin/env python3
"""Boot the server on a temp database and hit /api/health, /api/jobs, /api/progress."""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "app"
sys.path.insert(0, str(APP))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="njc-test-")
        data = Path(cls.tmp.name) / "data"
        data.mkdir()
        cls.port = _free_port()
        os.environ["NJC_ROOT"] = str(REPO)
        # Hermetic: never pick up a local config.toml with real settings.
        os.environ["NJC_CONFIG"] = str(REPO / "config.example.toml")
        os.environ["NJC_DB_FILE"] = "njc.db"
        os.environ["NJC_DATA"] = str(data)
        os.environ["NJC_PORT"] = str(cls.port)
        os.environ["NJC_BIND"] = "127.0.0.1"
        os.environ["NJC_PROFILE"] = str(REPO / "profile.example.json")
        os.environ["NJC_SEED"] = str(REPO / "seed" / "example_seed.json")
        os.environ["NJC_TIMEZONE"] = "local"
        import config
        config.CFG.reload()
        import server
        server.apply_runtime()
        server.init()
        cls.server_mod = server
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", cls.port), server.H)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.port
        # Wait until health answers.
        deadline = time.time() + 8
        last = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(cls.base + "/api/health", timeout=1) as r:
                    if r.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
                time.sleep(0.1)
        raise RuntimeError("server did not start: %s" % last)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
        except Exception:
            pass
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            body = r.read()
            ctype = r.headers.get("Content-Type", "")
            if "json" in ctype:
                return r.status, json.loads(body)
            return r.status, body

    def test_health(self):
        status, data = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        self.assertIn("version", data)
        self.assertGreaterEqual(data.get("jobs", 0), 1)
        self.assertEqual(data.get("app_name"), "NixNet Job Command")

    def test_jobs(self):
        status, data = self.get("/api/jobs")
        self.assertEqual(status, 200)
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 8)
        refs = {j.get("ref") for j in data}
        self.assertIn("J-001", refs)
        acme = next(j for j in data if j["ref"] == "J-001")
        self.assertEqual(acme.get("company"), "Acme Cloud")
        self.assertNotIn("jd", acme)  # light list omits the job description

    def test_progress(self):
        status, data = self.get("/api/progress")
        self.assertEqual(status, 200)
        self.assertIn("days", data)
        self.assertIn("goal", data)
        self.assertIn("start_date", data)
        self.assertIsInstance(data["days"], list)
        self.assertGreaterEqual(len(data["days"]), 1)
        self.assertGreaterEqual(data.get("total", 0), 1)

    def test_index(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"NixNet Job Command", body)


    def _send(self, method, path, body=None):
        req = urllib.request.Request(
            self.base + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")

    def test_hot_leads_sort_first_and_are_searchable(self):
        self._send("PATCH", "/api/jobs/J-003", {"hot": True, "due_label": "Friday noon"})
        try:
            _, jobs = self.get("/api/jobs")
            self.assertEqual(jobs[0]["ref"], "J-003")
            self.assertTrue(self.server_mod.is_hot(jobs[0]))
        finally:
            self._send("PATCH", "/api/jobs/J-003", {"hot": False, "due_label": ""})

    def test_answers_flag_has_both_names(self):
        _, made = self._send("POST", "/api/answers", {"question": "q", "answer": "a", "fred_decides": True})
        _, rows = self.get("/api/answers")
        row = next(r for r in rows if r["id"] == made["id"])
        self.assertEqual(row["needs_review"], 1)
        self.assertEqual(row["fred_decides"], 1)

    def test_legacy_fred_decides_column_is_detected(self):
        import sqlite3
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE answers(id TEXT, fred_decides INTEGER)")
        self.assertEqual(self.server_mod.detect_answers_flag(c), "fred_decides")
        c.execute("DROP TABLE answers")
        c.execute("CREATE TABLE answers(id TEXT, needs_review INTEGER)")
        self.assertEqual(self.server_mod.detect_answers_flag(c), "needs_review")
        # restore for the live test database
        real = sqlite3.connect(self.server_mod.DB)
        self.server_mod.detect_answers_flag(real)
        real.close()

    def test_seed_can_be_turned_off(self):
        import config
        os.environ["NJC_SEED"] = "none"
        try:
            config.CFG.reload()
            self.assertIsNone(config.CFG.seed_path)
        finally:
            os.environ["NJC_SEED"] = str(REPO / "seed" / "example_seed.json")
            config.CFG.reload()


if __name__ == "__main__":
    unittest.main(verbosity=2)
