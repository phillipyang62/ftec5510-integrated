"""Poll public spot tickers. Orders and credentials are outside this feed."""

import json
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from threading import Event, Lock, Thread
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .market import NoRedirect
from .validation import BusinessError, iso


MARKETS = {
    "BTC/USDT": ("Bitcoin", ["比特币", "XBT", "BTCUSDT"]),
    "ETH/USDT": ("Ethereum", ["以太坊", "以太币", "ETHUSDT"]),
    "SOL/USDT": ("Solana", ["索拉纳", "SOLUSDT"]),
}
BINANCE_PAIRS = {symbol.replace("/", ""): symbol for symbol in MARKETS}
OKX_PAIRS = {symbol.replace("/", "-"): symbol for symbol in MARKETS}
KRAKEN_PAIRS = {"XBTUSDT": "BTC/USDT", "ETHUSDT": "ETH/USDT", "SOLUSDT": "SOL/USDT"}
BINANCE_QUERY = urlencode({"symbols": json.dumps(list(BINANCE_PAIRS), separators=(",", ":"))})
KRAKEN_QUERY = urlencode({"pair": ",".join(KRAKEN_PAIRS)})
LOG = logging.getLogger(__name__)
MAX_BYTES = 1024 * 1024
QUOTE_MAX_AGE = 45


def _from_milliseconds(value):
    return datetime.fromtimestamp(int(value) / 1000, timezone.utc)


def _quote(symbol, venue, price, bid, ask, bid_size, ask_size, at, timestamp_source):
    name, aliases = MARKETS[symbol]
    return {"symbol": symbol, "source": venue, "price": price, "bid": bid, "ask": ask,
            "bid_size": bid_size, "ask_size": ask_size, "as_of": iso(at), "timestamp_source": timestamp_source,
            "fee_rate": None, "name": name, "aliases": aliases}


def _binance(payload, received):
    return [_quote(BINANCE_PAIRS[row["symbol"]], "Binance", row["lastPrice"], row["bidPrice"], row["askPrice"],
                   row["bidQty"], row["askQty"], _from_milliseconds(row["closeTime"]), "exchange")
            for row in payload if row["symbol"] in BINANCE_PAIRS]


def _okx(payload, received):
    if payload["code"] != "0":
        raise ValueError("OKX did not return its spot tickers")
    return [_quote(OKX_PAIRS[row["instId"]], "OKX", row["last"], row["bidPx"], row["askPx"],
                   row["bidSz"], row["askSz"], _from_milliseconds(row["ts"]), "exchange")
            for row in payload["data"] if row["instId"] in OKX_PAIRS]


def _kraken(payload, received):
    if payload["error"]:
        raise ValueError("Kraken did not return its spot tickers")
    # The ticker carries prices and sizes, but omits a per-pair timestamp.
    return [_quote(KRAKEN_PAIRS[key], "Kraken", row["c"][0], row["b"][0], row["a"][0],
                   row["b"][2], row["a"][2], received, "collected")
            for key, row in payload["result"].items() if key in KRAKEN_PAIRS]


PROVIDERS = {
    "Binance": ("https://data-api.binance.vision/api/v3/ticker/24hr?" + BINANCE_QUERY, _binance),
    "OKX": ("https://www.okx.com/api/v5/market/tickers?instType=SPOT", _okx),
    "Kraken": ("https://api.kraken.com/0/public/Ticker?" + KRAKEN_QUERY, _kraken),
}


def _fetch(url):
    request = Request(url, headers={"Accept": "application/json", "Cache-Control": "no-cache",
                                    "User-Agent": "HarborInvest-Classroom/1.0"})
    with build_opener(NoRedirect).open(request, timeout=5) as response:
        raw = response.read(MAX_BYTES + 1)
        age = int(response.headers.get("Age", "0"))
        response_date = response.headers.get("Date")
    if len(raw) > MAX_BYTES or age > QUOTE_MAX_AGE:
        raise ValueError("Ticker response is oversized or already stale")
    received = datetime.now(timezone.utc)
    if response_date:
        # Prefer an earlier HTTP snapshot time so a cached response never looks newer.
        received = min(received, parsedate_to_datetime(response_date).astimezone(timezone.utc))
    return json.loads(raw), received


class PublicMarketFeed:
    def __init__(self, office, *, interval=10, fetch=_fetch):
        self.office = office
        self.interval = max(10, interval)
        self.fetch = fetch
        self.stop_event = Event()
        self.lock = Lock()
        self.status = {name: {"state": "starting"} for name in PROVIDERS}
        self.threads = [Thread(target=self._run, args=(name,), daemon=True) for name in PROVIDERS]

    def snapshot(self):
        with self.lock:
            return self.status.copy()

    def poll(self, name):
        url, decode = PROVIDERS[name]
        payload, received = self.fetch(url)
        quotes = decode(payload, received)
        statuses = {row["symbol"] for row in quotes if self.office._fresh(row)}
        if not statuses:
            raise ValueError("No current tracked quotes")
        self.office.ingest_quotes({"quotes": quotes})
        return sorted(statuses)

    def _run(self, name):
        failures = 0
        while not self.stop_event.is_set():
            try:
                pairs = self.poll(name)
                result = {"state": "ok" if len(pairs) == len(MARKETS) else "partial", "pairs": pairs}
                failures = 0
            except (OSError, HTTPException, ValueError, OverflowError, KeyError, TypeError, IndexError,
                    RecursionError, BusinessError) as error:
                LOG.warning("Public market feed %s unavailable (%s)", name, type(error).__name__)
                result = {"state": "unavailable"}
                failures += 1
            with self.lock:
                self.status[name] = {**result, "checked_at": iso(datetime.now(timezone.utc))}
            delay = min(120, self.interval * 2 ** min(failures, 4))
            self.stop_event.wait(delay)

    def start(self):
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=6)
