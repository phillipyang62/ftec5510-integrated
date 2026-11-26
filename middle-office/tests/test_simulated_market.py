from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest

from middle_office.public_market import EXCHANGE_MARKETS, PROVIDER_MARKETS, PublicMarketFeed
from middle_office.service import MiddleOffice
from middle_office.simulated_market import SIMULATED_SOURCES, SIMULATOR_NAME, SimulatedMarket
from middle_office.validation import BusinessError, iso


class SimulatedMarketTests(unittest.TestCase):
    def test_ported_price_groups_and_quote_ticks(self):
        rng = Random(19)
        expected_btc = 75000.0 + rng.gauss(0.0, 0.1)
        expected_osl = 75001.0 + 0.9 * (expected_btc - 75001.0) + rng.gauss(0.0, 0.12)
        simulator = SimulatedMarket(Random(19))
        first = {(symbol, source): (price, bid, ask) for symbol, source, price, bid, ask in simulator.step()}
        self.assertEqual(set(first), {(symbol, source) for source, symbols in SIMULATED_SOURCES.items()
                                      for symbol in symbols})
        self.assertEqual(first["BTC/USD", "demo:MDGateway:HashKey"][0], Decimal(f"{expected_btc:.2f}"))
        self.assertEqual(first["BTC/USD", "demo:MDGateway:OSL"][0], Decimal(f"{expected_osl:.2f}"))
        for price, bid, ask in first.values():
            self.assertEqual((price - bid, ask - price), (Decimal("0.01"), Decimal("0.01")))
        for source in SIMULATED_SOURCES:
            self.assertEqual(first["ETH/USD", source], first["ETH/USDT", source])
        second = {(symbol, source): price for symbol, source, price, _, _ in simulator.step()}
        self.assertNotEqual(second["BTC/USD", "demo:MDGateway:HashKey"],
                            first["BTC/USD", "demo:MDGateway:HashKey"][0])

    def test_old_exchange_quotes_cannot_reach_btc_or_eth_in_mixed_mode(self):
        self.assertFalse(any(symbol.startswith(("BTC/", "ETH/")) for symbols in EXCHANGE_MARKETS.values()
                             for symbol in symbols))
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            office = MiddleOffice(Path(directory) / "ledger.sqlite3", clock=lambda: now, max_quote_age=45,
                                  public_sources=PROVIDER_MARKETS, public_source_pairs=PROVIDER_MARKETS)
            office.ingest_quotes({"quotes": [
                {"symbol": symbol, "source": "Binance", "price": "100", "bid_size": "1", "ask_size": "1",
                 "as_of": iso(now), "timestamp_source": "exchange"}
                for symbol in ("BTC/USDT", "ETH/USDT", "SOL/USDT")
            ]})
            self.assertEqual(office.quotes("BTC/USDT", all_sources=True)["quotes"], [])
            self.assertEqual(office.comparison("BTC/USDT")["quote_mode"], "simulation")
            self.assertEqual(office.comparison("SOL/USDT")["venues"][0]["source"], "Binance")
            self.assertEqual(office.comparison("SOL/USDT")["quote_mode"], "public")
            self.assertEqual(office.market_catalog()["pairs"]["SOL/USDT"], ["Binance", "Kraken", "OKX"])
            feed = PublicMarketFeed(office)
            feed.poll(SIMULATOR_NAME)
            office.create_account("simulation", {})
            for symbol in ("BTC/USDT", "ETH/USDT"):
                comparison = office.comparison(symbol, "0.01")
                self.assertEqual({row["source"] for row in comparison["venues"]}, set(SIMULATED_SOURCES))
                self.assertEqual(comparison["missing_sources"], [])
                terms = {"symbol": symbol, "side": "buy", "quantity": "0.01"}
                self.assertIn(office.preview_order("simulation", terms)["source"], SIMULATED_SOURCES)
                with self.assertRaisesRegex(BusinessError, "no fresh execution quote"):
                    office.preview_order("simulation", {**terms, "source": "Binance"})
            first = office.comparison("ETH/USDT")["venues"][0]["as_of"]
            now += timedelta(seconds=2)
            feed.poll(SIMULATOR_NAME)
            self.assertGreater(office.comparison("ETH/USDT")["venues"][0]["as_of"], first)
