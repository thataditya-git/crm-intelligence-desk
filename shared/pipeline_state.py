import json
import os
from datetime import datetime

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
PIPELINE_LOG = os.path.join(LOGS_DIR, "pipeline.jsonl")
PENDING_PAYLOAD_FILE = os.path.join(LOGS_DIR, "pending_payload.json")


def ensure_logs_dir():
    os.makedirs(LOGS_DIR, exist_ok=True)


def append_log(entry: dict):
    ensure_logs_dir()
    entry.setdefault("logged_at", datetime.utcnow().isoformat() + "Z")
    with open(PIPELINE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def read_logs() -> list:
    ensure_logs_dir()
    if not os.path.exists(PIPELINE_LOG):
        return []
    entries = []
    with open(PIPELINE_LOG, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def save_pending_payload(payload: dict):
    ensure_logs_dir()
    with open(PENDING_PAYLOAD_FILE, "w") as f:
        json.dump(payload, f, indent=2)


def load_pending_payload() -> dict:
    if not os.path.exists(PENDING_PAYLOAD_FILE):
        raise FileNotFoundError(f"No pending payload found at {PENDING_PAYLOAD_FILE}")
    with open(PENDING_PAYLOAD_FILE, "r") as f:
        return json.load(f)
