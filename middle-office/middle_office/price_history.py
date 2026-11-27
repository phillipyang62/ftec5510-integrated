"""Bounded, in-memory quote history for charts and recent market trends."""

from datetime import timedelta
from decimal import Decimal
from threading import Lock

from .validation import amount, iso, pair, require, timestamp


CHART_PAIRS = frozenset(("BTC/USDT", "ETH/USDT", "SOL/USDT"))
WINDOW_MINUTES = ("1", "5", "10", "15")
INTERVAL_SECONDS = 10
INTERVAL = timedelta(seconds=INTERVAL_SECONDS)
TREND_WINDOW_SECONDS = 10
PREFERRED_SOURCES = ("demo:MDGateway:HashKey", "demo:HashKey", "Binance")


def bucket_start(at):
    return at.replace(second=at.second // INTERVAL_SECONDS * INTERVAL_SECONDS, microsecond=0)


class PriceHistory:
    def __init__(self, pairs=None):
        self.pairs = CHART_PAIRS if pairs is None else frozenset(pairs)
        require(len(self.pairs) <= 50 and all(pair(symbol) == symbol for symbol in self.pairs),
                "invalid_chart_pairs", "configure at most 50 normalized chart pairs")
        self.lock = Lock()
        self.series = {}
        self.observations = {}

    def record(self, quotes, now):
        cutoff = bucket_start(now) - timedelta(minutes=int(WINDOW_MINUTES[-1])) + INTERVAL
        observation_cutoff = now - timedelta(seconds=TREND_WINDOW_SECONDS)
        with self.lock:
            for key, buckets in list(self.series.items()):
                for start in [start for start in buckets if start < cutoff]:
                    del buckets[start]
                if not buckets:
                    del self.series[key]
            for key, observations in list(self.observations.items()):
                for at in [at for at in observations if at < observation_cutoff]:
                    del observations[at]
                if not observations:
                    del self.observations[key]
            for quote in quotes:
                symbol = quote["symbol"]
                at = timestamp(quote["as_of"])
                price = Decimal(quote["price"])
                if at >= observation_cutoff:
                    observations = self.observations.setdefault((symbol, quote["source"]), {})
                    observations[at] = price
                if symbol not in self.pairs:
                    continue
                start = bucket_start(at)
                if start < cutoff:
                    continue
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

    def trends(self, now, max_quote_age):
        start = now - timedelta(seconds=TREND_WINDOW_SECONDS)
        rows = []
        with self.lock:
            pairs = {}
            for (symbol, source), observations in self.observations.items():
                samples = sorted((at, price) for at, price in observations.items() if start <= at <= now)
                if samples and (now - samples[-1][0]).total_seconds() <= max_quote_age:
                    pairs.setdefault(symbol, {})[source] = samples
            for symbol, sources in sorted(pairs.items()):
                source = max(sources, key=lambda name: (
                    len(sources[name]) >= 2,
                    -PREFERRED_SOURCES.index(name) if name in PREFERRED_SOURCES else -len(PREFERRED_SOURCES),
                    sources[name][-1][0],
                    name,
                ))
                samples = sources[source]
                first_at, opening = samples[0]
                last_at, latest = samples[-1]
                prices = [price for _, price in samples]
                rows.append({
                    "symbol": symbol,
                    "quote_currency": symbol.split("/")[1],
                    "source": source,
                    "quote_mode": "simulation" if source == "demo" or source.startswith("demo:") else "public",
                    "status": "trend" if len(samples) >= 2 else "single_sample",
                    "sample_count": len(samples),
                    "first_as_of": iso(first_at),
                    "last_as_of": iso(last_at),
                    "open": amount(opening),
                    "last": amount(latest),
                    "low": amount(min(prices)),
                    "high": amount(max(prices)),
                    "change_pct": amount((latest - opening) / opening * 100) if len(samples) >= 2 else None,
                })
        return {"as_of": iso(now), "start": iso(start), "window_seconds": TREND_WINDOW_SECONDS,
                "status": "ok" if rows else "empty", "rows": rows}

    def chart(self, symbol, minutes, now, max_quote_age):
        symbol = pair(symbol)
        require(symbol in self.pairs, "invalid_chart_pair", "price chart does not support this pair")
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
