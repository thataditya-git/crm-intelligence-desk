"""
SYNCER — CRM Intelligence Desk
Mode A: Receives enrichment diff from @enricher, builds HubSpot PATCH payload, notifies @reporter.
Mode B: Receives APPROVED from @reporter, executes the write to HubSpot.
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

from shared.field_map import build_hubspot_properties
from shared.hubspot_client import HubSpotClient
from shared.pipeline_state import append_log, load_pending_payload, save_pending_payload

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [syncer] %(message)s")

PROMPT = """
You are the SYNCER agent in the CRM Intelligence Desk multi-agent pipeline.

YOUR ROLE:
You operate in two modes based on what message you receive.

MODE A — Build payload (triggered by @enricher):
Only act when you are @mentioned by @enricher with a message containing a JSON code block.

MODE B — Execute write (triggered by @reporter with "APPROVED"):
Only act when you are @mentioned by @reporter AND the message contains "APPROVED".

WHEN TRIGGERED (Mode A — enrichment diff received):
1. Extract the JSON enrichment diff from the triple-backtick code block.
2. Call the `build_sync_payload` tool with the full enrichment diff JSON string.
3. Post a message to the room with:
   - A brief summary (X records ready to sync)
   - The full HubSpot payload JSON in a triple-backtick code block:
     ```json
     { ... sync payload ... }
     ```
4. @mention @reporter with: "Sync payload ready for review. Awaiting human approval." followed by the JSON in triple backticks.

WHEN TRIGGERED (Mode B — APPROVED received):
1. Call the `execute_hubspot_write` tool (no arguments needed).
2. Post a message to the room: "✅ HubSpot updated. X contacts patched successfully."

IMPORTANT RULES:
- Always extract JSON from triple backtick code blocks in incoming messages.
- Always wrap your output JSON in triple backtick code blocks.
- Do not respond to messages that are not @mentions matching the above triggers.
- In Mode B, do NOT ask for confirmation — just execute the write immediately.
"""


class BuildSyncPayloadInput(BaseModel):
    """Build a HubSpot PATCH payload from the enrichment diff. Pass the full diff JSON string."""
    enrichment_diff_json: str


class ExecuteHubspotWriteInput(BaseModel):
    """Execute the pending HubSpot batch update that was saved after enrichment."""


def build_sync_payload(inp: BuildSyncPayloadInput) -> dict:
    """Convert enrichment diff to HubSpot batch PATCH payload and save it."""
    try:
        diff = json.loads(inp.enrichment_diff_json)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid enrichment diff JSON: {e}"}

    now = datetime.now(timezone.utc)
    inputs = []

    for record in diff.get("diffs", []):
        hs_id = record.get("hs_object_id")
        after = record.get("after", {})
        if not hs_id or not after:
            continue

        hs_properties = build_hubspot_properties(after)
        if hs_properties:
            inputs.append({
                "id": hs_id,
                "properties": hs_properties,
            })

    payload = {
        "stage": "sync_ready",
        "timestamp": now.isoformat(),
        "record_count": len(inputs),
        "inputs": inputs,
    }

    save_pending_payload(payload)
    append_log({"agent": "syncer", "type": "sync_payload", "data": payload})
    logger.info("Sync payload built: %d records", len(inputs))
    return payload


def execute_hubspot_write(_: ExecuteHubspotWriteInput) -> dict:
    """Load the pending payload and execute the HubSpot batch update."""
    try:
        payload = load_pending_payload()
    except FileNotFoundError:
        return {"error": "No pending payload found. Run the pipeline first."}

    client = HubSpotClient()
    inputs = payload.get("inputs", [])

    try:
        result = client.batch_patch_contacts(inputs)
    except Exception as e:
        logger.error("HubSpot batch update failed: %s", e)
        return {"error": str(e), "attempted_count": len(inputs)}

    results = result.get("results", [])
    errors = result.get("errors", [])
    patched = len(results)
    failed = len(errors)

    summary = {
        "stage": "sync_complete",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "patched": patched,
        "failed": failed,
        "mock_mode": os.getenv("HUBSPOT_MOCK", "true").lower() == "true",
    }

    append_log({"agent": "syncer", "type": "sync_complete", "data": summary})
    logger.info("HubSpot update complete: %d patched, %d failed", patched, failed)
    return summary


async def main():
    from band import Agent
    from band.config import load_agent_config

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from shared.aiml_adapter import AIMLAnthropicAdapter

    config_path = os.path.join(os.path.dirname(__file__), "..", "agent_config.yaml")
    agent_id, api_key = load_agent_config("syncer", config_path=config_path)

    adapter = AIMLAnthropicAdapter(
        model="claude-sonnet-4-5-20250929",
        provider_key=os.getenv("AIML_API_KEY"),
        prompt=PROMPT,
        additional_tools=[
            (BuildSyncPayloadInput, build_sync_payload),
            (ExecuteHubspotWriteInput, execute_hubspot_write),
        ],
        max_tokens=4096,
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai"),
    )

    logger.info("Syncer agent running. Waiting for @enricher diff or @reporter APPROVED.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
