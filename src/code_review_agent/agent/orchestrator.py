import json
import logging
from typing import Any

from openai import OpenAI

from code_review_agent.agent.prompts import SYSTEM_PROMPT
from code_review_agent.agent.tools import ReviewToolkit, merge_automated_findings
from code_review_agent.config import Settings, check_ollama_available
from code_review_agent.models import AgentStep, AgentTrace, PullRequestContext, ReviewSummary

logger = logging.getLogger(__name__)


class ReviewAgent:
    """Runs a tool-calling loop until the agent submits a structured review."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not check_ollama_available(settings):
            raise RuntimeError(
                f"Ollama is not reachable at {settings.ollama_base_url}. "
                "Start it with: ollama serve"
            )
        self.client = OpenAI(
            api_key=settings.ollama_api_key,
            base_url=settings.ollama_base_url,
        )

    def review(
        self,
        diff: str,
        pr_context: PullRequestContext | None = None,
    ) -> tuple[ReviewSummary, AgentTrace]:
        toolkit = ReviewToolkit(diff=diff, pr_context=pr_context)
        trace = AgentTrace()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_message(diff, pr_context),
            },
        ]

        final_summary: ReviewSummary | None = None

        for iteration in range(1, self.settings.max_agent_iterations + 1):
            response = self.client.chat.completions.create(
                model=self.settings.ollama_model,
                messages=messages,
                tools=toolkit.get_tool_definitions(),
                tool_choice="auto",
            )
            message = response.choices[0].message

            if message.tool_calls:
                messages.append(message.model_dump(exclude_none=True))
                for tool_call in message.tool_calls:
                    name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    output, summary = toolkit.execute(name, args)
                    trace.steps.append(
                        AgentStep(
                            iteration=iteration,
                            tool_name=name,
                            tool_input=args,
                            tool_output=output[:4000],
                        )
                    )

                    if summary is not None:
                        final_summary = summary

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": output,
                        }
                    )

                if final_summary is not None:
                    break
                continue

            if message.content:
                trace.final_message = message.content
                messages.append({"role": "assistant", "content": message.content})
            break

        if final_summary is None:
            final_summary = _fallback_summary(toolkit, trace.final_message)

        final_summary = merge_automated_findings(
            final_summary, toolkit._automated_comments
        )
        final_summary.agent_steps = len(trace.steps)
        final_summary.tools_used = list(dict.fromkeys(toolkit.tools_used))
        return final_summary, trace


def _build_user_message(
    diff: str, pr_context: PullRequestContext | None
) -> str:
    header = "Review the following pull request diff."
    if pr_context:
        header += (
            f"\n\nPR #{pr_context.number}: {pr_context.title}"
            f"\nAuthor: {pr_context.author}"
        )
    truncated = diff if len(diff) <= 12000 else diff[:12000] + "\n\n... (diff truncated)"
    return f"{header}\n\n```diff\n{truncated}\n```"


def _fallback_summary(toolkit: ReviewToolkit, assistant_message: str) -> ReviewSummary:
    """Build a minimal review if the agent never called submit_review."""
    from code_review_agent.models import ReviewCategory, ReviewComment, Severity

    comments = list(toolkit._automated_comments)
    if assistant_message and not comments:
        comments.append(
            ReviewComment(
                file="(general)",
                severity=Severity.INFO,
                category=ReviewCategory.MAINTAINABILITY,
                title="Agent notes",
                body=assistant_message,
            )
        )

    has_critical = any(c.severity == Severity.CRITICAL for c in comments)
    verdict = "request_changes" if has_critical else "comment"

    return ReviewSummary(
        verdict=verdict,
        summary=assistant_message or "Automated review completed without agent summary.",
        comments=comments,
    )
