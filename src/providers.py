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
    """Collect the most recent published FINRA daily short-volume files.

    Returns up to `trend_days` distinct trading days (newest first) so compute can build
    both the latest-day boards and a multi-day short-pressure trend. The newest day's rows
    are also exposed as `reg_sho_rows` for backward compatibility.
    """
    tmpl = cfg["finra_daily_url"]
    lookback = int(cfg.get("max_lookback_days", 6))
    want_days = int(cfg.get("trend_days", 5))
    today = dt.date.today()

    days: List[Dict[str, Any]] = []
    i = 0
    # Walk back far enough to collect `want_days` published files (plus slack for holidays).
    while len(days) < want_days and i <= lookback + want_days + 5:
        d = today - dt.timedelta(days=i)
        i += 1
        if d.weekday() >= 5:  # skip Sat/Sun
            continue
        text = _fetch(tmpl.format(date=d.strftime("%Y%m%d")))
        if not text:
            continue
        rows = parse_regsho(text)
        if rows:
            days.append({"date": d.isoformat(), "rows": rows})

    if not days:
        return {"reg_sho_rows": [], "days": [], "as_of": None, "si_map": {}}
    return {"reg_sho_rows": days[0]["rows"], "days": days, "as_of": days[0]["date"], "si_map": {}}
