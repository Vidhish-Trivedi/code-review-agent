import re

from code_review_agent.models import ReviewCategory, ReviewComment, Severity
from code_review_agent.review.diff_parser import FileChange, get_changed_lines

SECURITY_PATTERNS: list[tuple[str, str, Severity, str]] = [
    (
        r"password\s*=\s*['\"][^'\"]+['\"]",
        "Hardcoded password detected",
        Severity.CRITICAL,
        "Move secrets to environment variables or a secrets manager.",
    ),
    (
        r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]",
        "Hardcoded API key detected",
        Severity.CRITICAL,
        "Use environment variables instead of embedding keys in source.",
    ),
    (
        r"eval\s*\(",
        "Use of eval()",
        Severity.CRITICAL,
        "Avoid eval(); use safer parsing or explicit logic.",
    ),
    (
        r"exec\s*\(",
        "Use of exec()",
        Severity.WARNING,
        "exec() can execute arbitrary code; validate inputs carefully.",
    ),
    (
        r"pickle\.loads?\(",
        "Unsafe deserialization with pickle",
        Severity.WARNING,
        "Pickle can execute arbitrary code on untrusted data.",
    ),
    (
        r"subprocess\.(call|run|Popen)\([^)]*shell\s*=\s*True",
        "Shell injection risk via subprocess",
        Severity.WARNING,
        "Avoid shell=True; pass arguments as a list.",
    ),
    (
        r"innerHTML\s*=",
        "Direct innerHTML assignment (XSS risk)",
        Severity.WARNING,
        "Sanitize HTML or use textContent / a safe templating layer.",
    ),
    (
        r"md5\s*\(",
        "Weak hash algorithm (MD5)",
        Severity.SUGGESTION,
        "Use SHA-256 or stronger for security-sensitive hashing.",
    ),
]

STYLE_PATTERNS: list[tuple[str, str]] = [
    (r"print\s*\(", "Debug print statement left in code"),
    (r"console\.log\s*\(", "Console.log left in code"),
    (r"#\s*TODO", "Unresolved TODO comment"),
    (r"//\s*TODO", "Unresolved TODO comment"),
    (r"except\s*:", "Bare except clause"),
    (r"pass\s*$", "Empty pass block — may indicate incomplete implementation"),
]


def run_security_scan(files: list[FileChange]) -> list[ReviewComment]:
    comments: list[ReviewComment] = []

    for file in files:
        if file.status == "deleted":
            continue
        for line_no, content in get_changed_lines(file.patch):
            for pattern, title, severity, suggestion in SECURITY_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    comments.append(
                        ReviewComment(
                            file=file.path,
                            line=line_no,
                            severity=severity,
                            category=ReviewCategory.SECURITY,
                            title=title,
                            body=f"Line {line_no}: `{content.strip()}`",
                            suggestion=suggestion,
                        )
                    )
    return comments


def run_style_scan(files: list[FileChange]) -> list[ReviewComment]:
    comments: list[ReviewComment] = []

    for file in files:
        if file.status == "deleted":
            continue
        for line_no, content in get_changed_lines(file.patch):
            for pattern, title in STYLE_PATTERNS:
                if re.search(pattern, content):
                    comments.append(
                        ReviewComment(
                            file=file.path,
                            line=line_no,
                            severity=Severity.SUGGESTION,
                            category=ReviewCategory.STYLE,
                            title=title,
                            body=f"Line {line_no}: `{content.strip()}`",
                        )
                    )
    return comments


def run_test_coverage_check(files: list[FileChange]) -> list[ReviewComment]:
    """Flag source changes that have no corresponding test file changes."""
    comments: list[ReviewComment] = []
    changed_paths = {f.path for f in files}
    source_files = [
        f
        for f in files
        if f.status in ("added", "modified")
        and f.language in ("python", "javascript", "typescript")
        and not _is_test_file(f.path)
    ]

    for source in source_files:
        test_candidates = _test_file_candidates(source.path)
        if not any(candidate in changed_paths for candidate in test_candidates):
            comments.append(
                ReviewComment(
                    file=source.path,
                    severity=Severity.SUGGESTION,
                    category=ReviewCategory.TESTING,
                    title="No test changes detected for modified source",
                    body=(
                        f"`{source.path}` was changed but no matching test file "
                        f"appears in this diff."
                    ),
                    suggestion="Add or update unit tests for the new behavior.",
                )
            )
    return comments


def _is_test_file(path: str) -> bool:
    lower = path.lower()
    return (
        "/test_" in lower
        or lower.startswith("test_")
        or "/tests/" in lower
        or lower.endswith("_test.py")
        or lower.endswith(".test.ts")
        or lower.endswith(".test.js")
        or lower.endswith(".spec.ts")
        or lower.endswith(".spec.js")
    )


def _test_file_candidates(source_path: str) -> list[str]:
    if source_path.endswith(".py"):
        stem = source_path.rsplit("/", 1)[-1].removesuffix(".py")
        directory = source_path.rsplit("/", 1)[0] if "/" in source_path else ""
        prefix = f"{directory}/" if directory else ""
        return [
            f"{prefix}test_{stem}.py",
            f"{prefix}tests/test_{stem}.py",
            f"tests/test_{stem}.py",
        ]
    if source_path.endswith((".ts", ".js", ".tsx", ".jsx")):
        return [
            source_path.replace(".ts", ".test.ts")
            .replace(".js", ".test.js")
            .replace(".tsx", ".test.tsx")
            .replace(".jsx", ".test.jsx"),
        ]
    return []
