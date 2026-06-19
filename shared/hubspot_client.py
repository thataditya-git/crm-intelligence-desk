import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

HUBSPOT_BASE = "https://api.hubapi.com/crm/v3/objects/contacts"


class HubSpotClient:
    def __init__(self):
        self.token = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
        self.mock = os.getenv("HUBSPOT_MOCK", "true").lower() == "true"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_contacts(self, limit: int = 20) -> list:
        if self.mock:
            logger.info("[HubSpot MOCK] get_contacts called — returning empty list (use mock_contacts.json instead)")
            return []
        url = f"{HUBSPOT_BASE}?limit={limit}&properties=phone,company,jobtitle,email,firstname,lastname,lastmodifieddate"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json().get("results", [])

    def patch_contact(self, contact_id: str, properties: dict) -> dict:
        if self.mock:
            logger.info(f"[HubSpot MOCK] patch_contact {contact_id}: {properties}")
            return {"id": contact_id, "properties": properties, "mock": True}
        url = f"{HUBSPOT_BASE}/{contact_id}"
        resp = requests.patch(url, headers=self.headers, json={"properties": properties})
        resp.raise_for_status()
        return resp.json()

    def batch_patch_contacts(self, inputs: list) -> dict:
        if self.mock:
            logger.info(f"[HubSpot MOCK] batch_patch_contacts — {len(inputs)} records:")
            for inp in inputs:
                logger.info(f"  id={inp['id']} props={inp['properties']}")
            return {
                "status": "COMPLETE",
                "results": [{"id": inp["id"], "mock": True} for inp in inputs],
                "numErrors": 0,
                "errors": [],
            }
        url = f"{HUBSPOT_BASE}/batch/update"
        resp = requests.post(url, headers=self.headers, json={"inputs": inputs})
        resp.raise_for_status()
        return resp.json()
