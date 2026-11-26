from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from middle_office.public_market import PROVIDER_MARKETS
from middle_office.service import MiddleOffice
from middle_office.validation import iso


class PriceHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.start = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
        self.now = self.start + timedelta(seconds=909)
        self.office = MiddleOffice(Path(directory.name) / "ledger.sqlite3", clock=lambda: self.now,
                                   max_quote_age=45, public_sources=PROVIDER_MARKETS,
                                   public_source_pairs=PROVIDER_MARKETS)

    def ingest(self, symbol, source, second, price):
        return self.office.ingest_quotes({"quotes": [{
            "symbol": symbol, "source": source, "price": price,
            "as_of": iso(self.start + timedelta(seconds=second)), "timestamp_source": "collected",
        }]})

    def test_aggregates_quote_prices_in_ten_second_candles_and_filters_ranges(self):
        source = "demo:MDGateway:HashKey"
        for second, price in [(20, 94), (320, 95), (620, 97), (850, 96),
                              (901, 100), (904, 103), (906, 99), (908, 102)]:
            self.ingest("BTC/USDT", source, second, price)
        self.assertEqual(self.ingest("BTC/USDT", source, 908, 999)["ignored"], 1)
        self.ingest("BTC/USDT", "demo:MDGateway:OSL", 909, 998)
        self.ingest("BTC/USDT", "Binance", 909, 997)

        for minutes, count in [("1", 2), ("5", 3), ("10", 4), ("15", 5)]:
            with self.subTest(minutes=minutes):
                chart = self.office.price_chart("BTC/USDT", minutes)
                self.assertEqual((chart["interval_seconds"], chart["source"], chart["status"]),
                                 (10, source, "live"))
                self.assertTrue(chart["simulated"])
                self.assertEqual(len(chart["candles"]), count)
                self.assertEqual(chart["candles"][-1], {
                    "start": iso(self.start + timedelta(seconds=900)),
                    "open": "100", "high": "103", "low": "99", "close": "102",
                })

    def test_keeps_pairs_separate_and_uses_fresh_sources(self):
        self.ingest("ETH/USDT", "demo:MDGateway:HashKey", 850, 3800)
        self.ingest("ETH/USDT", "demo:MDGateway:OSL", 908, 3801)
        self.ingest("SOL/USDT", "Binance", 908, 145)
        self.assertEqual(self.office.price_chart("BTC/USDT")["status"], "empty")
        self.assertEqual(self.office.price_chart("ETH/USDT")["source"], "demo:MDGateway:OSL")
        sol = self.office.price_chart("SOL/USDT")
        self.assertEqual(sol["source"], "Binance")
        self.assertFalse(sol["simulated"])
        self.assertEqual(sol["candles"][0]["close"], "145")

        self.now += timedelta(seconds=45)
        self.assertEqual(self.office.price_chart("ETH/USDT", "5")["status"], "stale")
        self.now += timedelta(minutes=15)
        self.assertEqual(self.office.price_chart("ETH/USDT", "15")["candles"], [])
