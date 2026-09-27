from pathlib import Path

from code_review_agent.review.analyzers import (
    run_security_scan,
    run_style_scan,
    run_test_coverage_check,
)
from code_review_agent.review.diff_parser import parse_diff, summarize_diff


SAMPLE_DIFF = Path(__file__).resolve().parents[1] / "examples" / "sample.diff"


def test_parse_diff_finds_two_files():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    files = parse_diff(diff)
    assert len(files) == 2
    paths = {f.path for f in files}
    assert "src/auth/service.py" in paths
    assert "src/api/users.py" in paths


def test_parse_diff_counts_lines():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    files = parse_diff(diff)
    auth = next(f for f in files if f.path.endswith("service.py"))
    assert auth.status == "added"
    assert auth.additions == 17
    assert auth.language == "python"


def test_summarize_diff():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    files = parse_diff(diff)
    summary = summarize_diff(files)
    assert "Changed files: 2" in summary
    assert "src/auth/service.py" in summary


def test_security_scan_finds_hardcoded_secrets():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    files = parse_diff(diff)
    findings = run_security_scan(files)
    titles = {f.title for f in findings}
    assert "Hardcoded API key detected" in titles
    assert "Use of eval()" in titles


def test_style_scan_finds_todo_and_print():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    files = parse_diff(diff)
    findings = run_style_scan(files)
    titles = {f.title for f in findings}
    assert "Unresolved TODO comment" in titles
    assert "Debug print statement left in code" in titles


def test_test_coverage_flags_missing_tests():
    diff = SAMPLE_DIFF.read_text(encoding="utf-8")
    files = parse_diff(diff)
    findings = run_test_coverage_check(files)
    assert any("No test changes" in f.title for f in findings)
