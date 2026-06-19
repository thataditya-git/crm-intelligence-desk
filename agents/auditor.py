"""
AUDITOR — CRM Intelligence Desk
Scans mock_contacts.json for data quality issues and hands off to @enricher.
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

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.hubspot_client import HubSpotClient
from shared.pipeline_state import append_log

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [auditor] %(message)s")

CONTACTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "mock_contacts.json")
STALE_DAYS = 90


def fetch_contacts() -> list:
    """Fetch contacts from HubSpot or fall back to mock file."""
    mock = os.getenv("HUBSPOT_MOCK", "true").lower() == "true"
    if mock:
        with open(CONTACTS_FILE) as f:
            return json.load(f)

    client = HubSpotClient()
    raw = client.get_contacts(limit=100)

    contacts = []
    for c in raw:
        props = c.get("properties", {})
        contacts.append({
            "id": f"contact_{c['id']}",
            "hs_object_id": c["id"],
            "firstname": props.get("firstname", ""),
            "lastname": props.get("lastname", ""),
            "email": props.get("email", ""),
            "phone": props.get("phone") or None,
            "company": props.get("company", ""),
            "jobtitle": props.get("jobtitle") or None,
            "last_modified": props.get("lastmodifieddate", ""),
            "deal_id": None,
        })
    logger.info("Fetched %d contacts from HubSpot", len(contacts))
    return contacts

PROMPT = """
You are the AUDITOR agent in the CRM Intelligence Desk multi-agent pipeline.

When you receive ANY message, you MUST immediately call the `run_audit` tool. Do not wait, do not ask questions, just call it right away.

After calling run_audit and getting the results:
1. Post a summary message to the room like:
"🔍 Audit complete! Scanned X contacts, found Y issues.
```json
{ paste the full JSON here }
```"

2. Then send a follow-up message: "@enricher Audit complete. Please enrich the flagged records.
```json
{ paste the full JSON here again }
```"

Always call the run_audit tool immediately. Never skip it.
"""


class RunAuditInput(BaseModel):
    """Run the CRM audit and return a structured report of all data quality issues."""


def run_audit(_: RunAuditInput) -> dict:
    """Execute audit rules against HubSpot contacts and return structured report."""
    contacts = fetch_contacts()

    now = datetime.now(timezone.utc)

    # Count email occurrences for duplicate detection
    email_counts: dict[str, list[str]] = {}
    for c in contacts:
        email = (c.get("email") or "").lower().strip()
        if email:
            email_counts.setdefault(email, []).append(c["id"])

    flagged_records = []
    issue_summary = {
        "missing_phone": 0,
        "missing_jobtitle": 0,
        "stale_data": 0,
        "duplicate_email": 0,
        "broken_association": 0,
    }

    for c in contacts:
        issues: list[str] = []

        if not c.get("phone"):
            issues.append("missing_phone")

        if not c.get("jobtitle"):
            issues.append("missing_jobtitle")

        lm = c.get("last_modified")
        if lm:
            try:
                lm_dt = datetime.fromisoformat(lm.replace("Z", "+00:00"))
                if (now - lm_dt).days > STALE_DAYS:
                    issues.append("stale_data")
            except ValueError:
                pass

        email = (c.get("email") or "").lower().strip()
        if email and len(email_counts.get(email, [])) > 1:
            issues.append("duplicate_email")

        if c.get("deal_id") == "BROKEN":
            issues.append("broken_association")

        if issues:
            for issue in issues:
                if issue in issue_summary:
                    issue_summary[issue] += 1
            flagged_records.append({
                "id": c["id"],
                "hs_object_id": c["hs_object_id"],
                "name": f"{c.get('firstname', '')} {c.get('lastname', '')}".strip(),
                "company": c.get("company", ""),
                "email": c.get("email", ""),
                "issues": issues,
            })

    report = {
        "stage": "audit",
        "timestamp": now.isoformat(),
        "total_scanned": len(contacts),
        "flagged_count": len(flagged_records),
        "issue_summary": issue_summary,
        "records": flagged_records,
    }

    append_log({"agent": "auditor", "type": "audit_report", "data": report})
    logger.info("Audit complete: %d/%d records flagged", len(flagged_records), len(contacts))
    return report


async def main():
    from band import Agent
    from band.config import load_agent_config

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from shared.aiml_adapter import AIMLAnthropicAdapter

    config_path = os.path.join(os.path.dirname(__file__), "..", "agent_config.yaml")
    agent_id, api_key = load_agent_config("auditor", config_path=config_path)

    adapter = AIMLAnthropicAdapter(
        model="claude-sonnet-4-5-20250929",
        provider_key=os.getenv("AIML_API_KEY"),
        prompt=PROMPT,
        additional_tools=[(RunAuditInput, run_audit)],
        max_tokens=4096,
    )

    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai"),
    )

    logger.info("Auditor agent running. @mention with 'run audit' to start the pipeline.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
