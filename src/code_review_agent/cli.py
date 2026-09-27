import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from code_review_agent.agent.orchestrator import ReviewAgent
from code_review_agent.config import check_ollama_available, get_settings
from code_review_agent.models import PullRequestContext
from code_review_agent.review.offline import run_offline_review

app = typer.Typer(
    name="code-review-agent",
    help="Agentic code review CLI — review diffs locally or from GitHub PRs.",
)
console = Console()


@app.command()
def review(
    diff_file: Path = typer.Argument(..., help="Path to a .diff or .patch file"),
    offline: bool = typer.Option(False, "--offline", help="Skip LLM; use static checks only"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON review to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show agent trace"),
) -> None:
    """Review a local diff file."""
    settings = get_settings()
    diff = diff_file.read_text(encoding="utf-8")

    if offline or not check_ollama_available(settings):
        if not offline and not check_ollama_available(settings):
            console.print(
                "[yellow]Ollama not reachable — running offline mode. "
                "Start with: ollama serve[/yellow]"
            )
        summary = run_offline_review(diff)
        trace = None
    else:
        agent = ReviewAgent(settings)
        summary, trace = agent.review(diff)

    _print_summary(summary)
    if verbose and trace:
        _print_trace(trace)

    if output:
        payload = summary.model_dump()
        if trace:
            payload["trace"] = trace.model_dump()
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print(f"\n[green]Saved review to {output}[/green]")


@app.command()
def pr(
    owner: str = typer.Argument(..., help="Repository owner"),
    repo: str = typer.Argument(..., help="Repository name"),
    number: int = typer.Argument(..., help="Pull request number"),
    post: bool = typer.Option(False, "--post", help="Post review to GitHub"),
    offline: bool = typer.Option(False, "--offline", help="Skip LLM"),
) -> None:
    """Review a GitHub pull request by number."""
    import asyncio

    import httpx

    from code_review_agent.github.client import GitHubClient

    settings = get_settings()
    if not settings.github_configured:
        console.print("[red]GITHUB_TOKEN is required[/red]")
        raise typer.Exit(1)

    async def _run() -> None:
        client = GitHubClient(settings.github_token)
        pr_context = await client.get_pr_context(owner, repo, number)
        diff = await client.get_pr_diff(owner, repo, number)

        if offline or not check_ollama_available(settings):
            summary = run_offline_review(diff, pr_context)
        else:
            agent = ReviewAgent(settings)
            summary, _ = agent.review(diff, pr_context)

        _print_summary(summary)

        if post:
            result = await client.post_review(
                owner, repo, number, summary, pr_context.head_sha
            )
            console.print(f"\n[green]Posted review: {result.get('html_url', 'ok')}[/green]")

    asyncio.run(_run())


@app.command()
def serve() -> None:
    """Start the FastAPI webhook server."""
    from code_review_agent.main import main

    main()


def _print_summary(summary) -> None:
    color = {"approve": "green", "comment": "yellow", "request_changes": "red"}.get(
        summary.verdict, "white"
    )
    console.print(
        Panel(
            summary.summary,
            title=f"Verdict: [{color}]{summary.verdict.upper()}[/{color}]",
            border_style=color,
        )
    )

    if summary.strengths:
        console.print("\n[bold green]Strengths[/bold green]")
        for s in summary.strengths:
            console.print(f"  • {s}")

    if summary.risks:
        console.print("\n[bold red]Risks[/bold red]")
        for r in summary.risks:
            console.print(f"  • {r}")

    if summary.comments:
        table = Table(title=f"Findings ({len(summary.comments)})")
        table.add_column("Severity", style="bold")
        table.add_column("File")
        table.add_column("Title")
        for c in summary.comments:
            table.add_row(
                c.severity.value,
                f"{c.file}" + (f":{c.line}" if c.line else ""),
                c.title,
            )
        console.print(table)

    console.print(
        f"\n[dim]Agent steps: {summary.agent_steps} | "
        f"Tools: {', '.join(summary.tools_used) or 'none'}[/dim]"
    )


def _print_trace(trace) -> None:
    console.print("\n[bold]Agent trace[/bold]")
    for step in trace.steps:
        console.print(
            f"  [{step.iteration}] {step.tool_name}({json.dumps(step.tool_input)})"
        )
        preview = step.tool_output[:200].replace("\n", " ")
        console.print(f"      → {preview}...")


if __name__ == "__main__":
    app()
