from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from middle_office.public_market import PROVIDER_MARKETS
from middle_office.server import Handler
from middle_office.service import MiddleOffice
from middle_office.validation import BusinessError, iso


class MarketTrendsTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
        self.office = MiddleOffice(Path(directory.name) / "ledger.sqlite3", clock=lambda: self.now)

    def ingest(self, symbol, source, seconds_ago, price):
        return self.office.ingest_quotes({"quotes": [{
            "symbol": symbol, "source": source, "price": price,
            "as_of": iso(self.now - timedelta(seconds=seconds_ago)), "timestamp_source": "exchange",
        }]})

    def test_all_pairs_are_observed_without_changing_supported_candle_pairs(self):
        self.ingest("DOT/USDT", "Binance", 10, "4")
        self.ingest("DOT/USDT", "Binance", 0, "5")
        self.ingest("DOT/USD", "Kraken", 1, "5.1")

        result = self.office.market_trends()

        self.assertEqual(result["window_seconds"], 10)
        self.assertEqual(result["start"], iso(self.now - timedelta(seconds=10)))
        self.assertEqual(result["as_of"], iso(self.now))
        self.assertEqual(result["status"], "ok")
        self.assertEqual([row["symbol"] for row in result["rows"]], ["DOT/USD", "DOT/USDT"])
        self.assertEqual(result["rows"][1], {
            "symbol": "DOT/USDT", "source": "Binance", "quote_currency": "USDT",
            "quote_mode": "public", "status": "trend", "sample_count": 2,
            "first_as_of": iso(self.now - timedelta(seconds=10)), "last_as_of": iso(self.now),
            "open": "4", "last": "5", "low": "4", "high": "5", "change_pct": "25",
        })
        self.assertEqual(result["rows"][0]["status"], "single_sample")
        self.assertIsNone(result["rows"][0]["change_pct"])
        with self.assertRaises(BusinessError):
            self.office.price_chart("DOT/USDT")

    def test_prefers_a_real_series_over_a_single_preferred_source_without_mixing_venues(self):
        self.ingest("DOT/USDT", "Binance", 1, "999")
        self.ingest("DOT/USDT", "Kraken", 8, "100")
        self.ingest("DOT/USDT", "Kraken", 4, "90")
        self.ingest("DOT/USDT", "Kraken", 2, "110")

        row, = self.office.market_trends()["rows"]

        self.assertEqual(row["source"], "Kraken")
        self.assertEqual(row["sample_count"], 3)
        self.assertEqual((row["open"], row["last"], row["low"], row["high"]), ("100", "110", "90", "110"))
        self.assertEqual(row["change_pct"], "10")

    def test_latest_source_must_be_fresh_then_preferred_source_breaks_series_ties(self):
        self.office.max_quote_age = 3
        self.ingest("DOT/USDT", "Binance", 10, "100")
        self.ingest("DOT/USDT", "Binance", 8, "110")
        self.ingest("DOT/USDT", "OKX", 4, "80")
        self.ingest("DOT/USDT", "OKX", 2, "88")
        self.ingest("DOT/USDT", "Kraken", 0, "999")

        self.assertEqual(self.office.market_trends()["rows"][0]["source"], "OKX")

        self.ingest("DOT/USDT", "Binance", 1, "120")
        row, = self.office.market_trends()["rows"]
        self.assertEqual(row["source"], "Binance")
        self.assertEqual(row["sample_count"], 3)
        self.assertEqual(row["change_pct"], "20")

    def test_window_is_inclusive_and_excludes_future_and_duplicate_observations(self):
        self.ingest("DOT/USDT", "Binance", 10.000001, "99")
        self.ingest("DOT/USDT", "Binance", 10, "100")
        self.ingest("DOT/USDT", "Binance", 0, "110")
        self.assertEqual(self.ingest("DOT/USDT", "Binance", 0, "999")["ignored"], 1)
        self.ingest("DOT/USDT", "Binance", -1, "999")
        self.ingest("LTC/USDT", "OKX", -1, "100")

        row, = self.office.market_trends()["rows"]

        self.assertEqual(row["sample_count"], 2)
        self.assertEqual(row["change_pct"], "10")
        self.assertEqual(row["last_as_of"], iso(self.now))
        self.now += timedelta(seconds=11.000001)
        self.assertEqual(self.office.market_trends()["status"], "empty")

    def test_single_fixed_quote_does_not_become_a_trend_on_repeated_reads(self):
        self.ingest("BTC/USDT", "demo:HashKey", 0, "68000")
        for _ in range(2):
            row, = self.office.market_trends()["rows"]
            self.assertEqual(row["quote_mode"], "simulation")
            self.assertEqual(row["sample_count"], 1)
            self.assertEqual(row["status"], "single_sample")
            self.assertIsNone(row["change_pct"])
        self.now += timedelta(seconds=10.000001)
        self.assertEqual(self.office.market_trends()["rows"], [])

    def test_legacy_demo_source_keeps_simulation_provenance(self):
        self.ingest("ETH/USDT", "demo", 2, "3500")
        self.ingest("ETH/USDT", "demo", 0, "3501")
        row, = self.office.market_trends()["rows"]
        self.assertEqual((row["source"], row["quote_mode"], row["status"]), ("demo", "simulation", "trend"))

    def test_mixed_mode_only_uses_visible_sources_and_keeps_provenance(self):
        self.office = MiddleOffice(self.office.store.path, clock=lambda: self.now,
                                   public_sources=PROVIDER_MARKETS, public_source_pairs=PROVIDER_MARKETS)
        self.ingest("BTC/USDT", "Binance", 1, "999")
        self.ingest("BTC/USDT", "demo:MDGateway:HashKey", 1, "75000")
        self.ingest("SOL/USDT", "Binance", 1, "182")
        self.ingest("SOL/USDT", "demo:MDGateway:HashKey", 1, "181")
        self.ingest("DOT/USDT", "Binance", 1, "4")
        rows = self.office.market_trends()["rows"]
        self.assertEqual([(row["symbol"], row["source"], row["quote_mode"]) for row in rows], [
            ("BTC/USDT", "demo:MDGateway:HashKey", "simulation"),
            ("DOT/USDT", "Binance", "public"),
            ("SOL/USDT", "demo:MDGateway:HashKey", "simulation"),
        ])

    def test_read_token_allows_only_get_and_missing_credentials_fail(self):
        handler = object.__new__(Handler)
        handler.server = SimpleNamespace(token="operator", read_token="reader", office=self.office)
        handler.path = "/api/market/trends"
        handler.command = "GET"
        handler.headers = {"Authorization": "Bearer reader"}
        status, result = handler._dispatch()
        self.assertEqual((status, result["status"]), (200, "empty"))

        handler.command = "POST"
        with self.assertRaises(BusinessError) as error:
            handler._dispatch()
        self.assertEqual(error.exception.status, 403)

        handler.command = "GET"
        handler.headers = {}
        with self.assertRaises(BusinessError) as error:
            handler._dispatch()
        self.assertEqual(error.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
