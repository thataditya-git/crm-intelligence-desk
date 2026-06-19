# CRM Intelligence Desk

> A multi-agent AI pipeline that audits HubSpot CRM contacts for data quality issues, enriches missing fields, and syncs fixes back — with a mandatory human approval gate before anything is written.

**Band of Agents Hackathon 2026 · Track: Internal Enterprise Workflows**

---

## The Problem

CRM data rots over time. Sales teams accumulate contacts with:
- Missing phone numbers
- Missing job titles
- Stale records (not updated in 90+ days)
- Duplicate emails
- Broken deal associations

Manual cleanup costs hours every quarter and is error-prone.

---

## The Solution

Four specialized AI agents collaborate inside a Band room to automatically detect, fix, and sync CRM data quality issues — with a human reviewer in the loop before any data is written.

```
Human → @auditor run audit
      → Auditor scans HubSpot contacts
      → @enricher (audit report JSON)
      → Enricher fills missing fields
      → @syncer (enrichment diff JSON)
      → Syncer builds HubSpot PATCH payload
      → @reporter (payload ready)
      → Reporter posts summary, waits for approval
      → Human types @reporter /approve
      → Syncer executes batch update to HubSpot ✅
```

---

## Agents

| Agent | Role |
|-------|------|
| 🔍 **Auditor** | Pulls all HubSpot contacts, flags missing phone, missing job title, stale data (90d+), duplicate emails, broken associations |
| 🔬 **Enricher** | Looks up missing values by company name in enrichment database, produces before/after diff |
| 🔄 **Syncer** | Converts enrichment diff to HubSpot PATCH payload, saves it, then executes batch update on approval |
| 📋 **Reporter** | Reads full pipeline logs, posts human-readable summary, waits for `@reporter /approve` or `@reporter /reject` |

---

## Human-in-the-Loop Gate

Nothing writes to HubSpot until the human explicitly approves. The reporter posts a full summary showing exactly what will change, then waits.

- Type `@reporter /approve` → syncer executes the batch update
- Type `@reporter /reject` → pipeline stops, nothing is written

The human reviewer is a first-class participant in the Band room — same room as all 4 agents, full visibility into every decision.

---

## Demo Results

From a live run against real HubSpot data:

| Metric | Value |
|--------|-------|
| Contacts scanned | 14 |
| Issues found | 7 |
| Records enriched | 7 |
| Contacts patched in HubSpot | 7 |
| Human effort | 2 messages |

---

## Why Band?

Band is the real coordination layer — not just a notification system. Each agent has its own identity in the room. Context flows as structured JSON in triple-backtick code blocks. Every handoff between agents is visible in real time. The human reviewer is in the same room as the agents. Full audit trail in the room history and `logs/pipeline.jsonl`.

- **Task handoffs** — each agent explicitly @mentions the next one with a full structured payload
- **Shared context** — the Band room history is the pipeline's audit trail
- **Role specialization** — each agent does one thing and does it well
- **Human-in-the-loop** — the human types a message in the same room, not in a separate UI

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Agent coordination | [Band SDK](https://band.ai) (`band-sdk[anthropic]`) |
| LLM | Azure OpenAI `o4-mini` (`api-version=2024-12-01-preview`) |
| CRM | HubSpot CRM REST API |
| Language | Python 3.11 |
| Validation | Pydantic |

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
│   ├── aiml_adapter.py     ← Azure OpenAI ↔ Band SDK bridge
│   ├── hubspot_client.py   ← HubSpot REST API wrapper (mock mode supported)
│   ├── field_map.py        ← field name → HubSpot property mappings
│   └── pipeline_state.py   ← append-only event log + pending payload store
├── data/
│   ├── enrichment_db.json  ← company → phone/jobtitle lookup table
│   └── mock_contacts.json  ← local contacts for offline testing
├── logs/
│   ├── pipeline.jsonl      ← append-only pipeline event log
│   └── pending_payload.json← saved HubSpot payload between syncer stages
├── scripts/
│   └── seed_hubspot.py     ← seeds HubSpot with demo contacts (with deliberate gaps)
├── agent_config.yaml       ← Band agent IDs and API keys
├── start_all.sh            ← starts all 4 agents in parallel
├── requirements.txt
└── .env.example
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-username/crm-intelligence-desk.git
cd crm-intelligence-desk
pip install -r requirements.txt
pip install openai
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
AZURE_OPENAI_API_KEY=your_azure_openai_key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=o4-mini
HUBSPOT_ACCESS_TOKEN=pat-na1-your-hubspot-private-app-token
HUBSPOT_MOCK=false
THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket
THENVOI_REST_URL=https://app.band.ai
```

### 3. Configure Band agents

Create 4 agents on [band.ai](https://band.ai), add them all to the same room, then fill in `agent_config.yaml`:

```yaml
auditor:
  agent_id: "your-auditor-agent-id"
  api_key: "band_a_..."
enricher:
  agent_id: "your-enricher-agent-id"
  api_key: "band_a_..."
syncer:
  agent_id: "your-syncer-agent-id"
  api_key: "band_a_..."
reporter:
  agent_id: "your-reporter-agent-id"
  api_key: "band_a_..."
```

### 4. HubSpot Private App scopes required

Your HubSpot Private App token must have:
- `crm.objects.contacts.read`
- `crm.objects.contacts.write`

### 5. (Optional) Seed demo data into HubSpot

```bash
python scripts/seed_hubspot.py
```

Creates 15 contacts with deliberate gaps — 4 missing phone, 3 missing job title, 1 duplicate email, 7 clean.

---

## Running

### Start all 4 agents

```bash
bash start_all.sh
```

### Trigger the pipeline

In your Band room:

```
@auditor run audit
```

### Approve the changes

When Reporter posts the summary:

```
@reporter /approve
```

HubSpot is updated. Done.

---

## Offline / Mock Mode

Set `HUBSPOT_MOCK=true` in `.env` to run the entire pipeline against `data/mock_contacts.json` without touching real HubSpot data. All API calls are logged instead of executed.

---

## License

MIT
