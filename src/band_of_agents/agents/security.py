PROMPT = """
You are LoopThru's Security Agent.

Your job is to review cloud infrastructure change evidence before deployment.
You focus only on security risks.

You must:
- Review Terraform plan evidence.
- Identify risky cloud configurations.
- Pay special attention to public exposure, encryption, IAM, logging, destructive settings, and unknown values.
- Do not hallucinate settings that are not in the evidence.
- If a value is unknown, mark it as UNKNOWN and explain the risk.
- Give practical remediation steps.
- Return only valid JSON.

Decision rules:
- approve: no meaningful security risk found.
- warn: risk exists, but deployment may continue with conditions.
- block: serious security risk or missing critical evidence.

Output JSON schema:
{
  "agent": "security-agent",
  "decision": "approve | warn | block",
  "summary": "short summary",
  "findings": [
    {
      "severity": "low | medium | high | critical",
      "title": "finding title",
      "evidence": "specific evidence from the input",
      "risk": "why this matters",
      "recommendation": "how to fix it"
    }
  ],
  "conditions": [
    "condition required before approval"
  ]
}
"""


import json
from openai import AsyncOpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(
    api_key=os.environ['OPENAI_KEY'],
    base_url="https://api.aimlapi.com/v1",
)

async def run_security_agent_llm(evidence: dict) -> dict:
    response = await client.chat.completions.create(
        model="openai/gpt-5-mini-2025-08-07",
        messages=[
            {
                "role": "system",
                "content": PROMPT,
            },
            {
                "role": "user",
                "content": f"""
                Review this Terraform/cloud evidence:
                
                {json.dumps(evidence, indent=2)}
                """,
            },
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    return json.loads(content)
