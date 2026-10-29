import json
import shutil
import tempfile
import unittest

from fang.config import Config
from fang.engine import analyze
from fang.models import RunReport
from fang.report_html import render_badge, render_html, render_markdown
from tests.helpers import calc_project


class HtmlReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="fang-html-")
        calc_project(cls.root)
        config = Config(root=cls.root, paths=["."], tests=["tests"], jobs=1, cache=False)
        cls.report = analyze(config)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_html_is_self_contained(self):
        document = render_html(self.report)
        self.assertTrue(document.startswith("<!doctype html>"))
        self.assertIn("mutation score", document)
        self.assertIn("%.1f" % self.report.score, document)
        self.assertIn("survived", document.lower())
        self.assertNotIn("<script src=", document)
        self.assertNotIn("<link", document)
        self.assertNotIn("googleapis", document)

    def test_embedded_json_round_trips(self):
        document = render_html(self.report)
        marker = '<script id="fang-data" type="application/json">'
        start = document.index(marker) + len(marker)
        end = document.index("</script>", start)
        data = json.loads(document[start:end])
        self.assertEqual(data["tool"], "fang")
        self.assertEqual(data["survived"], self.report.survived)
        self.assertEqual(len(data["results"]), len(self.report.results))

    def test_markdown(self):
        document = render_markdown(self.report)
        self.assertIn("Fang mutation report", document)
        self.assertIn("%.1f%%" % self.report.score, document)
        self.assertIn("Surviving mutants", document)

    def test_badge(self):
        badge = render_badge(self.report)
        self.assertIn("<svg", badge)
        self.assertIn("%.1f%%" % self.report.score, badge)

    def test_empty_report(self):
        report = RunReport(
            version="0.1.0",
            root=".",
            mode="diff",
            diff_base="HEAD",
            started_at="2026-01-01T00:00:00+00:00",
            duration=0.0,
            baseline_duration=0.0,
            test_label="unittest",
            test_command="python -m unittest",
            files_scanned=0,
            mutants_total=0,
            mutants_considered=0,
            sampled=False,
            sample_size=None,
            results=[],
            score=None,
            score_ci=None,
            python_version="3.9.0",
            git_head=None,
            cache_hits=0,
        )
        document = render_html(report)
        self.assertIn("n/a", document)
        self.assertIn("No mutants were evaluated", document)


if __name__ == "__main__":
    unittest.main()
