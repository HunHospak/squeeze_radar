"""Ingest: FINRA consolidated daily short-sale volume (free, no API key).

File format (pipe-delimited), one row per symbol for a trading day:
    Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
The header, trailer record count and trade date are validated before using the file.

Everything here is best-effort and defensive: on any network/parse failure we return
an empty payload so build_feed emits status="unavailable" and the public panel degrades
gracefully. No dependency on the Arken app.
"""
from __future__ import annotations

import datetime as dt
import math
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


def parse_regsho(text: str, expected_date: dt.date) -> List[Dict[str, Any]]:
    """Accept only complete consolidated files for the requested trade date."""
    lines = text.strip().lstrip("\ufeff").splitlines()
    if len(lines) < 2:
        return []
    header = lines[0].lower().replace(" ", "")
    if header != "date|symbol|shortvolume|shortexemptvolume|totalvolume|market":
        return []
    records = lines[1:-1]
    if lines[-1].strip() != str(len(records)):
        return []

    trade_date = expected_date.strftime("%Y%m%d")
    rows: List[Dict[str, Any]] = []
    seen = set()
    for line in records:
        parts = line.split("|")
        if len(parts) != 6 or parts[0] != trade_date:
            return []
        # FINRA can publish separate symbols that differ only by the case of a suffix.
        sym = parts[1].strip()
        if not sym or sym in seen:
            return []
        try:
            short_volume, short_exempt, total_volume = (float(value) for value in parts[2:5])
        except ValueError:
            return []
        if not math.isfinite(total_volume) or not 0 <= short_exempt <= short_volume <= total_volume or total_volume == 0:
            return []
        seen.add(sym)
        rows.append({
            "symbol": sym,
            "short_volume": short_volume,
            "short_exempt": short_exempt,
            "total_volume": total_volume,
            "market": parts[5].strip(),
        })
    return rows


def gather(cfg: Dict[str, Any], *, today: dt.date | None = None) -> Dict[str, Any]:
    """Collect the most recent published FINRA daily short-volume files.

    Returns up to `trend_days` distinct trading days (newest first) so compute can build
    both the latest-day boards and a multi-day short-pressure trend. The newest day's rows
    are also exposed as `reg_sho_rows` for backward compatibility.
    """
    tmpl = cfg["finra_daily_url"]
    lookback = int(cfg.get("max_lookback_days", 6))
    want_days = int(cfg.get("trend_days", 5))
    today = today or dt.datetime.now(dt.timezone.utc).date()

    days: List[Dict[str, Any]] = []
    i = 0
    # Walk back far enough to collect `want_days` published files (plus slack for holidays).
    while len(days) < want_days and i <= lookback + want_days + 5:
        if not days and i > lookback:
            break
        d = today - dt.timedelta(days=i)
        i += 1
        if d.weekday() >= 5:  # skip Sat/Sun
            continue
        text = _fetch(tmpl.format(date=d.strftime("%Y%m%d")))
        if not text:
            continue
        rows = parse_regsho(text, d)
        if rows:
            days.append({"date": d.isoformat(), "rows": rows})

    if not days:
        return {"reg_sho_rows": [], "days": [], "as_of": None, "si_map": {}}
    return {"reg_sho_rows": days[0]["rows"], "days": days, "as_of": days[0]["date"], "si_map": {}}
