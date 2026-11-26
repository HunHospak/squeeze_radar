"""Orchestration: ingest -> compute -> validate(schema) -> write out/."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from providers import gather  # noqa: E402
from compute import build_boards  # noqa: E402


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_schema() -> dict:
    return json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))


def build(cfg: dict, *, generated_at: dt.datetime | None = None) -> dict:
    now = generated_at or dt.datetime.now(dt.timezone.utc)
    raw = gather(cfg, today=now.date())
    boards = build_boards(raw, cfg)
    status = boards.pop("_status")
    notes = boards.pop("_notes", None)
    if status == "active":
        age = (now.date() - dt.date.fromisoformat(boards["as_of"])).days
        trend_days = int(cfg.get("trend_days", 5))
        limitations = []
        if age > 3:
            limitations.append(f"Latest complete FINRA file is from {boards['as_of']}.")
        if boards["trend_days"] < trend_days:
            limitations.append(f"Only {boards['trend_days']} of {trend_days} requested FINRA sessions were available.")
        if limitations:
            status, notes = "partial", " ".join(limitations)
    elif not raw["days"]:
        notes = f"No complete FINRA short-volume file within {int(cfg.get('max_lookback_days', 6))} calendar days."
    boards["disclaimer"] = "Short-selling activity from regulatory data. Informational only, not investment advice."

    feed = {
        "service": cfg["service"],
        "schema_version": str(cfg["schema_version"]),
        "generated_at": now.replace(microsecond=0).isoformat(),
        "status": status,
        "ttl_hours": cfg["ttl_hours"],
        "data": boards,
    }
    if notes:
        feed["notes"] = notes
    return feed


def main() -> None:
    cfg = load_config()
    feed = build(cfg)
    jsonschema.validate(feed, load_schema())
    out = ROOT / "out"
    (out / "history").mkdir(parents=True, exist_ok=True)
    payload = json.dumps(feed, separators=(",", ":"), allow_nan=False)
    (out / "squeeze_radar.json").write_text(payload, encoding="utf-8")
    as_of = feed["data"]["as_of"]
    if feed["data"]["universe_size"]:
        (out / "history" / f"{as_of}.json").write_text(payload, encoding="utf-8")
    print(f"[squeeze_radar] status={feed['status']} universe={feed['data']['universe_size']} as_of={as_of}")


if __name__ == "__main__":
    main()
