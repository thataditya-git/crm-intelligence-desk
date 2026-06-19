"""
ENRICHER — CRM Intelligence Desk
Receives audit report from @auditor, fills missing fields from enrichment_db.json,
and passes the diff to @syncer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.pipeline_state import append_log

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [enricher] %(message)s")

ENRICHMENT_DB_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "enrichment_db.json")
CONTACTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "mock_contacts.json")

PROMPT = """
You are the ENRICHER agent in the CRM Intelligence Desk multi-agent pipeline.

YOUR ROLE:
You receive an audit report from @auditor, look up missing field values from an enrichment
database, and produce a diff of what can be filled in. Then you pass the diff to @syncer.

TRIGGER:
Only act when you are @mentioned by @auditor with a message that contains a JSON code block
(inside triple backticks). Ignore ALL other messages.

WHEN TRIGGERED:
1. Extract the JSON audit report from the triple-backtick code block in the message.
2. Call the `run_enrichment` tool with the full audit report JSON string.
3. Post a message to the room with:
   - A brief human-readable summary (X records enriched, Y skipped)
   - The full enrichment diff JSON in a triple-backtick code block:
     ```json
     { ... enrichment diff ... }
     ```
4. Then @mention @syncer with: "Enrichment complete. Here is the diff:" followed by the full JSON in triple backticks.

IMPORTANT RULES:
- Always extract the JSON from triple backtick code blocks in incoming messages.
- Always wrap your output JSON in triple backtick code blocks.
- Do not skip the @syncer mention — the pipeline depends on it.
- Do not respond to messages that are not @mentions containing an audit report.
"""


class RunEnrichmentInput(BaseModel):
    """Run enrichment on flagged contacts. Pass the full audit report JSON string."""
    audit_report_json: str


def run_enrichment(inp: RunEnrichmentInput) -> dict:
    """Look up flagged contacts in enrichment_db and build a diff of changes."""
    try:
        audit_report = json.loads(inp.audit_report_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid audit report JSON: {e}"}

    with open(ENRICHMENT_DB_FILE) as f:
        enrichment_db: dict = json.load(f)

    # Build lookup by contact id for original data
    with open(CONTACTS_FILE) as f:
        contacts = json.load(f)
    contact_map = {c["id"]: c for c in contacts}

    now = datetime.now(timezone.utc)
    diffs = []
    skipped = []

    enrichable_issues = {"missing_phone": "phone", "missing_jobtitle": "jobtitle"}

    for record in audit_report.get("records", []):
        contact_id = record["id"]
        company = record.get("company", "")
        issues = record.get("issues", [])

        # Only try to enrich records with enrichable issues
        enrichable = [iss for iss in issues if iss in enrichable_issues]
        if not enrichable:
            continue

        if company not in enrichment_db:
            skipped.append({
                "id": contact_id,
                "hs_object_id": record["hs_object_id"],
                "reason": f"Company '{company}' not found in enrichment database",
            })
            continue

        db_entry = enrichment_db[company]
        original = contact_map.get(contact_id, {})
        before = {}
        after = {}

        for issue in enrichable:
            field = enrichable_issues[issue]
            if field in db_entry and db_entry[field]:
                before[field] = original.get(field)
                after[field] = db_entry[field]

        if after:
            diffs.append({
                "id": contact_id,
                "hs_object_id": record["hs_object_id"],
                "name": record.get("name", ""),
                "company": company,
                "before": before,
                "after": after,
            })
        else:
            skipped.append({
                "id": contact_id,
                "hs_object_id": record["hs_object_id"],
                "reason": "No enrichable fields found in database entry",
            })

    result = {
        "stage": "enrichment",
        "timestamp": now.isoformat(),
        "enriched_count": len(diffs),
        "skipped_count": len(skipped),
        "diffs": diffs,
        "skipped": skipped,
    }

    append_log({"agent": "enricher", "type": "enrichment_diff", "data": result})
    logger.info("Enrichment complete: %d enriched, %d skipped", len(diffs), len(skipped))
    return result


async def main():
    from band import Agent
    from band.config import load_agent_config

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from shared.aiml_adapter import AIMLAnthropicAdapter

    config_path = os.path.join(os.path.dirname(__file__), "..", "agent_config.yaml")
    agent_id, api_key = load_agent_config("enricher", config_path=config_path)

    adapter = AIMLAnthropicAdapter(
        model="claude-sonnet-4-5-20250929",
        provider_key=os.getenv("AIML_API_KEY"),
        prompt=PROMPT,
        additional_tools=[(RunEnrichmentInput, run_enrichment)],
        max_tokens=4096,
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai"),
    )

    logger.info("Enricher agent running. Waiting for @mention from @auditor.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
