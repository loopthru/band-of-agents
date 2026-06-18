from typing import Any
from fastapi import FastAPI

from band_of_agents.band_orchestrator import (
    build_default_coordinator_client,
    build_default_specialist_agents,
    build_default_specialist_clients,
    build_default_specialist_runners,
    build_default_summarizer_agent,
    build_default_summarizer_client,
    run_band_review,
)

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
    specialist_agents = build_default_specialist_agents()
    summarizer_agent = build_default_summarizer_agent()
    return await run_band_review(
        payload=payload,
        coordinator_client=build_default_coordinator_client(),
        specialist_agents=specialist_agents,
        specialist_clients=build_default_specialist_clients(specialist_agents),
        specialist_runners=build_default_specialist_runners(),
        summarizer_agent=summarizer_agent,
        summarizer_client=build_default_summarizer_client(summarizer_agent),
    )
