"""Ingest: FINRA consolidated daily short-sale volume (free, no API key).

File format (pipe-delimited), one row per symbol for a trading day:
    Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
The first line is a header and the last line is a record count; both are skipped.

Everything here is best-effort and defensive: on any network/parse failure we return
an empty payload so build_feed emits status="unavailable" and the public panel degrades
gracefully. No dependency on the Arken app.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

import requests


def _fetch(url: str, timeout: float = 12.0) -> str | None:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "arkenlabs-squeeze-radar/1.0"})
    except Exception:
        return None
    if r.status_code != 200 or not r.text:
        return None
    return r.text


def parse_regsho(text: str) -> List[Dict[str, Any]]:
    """Parse a FINRA CNMSshvol daily file into rows. Pure — unit-testable."""
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) < 6:
            continue
        if parts[0].strip().lower() == "date":
            continue
        sym = parts[1].strip().upper()
        if not sym:
            continue
        try:
            short_volume = float(parts[2])
            short_exempt = float(parts[3] or 0)
            total_volume = float(parts[4])
        except ValueError:
            continue
        if total_volume <= 0:
            continue
        rows.append({
            "symbol": sym,
            "short_volume": short_volume,
            "short_exempt": short_exempt,
            "total_volume": total_volume,
            "market": parts[5].strip(),
        })
    return rows


def gather(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Find the most recent published FINRA daily short-volume file and parse it."""
    tmpl = cfg["finra_daily_url"]
    lookback = int(cfg.get("max_lookback_days", 6))
    today = dt.date.today()
    for i in range(lookback + 1):
        d = today - dt.timedelta(days=i)
        if d.weekday() >= 5:  # skip Sat/Sun
            continue
        url = tmpl.format(date=d.strftime("%Y%m%d"))
        text = _fetch(url)
        if not text:
            continue
        rows = parse_regsho(text)
        if rows:
            return {"reg_sho_rows": rows, "as_of": d.isoformat(), "si_map": {}}
    return {"reg_sho_rows": [], "as_of": None, "si_map": {}}
