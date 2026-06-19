# CRM Intelligence Desk

> **Band of Agents Hackathon — Track 1: Internal Enterprise Workflows**

A multi-agent HubSpot CRM audit and enrichment pipeline built with the Band SDK. Four specialized AI agents collaborate through a Band room to find data rot, enrich records, and await human approval before writing anything back to HubSpot.

---

## Problem

CRM data rots. Contacts accumulate missing phone numbers, stale job titles, null company sizes, and duplicate records. Manual cleanup is expensive, error-prone, and never quite catches up. Enterprise teams waste hours every quarter chasing bad data — hours that could be spent selling.

---

## Solution

Four specialized agents work in sequence through a shared Band room:

1. **Auditor** — scans all contacts and flags issues (missing fields, stale records, duplicates, broken associations)
2. **Enricher** — looks up flagged records in an enrichment database and fills missing values
3. **Syncer** — maps enriched fields to HubSpot property names and builds a ready-to-write PATCH payload
4. **Reporter** — summarizes the full pipeline for a human reviewer and acts as the approval gate

No changes touch HubSpot until a human types `/approve` in the room. This is the core differentiator: **the human is a first-class participant in the same Band room as the agents**.

---

## Architecture

```
Human → @auditor run audit
          │
          ▼
    [Auditor] ── run_audit() ──► audit report JSON
          │
          └──► @enricher "Audit complete. Please enrich..."
                    │
                    ▼
              [Enricher] ── run_enrichment() ──► enrichment diff JSON
                    │
                    └──► @syncer "Enrichment complete. Here is the diff:"
                                │
                                ▼
                          [Syncer] ── build_sync_payload() ──► HubSpot payload JSON
                                │
                                └──► @reporter "Sync payload ready. Awaiting approval."
                                              │
                                              ▼
                                        [Reporter] ── build_summary()
                                              │
                                              └──► Human sees summary
                                                        │
                                          ┌─────────────┴────────────────┐
                                          │                              │
                                    /approve                         /reject
                                          │                              │
                                          ▼                              ▼
                                    @syncer APPROVED            ❌ Pipeline cancelled
                                          │
                                          ▼
                                    [Syncer] ── execute_hubspot_write()
                                          │
                                          ▼
                                    ✅ HubSpot updated
```

---

## Why Band?

Band is **the coordination layer, not a notification channel**. Each agent has a distinct identity in the room. Context flows as structured messages with JSON in code blocks that downstream agents parse. The handoff chain is:

- **Task handoffs**: each agent explicitly @mentions the next one with a full structured payload
- **Shared context**: the Band room history is the pipeline's audit trail — every agent can see what came before
- **Role specialization**: auditor, enricher, syncer, and reporter each do one thing and do it well
- **Human-in-the-loop**: the human reviewer reads the same room the agents do, types `/approve`, and the pipeline proceeds

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent coordination | [Band SDK](https://band.ai) (`band-sdk[anthropic]`) |
| LLM | `claude-sonnet-4-5` via [AI/ML API](https://aimlapi.com) |
| CRM | HubSpot CRM API (mock mode by default) |
| Language | Python 3.11+ |
| Package manager | uv / pip |
| Demo dashboard | Streamlit |

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo>
cd crm-intelligence-desk
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set:
#   AIML_API_KEY=your_key_from_aimlapi.com
#   HUBSPOT_MOCK=true   (keep this for demo)
```

### 3. Configure Band agents

The four agents are already created. Their IDs and API keys are in `agent_config.yaml`.
You must add all four agents to the same Band room before running.

```yaml
# agent_config.yaml (already configured)
auditor:
  agent_id: "08107e4b-f264-44be-b46a-5979025e8f4e"
  api_key: "band_a_..."
enricher:
  agent_id: "dbac0ba6-..."
  ...
```

### 4. Start all agents

```bash
bash start_all.sh
```

### 5. (Optional) Start the live dashboard

```bash
streamlit run demo/dashboard.py
```

---

## Demo

1. Start all agents with `bash start_all.sh`
2. In your Band room, type: `@auditor run audit`
3. Watch the agents hand off work to each other in real time:
   - @auditor posts the audit report (15 contacts scanned, 10+ issues found)
   - @enricher receives it, enriches 7 records, posts the diff
   - @syncer builds the HubSpot PATCH payload and asks @reporter to review
   - @reporter posts a formatted summary with `/approve` / `/reject` instructions
4. Type `/approve` in the room
5. @reporter tells @syncer to execute. @syncer calls HubSpot (in mock mode, logs the payload).

The entire pipeline — audit → enrich → review → write — happens in one Band room with visible agent-to-agent handoffs.

---

## Mock Data

- `data/mock_contacts.json` — 15 fake contacts with deliberate gaps:
  - 4 contacts: missing phone
  - 3 contacts: missing company size
  - 3 contacts: stale (last modified 100+ days ago)
  - 1 duplicate email pair
  - 2 broken deal associations
- `data/enrichment_db.json` — lookup table covering ~10 companies

---

## Project Structure

```
crm-intelligence-desk/
├── agents/
│   ├── auditor.py          ← Agent 1: data quality scanner
│   ├── enricher.py         ← Agent 2: field enrichment
│   ├── syncer.py           ← Agent 3: HubSpot sync (build + execute)
│   └── reporter.py         ← Agent 4: human-facing summary + approval gate
├── shared/
│   ├── aiml_adapter.py     ← AnthropicAdapter subclass using AI/ML API
│   ├── hubspot_client.py   ← HubSpot API wrapper (mock mode default)
│   ├── field_map.py        ← field name → HubSpot property mappings
│   └── pipeline_state.py   ← append-only log + pending payload store
├── data/
│   ├── mock_contacts.json
│   └── enrichment_db.json
├── logs/
│   └── pipeline.jsonl      ← append-only event log
├── demo/
│   └── dashboard.py        ← Streamlit live feed
├── agent_config.yaml
├── .env.example
├── requirements.txt
└── start_all.sh
```
