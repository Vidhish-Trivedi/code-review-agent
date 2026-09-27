import re
from pathlib import PurePosixPath

from code_review_agent.models import FileChange

DIFF_FILE_HEADER = re.compile(r"^diff --git a/(.*) b/(.*)$")
HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".sh": "shell",
}


def detect_language(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return LANGUAGE_MAP.get(suffix, "unknown")


def parse_diff(diff_text: str) -> list[FileChange]:
    """Parse a unified diff into structured file changes."""
    if not diff_text.strip():
        return []

    files: list[FileChange] = []
    current_path = ""
    current_status = "modified"
    patch_lines: list[str] = []
    additions = 0
    deletions = 0

    def flush() -> None:
        nonlocal current_path, current_status, patch_lines, additions, deletions
        if not current_path:
            return
        files.append(
            FileChange(
                path=current_path,
                status=current_status,
                additions=additions,
                deletions=deletions,
                patch="\n".join(patch_lines),
                language=detect_language(current_path),
            )
        )
        current_path = ""
        current_status = "modified"
        patch_lines = []
        additions = 0
        deletions = 0

    for line in diff_text.splitlines():
        file_match = DIFF_FILE_HEADER.match(line)
        if file_match:
            flush()
            current_path = file_match.group(2)
            patch_lines.append(line)
            continue

        if line.startswith("new file mode"):
            current_status = "added"
            patch_lines.append(line)
            continue

        if line.startswith("deleted file mode"):
            current_status = "deleted"
            patch_lines.append(line)
            continue

        if line.startswith("rename from"):
            current_status = "renamed"
            patch_lines.append(line)
            continue

        if current_path:
            patch_lines.append(line)
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

    flush()
    return files


def get_changed_lines(patch: str) -> list[tuple[int, str]]:
    """Return (line_number, content) for each added line in a patch."""
    lines: list[tuple[int, str]] = []
    current_line = 0

    for line in patch.splitlines():
        hunk = HUNK_HEADER.match(line)
        if hunk:
            current_line = int(hunk.group(1))
            continue

        if line.startswith("+++") or line.startswith("---"):
            continue

        if line.startswith("+") and not line.startswith("++"):
            lines.append((current_line, line[1:]))
            current_line += 1
        elif line.startswith("-") and not line.startswith("--"):
            continue
        elif line.startswith(" "):
            current_line += 1
        elif line.startswith("\\"):
            continue
        elif line and not line.startswith("diff ") and not line.startswith("index "):
            current_line += 1

    return lines


def summarize_diff(files: list[FileChange]) -> str:
    if not files:
        return "No file changes detected."

    total_add = sum(f.additions for f in files)
    total_del = sum(f.deletions for f in files)
    lines = [
        f"Changed files: {len(files)} (+{total_add}/-{total_del} lines)",
        "",
    ]
    for f in files:
        lines.append(
            f"- [{f.status}] {f.path} ({f.language}) +{f.additions}/-{f.deletions}"
        )
    return "\n".join(lines)
