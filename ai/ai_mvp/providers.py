"""Market quotes supplied by the frontend and read-only middle-office snapshots."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
from threading import Lock
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


_ASSET = re.compile(r"[A-Z0-9]{1,20}")
_PAIR = re.compile(r"([A-Z0-9]{1,20})\s*[/_-]\s*([A-Z0-9]{1,20})")
_TIMESTAMP = re.compile(
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:[0-5]\d)"
)
_STATUS = re.compile(r"[a-z][a-z0-9_]{0,31}")
_ASCII_WORD = re.compile(r"[a-z0-9_]")
_PAIR_SPACES = re.compile(r"(?<=[a-z0-9])\s*([/_-])\s*(?=[a-z0-9])")
_PAIR_MENTION = re.compile(r"(?<![a-z0-9_])([a-z0-9]{1,20})([/_-])([a-z0-9]{1,20})(?![a-z0-9_])")
_MAX_ACCOUNT_ROWS = 50
_MAX_SNAPSHOT_BYTES = 256 * 1024
_MAX_MARKET_ROWS = 50
QUOTE_CLOCK_SKEW_SECONDS = 15


def _lookup_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _PAIR_SPACES.sub(r"\1", " ".join(normalized.split()))


def _asset(value: object) -> str:
    code = _lookup_key(_required_text(value, "asset code")).upper()
    if not _ASSET.fullmatch(code):
        raise ValueError("asset code must contain 1–20 ASCII letters or digits")
    return code


def _pair(value: str) -> str | None:
    match = _PAIR.fullmatch(_lookup_key(value).upper())
    return "/".join(match.groups()) if match else None


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def _timestamp(value: object) -> str:
    raw = _required_text(value, "as_of")
    match = _TIMESTAMP.fullmatch(raw)
    if not match:
        raise ValueError("as_of must be an RFC 3339 timestamp with a timezone")
    date, fraction, offset = match.groups()
    fraction = (fraction or "").ljust(6, "0")
    offset = "+00:00" if offset == "Z" else offset
    try:
        utc = datetime.fromisoformat(f"{date}.{fraction}{offset}").astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError("as_of must be a valid timestamp") from exc
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decimal(value: object, field: str, *, positive: bool = False) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{field} must be a decimal number")
    raw = str(value)
    if len(raw) > 80:
        raise ValueError(f"{field} exceeds the maximum decimal length")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not number.is_finite() or (positive and number <= 0):
        requirement = "positive and finite" if positive else "finite"
        raise ValueError(f"{field} must be {requirement}")
    return str(number)


def _normalize_quote(record: Mapping) -> dict:
    if not isinstance(record, Mapping):
        raise ValueError("each quote must be an object")
    raw_symbol = _required_text(record.get("symbol"), "symbol")
    symbol = _pair(raw_symbol)
    if symbol is None:
        base = _asset(record.get("base"))
        quote_asset = _asset(record.get("quote"))
        if _lookup_key(raw_symbol).upper() != base + quote_asset:
            raise ValueError("symbol must agree with the base and quote assets")
        symbol = f"{base}/{quote_asset}"
    else:
        base, quote_asset = symbol.split("/")
        if "base" in record and _asset(record["base"]) != base:
            raise ValueError("base must agree with symbol")
        if "quote" in record and _asset(record["quote"]) != quote_asset:
            raise ValueError("quote must agree with symbol")

    normalized = {
        "symbol": symbol,
        "base": base,
        "quote": quote_asset,
        "price": _decimal(record.get("price"), "price", positive=True),
        "as_of": _timestamp(record.get("as_of")),
        "source": _required_text(record.get("source"), "source"),
    }
    if "name" in record:
        name = record["name"]
        normalized["name"] = _required_text(name, "name") if name is not None else None
    if "aliases" in record:
        aliases = record["aliases"]
        if not isinstance(aliases, (list, tuple)):
            raise ValueError("aliases must be a list of strings")
        normalized["aliases"] = tuple(dict.fromkeys(_required_text(alias, "alias") for alias in aliases))
    return normalized


def _public_quote(record: dict) -> dict:
    return {**record, "aliases": list(record["aliases"])}


def _limit(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 50:
        raise ValueError("limit must be an integer from 1 to 50")
    return value


class QuoteBook:
    """Process-local quote storage. Search and mention extraction share an alias index."""

    def __init__(self) -> None:
        self._quotes: dict[str, dict] = {}
        self._aliases: dict[str, set[str]] = {}
        self._assets: frozenset[str] = frozenset()
        self._mention_pattern: re.Pattern | None = None
        self._lock = Lock()

    def ingest(self, batch: Iterable[Mapping]) -> int:
        """Validate the entire batch before applying updates and count changed symbols."""
        incoming = [_normalize_quote(item) for item in batch]
        latest_valid = datetime.now(timezone.utc) + timedelta(seconds=QUOTE_CLOCK_SKEW_SECONDS)
        latest_valid_iso = latest_valid.isoformat(timespec="microseconds").replace("+00:00", "Z")
        if any(record["as_of"] > latest_valid_iso for record in incoming):
            raise ValueError("quote timestamp is too far in the future")
        with self._lock:
            pending = {}
            for record in incoming:
                symbol = record["symbol"]
                previous = pending.get(symbol, self._quotes.get(symbol))
                if previous is None or record["as_of"] >= previous["as_of"]:
                    pending[symbol] = {"name": None, "aliases": (), **(previous or {}), **record}
            updates = {
                symbol: record
                for symbol, record in pending.items()
                if record != self._quotes.get(symbol)
            }
            if updates:
                catalog_changed = any(
                    symbol not in self._quotes
                    or record["name"] != self._quotes[symbol]["name"]
                    or record["aliases"] != self._quotes[symbol]["aliases"]
                    for symbol, record in updates.items()
                )
                self._quotes.update(updates)
                if catalog_changed:
                    self._rebuild_aliases()
            return len(updates)

    def _rebuild_aliases(self) -> None:
        aliases: dict[str, set[str]] = {}
        pair_variants = {}
        assets = set()
        for symbol, record in self._quotes.items():
            base, counter = symbol.split("/")
            assets.update((base.lower(), counter.lower()))
            terms = (base, base + counter, record["name"], *record["aliases"])
            for term in terms:
                if term:
                    aliases.setdefault(_lookup_key(term), set()).add(symbol)
            for separator in ("/", "-", "_"):
                pair_variants[_lookup_key(f"{base}{separator}{counter}")] = {symbol}
        aliases.update(pair_variants)

        branches = []
        for term in sorted(aliases, key=lambda key: (-len(key), key)):
            left = r"(?<![a-z0-9_])" if _ASCII_WORD.fullmatch(term[0]) else ""
            right = r"(?![a-z0-9_])" if _ASCII_WORD.fullmatch(term[-1]) else ""
            branches.append(left + re.escape(term) + right)
        self._aliases = aliases
        self._assets = frozenset(assets)
        self._mention_pattern = re.compile(r"(?=(" + "|".join(branches) + r"))") if branches else None

    def snapshot(self, symbol: str) -> dict | None:
        """Resolve a pair or an unambiguous compact symbol."""
        normalized = _lookup_key(_required_text(symbol, "symbol")).upper()
        with self._lock:
            pair = _pair(normalized)
            if pair:
                record = self._quotes.get(pair)
                return _public_quote(record) if record else None
            compact_matches = [
                record for key, record in self._quotes.items() if key.replace("/", "") == normalized
            ]
            return _public_quote(compact_matches[0]) if len(compact_matches) == 1 else None

    def search(self, query: str, limit: int = 5) -> dict:
        limit = _limit(limit)
        normalized = _lookup_key(query)
        explicit_pair = _pair(normalized) if "/" in normalized else None
        with self._lock:
            matches = self._aliases.get(normalized, set())
            if explicit_pair:
                matches = {explicit_pair} if explicit_pair in self._quotes else set()
            if matches:
                status = "exact" if len(matches) == 1 else "ambiguous"
            elif normalized and not explicit_pair:
                matches = {
                    symbol
                    for alias, symbols in self._aliases.items()
                    if normalized in alias
                    for symbol in symbols
                }
                status = "match" if matches else "not_found"
            else:
                status = "not_found"
            return {
                "query": query,
                "status": status,
                "match_count": len(matches),
                "matches": [_public_quote(self._quotes[symbol]) for symbol in sorted(matches)[:limit]],
            }

    def mentions(self, message: str, limit: int = 5) -> list[str]:
        """Find distinct exact lookup terms in message order, preferring longer overlaps."""
        limit = _limit(limit)
        with self._lock:
            pattern = self._mention_pattern
            aliases = self._aliases
            assets = self._assets
        normalized = _lookup_key(message)
        candidates = []
        for match in _PAIR_MENTION.finditer(normalized):
            base, separator, counter = match.groups()
            term = match[0]
            pair = f"{base.upper()}/{counter.upper()}"
            if separator == "/" or (
                (base in assets or counter in assets)
                and (term not in aliases or pair in aliases[term])
            ):
                candidates.append((match.start(), match.end(), pair, True))
        if pattern:
            candidates.extend((*match.span(1), match[1], False) for match in pattern.finditer(normalized))
        candidates.sort(key=lambda item: (not item[3], item[0] - item[1], item[0]))

        occupied = set()
        selected = []
        for start, end, term, is_pair in candidates:
            positions = range(start, end)
            if occupied.isdisjoint(positions):
                occupied.update(positions)
                selected.append((start, term, is_pair))
        terms = []
        seen = set()
        for _, term, is_pair in sorted(selected):
            identity = frozenset({term} if is_pair else aliases[term])
            if identity not in seen:
                seen.add(identity)
                terms.append(term)
            if len(terms) == limit:
                break
        return terms


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class MarketUnavailable(RuntimeError):
    """A market upstream failed or returned invalid quote data."""


class HttpMarketProvider:
    """Search upstream candidates and validate them with the local quote index.

    Upstream name searches must include matching aliases in each quote and at
    least two distinct pairs when a query is ambiguous. match_count covers the
    returned candidate set.
    """

    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 2.0,
                 include_venues: bool = False) -> None:
        invalid_url = "market base URL must be an HTTP(S) URL without credentials, query, or fragment"
        try:
            url = urlsplit(base_url)
            port = url.port
        except (TypeError, ValueError):
            raise ValueError(invalid_url) from None
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or port == 0
            or url.username is not None
            or any(character in base_url for character in "?#\\")
            or any(character.isspace() or not character.isprintable() for character in base_url)
        ):
            raise ValueError(invalid_url)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (float, int))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("market timeout must be a positive finite number")
        if token is not None and (
            not isinstance(token, str)
            or not token
            or any(not 33 <= ord(char) <= 126 for char in token)
        ):
            raise ValueError("market token must contain printable ASCII token characters")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._include_venues = include_venues
        self._headers = {"Accept": "application/json"}
        if token is not None:
            self._headers["Authorization"] = f"Bearer {token}"
        self._opener = build_opener(_NoRedirect)

    def search(self, query: str, limit: int = 5) -> dict:
        limit = _limit(limit)
        query = _required_text(query, "query")
        parameters = {"q": query, "limit": max(2, limit)}
        if self._include_venues:
            parameters.update(all_sources="true", limit=max(20, limit))
        request = Request(f"{self._base_url}/quotes?{urlencode(parameters)}", headers=self._headers, method="GET")
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read(_MAX_SNAPSHOT_BYTES + 1)
        except (OSError, HTTPException, ValueError):
            raise MarketUnavailable("market upstream is unavailable") from None

        if len(raw) > _MAX_SNAPSHOT_BYTES:
            raise MarketUnavailable("market upstream returned invalid quote data")
        try:
            payload = json.loads(raw)
            quotes = payload.get("quotes") if isinstance(payload, dict) else None
            if not isinstance(quotes, list) or len(quotes) > _MAX_MARKET_ROWS:
                raise ValueError("quotes must be a bounded list")
            book = QuoteBook()
            book.ingest(quotes)
            result = book.search(_pair(query) or query, limit)
            if self._include_venues and result["status"] == "exact":
                result["venues"] = self._venue_quotes(quotes, result["matches"][0]["symbol"])
        except (ValueError, RecursionError):
            raise MarketUnavailable("market upstream returned invalid quote data") from None

        result["query"] = query
        return result

    @staticmethod
    def _venue_quotes(quotes, symbol):
        sources = {}
        for raw in quotes:
            quote = _normalize_quote(raw)
            if quote["symbol"] != symbol or raw.get("bid") is None or raw.get("ask") is None:
                continue
            quote["bid"] = _decimal(raw["bid"], "bid", positive=True)
            quote["ask"] = _decimal(raw["ask"], "ask", positive=True)
            if Decimal(quote["bid"]) > Decimal(quote["ask"]):
                raise ValueError("market quotes must not be crossed")
            if raw.get("timestamp_source") in ("exchange", "collected"):
                quote["timestamp_source"] = raw["timestamp_source"]
            source = quote["source"]
            if source not in sources or quote["as_of"] > sources[source]["as_of"]:
                sources[source] = {key: quote[key] for key in
                                   ("symbol", "source", "as_of", "price", "bid", "ask", "timestamp_source") if key in quote}
        return [sources[source] for source in sorted(sources)]


def _account_symbol(value: object) -> str:
    symbol = _required_text(value, "symbol")
    return _pair(symbol) or _asset(symbol)


def _position(row: dict) -> dict:
    return {
        "symbol": _account_symbol(row.get("symbol")),
        "quantity": _decimal(row.get("quantity"), "quantity"),
    }


def _open_order(row: dict) -> dict:
    side = _required_text(row.get("side"), "side").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    order = {
        "symbol": _account_symbol(row.get("symbol")),
        "side": side,
        "quantity": _decimal(row.get("quantity"), "quantity", positive=True),
    }
    if row.get("limit_price") is not None:
        order["limit_price"] = _decimal(row["limit_price"], "limit_price", positive=True)
    if row.get("status") is not None:
        status = _required_text(row["status"], "status").lower().replace("-", "_").replace(" ", "_")
        if not _STATUS.fullmatch(status):
            raise ValueError("status must be a short ASCII token")
        order["status"] = status
    return order


def _account_snapshot(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("snapshot must be an object")
    positions = payload.get("positions")
    orders = payload.get("open_orders")
    if not isinstance(positions, list) or not isinstance(orders, list):
        raise ValueError("snapshot must contain positions and open_orders lists")
    upstream_truncated = payload.get("truncated", False)
    if not isinstance(upstream_truncated, bool):
        raise ValueError("snapshot truncated must be a boolean")
    if any(not isinstance(row, dict) for row in positions[:_MAX_ACCOUNT_ROWS] + orders[:_MAX_ACCOUNT_ROWS]):
        raise ValueError("account rows must be objects")
    return {
        "state": "ok",
        "as_of": _timestamp(payload.get("as_of")),
        "positions": [_position(row) for row in positions[:_MAX_ACCOUNT_ROWS]],
        "open_orders": [_open_order(row) for row in orders[:_MAX_ACCOUNT_ROWS]],
        "truncated": upstream_truncated or max(len(positions), len(orders)) > _MAX_ACCOUNT_ROWS,
    }


class HttpTradingProvider:
    """Fetch account positions and open orders with a read-only GET request."""

    def __init__(self, base_url: str, *, token: str | None = None, timeout: float = 2.0) -> None:
        url = urlsplit(base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.query
            or url.fragment
        ):
            raise ValueError("trading base URL must be an HTTP(S) URL without credentials, query, or fragment")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {"Accept": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._opener = build_opener(_NoRedirect)

    def snapshot(self, user_id: str) -> dict:
        if not isinstance(user_id, str) or not user_id.strip() or user_id in {".", ".."}:
            return {"state": "unavailable", "reason": "invalid_user_id"}
        url = f"{self._base_url}/accounts/{quote(user_id, safe='')}/snapshot"
        request = Request(url, headers=self._headers, method="GET")
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read(_MAX_SNAPSHOT_BYTES + 1)
        except (OSError, HTTPException):
            return {"state": "unavailable", "reason": "upstream_unavailable"}

        if len(raw) > _MAX_SNAPSHOT_BYTES:
            return {"state": "unavailable", "reason": "invalid_response"}
        try:
            return _account_snapshot(json.loads(raw))
        except (ValueError, RecursionError):
            return {"state": "unavailable", "reason": "invalid_response"}
