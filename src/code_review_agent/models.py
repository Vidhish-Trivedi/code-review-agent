from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    SUGGESTION = "suggestion"
    WARNING = "warning"
    CRITICAL = "critical"


class ReviewCategory(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"


class FileChange(BaseModel):
    path: str
    status: str  # added | modified | deleted | renamed
    additions: int = 0
    deletions: int = 0
    patch: str = ""
    language: str = ""


class ReviewComment(BaseModel):
    file: str
    line: int | None = None
    severity: Severity
    category: ReviewCategory
    title: str
    body: str
    suggestion: str | None = None


class ReviewSummary(BaseModel):
    verdict: str = Field(
        description="approve | comment | request_changes"
    )
    summary: str
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    comments: list[ReviewComment] = Field(default_factory=list)
    agent_steps: int = 0
    tools_used: list[str] = Field(default_factory=list)


class PullRequestContext(BaseModel):
    owner: str
    repo: str
    number: int
    title: str
    body: str = ""
    author: str = ""
    base_branch: str = ""
    head_branch: str = ""
    head_sha: str = ""


class ReviewRequest(BaseModel):
    diff: str
    pr_context: PullRequestContext | None = None
    post_to_github: bool = False


class AgentStep(BaseModel):
    iteration: int
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: str


class AgentTrace(BaseModel):
    steps: list[AgentStep] = Field(default_factory=list)
    final_message: str = ""
