"""
CRM Intelligence Desk — Live Pipeline Dashboard
Run with: streamlit run demo/dashboard.py
"""

import json
import os
import time
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).parent.parent
PIPELINE_LOG = PROJECT_ROOT / "logs" / "pipeline.jsonl"
START_TRIGGER = PROJECT_ROOT / "logs" / "start_trigger.txt"

AGENT_COLORS = {
    "auditor": "#3B82F6",    # blue
    "enricher": "#EAB308",   # yellow
    "syncer": "#F97316",     # orange
    "reporter": "#22C55E",   # green
}

AGENT_ICONS = {
    "auditor": "🔍",
    "enricher": "🔬",
    "syncer": "🔄",
    "reporter": "📋",
}

TYPE_LABELS = {
    "audit_report": "Audit Report",
    "enrichment_diff": "Enrichment Diff",
    "sync_payload": "Sync Payload",
    "sync_complete": "Sync Complete",
    "summary_posted": "Summary Posted",
}

STAGE_ORDER = ["audit_report", "enrichment_diff", "sync_payload", "sync_complete"]
STAGE_LABELS = ["Audit", "Enrichment", "Sync Ready", "Complete"]


def read_logs():
    if not PIPELINE_LOG.exists():
        return []
    entries = []
    with open(PIPELINE_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def get_pipeline_stage(entries):
    seen_types = {e.get("type") for e in entries}
    stage = 0
    for i, t in enumerate(STAGE_ORDER):
        if t in seen_types:
            stage = i + 1
    return stage


def render_audit_card(data):
    issues = data.get("issue_summary", {})
    st.markdown(f"""
**Records scanned:** {data.get('total_scanned', '?')} &nbsp;|&nbsp;
**Flagged:** {data.get('flagged_count', '?')}

| Issue | Count |
|---|---|
| Missing phone | {issues.get('missing_phone', 0)} |
| Missing company size | {issues.get('missing_company_size', 0)} |
| Stale data (90d+) | {issues.get('stale_data', 0)} |
| Duplicate email | {issues.get('duplicate_email', 0)} |
| Broken associations | {issues.get('broken_association', 0)} |
""")


def render_enrichment_card(data):
    st.markdown(f"""
**Enriched:** {data.get('enriched_count', '?')} &nbsp;|&nbsp;
**Skipped:** {data.get('skipped_count', '?')}
""")
    diffs = data.get("diffs", [])
    if diffs:
        rows = []
        for d in diffs[:5]:
            before_str = ", ".join(f"{k}: {v}" for k, v in d.get("before", {}).items())
            after_str = ", ".join(f"{k}: {v}" for k, v in d.get("after", {}).items())
            rows.append(f"| {d.get('name', d['id'])} | {d.get('company', '')} | {before_str} | {after_str} |")
        table = "| Name | Company | Before | After |\n|---|---|---|---|\n" + "\n".join(rows)
        st.markdown(table)


def render_sync_card(data):
    st.markdown(f"**Records to write:** {data.get('record_count', '?')}")


def render_sync_complete_card(data):
    mock = " *(mock mode)*" if data.get("mock_mode") else ""
    st.markdown(f"**Patched:** {data.get('patched', '?')} &nbsp;|&nbsp; **Failed:** {data.get('failed', 0)}{mock}")


def render_card(entry):
    agent = entry.get("agent", "unknown")
    entry_type = entry.get("type", "event")
    data = entry.get("data", {})
    color = AGENT_COLORS.get(agent, "#6B7280")
    icon = AGENT_ICONS.get(agent, "🤖")
    label = TYPE_LABELS.get(entry_type, entry_type.replace("_", " ").title())
    ts = entry.get("logged_at", data.get("timestamp", ""))[:19].replace("T", " ")

    with st.container():
        st.markdown(
            f"""<div style="border-left: 4px solid {color}; padding: 8px 16px; margin: 8px 0;
                background: rgba(0,0,0,0.03); border-radius: 4px;">
                <strong style="color:{color}">{icon} {agent.upper()}</strong>
                &nbsp;·&nbsp;<em>{label}</em>
                <span style="float:right; color:#888; font-size:0.85em">{ts}</span>
            </div>""",
            unsafe_allow_html=True,
        )

        if entry_type == "audit_report":
            render_audit_card(data)
        elif entry_type == "enrichment_diff":
            render_enrichment_card(data)
        elif entry_type == "sync_payload":
            render_sync_card(data)
        elif entry_type == "sync_complete":
            render_sync_complete_card(data)
        else:
            st.json(data)

        st.divider()


# ── Page setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="CRM Intelligence Desk",
    page_icon="🏢",
    layout="wide",
)

st.title("🏢 CRM Intelligence Desk")
st.caption("Multi-agent HubSpot CRM audit & enrichment pipeline · Band SDK")

# ── Controls ──────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns([2, 2, 4])
with col1:
    if st.button("🚀 Start Pipeline", use_container_width=True):
        START_TRIGGER.parent.mkdir(exist_ok=True)
        START_TRIGGER.write_text("start")
        st.success("Trigger written! @mention @auditor 'run audit' in Band.")

with col2:
    if st.button("🔄 Clear Logs", use_container_width=True):
        if PIPELINE_LOG.exists():
            PIPELINE_LOG.write_text("")
        st.rerun()

# ── Pipeline progress ─────────────────────────────────────────────────────────

entries = read_logs()
stage = get_pipeline_stage(entries)

st.markdown("### Pipeline Progress")
progress_cols = st.columns(4)
for i, (label, col) in enumerate(zip(STAGE_LABELS, progress_cols)):
    with col:
        done = stage > i
        active = stage == i
        if done:
            st.success(f"✅ {label}")
        elif active:
            st.info(f"⏳ {label}")
        else:
            st.empty()
            st.markdown(f"<div style='color:#888'>⬜ {label}</div>", unsafe_allow_html=True)

st.progress(min(stage / 4, 1.0))

# ── Agent feed ────────────────────────────────────────────────────────────────

st.markdown("### Live Agent Feed")

if not entries:
    st.info("No pipeline activity yet. Start the agents and trigger the pipeline in Band.")
else:
    for entry in reversed(entries):
        render_card(entry)

# ── Stats sidebar ─────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## Agent Status")
    for agent, color in AGENT_COLORS.items():
        icon = AGENT_ICONS[agent]
        agent_entries = [e for e in entries if e.get("agent") == agent]
        status = "✅ Done" if agent_entries else "💤 Idle"
        st.markdown(
            f'<span style="color:{color}">**{icon} {agent.capitalize()}**</span> — {status}',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("## Quick Stats")
    if entries:
        st.metric("Pipeline Events", len(entries))
        if stage == 4:
            st.success("Pipeline complete!")
        elif stage > 0:
            st.info(f"Stage {stage}/4 in progress")
    else:
        st.caption("No data yet.")

    st.markdown("---")
    st.caption("Auto-refreshes every 3s")

# ── Auto-refresh ──────────────────────────────────────────────────────────────

time.sleep(3)
st.rerun()
