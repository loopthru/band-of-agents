from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from band_of_agents.agents.compliance import run_compliance_agent_llm
from band_of_agents.agents.cost import run_cost_agent_llm
from band_of_agents.agents.reliability import run_reliability_agent_llm
from band_of_agents.agents.security import run_security_agent_llm
from band_of_agents.agents.summarizer import run_summarizer_agent_llm
from band_of_agents.agents_orchestrator import (
    SAMPLE_EVIDENCE,
    gather_agent_results,
    review_gathered_results,
    save_review_output,
)
from band_of_agents.band_client import BandClient

from dotenv import load_dotenv

load_dotenv()

AgentRunner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


@dataclass(frozen=True)
class BandAgentSpec:
    id: str
    name: str
    required: bool = True


async def run_band_review(
    payload: dict[str, Any],
    coordinator_client: Any,
    specialist_agents: list[BandAgentSpec],
    specialist_clients: dict[str, Any],
    specialist_runners: dict[str, AgentRunner],
    summarizer_agent: BandAgentSpec,
    summarizer_client: Any,
    session_uid: str | None = None,
    review_id: str | None = None,
    review_repository: Any | None = None,
    summarizer_runner: AgentRunner = run_summarizer_agent_llm,
    timeout_seconds: float = 180,
    poll_interval_seconds: float = 3,
) -> dict[str, Any]:
    evidence = payload.get("evidence") or SAMPLE_EVIDENCE
    room = await coordinator_client.create_room()
    chat_id = room["data"]["id"]
    participants = [
        *[{"id": agent.id, "name": agent.name} for agent in specialist_agents],
        {"id": summarizer_agent.id, "name": summarizer_agent.name},
    ]

    await coordinator_client.add_participants(participants=participants, chat_id=chat_id)
    if review_repository and review_id:
        review_repository.mark_review_agents_running(review_id, chat_id)
        review_repository.ensure_review_status_rows(review_id)

    await send_specialist_task(
        coordinator_client=coordinator_client,
        chat_id=chat_id,
        agents=specialist_agents,
        evidence=evidence,
    )

    agent_results = await run_specialist_agents_from_band_messages(
        chat_id=chat_id,
        agents=specialist_agents,
        specialist_clients=specialist_clients,
        specialist_runners=specialist_runners,
        coordinator_id=getattr(coordinator_client, "agent_id", None),
        review_id=review_id,
        review_repository=review_repository,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )

    gathered = gather_agent_results(agent_results)
    review = review_gathered_results(evidence=evidence, gathered=gathered)
    review_output = {
        "chat_id": chat_id,
        "decision": review["decision"],
        "summary": review["summary"],
        "recommended_actions": review["recommended_actions"],
        "agent_results": agent_results,
        "gathered": gathered,
    }
    if session_uid:
        review_output["session_uid"] = session_uid
    if review_id:
        review_output["review_id"] = review_id

    await send_summarizer_task(
        coordinator_client=coordinator_client,
        chat_id=chat_id,
        summarizer_agent=summarizer_agent,
        review_output=review_output,
    )
    summarizer_result = await run_band_agent_once(
        chat_id=chat_id,
        agent=summarizer_agent,
        client=summarizer_client,
        runner=summarizer_runner,
        task_input_key="review_output",
        coordinator_id=getattr(coordinator_client, "agent_id", None),
        review_id=review_id,
        review_repository=review_repository,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    review_output["summarizer_output"] = (
        summarizer_result["output"] if summarizer_result["status"] == "ok" else summarizer_result
    )
    if review_repository and review_id:
        if summarizer_result["status"] == "ok":
            review_repository.save_review_summarizer_output(
                review_id,
                review_output["summarizer_output"],
            )
            review_repository.mark_review_summarized(review_id)
        else:
            review_repository.mark_review_failed(review_id)
    return review_output


async def send_specialist_task(
    coordinator_client: Any,
    chat_id: str,
    agents: list[BandAgentSpec],
    evidence: dict[str, Any],
) -> None:
    task = {
        "type": "specialist_review",
        "evidence": evidence,
    }
    content = (
        "Please review this evidence.\n"
        "```json\n"
        f"{json.dumps(task, indent=2)}\n"
        "```"
    )
    payload = {
        "message": {
            "content": content,
            "mentions": [{"id": agent.id} for agent in agents],
        }
    }
    await coordinator_client.send_message(chat_id=chat_id, payload=payload)


async def send_summarizer_task(
    coordinator_client: Any,
    chat_id: str,
    summarizer_agent: BandAgentSpec,
    review_output: dict[str, Any],
) -> None:
    task = {
        "type": "summarizer_review",
        "review_output": review_output,
    }
    content = (
        "Compile the gathered specialist outputs. Do not perform new analysis.\n"
        "Return one valid JSON object using the summarizer schema.\n"
        "```json\n"
        f"{json.dumps(task, indent=2)}\n"
        "```"
    )
    payload = {
        "message": {
            "content": content,
            "mentions": [{"id": summarizer_agent.id}],
        }
    }
    await coordinator_client.send_message(chat_id=chat_id, payload=payload)


async def run_specialist_agents_from_band_messages(
    chat_id: str,
    agents: list[BandAgentSpec],
    specialist_clients: dict[str, Any],
    specialist_runners: dict[str, AgentRunner],
    coordinator_id: str | None,
    timeout_seconds: float,
    poll_interval_seconds: float,
    review_id: str | None = None,
    review_repository: Any | None = None,
) -> list[dict[str, Any]]:
    tasks = []
    for agent in agents:
        client = specialist_clients.get(agent.name)
        runner = specialist_runners.get(agent.name)
        if client is None or runner is None:
            if review_repository and review_id:
                review_repository.mark_agent_failed(
                    review_id,
                    agent.name,
                    "Timed out waiting for agent response",
                )
            tasks.append(_completed_result(_missing_agent_result(agent)))
            continue
        tasks.append(
            run_band_agent_once(
                chat_id=chat_id,
                agent=agent,
                client=client,
                runner=runner,
                task_input_key="evidence",
                coordinator_id=coordinator_id,
                review_id=review_id,
                review_repository=review_repository,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
        )

    return list(await asyncio.gather(*tasks))


async def _completed_result(result: dict[str, Any]) -> dict[str, Any]:
    return result


async def run_band_agent_once(
    chat_id: str,
    agent: BandAgentSpec,
    client: Any,
    runner: AgentRunner,
    task_input_key: str,
    coordinator_id: str | None,
    timeout_seconds: float,
    poll_interval_seconds: float,
    review_id: str | None = None,
    review_repository: Any | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        response = await client.get_next_message(chat_id)
        if response.status_code == 204:
            await asyncio.sleep(poll_interval_seconds)
            continue

        message = response.json()["data"]
        message_id = message["id"]
        await client.change_message_status(chat_id, message_id, "processing")
        if review_repository and review_id:
            review_repository.mark_agent_processing(review_id, agent.name)

        task = parse_json_message(message) or {}
        task_input = task.get(task_input_key)
        if task_input_key == "evidence" and not task_input:
            task_input = SAMPLE_EVIDENCE
        elif task_input is None:
            task_input = {}

        try:
            output = runner(task_input)
            if inspect.isawaitable(output):
                output = await output
        except Exception as exc:  # noqa: BLE001 - agent failures become review inputs.
            error_message = str(exc)
            if review_repository and review_id:
                review_repository.mark_agent_failed(review_id, agent.name, error_message)
            await client.change_message_status(chat_id, message_id, "processed")
            return {
                "agent": agent.name,
                "status": "error",
                "required": agent.required,
                "error": error_message,
                "output": None,
            }

        await post_agent_reply(
            client=client,
            chat_id=chat_id,
            output=output,
            agent_name=agent.name,
            coordinator_id=coordinator_id,
        )
        await client.change_message_status(chat_id, message_id, "processed")
        if review_repository and review_id:
            review_repository.mark_agent_completed(review_id, agent.name, output)
        return {
            "agent": agent.name,
            "status": "ok",
            "required": agent.required,
            "output": output,
        }

    result = _missing_agent_result(agent)
    if review_repository and review_id:
        review_repository.mark_agent_failed(review_id, agent.name, result["error"])
    return result


async def post_agent_reply(
    client: Any,
    chat_id: str,
    output: Any,
    agent_name: str | None,
    coordinator_id: str | None,
) -> None:
    payload = {
        "message": {
            "content": _message_content(output, agent_name=agent_name),
            "mentions": [{"id": coordinator_id}] if coordinator_id else [],
        }
    }
    await client.send_message(chat_id=chat_id, payload=payload)


def _message_content(output: Any, agent_name: str | None = None) -> str:
    if isinstance(output, str):
        return output
    intro = _message_intro(agent_name or _output_agent_name(output))
    content = (
        f"{intro}\n"
        "```json\n"
        f"{json.dumps(output, indent=2)}\n"
        "```"
    )
    return content


def _output_agent_name(output: Any) -> str | None:
    if isinstance(output, dict):
        agent = output.get("agent")
        return agent if isinstance(agent, str) else None
    return None


def _message_intro(agent_name: str | None) -> str:
    if agent_name == "summarizer-agent":
        return "Here's the analysis summary."
    if agent_name:
        label = agent_name.removesuffix("-agent").replace("-", " ").title()
        return f"Here's my {label} Analysis."
    return "Here's my analysis."


def parse_json_message(message: dict[str, Any]) -> dict[str, Any] | None:
    content = (
        message.get("content")
        or message.get("message", {}).get("content")
        or message.get("body")
    )
    if not content:
        return None
    parsed = _loads_json_object(content)
    return parsed if isinstance(parsed, dict) else None


def _loads_json_object(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(content[index:])
            return parsed
        except json.JSONDecodeError:
            continue
    return None


def _missing_agent_result(agent: BandAgentSpec) -> dict[str, Any]:
    return {
        "agent": agent.name,
        "status": "error",
        "required": agent.required,
        "error": "Timed out waiting for agent response",
        "output": None,
    }


def build_default_specialist_agents() -> list[BandAgentSpec]:
    return [
        BandAgentSpec(id=_required_env("BAND_SECURITY_AGENT_ID"), name="security-agent"),
        BandAgentSpec(id=_required_env("BAND_COMPLIANCE_AGENT_ID"), name="compliance-agent"),
        BandAgentSpec(id=_required_env("BAND_RELIABILITY_AGENT_ID"), name="reliability-agent"),
        BandAgentSpec(id=_required_env("BAND_COST_AGENT_ID"), name="cost-agent"),
    ]


def build_default_specialist_runners() -> dict[str, AgentRunner]:
    return {
        "security-agent": run_security_agent_llm,
        "compliance-agent": run_compliance_agent_llm,
        "reliability-agent": run_reliability_agent_llm,
        "cost-agent": run_cost_agent_llm,
    }


def build_default_coordinator_client() -> BandClient:
    return BandClient(
        agent_id=_required_env("BAND_COORDINATOR_AGENT_ID"),
        agent_key=_required_env("BAND_COORDINATOR_AGENT_KEY"),
    )


def build_default_specialist_clients(agents: list[BandAgentSpec]) -> dict[str, BandClient]:
    key_env_by_agent = {
        "security-agent": "BAND_SECURITY_AGENT_KEY",
        "compliance-agent": "BAND_COMPLIANCE_AGENT_KEY",
        "reliability-agent": "BAND_RELIABILITY_AGENT_KEY",
        "cost-agent": "BAND_COST_AGENT_KEY",
    }
    return {
        agent.name: BandClient(
            agent_id=agent.id,
            agent_key=_required_env(key_env_by_agent[agent.name]),
        )
        for agent in agents
    }


def build_default_summarizer_agent() -> BandAgentSpec:
    return BandAgentSpec(
        id=_required_env("BAND_SUMMARIZER_AGENT_ID"),
        name="summarizer-agent",
    )


def build_default_summarizer_client(summarizer_agent: BandAgentSpec) -> BandClient:
    return BandClient(
        agent_id=summarizer_agent.id,
        agent_key=_required_env("BAND_SUMMARIZER_AGENT_KEY"),
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_payload(evidence_file: str | None) -> dict[str, Any]:
    if not evidence_file:
        return {"evidence": SAMPLE_EVIDENCE}
    with open(evidence_file, encoding="utf-8") as file:
        return {"evidence": json.load(file)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run single-process Band.ai polling orchestration for LoopThru agents."
    )
    parser.add_argument("--evidence-file", help="Optional JSON evidence file.")
    parser.add_argument(
        "--output-file",
        default="docs/reviews/band-review.json",
        help="Path where the final review JSON should be saved.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument("--poll-interval-seconds", type=float, default=3)
    return parser.parse_args()


async def async_main() -> dict[str, Any]:
    args = parse_args()
    specialist_agents = build_default_specialist_agents()
    summarizer_agent = build_default_summarizer_agent()
    result = await run_band_review(
        payload=load_payload(args.evidence_file),
        coordinator_client=build_default_coordinator_client(),
        specialist_agents=specialist_agents,
        specialist_clients=build_default_specialist_clients(specialist_agents),
        specialist_runners=build_default_specialist_runners(),
        summarizer_agent=summarizer_agent,
        summarizer_client=build_default_summarizer_client(summarizer_agent),
        summarizer_runner=run_summarizer_agent_llm,
        timeout_seconds=args.timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    save_review_output(result, Path(args.output_file))
    return result


def main() -> None:
    result = asyncio.run(async_main())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
