"""BTC and ETH quote model adapted from the team's MDGatewaySimulator."""

from decimal import Decimal, ROUND_HALF_UP
from random import Random


SIMULATED_SOURCES = {
    "demo:MDGateway:HashKey": ("BTC/USD", "BTC/USDT", "BTC/HKD", "ETH/USD", "ETH/USDT"),
    "demo:MDGateway:OSL": ("BTC/USD", "BTC/USDT", "ETH/USD", "ETH/USDT"),
}
SIMULATOR_NAME = "MDGateway simulator"
SIMULATOR_INTERVAL = 2
TICK = Decimal("0.01")

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
)


class SimulatedMarket:
    def __init__(self, rng=None):
        self.rng = rng if rng is not None else Random()
        self.prices = {(symbol, venue): price for group in PRICE_GROUPS for symbol, venue, price, *_ in group}

    def step(self):
        quotes = []
        for group in PRICE_GROUPS:
            symbol, venue, _, _, _, sigma = group[0]
            self.prices[symbol, venue] += self.rng.gauss(0.0, sigma)
            reference = self.prices[symbol, venue]
            for symbol, venue, _, fx_ratio, theta, sigma in group[1:]:
                current = self.prices[symbol, venue]
                change = theta * (reference - current / fx_ratio) + self.rng.gauss(0.0, sigma)
                self.prices[symbol, venue] = current + change * fx_ratio
        for (symbol, venue), raw_price in self.prices.items():
            price = max(2 * TICK, Decimal(str(raw_price)).quantize(TICK, rounding=ROUND_HALF_UP))
            source = f"demo:MDGateway:{venue}"
            quotes.append((symbol, source, price, price - TICK, price + TICK))
            if symbol == "ETH/USD":
                quotes.append(("ETH/USDT", source, price, price - TICK, price + TICK))
        return quotes
