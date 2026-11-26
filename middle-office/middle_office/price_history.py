"""Bounded, in-memory quote history for the simulation order chart."""

from datetime import timedelta
from decimal import Decimal
from threading import Lock

from .validation import amount, iso, pair, require, timestamp


CHART_PAIRS = frozenset(("BTC/USDT", "ETH/USDT", "SOL/USDT"))
WINDOW_MINUTES = ("1", "5", "10", "15")
INTERVAL_SECONDS = 10
INTERVAL = timedelta(seconds=INTERVAL_SECONDS)
PREFERRED_SOURCES = ("demo:MDGateway:HashKey", "demo:HashKey", "Binance")


def bucket_start(at):
    return at.replace(second=at.second // INTERVAL_SECONDS * INTERVAL_SECONDS, microsecond=0)


class PriceHistory:
    def __init__(self):
        self.lock = Lock()
        self.series = {}

    def record(self, quotes, now):
        cutoff = bucket_start(now) - timedelta(minutes=int(WINDOW_MINUTES[-1])) + INTERVAL
        with self.lock:
            for key, buckets in list(self.series.items()):
                for start in [start for start in buckets if start < cutoff]:
                    del buckets[start]
                if not buckets:
                    del self.series[key]
            for quote in quotes:
                symbol = quote["symbol"]
                if symbol not in CHART_PAIRS:
                    continue
                at = timestamp(quote["as_of"])
                start = bucket_start(at)
                if start < cutoff:
                    continue
                price = Decimal(quote["price"])
                buckets = self.series.setdefault((symbol, quote["source"]), {})
                candle = buckets.get(start)
                if candle is None:
                    buckets[start] = {"first": at, "last": at, "open": price, "high": price,
                                      "low": price, "close": price}
                    continue
                if at < candle["first"]:
                    candle.update(first=at, open=price)
                if at > candle["last"]:
                    candle.update(last=at, close=price)
                candle["high"] = max(candle["high"], price)
                candle["low"] = min(candle["low"], price)

    def chart(self, symbol, minutes, now, max_quote_age):
        symbol = pair(symbol)
        require(symbol in CHART_PAIRS, "invalid_chart_pair", "price chart only supports BTC, ETH and SOL / USDT")
        require(minutes in WINDOW_MINUTES, "invalid_chart_range", "minutes must be 1, 5, 10 or 15")
        end = bucket_start(now) + INTERVAL
        start = end - timedelta(minutes=int(minutes))
        with self.lock:
            candidates = {}
            for (series_symbol, source), buckets in self.series.items():
                if series_symbol != symbol:
                    continue
                rows = sorted((at, candle) for at, candle in buckets.items()
                              if start <= at < end and candle["last"] <= now)
                if rows:
                    candidates[source] = rows
            fresh = [source for source, rows in candidates.items()
                     if (now - rows[-1][1]["last"]).total_seconds() <= max_quote_age]
            available = fresh or list(candidates)
            source = next((name for name in PREFERRED_SOURCES if name in available), None)
            if source is None and available:
                source = max(available, key=lambda name: (candidates[name][-1][1]["last"], name))
            rows = candidates.get(source, [])
            candles = [{"start": iso(at), **{field: amount(candle[field])
                                           for field in ("open", "high", "low", "close")}}
                       for at, candle in rows]
            last = iso(rows[-1][1]["last"]) if rows else None
        return {"symbol": symbol, "quote_currency": symbol.split("/")[1], "minutes": int(minutes),
                "interval_seconds": INTERVAL_SECONDS, "start": iso(start), "end": iso(end),
                "source": source, "simulated": bool(source and source.startswith("demo:")),
                "as_of": last, "status": "live" if fresh else "stale" if rows else "empty",
                "candles": candles}
