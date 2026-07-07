"""Generate a ready-to-post social snippet from the latest feed."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    feed = json.loads((ROOT / "out" / "squeeze_radar.json").read_text(encoding="utf-8"))
    d = feed["data"]
    lines = [f"Squeeze radar — {d.get('as_of', '')}"]
    top = d.get("squeeze_score", [])[:3]
    if top:
        lines.append("Highest short-selling pressure:")
        for x in top:
            lines.append(f"  {x['ticker']}  squeeze {x['score']}/100  (short vol {x['short_ratio_pct']}%)")
    else:
        lines.append("No short-volume data available today.")
    lines.append("From FINRA regulatory data · not investment advice · arkenlabs.eu")
    text = "\n".join(lines)
    (ROOT / "out" / "post.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
