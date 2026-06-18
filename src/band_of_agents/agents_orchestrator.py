from __future__ import annotations

import argparse
import asyncio
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable


Decision = str
AgentOutput = dict[str, Any]
AgentResult = dict[str, Any]
AgentCallable = Callable[[dict[str, Any]], Awaitable[AgentOutput] | AgentOutput]

DECISION_RANK: dict[Decision, int] = {
    "approve": 0,
    "warn": 1,
    "block": 2,
}

SAMPLE_EVIDENCE = {
  "schema_version": "2026-06-16.mvp.v1",
  "engine": {
    "name": "loopthru-evidence-engine",
    "version": "0.1.0"
  },
  "summary": {
    "resources_total": 1,
    "resources_evaluated": 1,
    "resources_unsupported": 0,
    "controls_by_status": {
      "passed": 6,
      "gap": 8,
      "unknown": 4
    }
  },
  "resources": [
    {
      "address": "aws_s3_bucket.customer_data",
      "type": "aws_s3_bucket",
      "name": "customer_data",
      "provider": "aws",
      "change_actions": ["create"],
      "before": None,
      "after": {
        "bucket": "customer-data-prod"
      },
      "controls": [
        {
          "id": "s3.encryption",
          "name": "S3 encryption",
          "category": "security",
          "status": "passed",
          "severity": "high",
          "message": "S3 bucket has server-side encryption configured using SSE-S3 AES256.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[1].change.after.rule",
            "before": None,
            "after": [
              {
                "apply_server_side_encryption_by_default": [
                  {
                    "sse_algorithm": "AES256"
                  }
                ]
              }
            ]
          }
        },
        {
          "id": "s3.public_access_block",
          "name": "S3 public access block",
          "category": "security",
          "status": "passed",
          "severity": "high",
          "message": "S3 bucket public access block enables all required protections.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[2].change.after",
            "before": None,
            "after": {
              "bucket": "customer-data-prod",
              "block_public_acls": True,
              "block_public_policy": True,
              "ignore_public_acls": True,
              "restrict_public_buckets": True
            }
          }
        },
        {
          "id": "s3.bucket_policy_exposure",
          "name": "S3 bucket policy exposure",
          "category": "security",
          "status": "passed",
          "severity": "high",
          "message": "S3 bucket policy does not allow public principal access, but grants access to the account root principal.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[5].change.after.policy",
            "before": None,
            "after": {
              "Statement": [
                {
                  "Effect": "Allow",
                  "Principal": {
                    "AWS": "arn:aws:iam::123456789012:root"
                  },
                  "Action": "s3:GetObject",
                  "Resource": "arn:aws:s3:::customer-data-prod/*"
                }
              ]
            }
          }
        },
        {
          "id": "s3.versioning",
          "name": "S3 versioning",
          "category": "reliability",
          "status": "passed",
          "severity": "medium",
          "message": "S3 bucket versioning is enabled.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[3].change.after.versioning_configuration",
            "before": None,
            "after": [
              {
                "status": "Enabled"
              }
            ]
          }
        },
        {
          "id": "s3.lifecycle_transition",
          "name": "S3 lifecycle transition",
          "category": "cost",
          "status": "passed",
          "severity": "low",
          "message": "S3 lifecycle rule includes transition to STANDARD_IA.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[4].change.after.rule",
            "before": None,
            "after": [
              {
                "transition": [
                  {
                    "storage_class": "STANDARD_IA"
                  }
                ]
              }
            ]
          }
        },
        {
          "id": "s3.logging",
          "name": "S3 access logging",
          "category": "compliance",
          "status": "gap",
          "severity": "medium",
          "message": "No S3 server access logging or CloudTrail data event logging evidence is present.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resources[0].controls",
            "before": None,
            "after": None
          }
        },
        {
          "id": "s3.retention_expiration",
          "name": "S3 retention and expiration",
          "category": "compliance",
          "status": "gap",
          "severity": "medium",
          "message": "Lifecycle evidence does not show explicit retention, expiration, or noncurrent version cleanup rules.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[4].change.after.rule",
            "before": None,
            "after": [
              {
                "transition": [
                  {
                    "storage_class": "STANDARD_IA"
                  }
                ]
              }
            ]
          }
        },
        {
          "id": "s3.least_privilege_access",
          "name": "S3 least privilege access",
          "category": "security",
          "status": "unknown",
          "severity": "low",
          "message": "Bucket policy is not public, but access is granted to account root. No scoped IAM role evidence is present.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[5].change.after.policy",
            "before": None,
            "after": {
              "Statement": [
                {
                  "Effect": "Allow",
                  "Principal": {
                    "AWS": "arn:aws:iam::123456789012:root"
                  },
                  "Action": "s3:GetObject",
                  "Resource": "arn:aws:s3:::customer-data-prod/*"
                }
              ]
            }
          }
        },
        {
          "id": "s3.change_management",
          "name": "Change management evidence",
          "category": "governance",
          "status": "unknown",
          "severity": "low",
          "message": "No change ticket, approval, or PR metadata is included in the evidence.",
          "evidence": {
            "source": "evidence_bundle",
            "path": "metadata.change_record",
            "before": None,
            "after": None
          }
        },
        {
          "id": "s3.replication",
          "name": "S3 replication or backup",
          "category": "reliability",
          "status": "gap",
          "severity": "high",
          "message": "No same-region or cross-region replication evidence is present.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resources[0].controls",
            "before": None,
            "after": None
          }
        },
        {
          "id": "s3.disaster_recovery",
          "name": "S3 disaster recovery",
          "category": "reliability",
          "status": "gap",
          "severity": "high",
          "message": "No DR strategy, replica bucket, or recovery runbook evidence is present.",
          "evidence": {
            "source": "evidence_bundle",
            "path": "metadata.dr_evidence",
            "before": None,
            "after": None
          }
        },
        {
          "id": "s3.deletion_protection",
          "name": "S3 deletion protection",
          "category": "reliability",
          "status": "gap",
          "severity": "medium",
          "message": "Versioning is enabled, but no Object Lock, MFA delete, or delete restriction evidence is present.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resources[0].controls[3].evidence.after",
            "before": None,
            "after": [
              {
                "status": "Enabled"
              }
            ]
          }
        },
        {
          "id": "s3.monitoring_alerting",
          "name": "S3 monitoring and alerting",
          "category": "reliability",
          "status": "gap",
          "severity": "medium",
          "message": "No CloudWatch alarms, access anomaly monitoring, or operational alerting evidence is present.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resources[0].controls",
            "before": None,
            "after": None
          }
        },
        {
          "id": "s3.lifecycle_details",
          "name": "S3 lifecycle rule details",
          "category": "cost",
          "status": "gap",
          "severity": "medium",
          "message": "Lifecycle transition exists, but days, filters, expiration, and noncurrent version cleanup are not shown.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[4].change.after.rule",
            "before": None,
            "after": [
              {
                "transition": [
                  {
                    "storage_class": "STANDARD_IA"
                  }
                ]
              }
            ]
          }
        },
        {
          "id": "s3.cost_tags",
          "name": "S3 cost allocation tags",
          "category": "cost",
          "status": "unknown",
          "severity": "low",
          "message": "No cost allocation tags are present in the evidence.",
          "evidence": {
            "source": "terraform_plan",
            "path": "resource_changes[0].change.after.tags",
            "before": None,
            "after": None
          }
        },
        {
          "id": "s3.budget_alerts",
          "name": "S3 budget alerts",
          "category": "cost",
          "status": "unknown",
          "severity": "low",
          "message": "No budget or spend alert evidence is included for this bucket.",
          "evidence": {
            "source": "evidence_bundle",
            "path": "metadata.budget_controls",
            "before": None,
            "after": None
          }
        }
      ]
    }
  ]
}


