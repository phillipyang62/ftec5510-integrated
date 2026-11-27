"""Classroom spot quotes using the team's MDGatewaySimulator price dynamics.

Initial prices, ticks and noise are simulation parameters, not current market data.
USDC and RLUSD reference legs revert toward a simulated 1.0000 USDT peg.
"""

from decimal import Decimal, ROUND_HALF_UP
from random import Random


SIMULATOR_NAME = "MDGateway simulator"
SIMULATOR_INTERVAL = 2
TICK = Decimal("0.01")

# Base -> (initial USDT price, quote tick, per-step Gaussian noise).
ASSET_CONFIGS = {
    "XRP": (2.2, Decimal("0.0001"), 0.0005),
    "ADA": (0.6, Decimal("0.0001"), 0.0002),
    "LINK": (15.0, Decimal("0.001"), 0.01),
    "SOL": (182.0, Decimal("0.01"), 0.08),
    "AVAX": (25.0, Decimal("0.001"), 0.02),
    "DOGE": (0.15, Decimal("0.00001"), 0.0001),
    "USDC": (0.9998, Decimal("0.0001"), 0.0003),
    "RLUSD": (0.9998, Decimal("0.0001"), 0.0003),
}
SIMULATED_BASES = frozenset({"BTC", "ETH", *ASSET_CONFIGS})
STABLECOIN_BASES = frozenset({"USDC", "RLUSD"})
STABLECOIN_PEG = 1.0000
STABLECOIN_REVERSION = 0.90
PRICE_TICKS = {"BTC": TICK, "ETH": TICK, **{base: tick for base, (_, tick, _) in ASSET_CONFIGS.items()}}
_ADDITIONAL_PAIRS = tuple(f"{base}/USDT" for base in ASSET_CONFIGS)
SIMULATED_SOURCES = {
    "demo:MDGateway:HashKey": ("BTC/USD", "BTC/USDT", "BTC/HKD", "ETH/USD", "ETH/USDT", *_ADDITIONAL_PAIRS),
    "demo:MDGateway:OSL": ("BTC/USD", "BTC/USDT", "ETH/USD", "ETH/USDT", *_ADDITIONAL_PAIRS),
}

PRICE_GROUPS = (
    (
        ("BTC/USD", "HashKey", 75000.0, 1.0, 0.0, 0.1),
        ("BTC/USD", "OSL", 75001.0, 1.0, 0.9, 0.12),
        ("BTC/USDT", "HashKey", 74998.0, 1.0, 0.9, 0.15),
        ("BTC/USDT", "OSL", 74996.0, 1.0, 0.9, 0.18),
        ("BTC/HKD", "HashKey", 585000.0, 7.8, 0.8, 0.20),
    ),
    (
        ("ETH/USD", "HashKey", 2150.0, 1.0, 0.0, 0.3),
        ("ETH/USD", "OSL", 2155.0, 1.0, 0.75, 0.20),
    ),
    *(
        (
            (f"{base}/USDT", "HashKey", price, 1.0, 0.0, sigma),
            (f"{base}/USDT", "OSL", price + 2 * float(tick), 1.0, 0.75, sigma),
        )
        for base, (price, tick, sigma) in ASSET_CONFIGS.items()
        if base not in STABLECOIN_BASES
    ),
    *(
        (
            (f"{base}/USDT", "HashKey", price, 1.0, 0.0, sigma),
            (f"{base}/USDT", "OSL", 1.0001, 1.0, 0.50, 0.0004),
        )
        for base, (price, _, sigma) in ASSET_CONFIGS.items()
        if base in STABLECOIN_BASES
    ),
)


class SimulatedMarket:
    def __init__(self, rng=None):
        self.rng = rng if rng is not None else Random()
        self.prices = {(symbol, venue): price for group in PRICE_GROUPS for symbol, venue, price, *_ in group}

    def step(self):
        quotes = []
        for group in PRICE_GROUPS:
            symbol, venue, _, _, _, sigma = group[0]
            change = self.rng.gauss(0.0, sigma)
            if symbol.split("/")[0] in STABLECOIN_BASES:
                change += STABLECOIN_REVERSION * (STABLECOIN_PEG - self.prices[symbol, venue])
            self.prices[symbol, venue] += change
            reference = self.prices[symbol, venue]
            for symbol, venue, _, fx_ratio, theta, sigma in group[1:]:
                current = self.prices[symbol, venue]
                change = theta * (reference - current / fx_ratio) + self.rng.gauss(0.0, sigma)
                self.prices[symbol, venue] = current + change * fx_ratio
        for (symbol, venue), raw_price in self.prices.items():
            tick = PRICE_TICKS[symbol.split("/")[0]]
            price = max(2 * tick, Decimal(str(raw_price)).quantize(tick, rounding=ROUND_HALF_UP))
            source = f"demo:MDGateway:{venue}"
            quotes.append((symbol, source, price, price - tick, price + tick))
            if symbol == "ETH/USD":
                quotes.append(("ETH/USDT", source, price, price - tick, price + tick))
        return quotes
