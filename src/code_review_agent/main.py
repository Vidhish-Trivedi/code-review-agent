import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from code_review_agent import __version__
from code_review_agent.agent.orchestrator import ReviewAgent
from code_review_agent.config import check_ollama_available, get_settings
from code_review_agent.github.client import (
    GitHubClient,
    parse_webhook_payload,
    verify_webhook_signature,
)
from code_review_agent.models import ReviewRequest, ReviewSummary
from code_review_agent.review.offline import run_offline_review

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    yield


app = FastAPI(
    title="Code Review Agent",
    description="Agentic AI service for automated pull request reviews",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    ollama_up = check_ollama_available(settings)
    return {
        "status": "ok",
        "version": __version__,
        "ollama_available": ollama_up,
        "ollama_model": settings.ollama_model,
        "github_configured": settings.github_configured,
    }


@app.post("/review", response_model=ReviewSummary)
async def review_pr(request: ReviewRequest) -> ReviewSummary:
    settings = get_settings()
    if not request.diff.strip():
        raise HTTPException(status_code=400, detail="diff cannot be empty")

    if check_ollama_available(settings):
        agent = ReviewAgent(settings)
        summary, _ = agent.review(request.diff, request.pr_context)
    else:
        summary = run_offline_review(request.diff, request.pr_context)

    if request.post_to_github and request.pr_context:
        if not settings.github_configured:
            raise HTTPException(status_code=400, detail="GITHUB_TOKEN not configured")
        client = GitHubClient(settings.github_token)
        await client.post_review(
            request.pr_context.owner,
            request.pr_context.repo,
            request.pr_context.number,
            summary,
            request.pr_context.head_sha,
        )

    return summary


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
) -> JSONResponse:
    settings = get_settings()
    body = await request.body()

    if settings.github_webhook_secret:
        if not verify_webhook_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(body)

    if x_github_event != "pull_request":
        return JSONResponse({"status": "ignored", "reason": "not a pull_request event"})

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened", "ready_for_review"):
        return JSONResponse({"status": "ignored", "reason": f"action={action}"})

    if payload.get("pull_request", {}).get("draft"):
        return JSONResponse({"status": "ignored", "reason": "draft PR"})

    pr_context = parse_webhook_payload(payload)
    if pr_context is None:
        raise HTTPException(status_code=400, detail="Invalid pull_request payload")

    background_tasks.add_task(_process_pr_webhook, pr_context)
    return JSONResponse({"status": "accepted", "pr": pr_context.number})


async def _process_pr_webhook(pr_context) -> None:
    settings = get_settings()
    try:
        if not settings.github_configured:
            logger.error("GITHUB_TOKEN not set; cannot process webhook")
            return

        client = GitHubClient(settings.github_token)
        diff = await client.get_pr_diff(
            pr_context.owner, pr_context.repo, pr_context.number
        )

        if check_ollama_available(settings):
            agent = ReviewAgent(settings)
            summary, trace = agent.review(diff, pr_context)
            logger.info(
                "Reviewed PR #%s with %d agent steps",
                pr_context.number,
                len(trace.steps),
            )
        else:
            summary = run_offline_review(diff, pr_context)

        await client.post_review(
            pr_context.owner,
            pr_context.repo,
            pr_context.number,
            summary,
            pr_context.head_sha,
        )
        logger.info("Posted review for PR #%s", pr_context.number)
    except Exception:
        logger.exception("Failed to process PR #%s", pr_context.number)


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "code_review_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
