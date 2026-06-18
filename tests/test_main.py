from fastapi.testclient import TestClient

import band_of_agents.main as main
from band_of_agents.band_orchestrator import BandAgentSpec
from band_of_agents.main import app


client = TestClient(app)


def test_root_returns_app_metadata():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "band-of-agents",
        "status": "ok",
    }


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_local_vite_frontend_preflight():
    response = client.options(
        "/review",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_review_runs_band_orchestrator_from_session_uid(monkeypatch):
    captured = {}
    session_uid = "7df7eaa4-9d30-47df-b5b8-7f9e96df6e0d"
    evidence = {
        "summary": {"resources_total": 1},
        "resources": [{"address": "aws_s3_bucket.customer_data"}],
    }

    class FakeReviewRepository:
        def get_review_by_session_uid(self, value):
            assert value == session_uid
            return {
                "id": "review-123",
                "session_uid": session_uid,
                "evidence": evidence,
            }

    async def fake_run_band_review(**kwargs):
        captured.update(kwargs)
        return {
            "session_uid": session_uid,
            "review_id": "review-123",
            "chat_id": "chat-123",
            "decision": "approve",
            "summary": "ready",
            "recommended_actions": [],
            "agent_results": [],
            "gathered": {"finding_count": 0},
            "summarizer_output": {"summary": "ready"},
        }

    specialist_agents = [
        BandAgentSpec(id="security-id", name="security-agent"),
        BandAgentSpec(id="cost-id", name="cost-agent"),
    ]
    summarizer_agent = BandAgentSpec(id="summarizer-id", name="summarizer-agent")

    monkeypatch.setattr(main, "run_band_review", fake_run_band_review)
    monkeypatch.setattr(main, "build_review_repository", lambda: FakeReviewRepository())
    monkeypatch.setattr(main, "build_default_coordinator_client", lambda: "coordinator")
    monkeypatch.setattr(main, "build_default_specialist_agents", lambda: specialist_agents)
    monkeypatch.setattr(
        main,
        "build_default_specialist_clients",
        lambda agents: {"security-agent": "security-client", "cost-agent": "cost-client"},
    )
    monkeypatch.setattr(
        main,
        "build_default_specialist_runners",
        lambda: {"security-agent": "security-runner", "cost-agent": "cost-runner"},
    )
    monkeypatch.setattr(main, "build_default_summarizer_agent", lambda: summarizer_agent)
    monkeypatch.setattr(
        main,
        "build_default_summarizer_client",
        lambda agent: "summarizer-client",
    )

    payload = {"session_uid": session_uid}
    response = client.post(
        "/review",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["summary"] == "ready"
    assert captured == {
        "payload": {"evidence": evidence},
        "session_uid": session_uid,
        "review_id": "review-123",
        "review_repository": captured["review_repository"],
        "coordinator_client": "coordinator",
        "specialist_agents": specialist_agents,
        "specialist_clients": {
            "security-agent": "security-client",
            "cost-agent": "cost-client",
        },
        "specialist_runners": {
            "security-agent": "security-runner",
            "cost-agent": "cost-runner",
        },
        "summarizer_agent": summarizer_agent,
        "summarizer_client": "summarizer-client",
    }


def test_review_returns_404_when_session_uid_is_unknown(monkeypatch):
    class FakeReviewRepository:
        def get_review_by_session_uid(self, value):
            return None

    monkeypatch.setattr(main, "build_review_repository", lambda: FakeReviewRepository())

    response = client.post(
        "/review",
        json={"session_uid": "7df7eaa4-9d30-47df-b5b8-7f9e96df6e0d"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Review session not found"