@dataclass(frozen=True)
class AgentSpec:
    name: str
    run: AgentCallable
    required: bool = True


async def run_review_pipeline(
    payload: dict[str, Any],
    agents: list[AgentSpec] | None = None,
) -> dict[str, Any]:
    evidence = payload.get("evidence") or SAMPLE_EVIDENCE
    selected_agents = agents or build_live_agents()
    agent_results = await asyncio.gather(
        *[_run_agent(agent, evidence) for agent in selected_agents]
    )
    gathered = gather_agent_results(agent_results)
    review = review_gathered_results(evidence=evidence, gathered=gathered)

    return {
        "decision": review["decision"],
        "summary": review["summary"],
        "recommended_actions": review["recommended_actions"],
        "agent_results": agent_results,
        "gathered": gathered,
    }

async def _run_agent(agent: AgentSpec, evidence: dict[str, Any]) -> AgentResult:
    try:
        output = agent.run(evidence)
        if inspect.isawaitable(output):
            output = await output
        return {
            "agent": agent.name,
            "status": "ok",
            "required": agent.required,
            "output": output,
        }
    except Exception as exc:  # noqa: BLE001 - agent failures become review inputs.
        return {
            "agent": agent.name,
            "status": "error",
            "required": agent.required,
            "error": str(exc),
            "output": None,
        }

