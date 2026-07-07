# squeeze_radar

Independent ArkenLabs satellite service. Publishes a daily short-selling / squeeze-pressure
feed derived from **FINRA consolidated daily short-sale volume** (free, no API key).

It is fully decoupled from the ArkenLabs app: it builds a JSON feed, publishes it to GitHub
Pages, and the app fetches it read-only. If this service is down, the app's `/signals` page
simply shows the short-interest panels as unavailable.

## What it produces

`out/squeeze_radar.json` (ArkenLabs feed envelope), with `data`:

- `squeeze_score` — composite 0-100, percentile blend of short-volume ratio + absolute short volume
- `short_volume_ratio` — short volume / total volume (today's short-selling pressure)
- `largest_short_volume` — absolute short-volume leaders
- `most_shorted`, `off_exchange` — reserved (empty) until bi-monthly FINRA short interest and
  consolidated volume are wired in
- `by_ticker` — per-symbol map for the company page

## Data source

`https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt` — consolidated NMS
short-sale volume, pipe-delimited. The builder walks back a few days to find the latest
published file (weekends/holidays skipped).

## Run locally

```bash
pip install -r requirements.txt
python src/build_feed.py
python scripts/post_text.py
```

## Publish

GitHub Actions (`.github/workflows/publish.yml`) runs weekdays after the US close and on
manual `workflow_dispatch`, publishing `out/` to the `gh-pages` branch. No secrets required.

## Not investment advice

Informational short-selling data from regulatory filings. Not a recommendation.
