"""Offline review path using static analyzers only (no LLM)."""

from code_review_agent.agent.tools import ReviewToolkit, merge_automated_findings
from code_review_agent.models import PullRequestContext, ReviewComment, ReviewSummary, Severity
from code_review_agent.review.analyzers import (
    run_security_scan,
    run_style_scan,
    run_test_coverage_check,
)
from code_review_agent.review.diff_parser import parse_diff, summarize_diff


def run_offline_review(
    diff: str, pr_context: PullRequestContext | None = None
) -> ReviewSummary:
    """Run deterministic checks without calling an LLM."""
    files = parse_diff(diff)
    automated: list[ReviewComment] = []
    automated.extend(run_security_scan(files))
    automated.extend(run_style_scan(files))
    automated.extend(run_test_coverage_check(files))

    has_critical = any(c.severity == Severity.CRITICAL for c in automated)
    has_warning = any(c.severity == Severity.WARNING for c in automated)
    verdict = "request_changes" if has_critical else ("comment" if has_warning or automated else "approve")

    overview = summarize_diff(files)
    summary = ReviewSummary(
        verdict=verdict,
        summary=f"Offline static analysis completed.\n\n{overview}",
        comments=automated,
        tools_used=["check_security", "check_style", "check_test_coverage"],
        agent_steps=3,
    )
    return summary
