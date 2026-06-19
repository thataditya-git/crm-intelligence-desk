"""
REPORTER — CRM Intelligence Desk
Receives sync payload from @syncer, posts a human-readable summary, then
listens for /approve or /reject from the human reviewer.
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

from shared.pipeline_state import append_log, read_logs

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [reporter] %(message)s")

PROMPT = """
You are the REPORTER agent in the CRM Intelligence Desk multi-agent pipeline.

YOUR ROLE:
You are the human-facing agent. You receive the sync payload from @syncer, produce a
clear summary for human review, and then act on their approval or rejection.

TRIGGER A — Sync payload received:
Act when @mentioned by @syncer with a message containing a JSON code block.

TRIGGER B — Human approval/rejection:
Act when you are @mentioned and the message contains "/approve" or "/reject".

WHEN TRIGGERED (Trigger A — payload received):
1. Extract the JSON sync payload from the triple-backtick code block.
2. Call the `build_summary` tool with the full sync payload JSON string.
3. Post the formatted summary (the tool returns it as a string) to the room exactly as returned.
4. Do NOT @mention anyone yet — wait for human input.

WHEN TRIGGERED (Trigger B — /approve):
1. Post: "@syncer APPROVED — execute write to HubSpot"
2. Log the approval.

WHEN TRIGGERED (Trigger B — /reject):
1. Post: "❌ Pipeline cancelled by human reviewer. No changes written to HubSpot."
2. Log the rejection.

IMPORTANT RULES:
- Watch ALL room messages for /approve and /reject, even if you are not @mentioned.
- The summary must be posted verbatim as returned by build_summary — do not reformat it.
- Do not ask for confirmation or repeat the summary when approving — just relay to @syncer.
"""


class BuildSummaryInput(BaseModel):
    """Build a human-readable pipeline summary. Pass the full sync payload JSON string."""
    sync_payload_json: str


def build_summary(inp: BuildSummaryInput) -> str:
    """Read all pipeline logs and produce a formatted summary for human review."""
    try:
        payload = json.loads(inp.sync_payload_json)
    except json.JSONDecodeError:
        payload = {}

    logs = read_logs()

    # Extract counts from logs
    audit_data: dict = {}
    enrichment_data: dict = {}
    for entry in logs:
        if entry.get("agent") == "auditor" and entry.get("type") == "audit_report":
            audit_data = entry.get("data", {})
        if entry.get("agent") == "enricher" and entry.get("type") == "enrichment_diff":
            enrichment_data = entry.get("data", {})

    issue_summary = audit_data.get("issue_summary", {})
    total_scanned = audit_data.get("total_scanned", "?")
    flagged_count = audit_data.get("flagged_count", "?")
    enriched_count = enrichment_data.get("enriched_count", "?")
    skipped_count = enrichment_data.get("skipped_count", "?")
    record_count = payload.get("record_count", enriched_count)

    now = datetime.now(timezone.utc).isoformat()

    summary = f"""╔══════════════════════════════════════════╗
║     CRM Intelligence Desk — Summary     ║
╚══════════════════════════════════════════╝

📋 Audit Results
  Records scanned:        {total_scanned}
  Records flagged:        {flagged_count}
  Issues found:
    • Missing phone:        {issue_summary.get('missing_phone', 0)}
    • Missing company size: {issue_summary.get('missing_company_size', 0)}
    • Stale data (90d+):    {issue_summary.get('stale_data', 0)}
    • Duplicate email:      {issue_summary.get('duplicate_email', 0)}
    • Broken associations:  {issue_summary.get('broken_association', 0)}

🔬 Enrichment Results
  Successfully enriched:  {enriched_count}
  Could not enrich:       {skipped_count}

📦 Sync Payload
  Records ready to write: {record_count}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  @reporter /approve  → write {record_count} records to HubSpot
  @reporter /reject   → discard all changes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    append_log({
        "agent": "reporter",
        "type": "summary_posted",
        "data": {
            "timestamp": now,
            "record_count": record_count,
        }
    })
    logger.info("Summary built and ready to post.")
    return summary


async def main():
    from band import Agent
    from band.config import load_agent_config

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from shared.aiml_adapter import AIMLAnthropicAdapter

    config_path = os.path.join(os.path.dirname(__file__), "..", "agent_config.yaml")
    agent_id, api_key = load_agent_config("reporter", config_path=config_path)

    adapter = AIMLAnthropicAdapter(
        model="claude-sonnet-4-5-20250929",
        provider_key=os.getenv("AIML_API_KEY"),
        prompt=PROMPT,
        additional_tools=[(BuildSummaryInput, build_summary)],
        max_tokens=4096,
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai"),
    )

    logger.info("Reporter agent running. Waiting for @syncer payload or /approve /reject.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
