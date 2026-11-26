"""Collect public spot quotes and the team's simulated BTC and ETH quotes."""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from threading import Event, Lock, Thread
from time import monotonic
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .market import NoRedirect
from .simulated_market import SIMULATED_SOURCES, SIMULATOR_INTERVAL, SIMULATOR_NAME, SimulatedMarket
from .validation import BusinessError, amount, iso, number


ASSETS = {
    "BTC": ("Bitcoin", ["比特币", "XBT"]),
    "ETH": ("Ethereum", ["以太坊", "以太币"]),
    "SOL": ("Solana", ["索拉纳"]),
    "XRP": ("XRP", ["瑞波币"]),
    "DOGE": ("Dogecoin", ["狗狗币"]),
    "ADA": ("Cardano", ["艾达币"]),
    "LINK": ("Chainlink", []),
    "AVAX": ("Avalanche", ["雪崩"]),
    "DOT": ("Polkadot", ["波卡"]),
    "LTC": ("Litecoin", ["莱特币"]),
    "USDT": ("Tether", ["泰达币"]),
    "USDC": ("USD Coin", []),
}
USDT_PAIRS = tuple(f"{ticker}/USDT" for ticker in (
    "BTC ETH SOL XRP LINK AVAX ADA DOGE DOT LTC BCH UNI ATOM XLM SUI NEAR APT ETC HBAR TRX "
    "BNB SHIB PEPE FIL ARB OP ICP AAVE INJ POL SEI WLD RENDER ALGO GRT COMP ZEC STX USDC RLUSD USDS"
).split())
KRAKEN_PAIRS = {
    f"{ticker}USDT": f"{ticker}/USDT" for ticker in
    "SOL XRP LINK AVAX ADA DOT LTC BCH ATOM BNB TON SHIB ALGO USDC DAI RLUSD".split()
}
HK_PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD", "BTC/HKD", "ETH/HKD", "LINK/USD", "USDT/USD", "USDT/HKD")
_EXCHANGE_MARKETS = {
    "Binance": (*USDT_PAIRS, "FDUSD/USDT", "TUSD/USDT"),
    "OKX": (*USDT_PAIRS, "TON/USDT", "PYUSD/USDT"),
    "Kraken": tuple(KRAKEN_PAIRS.values()),
    "HashKey": (*HK_PAIRS, "BTC/USDT", "ETH/USDT", "FDUSD/USD", "RLUSD/USD",
                "AAVE/USD", "ARB/USD", "POL/USD", "OP/USD", "LTC/USD", "SUI/USD",
                "APT/USD", "XRP/USD", "AVAX/USD", "DOGE/USD", "UNI/USD"),
    "OSL": (*HK_PAIRS, "SOL/HKD", "RLUSD/HKD", "USDGO/USD", "USDGO/USDT"),
}
EXCHANGE_MARKETS = {
    source: tuple(symbol for symbol in symbols if not symbol.startswith(("BTC/", "ETH/")))
    for source, symbols in _EXCHANGE_MARKETS.items()
}
PROVIDER_MARKETS = {**EXCHANGE_MARKETS, **SIMULATED_SOURCES}
FEED_MARKETS = {**EXCHANGE_MARKETS, SIMULATOR_NAME: frozenset().union(*SIMULATED_SOURCES.values())}
BINANCE_PAIRS = {symbol.replace("/", ""): symbol for symbol in PROVIDER_MARKETS["Binance"]}
OKX_PAIRS = {symbol.replace("/", "-"): symbol for symbol in PROVIDER_MARKETS["OKX"]}
HASHKEY_PAIRS = {symbol.replace("/", ""): symbol for symbol in PROVIDER_MARKETS["HashKey"]}
OSL_PAIRS = {symbol.replace("/", ""): symbol for symbol in PROVIDER_MARKETS["OSL"]}
HASHKEY_BASE = "https://api-pro.hashkey.com/quote/v1/ticker/"
OSL_PUBLIC_STREAM = "wss://stream-hk.osl.com/ws/v5/public"
BINANCE_QUERY = urlencode({"symbols": json.dumps(list(BINANCE_PAIRS), separators=(",", ":"))})
KRAKEN_QUERY = urlencode({"pair": ",".join(KRAKEN_PAIRS)})
LOG = logging.getLogger(__name__)
MAX_BYTES = 1024 * 1024
QUOTE_MAX_AGE = 45


def _from_milliseconds(value):
    return datetime.fromtimestamp(int(value) / 1000, timezone.utc)


def _quote(symbol, venue, price, bid, ask, bid_size, ask_size, at, timestamp_source):
    fields = ("price", "bid", "ask", "bid_size", "ask_size")
    try:
        values = {
            field: number(amount(Decimal(str(value))), field, positive=True)
            for field, value in zip(fields, (price, bid, ask, bid_size, ask_size))
        }
    except (BusinessError, InvalidOperation, ValueError):
        return None
    if values["bid"] > values["ask"]:
        return None
    ticker = symbol.split("/")[0]
    name, aliases = ASSETS.get(ticker, (ticker, []))
    return {"symbol": symbol, "source": venue, **{field: amount(value) for field, value in values.items()},
            "as_of": iso(at), "timestamp_source": timestamp_source,
            "fee_rate": None, "name": name, "aliases": [*aliases, symbol.replace("/", "")]}


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


