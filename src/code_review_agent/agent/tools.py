import json
from typing import Any

from code_review_agent.models import (
    PullRequestContext,
    ReviewCategory,
    ReviewComment,
    ReviewSummary,
    Severity,
)
from code_review_agent.review.analyzers import (
    run_security_scan,
    run_style_scan,
    run_test_coverage_check,
)
from code_review_agent.review.diff_parser import parse_diff, summarize_diff


class ReviewToolkit:
    """Stateful tool registry bound to a single diff review session."""

    def __init__(self, diff: str, pr_context: PullRequestContext | None = None) -> None:
        self.diff = diff
        self.pr_context = pr_context
        self.files = parse_diff(diff)
        self._automated_comments: list[ReviewComment] = []
        self.tools_used: list[str] = []

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "inspect_diff",
                    "description": "Get an overview of all changed files, languages, and line counts.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_file",
                    "description": "Get the full patch/diff for a specific changed file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path of the file to inspect.",
                            }
                        },
                        "required": ["file_path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_security",
                    "description": "Run security pattern checks on all changed lines.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_style",
                    "description": "Run style and hygiene checks (TODOs, debug prints, bare except).",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_test_coverage",
                    "description": "Flag source file changes that have no matching test changes in the diff.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_review",
                    "description": "Submit the final structured code review. Call this when done.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "verdict": {
                                "type": "string",
                                "enum": ["approve", "comment", "request_changes"],
                            },
                            "summary": {"type": "string"},
                            "strengths": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "risks": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "comments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "file": {"type": "string"},
                                        "line": {"type": ["integer", "null"]},
                                        "severity": {
                                            "type": "string",
                                            "enum": [
                                                "info",
                                                "suggestion",
                                                "warning",
                                                "critical",
                                            ],
                                        },
                                        "category": {
                                            "type": "string",
                                            "enum": [
                                                "bug",
                                                "security",
                                                "performance",
                                                "style",
                                                "maintainability",
                                                "testing",
                                            ],
                                        },
                                        "title": {"type": "string"},
                                        "body": {"type": "string"},
                                        "suggestion": {"type": ["string", "null"]},
                                    },
                                    "required": [
                                        "file",
                                        "severity",
                                        "category",
                                        "title",
                                        "body",
                                    ],
                                },
                            },
                        },
                        "required": ["verdict", "summary", "comments"],
                    },
                },
            },
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> tuple[str, ReviewSummary | None]:
        self.tools_used.append(name)

        if name == "inspect_diff":
            overview = summarize_diff(self.files)
            context = ""
            if self.pr_context:
                context = (
                    f"\n\nPR #{self.pr_context.number}: {self.pr_context.title}\n"
                    f"Author: {self.pr_context.author}\n"
                    f"Branch: {self.pr_context.head_branch} → {self.pr_context.base_branch}"
                )
            return overview + context, None

        if name == "analyze_file":
            path = arguments.get("file_path", "")
            match = next((f for f in self.files if f.path == path), None)
            if not match:
                available = ", ".join(f.path for f in self.files) or "(none)"
                return f"File not found: {path}. Available: {available}", None
            header = (
                f"File: {match.path} [{match.status}] "
                f"(+{match.additions}/-{match.deletions}, {match.language})\n\n"
            )
            return header + (match.patch or "(empty patch)"), None

        if name == "check_security":
            findings = run_security_scan(self.files)
            self._automated_comments.extend(findings)
            return _format_comments(findings), None

        if name == "check_style":
            findings = run_style_scan(self.files)
            self._automated_comments.extend(findings)
            return _format_comments(findings), None

        if name == "check_test_coverage":
            findings = run_test_coverage_check(self.files)
            self._automated_comments.extend(findings)
            return _format_comments(findings), None

        if name == "submit_review":
            return "Review submitted.", _build_summary(arguments)

        return f"Unknown tool: {name}", None


def _format_comments(comments: list[ReviewComment]) -> str:
    if not comments:
        return "No issues found."
    lines = [f"Found {len(comments)} issue(s):"]
    for c in comments:
        loc = f"{c.file}:{c.line}" if c.line else c.file
        lines.append(f"- [{c.severity.value}/{c.category.value}] {loc} — {c.title}")
        lines.append(f"  {c.body}")
        if c.suggestion:
            lines.append(f"  Suggestion: {c.suggestion}")
    return "\n".join(lines)


def _build_summary(payload: dict[str, Any]) -> ReviewSummary:
    comments = [
        ReviewComment(
            file=c["file"],
            line=c.get("line"),
            severity=Severity(c["severity"]),
            category=ReviewCategory(c["category"]),
            title=c["title"],
            body=c["body"],
            suggestion=c.get("suggestion"),
        )
        for c in payload.get("comments", [])
    ]
    return ReviewSummary(
        verdict=payload["verdict"],
        summary=payload["summary"],
        strengths=payload.get("strengths", []),
        risks=payload.get("risks", []),
        comments=comments,
    )


def merge_automated_findings(
    summary: ReviewSummary, automated: list[ReviewComment]
) -> ReviewSummary:
    """Deduplicate and merge static analyzer results into the agent review."""
    seen = {(c.file, c.line, c.title) for c in summary.comments}
    merged = list(summary.comments)
    for comment in automated:
        key = (comment.file, comment.line, comment.title)
        if key not in seen:
            merged.append(comment)
            seen.add(key)

    critical = [c for c in merged if c.severity == Severity.CRITICAL]
    warnings = [c for c in merged if c.severity == Severity.WARNING]
    verdict = summary.verdict
    if critical and verdict == "approve":
        verdict = "request_changes"
    elif warnings and verdict == "approve":
        verdict = "comment"

    return summary.model_copy(update={"comments": merged, "verdict": verdict})
