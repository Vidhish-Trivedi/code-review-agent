import json

from code_review_agent.agent.tools import ReviewToolkit
from code_review_agent.review.offline import run_offline_review

from pathlib import Path

SAMPLE_DIFF = Path(__file__).resolve().parents[1] / "examples" / "sample.diff"


def test_toolkit_inspect_diff():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    toolkit = ReviewToolkit(diff)
    output, summary = toolkit.execute("inspect_diff", {})
    assert summary is None
    assert "Changed files: 2" in output


def test_toolkit_analyze_file():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    toolkit = ReviewToolkit(diff)
    output, _ = toolkit.execute("analyze_file", {"file_path": "src/auth/service.py"})
    assert "API_KEY" in output


def test_toolkit_submit_review():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    toolkit = ReviewToolkit(diff)
    payload = {
        "verdict": "request_changes",
        "summary": "Security issues found.",
        "comments": [
            {
                "file": "src/auth/service.py",
                "line": 3,
                "severity": "critical",
                "category": "security",
                "title": "Hardcoded key",
                "body": "Remove hardcoded API key.",
            }
        ],
    }
    _, summary = toolkit.execute("submit_review", payload)
    assert summary is not None
    assert summary.verdict == "request_changes"
    assert len(summary.comments) == 1


def test_offline_review():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    summary = run_offline_review(diff)
    assert summary.verdict in ("comment", "request_changes")
    assert len(summary.comments) > 0