HTTP_PROVIDERS = {
    "Binance": ("https://data-api.binance.vision/api/v3/ticker/24hr?" + BINANCE_QUERY, _binance),
    "OKX": ("https://www.okx.com/api/v5/market/tickers?instType=SPOT", _okx),
    "Kraken": ("https://api.kraken.com/0/public/Ticker?" + KRAKEN_QUERY, _kraken),
}


def _hk_quote(symbol, venue, values, timestamp):
    try:
        at = _from_milliseconds(timestamp)
    except (ValueError, TypeError, OSError, OverflowError):
        return None
    return _quote(symbol, venue, *values, at, "exchange")


def _hashkey(fetch):
    books, _ = fetch(HASHKEY_BASE + "bookTicker?site=HK")
    tickers, _ = fetch(HASHKEY_BASE + "price?site=HK")
    prices = {row["s"]: row["p"] for row in tickers}
    quotes = []
    for row in books:
        key = row.get("s")
        if key in HASHKEY_PAIRS and key in prices:
            values = (prices[key], row.get("b"), row.get("a"), row.get("bq"), row.get("aq"))
            quote = _hk_quote(HASHKEY_PAIRS[key], "HashKey", values, row.get("t"))
            if quote:
                quotes.append(quote)
    return quotes


def _osl(stop_event):
    from websockets.exceptions import WebSocketException
    from websockets.sync.client import connect

    subscription = {"op": "subscribe", "args": [
        {"instType": "SPOT", "channel": "ticker", "instId": key} for key in OSL_PAIRS
    ]}
    quotes = {}
    try:
        with connect(OSL_PUBLIC_STREAM, open_timeout=4, close_timeout=1, max_size=65536) as stream:
            stream.send(json.dumps(subscription))
            deadline = monotonic() + 4
            while len(quotes) < len(OSL_PAIRS) and not stop_event.is_set():
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                try:
                    message = json.loads(stream.recv(timeout=remaining))
                except TimeoutError:
                    break
                if (message.get("arg") or {}).get("channel") != "ticker":
                    continue
                for row in message.get("data", []):
                    symbol = OSL_PAIRS.get(row.get("instId"))
                    if symbol:
                        values = tuple(row.get(key) for key in ("lastPr", "bidPr", "askPr", "bidSz", "askSz"))
                        quote = _hk_quote(symbol, "OSL", values, row.get("ts"))
                        if quote:
                            quotes[symbol] = quote
    except WebSocketException as error:
        if not quotes:
            raise OSError("OSL public ticker connection failed") from error
    return list(quotes.values())


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
        self.simulator = SimulatedMarket()
        self.status = {name: {"state": "starting"} for name in FEED_MARKETS}
        self.threads = [Thread(target=self._run, args=(name,), daemon=True) for name in FEED_MARKETS]

    def snapshot(self):
        with self.lock:
            return self.status.copy()

    def poll(self, name):
        if name == SIMULATOR_NAME:
            now = self.office.clock()
            quotes = [_quote(symbol, source, price, bid, ask, 1, 1, now, "collected")
                      for symbol, source, price, bid, ask in self.simulator.step()]
        elif name == "HashKey":
            quotes = _hashkey(self.fetch)
        elif name == "OSL":
            quotes = _osl(self.stop_event)
        else:
            url, decode = HTTP_PROVIDERS[name]
            payload, received = self.fetch(url)
            quotes = decode(payload, received)
        if self.stop_event.is_set():
            return []
        quotes = [row for row in quotes if row is not None]
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
                result = {"state": "ok" if len(pairs) == len(FEED_MARKETS[name]) else "partial", "pairs": pairs}
                failures = 0
            except ModuleNotFoundError:
                LOG.warning("OSL public feed requires the optional requirements-live.txt dependency")
                with self.lock:
                    self.status[name] = {"state": "dependency_missing", "checked_at": iso(datetime.now(timezone.utc))}
                return
            except (OSError, HTTPException, ValueError, OverflowError, KeyError, TypeError, IndexError,
                    RecursionError, AttributeError, BusinessError) as error:
                LOG.warning("Public market feed %s unavailable (%s)", name, type(error).__name__)
                result = {"state": "unavailable"}
                failures += 1
            with self.lock:
                self.status[name] = {**result, "checked_at": iso(datetime.now(timezone.utc))}
            interval = SIMULATOR_INTERVAL if name == SIMULATOR_NAME else self.interval
            delay = min(120, interval * 2 ** min(failures, 4))
            self.stop_event.wait(delay)

    def start(self):
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=6)
