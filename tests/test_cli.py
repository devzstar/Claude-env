"""End-to-end test of the M1 manual loop through the CLI. Run: python -m unittest"""

import contextlib
import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from clipper import cli


class CliLoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        os.environ["CLIPPER_DB"] = str(self.db)

    def tearDown(self):
        os.environ.pop("CLIPPER_DB", None)
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cli.main(list(argv))
        return out.getvalue(), err.getvalue()

    def q(self, sql, *params):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(sql, params).fetchall()

    def test_full_manual_loop(self):
        self.run_cli("account", "add", "tiktok", "@me", "--whop-linked")
        self.run_cli("campaign", "add", "Podcast X", "--rate", "2", "--budget", "5000",
                     "--min", "4", "--max", "300", "--platforms", "tt,yt", "--tags", "#ad,@podx")
        self.run_cli("source", "add", "1", "sources/podx/ep1.mp4", "--duration", "3600")
        self.run_cli("clip", "add", "1", "--source", "1", "--start", "120", "--end", "150",
                     "--hook", "He said WHAT")
        out, err = self.run_cli("post", "add", "1", "tiktok", "https://tiktok.com/@me/video/1",
                                "--caption", "wild #ad @podx")
        self.assertIn("clipper submit add 1", out)
        self.assertEqual(err, "")  # linked account, eligible platform, tags present, fresh budget

        out, _ = self.run_cli("post", "list", "--unsubmitted")
        self.assertIn("NOT SUBMITTED", out)
        self.run_cli("submit", "add", "1")
        out, _ = self.run_cli("post", "list", "--unsubmitted")
        self.assertIn("(none)", out)

        self.run_cli("snap", "add", "1", "1000")
        out, _ = self.run_cli("snap", "add", "1", "4500", "--shot", "screenshots/1-24h.png")
        self.assertIn("+3,500", out)
        self.run_cli("submit", "set", "1", "approved")
        self.run_cli("payout", "add", "1", "9.00")
        self.run_cli("time", "add", "45", "post")

        self.assertEqual(self.q("SELECT status FROM clips")[0][0], "posted")
        self.assertEqual(self.q("SELECT status FROM submissions")[0][0], "approved")
        self.assertEqual(self.q("SELECT COUNT(*) FROM view_snaps")[0][0], 2)
        self.assertEqual(self.q("SELECT amount FROM payouts")[0][0], 9.0)

    def test_guardrails_warn_but_still_log(self):
        self.run_cli("account", "add", "instagram", "@me")  # not Whop-linked
        self.run_cli("campaign", "add", "TT only", "--rate", "1", "--platforms", "tiktok",
                     "--tags", "#ad")
        self.run_cli("clip", "add", "1")
        _, err = self.run_cli("post", "add", "1", "ig", "https://instagram.com/reel/1",
                              "--caption", "no tags here")
        self.assertIn("NOT linked to Whop", err)
        self.assertIn("doesn't list instagram", err)
        self.assertIn("missing required tags", err)
        self.assertIn("budget not checked", err)
        self.assertEqual(self.q("SELECT COUNT(*) FROM posts")[0][0], 1)

    def test_duplicate_url_and_submission_rejected(self):
        self.run_cli("account", "add", "youtube", "@me", "--whop-linked")
        self.run_cli("campaign", "add", "C", "--rate", "1", "--budget-left", "100")
        self.run_cli("clip", "add", "1")
        self.run_cli("post", "add", "1", "yt", "https://youtube.com/shorts/a", "--submitted")
        with self.assertRaises(SystemExit):
            self.run_cli("post", "add", "1", "yt", "https://youtube.com/shorts/a")
        with self.assertRaises(SystemExit):
            self.run_cli("submit", "add", "1")


if __name__ == "__main__":
    unittest.main()
