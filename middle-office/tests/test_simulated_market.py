from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest

from middle_office.public_market import EXCHANGE_MARKETS, PROVIDER_MARKETS, PublicMarketFeed
from middle_office.service import MiddleOffice
from middle_office.simulated_market import (
    ASSET_CONFIGS, PRICE_TICKS, SIMULATED_BASES, SIMULATED_SOURCES, SIMULATOR_NAME,
    STABLECOIN_BASES, SimulatedMarket,
)
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
        self.assertEqual(len(first), 25)
        self.assertEqual([len(symbols) for symbols in SIMULATED_SOURCES.values()], [13, 12])
        self.assertEqual(SIMULATED_BASES, {"BTC", "ETH", "XRP", "ADA", "LINK", "SOL", "AVAX", "DOGE", "USDC", "RLUSD"})
        self.assertEqual(first["BTC/USD", "demo:MDGateway:HashKey"][0], Decimal(f"{expected_btc:.2f}"))
        self.assertEqual(first["BTC/USD", "demo:MDGateway:OSL"][0], Decimal(f"{expected_osl:.2f}"))
        for (symbol, _), (price, bid, ask) in first.items():
            tick = PRICE_TICKS[symbol.split("/")[0]]
            self.assertEqual((price - bid, ask - price), (tick, tick))
            self.assertEqual(price % tick, 0)
            self.assertGreater(bid, 0)
        for source in SIMULATED_SOURCES:
            self.assertEqual(first["ETH/USD", source], first["ETH/USDT", source])
        second = {(symbol, source): price for symbol, source, price, _, _ in simulator.step()}
        self.assertNotEqual(second["BTC/USD", "demo:MDGateway:HashKey"],
                            first["BTC/USD", "demo:MDGateway:HashKey"][0])

    def test_additional_groups_use_classroom_starting_values_and_small_ticks(self):
        class ZeroNoise:
            def gauss(self, mean, sigma):
                return 0.0

        simulator = SimulatedMarket(ZeroNoise())
        quotes = {(symbol, source): price for symbol, source, price, _, _ in simulator.step()}
        for base, (price, tick, _) in ASSET_CONFIGS.items():
            if base in STABLECOIN_BASES:
                continue
            self.assertEqual(quotes[f"{base}/USDT", "demo:MDGateway:HashKey"], Decimal(str(price)))
            self.assertLessEqual(abs(quotes[f"{base}/USDT", "demo:MDGateway:OSL"] - Decimal(str(price))), tick)

    def test_stablecoin_initial_prices_ticks_and_per_venue_noise_parameters(self):
        class RecordedZeroNoise:
            def __init__(self):
                self.calls = []

            def gauss(self, mean, sigma):
                self.calls.append((mean, sigma))
                return 0.0

        noise = RecordedZeroNoise()
        simulator = SimulatedMarket(noise)
        for base in STABLECOIN_BASES:
            self.assertEqual(PRICE_TICKS[base], Decimal("0.0001"))
            self.assertEqual(simulator.prices[f"{base}/USDT", "HashKey"], 0.9998)
            self.assertEqual(simulator.prices[f"{base}/USDT", "OSL"], 1.0001)

        simulator.step()

        self.assertEqual(noise.calls.count((0.0, 0.0003)), 2)
        self.assertEqual(noise.calls.count((0.0, 0.0004)), 2)
        for base in STABLECOIN_BASES:
            self.assertAlmostEqual(simulator.prices[f"{base}/USDT", "HashKey"], 0.99998, places=12)
            self.assertAlmostEqual(simulator.prices[f"{base}/USDT", "OSL"], 1.00004, places=12)

    def test_stablecoins_move_at_subcent_precision_and_return_toward_simulated_peg(self):
        class ZeroNoise:
            def gauss(self, mean, sigma):
                return 0.0

        simulator = SimulatedMarket(ZeroNoise())
        simulator.prices["USDC/USDT", "HashKey"] = 1.01
        simulator.prices["RLUSD/USDT", "HashKey"] = 0.99
        for base in STABLECOIN_BASES:
            simulator.prices[f"{base}/USDT", "OSL"] = 1.0
        quotes = {(symbol, source): price for symbol, source, price, _, _ in simulator.step()}
        self.assertEqual(quotes["USDC/USDT", "demo:MDGateway:HashKey"], Decimal("1.0010"))
        self.assertEqual(quotes["RLUSD/USDT", "demo:MDGateway:HashKey"], Decimal("0.9990"))
        self.assertEqual(quotes["USDC/USDT", "demo:MDGateway:OSL"], Decimal("1.0005"))
        self.assertEqual(quotes["RLUSD/USDT", "demo:MDGateway:OSL"], Decimal("0.9995"))

        simulator = SimulatedMarket(Random(19))
        prices = {(base, source): set() for base in STABLECOIN_BASES for source in SIMULATED_SOURCES}
        for _ in range(1000):
            for symbol, source, price, bid, ask in simulator.step():
                base = symbol.split("/")[0]
                if base in STABLECOIN_BASES:
                    prices[base, source].add(price)
                    self.assertTrue(Decimal("0.995") < bid < ask < Decimal("1.005"))
        self.assertTrue(all(len(values) > 2 for values in prices.values()))
        for identity, values in prices.items():
            with self.subTest(pair_and_source=identity):
                self.assertTrue(any(value < Decimal("1.0000") for value in values))
                self.assertTrue(any(value > Decimal("1.0000") for value in values))

    def test_old_exchange_quotes_cannot_reach_simulated_assets_in_mixed_mode(self):
        self.assertFalse(any(symbol.split("/")[0] in SIMULATED_BASES for symbols in EXCHANGE_MARKETS.values()
                             for symbol in symbols))
        with TemporaryDirectory() as directory:
            now = datetime.now(timezone.utc)
            office = MiddleOffice(Path(directory) / "ledger.sqlite3", clock=lambda: now, max_quote_age=45,
                                  public_sources=PROVIDER_MARKETS, public_source_pairs=PROVIDER_MARKETS)
            office.ingest_quotes({"quotes": [
                {"symbol": symbol, "source": "Binance", "price": "100", "bid_size": "1", "ask_size": "1",
                 "as_of": iso(now), "timestamp_source": "exchange"}
                for symbol in (*(f"{base}/USDT" for base in SIMULATED_BASES), "SUI/USDT")
            ]})
            for base in SIMULATED_BASES:
                self.assertEqual(office.quotes(f"{base}/USDT", all_sources=True)["quotes"], [])
                self.assertEqual(office.comparison(f"{base}/USDT")["quote_mode"], "simulation")
            self.assertEqual(office.comparison("SUI/USDT")["venues"][0]["source"], "Binance")
            self.assertEqual(office.comparison("SUI/USDT")["quote_mode"], "public")
            self.assertIn("Binance", office.market_catalog()["pairs"]["SUI/USDT"])
            feed = PublicMarketFeed(office)
            feed.poll(SIMULATOR_NAME)
            office.create_account("simulation", {})
            for symbol in (f"{base}/USDT" for base in SIMULATED_BASES):
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