def gather_agent_results(agent_results: list[AgentResult]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    agent_errors: list[dict[str, Any]] = []
    decisions: list[Decision] = []

    for result in agent_results:
        agent_name = result["agent"]
        if result["status"] != "ok":
            agent_errors.append(
                {
                    "source_agent": agent_name,
                    "required": result.get("required", True),
                    "error": result.get("error", "unknown agent error"),
                }
            )
            if result.get("required", True):
                decisions.append("block")
            continue

        output = result.get("output") or {}
        decision = _normalize_decision(output.get("decision"))
        decisions.append(decision)

        for finding in output.get("findings", []):
            findings.append(
                _normalize_finding(
                    source_agent=agent_name,
                    finding_type="finding",
                    item=finding,
                )
            )

        for control in output.get("mapped_controls", []):
            findings.append(
                _normalize_finding(
                    source_agent=agent_name,
                    finding_type="mapped_control",
                    item=control,
                )
            )

        findings.extend(_normalize_resource_grouped_findings(agent_name, output))

    highest_decision = max(decisions or ["approve"], key=lambda item: DECISION_RANK[item])

    return {
        "highest_decision": highest_decision,
        "finding_count": len(findings),
        "findings": findings,
        "agent_errors": agent_errors,
        "raw_results": agent_results,
    }


def review_gathered_results(
    evidence: dict[str, Any],
    gathered: dict[str, Any],
) -> dict[str, Any]:
    decision = gathered["highest_decision"]
    summaries = _agent_summaries(gathered["raw_results"])
    resource_count = evidence.get("summary", {}).get("resources_total", "unknown")
    finding_count = gathered["finding_count"]

    if summaries:
        summary = (
            f"Reviewed {resource_count} resource(s). "
            f"Found {finding_count} gathered finding(s): "
            f"{'; '.join(summaries)}"
        )
    else:
        summary = f"Reviewed {resource_count} resource(s). No agent findings were returned."

    if gathered["agent_errors"]:
        summary = f"{summary} Agent errors require attention before approval."

    return {
        "decision": decision,
        "summary": summary,
        "recommended_actions": _recommended_actions(gathered["findings"]),
    }


def build_live_agents() -> list[AgentSpec]:
    from band_of_agents.agents.compliance import run_compliance_agent_llm
    from band_of_agents.agents.security import run_security_agent_llm
    from band_of_agents.agents.cost import run_cost_agent_llm
    from band_of_agents.agents.reliability import run_reliability_agent_llm

    async def security_agent(evidence: dict[str, Any]) -> AgentOutput:
        return await run_security_agent_llm(evidence=evidence)

    async def compliance_agent(evidence: dict[str, Any]) -> AgentOutput:
        return await run_compliance_agent_llm(evidence=evidence)

    async def reliability_agent(evidence: dict[str, Any]) -> AgentOutput:
        return await run_reliability_agent_llm(evidence=evidence)

    async def cost_agent(evidence: dict[str, Any]) -> AgentOutput:
        return await run_cost_agent_llm(evidence=evidence)

    return [
        AgentSpec(name="security-agent", run=security_agent),
        AgentSpec(name="compliance-agent", run=compliance_agent),
        AgentSpec(name="reliability-agent", run=reliability_agent),
        AgentSpec(name="cost-agent", run=cost_agent),
    ]

def _normalize_finding(
    source_agent: str,
    finding_type: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    title = item.get("title")
    if not title and item.get("framework"):
        title = f"{item.get('framework')} {item.get('control_area', 'control')} {item.get('status', 'gap')}"

    return {
        "source_agent": source_agent,
        "type": finding_type,
        "severity": item.get("severity"),
        "title": title or "Untitled finding",
        "evidence_path": item.get("evidence_path") or item.get("evidence"),
        "claim": item.get("risk") or item.get("impact") or item.get("evidence"),
        "recommendation": item.get("recommendation") or item.get("required_fix"),
        "raw": item,
    }


def _normalize_resource_grouped_findings(
    source_agent: str,
    output: dict[str, Any],
) -> list[dict[str, Any]]:
    findings = []
    for resource in output.get("resources", []):
        resource_items = [
            *resource.get("findings", []),
            *resource.get("violations", []),
        ]
        for item in resource_items:
            normalized = _normalize_finding(
                source_agent=source_agent,
                finding_type="resource_finding",
                item=item,
            )
            normalized["resource"] = resource.get("resource")
            normalized["resource_name"] = resource.get("name")
            normalized["resource_evidence_path"] = resource.get("resource_evidence_path")
            findings.append(normalized)
    return findings


def _normalize_decision(value: Any) -> Decision:
    if value in DECISION_RANK:
        return value
    return "warn"


def _agent_summaries(agent_results: list[AgentResult]) -> list[str]:
    summaries = []
    for result in agent_results:
        if result["status"] != "ok":
            summaries.append(f"{result['agent']} failed: {result.get('error')}")
            continue
        output = result.get("output") or {}
        summary = output.get("summary")
        if summary:
            summaries.append(summary)
    return summaries


def _recommended_actions(findings: list[dict[str, Any]]) -> list[str]:
    actions = []
    seen = set()
    for finding in findings:
        recommendation = finding.get("recommendation")
        if not recommendation or recommendation in seen:
            continue
        seen.add(recommendation)
        actions.append(recommendation)
    return actions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Band of Agents v2 live orchestration pipeline."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use live LLM agents. This is the only v2 runtime mode.",
    )
    parser.add_argument(
        "--evidence-file",
        help="Optional JSON evidence file. Defaults to built-in sample evidence.",
    )
    parser.add_argument(
        "--output-file",
        help="Optional path where the final review JSON should be saved.",
    )
    return parser.parse_args()


def load_payload(evidence_file: str | None) -> dict[str, Any]:
    if not evidence_file:
        return {"evidence": SAMPLE_EVIDENCE}
    with open(evidence_file, encoding="utf-8") as file:
        return {"evidence": json.load(file)}


async def async_main() -> dict[str, Any]:
    args = parse_args()
    payload = load_payload(args.evidence_file)
    response = await run_review_pipeline(payload, agents=build_live_agents())
    if args.output_file:
        save_review_output(response, args.output_file)

    from band_of_agents.agents.summarizer import run_summarizer_agent_llm
    summarized = await run_summarizer_agent_llm(output=response)
    save_review_output(summarized, "docs/reviews/summarizer.json")

    return response


def save_review_output(response: dict[str, Any], output_file: str | Path) -> None:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(response, indent=2)}\n", encoding="utf-8")


def main() -> None:
    response = asyncio.run(async_main())
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
