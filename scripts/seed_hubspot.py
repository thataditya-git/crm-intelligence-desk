"""
Seed HubSpot with 15 demo contacts that have deliberate data gaps.
Uses only standard HubSpot contact properties guaranteed to exist.

Usage:
    python scripts/seed_hubspot.py
"""

import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
if not TOKEN:
    print("ERROR: HUBSPOT_ACCESS_TOKEN not set in .env")
    sys.exit(1)

BASE = "https://api.hubapi.com/crm/v3/objects/contacts"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Only standard HubSpot contact fields used here
CONTACTS = [
    # --- 4 contacts missing phone ---
    {"firstname": "Jane",  "lastname": "Doe",      "email": "jane.doe@acmecorp.com",      "phone": None,          "company": "Acme Corp",       "jobtitle": "CEO"},
    {"firstname": "Alice", "lastname": "Chen",     "email": "alice.chen@initech.com",     "phone": None,          "company": "Initech",         "jobtitle": "Engineer"},
    {"firstname": "David", "lastname": "Lee",      "email": "david.lee@wayne.com",        "phone": None,          "company": "Wayne Enterprises","jobtitle": "Director"},
    {"firstname": "Frank", "lastname": "Nguyen",   "email": "frank.nguyen@oscorp.com",    "phone": None,          "company": "Oscorp",          "jobtitle": "Manager"},

    # --- 3 contacts missing jobtitle ---
    {"firstname": "Bob",   "lastname": "Martinez", "email": "bob.martinez@umbrella.com",  "phone": "+1-555-0104", "company": "Umbrella Corp",   "jobtitle": None},
    {"firstname": "Eva",   "lastname": "Brown",    "email": "eva.brown@stark.com",        "phone": "+1-555-0107", "company": "Stark Industries", "jobtitle": None},
    {"firstname": "Leo",   "lastname": "Jackson",  "email": "leo.jackson@globex.com",     "phone": "+1-555-0114", "company": "Globex",          "jobtitle": None},

    # --- 1 duplicate email (same as Jane Doe) ---
    {"firstname": "Grace", "lastname": "Wilson",   "email": "jane.doe@acmecorp.com",      "phone": "+1-555-0109", "company": "Acme Corp",       "jobtitle": "Sales"},

    # --- 7 clean contacts ---
    {"firstname": "John",  "lastname": "Smith",    "email": "john.smith@globex.com",      "phone": "+1-555-0102", "company": "Globex",          "jobtitle": "VP Sales"},
    {"firstname": "Henry", "lastname": "Anderson", "email": "henry.anderson@nakatomi.com","phone": "+1-555-0110", "company": "Nakatomi Corp",   "jobtitle": "CFO"},
    {"firstname": "Iris",  "lastname": "Thompson", "email": "iris.thompson@soylent.com",  "phone": "+1-555-0111", "company": "Soylent Corp",    "jobtitle": "COO"},
    {"firstname": "Jack",  "lastname": "Harris",   "email": "jack.harris@initech.com",    "phone": "+1-555-0112", "company": "Initech",         "jobtitle": "Developer"},
    {"firstname": "Karen", "lastname": "Moore",    "email": "karen.moore@dunder.com",     "phone": "+1-555-0113", "company": "Dunder Mifflin",  "jobtitle": "HR Manager"},
    {"firstname": "Mia",   "lastname": "White",    "email": "mia.white@wayne.com",        "phone": "+1-555-0115", "company": "Wayne Enterprises","jobtitle": "CMO"},
    {"firstname": "Carol", "lastname": "Williams", "email": "carol.williams@oscorp.com",  "phone": "+1-555-0105", "company": "Oscorp",          "jobtitle": "CTO"},
]


def create_contact(props: dict) -> dict:
    clean = {k: v for k, v in props.items() if v is not None}
    resp = requests.post(BASE, headers=HEADERS, json={"properties": clean})
    if resp.status_code == 409:
        return {"status": "duplicate", "email": props.get("email")}
    resp.raise_for_status()
    return resp.json()


def main():
    print(f"Seeding {len(CONTACTS)} contacts into HubSpot...")
    print(f"Token: {TOKEN[:25]}...")
    print()

    created, skipped, failed = 0, 0, 0

    for i, contact in enumerate(CONTACTS, 1):
        name = f"{contact['firstname']} {contact['lastname']}"
        try:
            result = create_contact(contact)
            if result.get("status") == "duplicate":
                print(f"  [{i:02d}] ⚠️  DUPLICATE  {name} ({contact['email']})")
                skipped += 1
            else:
                hs_id = result.get("id", "?")
                missing = [k for k in ("phone", "jobtitle") if not contact.get(k)]
                gap_str = f" [missing: {', '.join(missing)}]" if missing else " [clean]"
                print(f"  [{i:02d}] ✅ CREATED   {name} (id={hs_id}){gap_str}")
                created += 1
        except Exception as e:
            print(f"  [{i:02d}] ❌ FAILED    {name} — {e}")
            failed += 1

        time.sleep(0.3)

    print()
    print("=" * 55)
    print(f"Done!  Created: {created}  |  Skipped (dup): {skipped}  |  Failed: {failed}")
    print()
    print("Your HubSpot CRM now has contacts with:")
    print("  • 4 missing phone numbers")
    print("  • 3 missing job titles")
    print("  • 1 duplicate email pair")
    print("  • 7 clean contacts")
    print()
    print("Next: bash start_all.sh  →  @auditor run audit")


if __name__ == "__main__":
    main()
