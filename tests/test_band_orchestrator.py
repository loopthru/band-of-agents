import asyncio
import json

from band_of_agents.band_orchestrator import (
    BandAgentSpec,
    _message_content,
    parse_json_message,
    run_band_agent_once,
    run_band_review,
    run_specialist_agents_from_band_messages,
)


class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


class FakeBandRoom:
    def __init__(self):
        self.queues = {}
        self.sent_messages = []
        self.participants = []
        self.status_changes = []
        self.next_id = 1

    def client(self, agent_id):
        self.queues.setdefault(agent_id, [])
        return FakeBandClient(self, agent_id)

    def post_message(self, sender_id, chat_id, payload):
        message_id = f"msg-{self.next_id}"
        self.next_id += 1
        message = {
            "id": message_id,
            "sender_id": sender_id,
            "content": payload["message"]["content"],
        }
        self.sent_messages.append((sender_id, chat_id, payload))
        for mention in payload["message"].get("mentions", []):
            self.queues.setdefault(mention["id"], []).append(message)
        return FakeResponse(201, {"data": {"id": message_id}})


class FakeBandClient:
    def __init__(self, room, agent_id):
        self.room = room
        self.agent_id = agent_id

    async def create_room(self):
        return {"data": {"id": "chat-123"}}

    async def add_participants(self, participants, chat_id):
        self.room.participants.append((chat_id, participants))

    async def send_message(self, chat_id, payload):
        return self.room.post_message(self.agent_id, chat_id, payload)

    async def get_next_message(self, chat_id):
        queue = self.room.queues.setdefault(self.agent_id, [])
        if not queue:
            return FakeResponse(204)
        return FakeResponse(200, {"data": queue.pop(0)})

    async def change_message_status(self, chat_id, message_id, status):
        self.room.status_changes.append((self.agent_id, chat_id, message_id, status))
        return FakeResponse(200)


async def fake_security(evidence):
    return {
        "agent": "security-agent",
        "decision": "block",
        "summary": "Security blocked",
        "findings": [
            {
                "severity": "high",
                "title": "Public access risk",
                "evidence_path": "resources[0].controls[1]",
                "recommendation": "Enable public access block.",
            }
        ],
    }


async def fake_compliance(evidence):
    return {
        "agent": "compliance-agent",
        "decision": "warn",
        "summary": "Compliance warned",
        "resources": [
            {
                "resource": "aws_s3_bucket.customer_data",
                "resource_evidence_path": "resources[0]",
                "violations": [
                    {
                        "control_area": "access_control",
                        "status": "gap",
                        "evidence_path": "resources[0].controls[1]",
                        "evidence": "Public access block is missing.",
                        "required_fix": "Enable public access block.",
                    }
                ],
            }
        ],
    }


async def fake_summarizer(output):
    return {
        "decision": output["decision"],
        "summary": "compiled review",
        "agents_consulted": [
            result["agent"]
            for result in output["agent_results"]
            if result["status"] == "ok"
        ],
    }


def test_run_band_review_agents_poll_messages_then_summarizer_polls_gathered_output():
    room = FakeBandRoom()
    coordinator = room.client("coordinator-id")
    security_client = room.client("security-id")
    compliance_client = room.client("compliance-id")
    summarizer_client = room.client("summarizer-id")
    agents = [
        BandAgentSpec(id="security-id", name="security-agent"),
        BandAgentSpec(id="compliance-id", name="compliance-agent"),
    ]

    result = asyncio.run(
        run_band_review(
            payload={"evidence": {"summary": {"resources_total": 1}, "resources": []}},
            coordinator_client=coordinator,
            specialist_agents=agents,
            specialist_clients={
                "security-agent": security_client,
                "compliance-agent": compliance_client,
            },
            specialist_runners={
                "security-agent": fake_security,
                "compliance-agent": fake_compliance,
            },
            summarizer_agent=BandAgentSpec(id="summarizer-id", name="summarizer-agent"),
            summarizer_client=summarizer_client,
            summarizer_runner=fake_summarizer,
            timeout_seconds=1,
            poll_interval_seconds=0,
        )
    )

    kickoff_payload = room.sent_messages[0][2]
    security_reply_payload = room.sent_messages[1][2]
    compliance_reply_payload = room.sent_messages[2][2]
    summarizer_payload = room.sent_messages[3][2]

    assert room.participants == [
        (
            "chat-123",
            [
                {"id": "security-id", "name": "security-agent"},
                {"id": "compliance-id", "name": "compliance-agent"},
                {"id": "summarizer-id", "name": "summarizer-agent"},
            ],
        )
    ]
    assert kickoff_payload["message"]["mentions"] == [
        {"id": "security-id"},
        {"id": "compliance-id"},
    ]
    assert (
        parse_json_message({"content": kickoff_payload["message"]["content"]})["type"]
        == "specialist_review"
    )
    assert security_reply_payload["message"]["content"].startswith(
        "Here's my Security Analysis.\n```json\n"
    )
    assert security_reply_payload["message"]["content"].endswith("\n```")
    assert parse_json_message(
        {"content": security_reply_payload["message"]["content"]}
    )["agent"] == "security-agent"
    assert compliance_reply_payload["message"]["content"].startswith(
        "Here's my Compliance Analysis.\n```json\n"
    )
    assert parse_json_message(
        {"content": compliance_reply_payload["message"]["content"]}
    )["agent"] == "compliance-agent"
    assert summarizer_payload["message"]["mentions"] == [{"id": "summarizer-id"}]
    assert (
        parse_json_message({"content": summarizer_payload["message"]["content"]})["type"]
        == "summarizer_review"
    )

    assert result["chat_id"] == "chat-123"
    assert result["decision"] == "block"
    assert result["gathered"]["finding_count"] == 2
    assert result["summarizer_output"]["summary"] == "compiled review"
    assert [message[0] for message in room.sent_messages] == [
        "coordinator-id",
        "security-id",
        "compliance-id",
        "coordinator-id",
        "summarizer-id",
    ]
    assert room.status_changes == [
        ("security-id", "chat-123", "msg-1", "processing"),
        ("security-id", "chat-123", "msg-1", "processed"),
        ("compliance-id", "chat-123", "msg-1", "processing"),
        ("compliance-id", "chat-123", "msg-1", "processed"),
        ("summarizer-id", "chat-123", "msg-4", "processing"),
        ("summarizer-id", "chat-123", "msg-4", "processed"),
    ]


