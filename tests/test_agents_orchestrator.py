import asyncio

import band_of_agents.agents_orchestrator as orchestrator_v2
from band_of_agents.agents_orchestrator import (
    AgentSpec,
    build_live_agents,
    gather_agent_results,
    run_review_pipeline,
    save_review_output,
)


async def security_agent(evidence):
    return {
        "agent": "security-agent",
        "decision": "block",
        "summary": "Public S3 exposure risk",
        "findings": [
            {
                "severity": "high",
                "title": "S3 public access block missing",
                "evidence_path": "resources[0].controls[1]",
                "recommendation": "Enable public access block",
            }
        ],
    }


async def compliance_agent(evidence):
    return {
        "agent": "compliance-agent",
        "decision": "warn",
        "summary": "SOC 2 gap",
        "mapped_controls": [
            {
                "framework": "SOC 2",
                "control_area": "access control",
                "status": "gap",
                "evidence_path": "resources[0].controls[1]",
                "recommendation": "Document and enforce private access",
            }
        ],
    }


def test_gather_agent_results_preserves_findings_and_controls():
    gathered = gather_agent_results(
        [
            {
                "agent": "security-agent",
                "status": "ok",
                "output": asyncio.run(security_agent({})),
            },
            {
                "agent": "compliance-agent",
                "status": "ok",
                "output": asyncio.run(compliance_agent({})),
            },
        ]
    )

    assert gathered["finding_count"] == 2
    assert gathered["highest_decision"] == "block"
    assert gathered["findings"][0]["source_agent"] == "security-agent"
    assert gathered["findings"][1]["source_agent"] == "compliance-agent"
    assert gathered["findings"][0]["evidence_path"] == "resources[0].controls[1]"


def test_run_review_pipeline_uses_specialists_gatherer_and_reviewer():
    response = asyncio.run(
        run_review_pipeline(
            {"evidence": {"resources": []}},
            agents=[
                AgentSpec(name="security-agent", run=security_agent),
                AgentSpec(name="compliance-agent", run=compliance_agent),
            ],
        )
    )

    assert response["decision"] == "block"
    assert "Public S3 exposure risk" in response["summary"]
    assert response["gathered"]["finding_count"] == 2
    assert len(response["agent_results"]) == 2


def test_run_review_pipeline_defaults_to_live_agents(monkeypatch):
    async def live_agent(evidence):
        return {
            "agent": "live-agent",
            "decision": "approve",
            "summary": "live agent used",
            "findings": [],
        }

    monkeypatch.setattr(
        orchestrator_v2,
        "build_live_agents",
        lambda: [AgentSpec(name="live-agent", run=live_agent)],
    )

    response = asyncio.run(run_review_pipeline({"evidence": {"resources": []}}))

    assert response["agent_results"][0]["agent"] == "live-agent"
    assert response["summary"] == (
        "Reviewed unknown resource(s). Found 0 gathered finding(s): live agent used"
    )


def test_save_review_output_writes_pretty_json(tmp_path):
    output_file = tmp_path / "review-output.json"
    response = {
        "decision": "block",
        "summary": "example",
        "recommended_actions": ["fix encryption"],
    }

    save_review_output(response, output_file)

    assert output_file.read_text(encoding="utf-8") == (
        '{\n'
        '  "decision": "block",\n'
        '  "summary": "example",\n'
        '  "recommended_actions": [\n'
        '    "fix encryption"\n'
        '  ]\n'
        '}\n'
    )


def test_live_agents_call_their_own_domain_functions(monkeypatch):
    async def fake_security(evidence):
        return {"agent": "security-agent", "decision": "approve"}

    async def fake_compliance(evidence):
        return {"agent": "compliance-agent", "decision": "approve"}

    async def fake_reliability(evidence):
        return {"agent": "reliability-agent", "decision": "approve"}

    async def fake_cost(evidence):
        return {"agent": "cost-agent", "decision": "approve"}

    monkeypatch.setattr(
        "band_of_agents.agents.security.run_security_agent_llm",
        fake_security,
    )
    monkeypatch.setattr(
        "band_of_agents.agents.compliance.run_compliance_agent_llm",
        fake_compliance,
    )
    monkeypatch.setattr(
        "band_of_agents.agents.reliability.run_reliability_agent_llm",
        fake_reliability,
    )
    monkeypatch.setattr(
        "band_of_agents.agents.cost.run_cost_agent_llm",
        fake_cost,
    )

    agents = build_live_agents()
    outputs = {
        agent.name: asyncio.run(agent.run({"resources": []}))
        for agent in agents
    }

    assert outputs["security-agent"]["agent"] == "security-agent"
    assert outputs["compliance-agent"]["agent"] == "compliance-agent"
    assert outputs["reliability-agent"]["agent"] == "reliability-agent"
    assert outputs["cost-agent"]["agent"] == "cost-agent"


def test_gather_agent_results_flattens_resource_grouped_outputs():
    gathered = gather_agent_results(
        [
            {
                "agent": "reliability-agent",
                "status": "ok",
                "output": {
                    "agent": "reliability-agent",
                    "decision": "warn",
                    "summary": "Versioning is missing",
                    "resources": [
                        {
                            "resource": "aws_s3_bucket.customer_data",
                            "name": "customer-data-prod",
                            "resource_evidence_path": "resources[0]",
                            "decision": "warn",
                            "findings": [
                                {
                                    "risk_area": "backup_recovery",
                                    "severity": "medium",
                                    "status": "gap",
                                    "evidence_path": "resources[0].controls[3]",
                                    "evidence": "S3 versioning is not configured.",
                                    "impact": "Recovery from accidental deletion is weaker.",
                                    "required_fix": "Enable S3 versioning.",
                                }
                            ],
                        }
                    ],
                },
            },
            {
                "agent": "cost-agent",
                "status": "ok",
                "output": {
                    "agent": "cost-agent",
                    "decision": "warn",
                    "summary": "Lifecycle policy is missing",
                    "resources": [
                        {
                            "resource": "aws_s3_bucket.customer_data",
                            "name": "customer-data-prod",
                            "resource_evidence_path": "resources[0]",
                            "decision": "warn",
                            "findings": [
                                {
                                    "cost_area": "lifecycle_management",
                                    "severity": "low",
                                    "status": "gap",
                                    "evidence_path": "resources[0].controls[4]",
                                    "evidence": "S3 lifecycle rules are not configured.",
                                    "impact": "Objects may remain in expensive storage longer than needed.",
                                    "required_fix": "Add lifecycle transitions.",
                                }
                            ],
                        }
                    ],
                },
            },
        ]
    )

    assert gathered["finding_count"] == 2
    assert gathered["findings"][0]["source_agent"] == "reliability-agent"
    assert gathered["findings"][0]["type"] == "resource_finding"
    assert gathered["findings"][0]["resource"] == "aws_s3_bucket.customer_data"
    assert gathered["findings"][0]["evidence_path"] == "resources[0].controls[3]"
    assert gathered["findings"][0]["recommendation"] == "Enable S3 versioning."
    assert gathered["findings"][1]["source_agent"] == "cost-agent"
    assert gathered["findings"][1]["resource_evidence_path"] == "resources[0]"
