import datetime as dt
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import build_feed
import providers
from compute import _percentiles


HEADER = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market"
RUN_TIME = dt.datetime(2026, 11, 23, 22, tzinfo=dt.timezone.utc)


def daily_file(day):
    return f"{HEADER}\n{day}|AAA|200000.25|0|500000|N,Q\n1\n"


class FinraIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            **build_feed.load_config(), "finra_daily_url": "https://example/{date}",
            "trend_days": 2, "max_lookback_days": 6,
        }

    def test_complete_file_accepts_fractional_volumes(self):
        rows = providers.parse_regsho(daily_file("20261123"), RUN_TIME.date())
        self.assertEqual(rows[0]["short_volume"], 200000.25)

    def test_mixed_case_finra_symbols_do_not_collide(self):
        file = f"{HEADER}\n20261123|ABCD|20|0|50|N\n20261123|ABCd|30|0|60|N\n2\n"
        rows = providers.parse_regsho(file, RUN_TIME.date())
        self.assertEqual([row["symbol"] for row in rows], ["ABCD", "ABCd"])

    def test_invalid_dates_trailers_duplicates_and_volumes_reject_file(self):
        good = daily_file("20261123")
        samples = [
            daily_file("20261120"),
            good.replace("\n1\n", "\n2\n"),
            good.replace("\n1\n", "\n20261123|AAA|200000|0|500000|N\n2\n"),
            good.replace("200000.25", "nan"),
            good.replace("200000.25", "500001"),
            good.replace("|0|", "|-5|"),
            good.replace(HEADER, "<html>"),
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(providers.parse_regsho(sample, RUN_TIME.date()), [])

    def test_partial_history_uses_actual_date_when_newest_file_is_invalid(self):
        files = {
            "20261123": daily_file("20261120"),
            "20261120": daily_file("20261120"),
        }
        with patch.object(providers, "_fetch", side_effect=lambda url: files.get(url.rsplit("/", 1)[-1])):
            feed = build_feed.build(self.cfg, generated_at=RUN_TIME)
        self.assertEqual(feed["status"], "partial")
        self.assertEqual(feed["data"]["as_of"], "2026-11-20")
        self.assertIn("Only 1 of 2", feed["notes"])

    def test_expired_file_is_not_used_even_when_trend_history_search_is_longer(self):
        with patch.object(providers, "_fetch", side_effect=lambda url: daily_file("20261116") if url.endswith("20261116") else None) as fetch:
            feed = build_feed.build(self.cfg, generated_at=RUN_TIME)
        self.assertEqual(feed["status"], "unavailable")
        self.assertIsNone(feed["data"]["as_of"])
        self.assertNotIn(call("https://example/20261116"), fetch.call_args_list)

    def test_older_acceptable_files_mark_full_trend_partial(self):
        dates = {"20261119", "20261118"}

        def fetch(url):
            day = url.rsplit("/", 1)[-1]
            return daily_file(day) if day in dates else None

        with patch.object(providers, "_fetch", side_effect=fetch):
            feed = build_feed.build(self.cfg, generated_at=RUN_TIME)
        self.assertEqual(feed["status"], "partial")
        self.assertEqual(feed["data"]["trend_days"], 2)
        self.assertIn("2026-11-19", feed["notes"])

    def test_ties_share_the_lower_rank(self):
        self.assertEqual(_percentiles([7, 3, 7, 3, 10]), [50.0, 0.0, 50.0, 0.0, 100.0])

    def test_entrypoint_writes_unavailable_feed_when_no_file_is_usable(self):
        schema = build_feed.load_schema()
        with (
            TemporaryDirectory() as directory,
            patch.object(build_feed, "ROOT", Path(directory)),
            patch.object(build_feed, "load_config", return_value=self.cfg),
            patch.object(build_feed, "load_schema", return_value=schema),
            patch.object(providers, "_fetch", return_value=None),
        ):
            build_feed.main()
            out = Path(directory) / "out"
            feed = json.loads((out / "squeeze_radar.json").read_bytes())
            self.assertEqual(feed["status"], "unavailable")
            self.assertEqual(list((out / "history").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