def test_run_band_review_marks_missing_required_agent_as_error():
    room = FakeBandRoom()
    coordinator = room.client("coordinator-id")
    security_client = room.client("security-id")
    agents = [BandAgentSpec(id="security-id", name="security-agent")]

    result = asyncio.run(
        run_band_review(
            payload={"evidence": {"resources": []}},
            coordinator_client=coordinator,
            specialist_agents=agents,
            specialist_clients={"security-agent": security_client},
            specialist_runners={},
            summarizer_agent=BandAgentSpec(id="summarizer-id", name="summarizer-agent"),
            summarizer_client=room.client("summarizer-id"),
            summarizer_runner=fake_summarizer,
            timeout_seconds=0,
            poll_interval_seconds=0,
        )
    )

    assert result["decision"] == "block"
    assert result["agent_results"] == [
        {
            "agent": "security-agent",
            "status": "error",
            "required": True,
            "error": "Timed out waiting for agent response",
            "output": None,
        }
    ]


def test_specialist_agents_run_in_parallel_after_polling_messages():
    room = FakeBandRoom()
    room.queues.setdefault("security-id", []).append(
        {
            "id": "msg-security",
            "content": json.dumps({"type": "specialist_review", "evidence": {"resources": []}}),
        }
    )
    room.queues.setdefault("compliance-id", []).append(
        {
            "id": "msg-compliance",
            "content": json.dumps({"type": "specialist_review", "evidence": {"resources": []}}),
        }
    )
    all_started = asyncio.Event()
    started = []

    async def runner(evidence):
        started.append(evidence)
        if len(started) == 2:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), timeout=0.1)
        return {"agent": f"agent-{len(started)}", "decision": "approve"}

    result = asyncio.run(
        run_specialist_agents_from_band_messages(
            chat_id="chat-123",
            agents=[
                BandAgentSpec(id="security-id", name="security-agent"),
                BandAgentSpec(id="compliance-id", name="compliance-agent"),
            ],
            specialist_clients={
                "security-agent": room.client("security-id"),
                "compliance-agent": room.client("compliance-id"),
            },
            specialist_runners={
                "security-agent": runner,
                "compliance-agent": runner,
            },
            coordinator_id="coordinator-id",
            timeout_seconds=1,
            poll_interval_seconds=0,
        )
    )

    assert [item["status"] for item in result] == ["ok", "ok"]


def test_parse_json_message_extracts_json_after_band_mention_prefix():
    message = {
        "id": "msg-json",
        "content": (
            '@[[security-id]] {"type": "specialist_review", '
            '"evidence": {"resources": [{"address": "aws_s3_bucket.customer_data"}]}}'
        ),
    }

    parsed = parse_json_message(message)

    assert parsed == {
        "type": "specialist_review",
        "evidence": {
            "resources": [
                {"address": "aws_s3_bucket.customer_data"},
            ]
        },
    }


def test_run_band_agent_once_uses_sample_evidence_when_message_has_no_evidence():
    room = FakeBandRoom()
    client = room.client("security-id")
    room.queues["security-id"].append(
        {
            "id": "msg-no-evidence",
            "content": "@[[security-id]] Do you copy?",
        }
    )
    captured = {}

    async def runner(evidence):
        captured["evidence"] = evidence
        return {"agent": "security-agent", "decision": "approve"}

    result = asyncio.run(
        run_band_agent_once(
            chat_id="chat-123",
            agent=BandAgentSpec(id="security-id", name="security-agent"),
            client=client,
            runner=runner,
            task_input_key="evidence",
            coordinator_id="coordinator-id",
            timeout_seconds=1,
            poll_interval_seconds=0,
        )
    )

    assert result["status"] == "ok"
    assert captured["evidence"]["resources"]


def test_parse_json_message_extracts_json_from_markdown_fence():
    message = {
        "id": "msg-fenced-json",
        "content": (
            "Here is the payload:\n\n"
            "```json\n"
            '{"type": "specialist_review", "evidence": {"resources": []}}\n'
            "```"
        ),
    }

    parsed = parse_json_message(message)

    assert parsed == {
        "type": "specialist_review",
        "evidence": {"resources": []},
    }


def test_message_content_uses_cost_agent_intro_before_json():
    content = _message_content(
        {"agent": "cost-agent", "decision": "warn"},
        agent_name="cost-agent",
    )

    assert content.startswith("Here's my Cost Analysis.\n```json\n")
    assert content.endswith("\n```")
    assert parse_json_message({"content": content})["agent"] == "cost-agent"


def test_message_content_uses_summarizer_intro_before_json():
    content = _message_content(
        {"decision": "block", "summary": "compiled review"},
        agent_name="summarizer-agent",
    )

    assert content.startswith("Here's the analysis summary.\n```json\n")
    assert parse_json_message({"content": content})["summary"] == "compiled review"
