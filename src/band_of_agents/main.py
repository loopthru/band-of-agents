from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException

from band_of_agents.band_orchestrator import (
    build_default_coordinator_client,
    build_default_specialist_agents,
    build_default_specialist_clients,
    build_default_specialist_runners,
    build_default_summarizer_agent,
    build_default_summarizer_client,
    run_band_review,
)
from band_of_agents.review_repository import ReviewRepository

app = FastAPI(title="Band of Agents")


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "name": "band-of-agents",
        "status": "ok",
    }


@app.get("/health")
def read_health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/review")
async def review(payload: dict[str, Any]) -> dict:
    return await run_review(payload)


async def run_review(payload: dict[str, Any]) -> dict[str, Any]:
    session_uid = payload.get("session_uid")
    if not session_uid:
        raise HTTPException(status_code=400, detail="session_uid is required")
    try:
        session_uid = str(UUID(str(session_uid)))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="session_uid must be a valid UUID",
        ) from exc

    review_repository = build_review_repository()
    review = review_repository.get_review_by_session_uid(session_uid)
    if not review:
        raise HTTPException(status_code=404, detail="Review session not found")

    specialist_agents = build_default_specialist_agents()
    summarizer_agent = build_default_summarizer_agent()
    return await run_band_review(
        payload={"evidence": review["evidence"]},
        session_uid=session_uid,
        review_id=review["id"],
        review_repository=review_repository,
        coordinator_client=build_default_coordinator_client(),
        specialist_agents=specialist_agents,
        specialist_clients=build_default_specialist_clients(specialist_agents),
        specialist_runners=build_default_specialist_runners(),
        summarizer_agent=summarizer_agent,
        summarizer_client=build_default_summarizer_client(summarizer_agent),
    )


def build_review_repository() -> ReviewRepository:
    return ReviewRepository()
