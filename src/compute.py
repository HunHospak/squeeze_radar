"""Pure computation for squeeze_radar. No I/O, fully unit-testable.

From one day of FINRA consolidated short-volume rows we derive three honest boards:
  - squeeze_score        : composite 0-100 (percentile blend of short ratio + short volume)
  - short_volume_ratio   : short volume / total volume, today's short-selling pressure
  - largest_short_volume : absolute short volume leaders (crowdedness)

True bi-monthly short interest %, days-to-cover and off-exchange share are reserved for a
later revision (they need the FINRA short-interest feed + a float source); the envelope
carries empty `most_shorted`/`off_exchange` arrays until then so consumers stay forward-compatible.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _percentiles(values: List[float]) -> List[float]:
    """Map each value to its 0-100 percentile rank (ties share the lower rank position)."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [100.0]
    order = sorted(range(n), key=lambda i: values[i])
    pct = [0.0] * n
    for rank, i in enumerate(order):
        pct[i] = 100.0 * rank / (n - 1)
    return pct


def build_boards(raw: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    rows = raw.get("reg_sho_rows") or []
    si_map = raw.get("si_map") or {}
    floor = float(cfg.get("min_total_volume", 0))
    top_n = int(cfg.get("top_n", 25))
    universe = set(str(s).upper() for s in (cfg.get("universe") or []))
    w = cfg.get("weights", {}) or {}
    wr = float(w.get("short_ratio", 1.0))
    wv = float(w.get("short_volume_magnitude", 0.6))

    items: List[Dict[str, Any]] = []
    for r in rows:
        if r["total_volume"] < floor:
            continue
        if universe and r["symbol"] not in universe:
            continue
        ratio = r["short_volume"] / r["total_volume"]
        items.append({
            "ticker": r["symbol"],
            "short_volume": r["short_volume"],
            "total_volume": r["total_volume"],
            "short_ratio": ratio,
        })

    if not items:
        return {
            "as_of": raw.get("as_of"),
            "universe_size": 0,
            "squeeze_score": [], "short_volume_ratio": [], "largest_short_volume": [],
            "most_shorted": [], "off_exchange": [], "by_ticker": {},
            "_status": "unavailable",
            "_notes": "No FINRA short-volume rows above the liquidity floor.",
        }

    ratio_pct = _percentiles([it["short_ratio"] for it in items])
    vol_pct = _percentiles([it["short_volume"] for it in items])
    for i, it in enumerate(items):
        it["squeeze_score"] = round((wr * ratio_pct[i] + wv * vol_pct[i]) / (wr + wv), 1)
        it["short_ratio_pct"] = round(it["short_ratio"] * 100, 1)

    squeeze = sorted(items, key=lambda x: -x["squeeze_score"])[:top_n]
    squeeze_out = [
        {"ticker": x["ticker"], "score": x["squeeze_score"], "short_ratio_pct": x["short_ratio_pct"]}
        for x in squeeze
    ]

    ratio_board = sorted(items, key=lambda x: -x["short_ratio"])[:top_n]
    ratio_out = [{"ticker": x["ticker"], "ratio_pct": x["short_ratio_pct"]} for x in ratio_board]

    largest = sorted(items, key=lambda x: -x["short_volume"])[:top_n]
    largest_out = [
        {"ticker": x["ticker"], "short_volume": round(x["short_volume"]),
         "short_volume_m": round(x["short_volume"] / 1e6, 2)}
        for x in largest
    ]

    by_ticker = {
        x["ticker"]: {"squeeze_score": x["squeeze_score"], "short_ratio_pct": x["short_ratio_pct"]}
        for x in items
    }

    return {
        "as_of": raw.get("as_of"),
        "universe_size": len(items),
        "squeeze_score": squeeze_out,
        "short_volume_ratio": ratio_out,
        "largest_short_volume": largest_out,
        "most_shorted": [],     # reserved: needs bi-monthly FINRA short interest
        "off_exchange": [],     # reserved: needs consolidated market volume
        "by_ticker": by_ticker,
        "_status": "active",
        "_notes": "Derived from FINRA daily consolidated short-sale volume. Bi-monthly short interest % and off-exchange share are planned additions.",
    }
