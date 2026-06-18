from openai import AsyncOpenAI
import os

client = AsyncOpenAI(
    api_key=os.environ['OPENAI_KEY'],
    base_url="https://api.aimlapi.com/v1",
)

CHAT_SUMMARIZER_PROMPT = """
You are a Review Summary Formatter for LoopThru.

Your task is to convert the provided analysis output into concise, professional Markdown suitable for a chat room.

Rules:

* Output Markdown only.
* Do not output JSON.
* Do not invent findings.
* Do not change severity levels.
* Preserve the original meaning.
* Focus on the most important findings first.
* Keep the summary concise and easy to scan.
* Use bullet points instead of large paragraphs.
* Assume the full JSON report is stored separately for audit and traceability.

Output format:

# <Review Type>

**Risk Level:** <risk level>

## Key Findings

* Finding 1
* Finding 2
* Finding 3

## Recommendation

Short summary of the recommended action.

If there are no findings, state that no significant issues were identified.

Convert the following analysis into the format above:
"""

async def run_chat_formatter(output: dict) -> str:
    response = await client.chat.completions.create(
        model="openai/gpt-5-mini-2025-08-07",
        messages=[
            {"role": "system", "content": CHAT_SUMMARIZER_PROMPT},
            {
                "role": "user",
                "content": f"""
                    Convert the following infrastructure review analysis into a concise Markdown summary suitable for a chat room.

                    Analysis Output:
                    {output}

                    Requirements:

                    Preserve all findings and risk levels.
                    Do not output JSON.
                    Do not invent information.
                    Keep the summary concise and easy to scan.
                """
            },
        ],
        temperature=0.1,
    )

    return response.choices[0].message.content or ""
