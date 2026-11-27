import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from ai_mvp.providers import HttpMarketProvider, HttpTradingProvider, MarketUnavailable, QuoteBook


def market_quote(symbol="BTC/USDT", **overrides):
    return {
        "symbol": symbol,
        "price": "63000.123456789",
        "as_of": "2025-01-09T08:00:00Z",
        "source": "demo",
        **overrides,
    }


def trend_snapshot(age=0):
    now = datetime.now(timezone.utc) - timedelta(seconds=age)
    return {"as_of": now.isoformat(), "start": (now - timedelta(seconds=10)).isoformat(),
            "window_seconds": 10, "status": "ok", "rows": [{
                "symbol": "BTC/USDT", "quote_currency": "USDT", "source": "Binance", "quote_mode": "public",
                "status": "trend", "sample_count": 2,
                "first_as_of": (now - timedelta(seconds=9)).isoformat(),
                "last_as_of": (now - timedelta(seconds=1)).isoformat(),
                "open": "100", "last": "101", "low": "100", "high": "101", "change_pct": "1",
            }]}


class QuoteBookTests(unittest.TestCase):
    def test_batch_is_atomic_and_snapshots_do_not_mutate_storage(self):
        book = QuoteBook()
        with self.assertRaises(ValueError):
            book.ingest([market_quote(), market_quote("SOL/USDT", price="NaN")])
        self.assertIsNone(book.snapshot("BTC/USDT"))
        book.ingest([market_quote(aliases=["比特币"], as_of="2025-01-09T16:00:00.1+08:00")])
        snapshot = book.snapshot("ｂｔｃ＿ｕｓｄｔ")
        self.assertEqual(snapshot["price"], "63000.123456789")
        self.assertEqual(snapshot["as_of"], "2025-01-09T08:00:00.100000Z")
        snapshot["aliases"].clear()
        self.assertEqual(book.snapshot("BTCUSDT")["aliases"], ["比特币"])

    def test_latest_quote_wins_for_concurrent_batches(self):
        book = QuoteBook()
        records = [
            market_quote(as_of=f"2025-01-09T08:00:{second:02d}Z", price=second)
            for second in range(20, 0, -1)
        ]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda record: book.ingest([record]), records))
        self.assertEqual(book.snapshot("btc-usdt")["price"], "20")
        self.assertEqual(book.ingest(records), 0)

    def test_price_updates_preserve_optional_market_metadata(self):
        book = QuoteBook()
        book.ingest([
            market_quote(name="比特币", aliases=["Bitcoin"]),
            market_quote(as_of="2025-01-09T08:01:00Z", price="63001"),
        ])
        book.ingest([market_quote(as_of="2025-01-09T08:02:00Z", price="63002")])
        self.assertEqual(book.mentions("比特币行情"), ["比特币"])
        self.assertEqual(book.search("Bitcoin")["matches"][0]["price"], "63002")
        book.ingest([market_quote(as_of="2025-01-09T08:03:00Z", name=None, aliases=[])])
        self.assertEqual(book.search("Bitcoin")["status"], "not_found")

    def test_future_tick_cannot_overwrite_current_quote(self):
        book = QuoteBook()
        book.ingest([market_quote()])
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with self.assertRaisesRegex(ValueError, "future"):
            book.ingest([market_quote(as_of=future.isoformat(), price="1")])
        self.assertEqual(book.snapshot("BTC/USDT")["price"], "63000.123456789")

    def test_search_reports_ambiguous_exact_alias_before_fuzzy_results(self):
        book = QuoteBook()
        book.ingest([
            market_quote(name="比特币", aliases=["Bitcoin"]),
            market_quote("BTCUSD", base="BTC", quote="USD", name="比特币"),
            market_quote("SOL/USDT", name="Solana"),
        ])
        matches = book.search("比特币", limit=1)
        self.assertEqual(
            (matches["status"], matches["match_count"], len(matches["matches"])), ("ambiguous", 2, 1)
        )
        self.assertEqual(book.search("btc _ usdt")["matches"][0]["symbol"], "BTC/USDT")
        self.assertEqual(book.search("sola")["status"], "match")
        self.assertEqual(book.search("未知资产")["status"], "not_found")

    def test_mentions_respect_ascii_boundaries_and_choose_longest_overlap(self):
        book = QuoteBook()
        book.ingest([
            market_quote(name="比特币", aliases=["币"]),
            market_quote("SOL/USDT", name="Solana"),
            market_quote("ETH/USDT", name="以太币", aliases=["特币乙"]),
        ])
        self.assertEqual(book.mentions("SOLUTION不是SOL，查询btc / usdt和比特币"), ["sol", "BTC/USDT"])
        self.assertEqual(book.mentions("查询比特币和Solana"), ["比特币", "solana"])
        self.assertEqual(book.mentions("SOLUTION和DESOLATE"), [])
        self.assertEqual(book.mentions("查询比特币和Solana", limit=1), ["比特币"])

    def test_explicit_unknown_pair_is_never_replaced_by_its_base_asset(self):
        book = QuoteBook()
        self.assertEqual(book.mentions("BTC/EUR现价"), ["BTC/EUR"])
        book.ingest([
            market_quote(name="比特币"),
            market_quote("BTC/EURX", aliases=["BTC/EUR"]),
        ])
        self.assertEqual(book.mentions("查 BTC/EUR、BTC-CHF 和 BTC/USDT"), ["BTC/EUR", "BTC/CHF", "BTC/USDT"])
        self.assertEqual(book.search("BTC/EUR")["status"], "not_found")
        self.assertEqual(book.search("BTC/USDT")["status"], "exact")


class HttpTradingProviderTests(unittest.TestCase):
    def test_holdings_use_exact_nonzero_portfolio_positions_only(self):
        provider = HttpTradingProvider("https://middleware.example", token="reader")
        payload = {
            "state": "partial", "as_of": "2026-11-09T08:00:00Z",
            "account": {"positions": [{"symbol": "USDT", "quantity": "500"}], "truncated": True,
                        "open_orders": [{"symbol": "ETH/USDT", "quantity": "200"}]},
            "portfolio": {"positions": [{"symbol": "BTC-usdt", "quantity": "1.25", "cost": "7000"},
                                        {"symbol": "PEPE/USDT", "quantity": "0.0"}]},
        }
        with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())) as opener:
            result = provider.holdings("demo")
        self.assertEqual(opener.call_args.args[0].full_url, "https://middleware.example/accounts/demo/analysis_snapshot")
        self.assertEqual(result["positions"], [{"symbol": "BTC/USDT", "quantity": "1.25"}])
        self.assertFalse(result["truncated"])
        self.assertIs(result["simulated"], False)
        self.assertEqual(set(result), {"state", "as_of", "positions", "truncated", "simulated"})

    def test_only_the_snapshot_mode_marks_holdings_as_simulated(self):
        provider = HttpTradingProvider("https://middleware.example", token="reader")
        payload = {
            "state": "ok", "as_of": "2026-11-09T08:00:00Z",
            "portfolio": {"mode": "simulation", "positions": [{"symbol": "BTC/USDT", "quantity": "2"}]},
        }
        for mode, expected in (("simulation", True), ("live", False), (True, False), (None, False)):
            with self.subTest(mode=mode), patch.object(
                provider._opener, "open", return_value=BytesIO(json.dumps({**payload, "mode": mode}).encode()),
            ):
                self.assertIs(provider.holdings("demo")["simulated"], expected)

    def test_partial_portfolio_exposure_uses_only_comparable_valued_positions(self):
        provider = HttpTradingProvider("https://middleware.example", token="reader")
        payload = {
            "state": "partial", "as_of": "2026-11-09T08:00:00Z",
            "portfolio": {
                "state": "partial", "valuation_currency": "USDT", "total_assets": None,
                "positions": [
                    {"symbol": "BTC/USDT", "quantity": "2", "state": "valued", "market_value": "123.45"},
                    {"symbol": "ETH/USDT", "quantity": "3", "state": "unvalued", "market_value": None},
                    {"symbol": "SOL/HKD", "quantity": "4", "state": "valued", "market_value": "900"},
                    {"symbol": "DOGE/USDT", "quantity": "0", "state": "valued", "market_value": "0"},
                ],
                "balances": [{"currency": "USDT", "available": "30"}],
            },
        }
        with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())) as opener:
            snapshot = provider.portfolio("demo")
        opener.assert_called_once()
        self.assertEqual(snapshot["state"], "partial")
        self.assertEqual(snapshot["observed_gross_exposure"], "123.45")
        self.assertIsNone(snapshot["gross_exposure"])
        self.assertIsNone(snapshot["largest_position"])
        self.assertEqual([row["symbol"] for row in snapshot["positions"]], ["BTC/USDT", "ETH/USDT", "SOL/HKD"])
        self.assertIsNone(snapshot["positions"][1]["market_value"])
        self.assertEqual(snapshot["positions"][2]["quote_currency"], "HKD")

    def test_preserves_upstream_truncation_and_rejects_invalid_flag(self):
        provider = HttpTradingProvider("https://middleware.example")
        payload = {"as_of": "2026-11-09T08:00:00Z", "positions": [], "open_orders": [], "truncated": True}
        with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())):
            self.assertTrue(provider.snapshot("test")["truncated"])
        payload["truncated"] = "true"
        with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())):
            self.assertEqual(provider.snapshot("test"), {"state": "unavailable", "reason": "invalid_response"})

    def test_fetches_only_snapshot_and_returns_normalized_allowlisted_rows(self):
        provider = HttpTradingProvider("https://middleware.example/v1/", token="example-token")
        payload = {
            "as_of": "2026-11-09T08:00:00Z",
            "notes": "untrusted",
            "positions": [{"symbol": "btc", "quantity": "-0.0100", "account_name": "untrusted"}] * 51,
            "open_orders": [{
                "symbol": "BTC-USDT",
                "side": "BUY",
                "quantity": 2,
                "limit_price": "63000.25",
                "status": "partially-filled",
                "notes": "untrusted",
            }],
        }
        with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())) as opener:
            result = provider.snapshot("user/42")
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "https://middleware.example/v1/accounts/user%2F42/snapshot")
        self.assertEqual(request.get_header("Authorization"), "Bearer example-token")
        self.assertEqual(result["state"], "ok")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["positions"]), 50)
        self.assertEqual(result["positions"][0], {"symbol": "BTC", "quantity": "-0.0100"})
        self.assertEqual(result["open_orders"][0], {
            "symbol": "BTC/USDT", "side": "buy", "quantity": "2",
            "limit_price": "63000.25", "status": "partially_filled",
        })
        self.assertNotIn("notes", result)

    def test_invalid_or_unavailable_snapshot_produces_safe_state(self):
        provider = HttpTradingProvider("http://localhost:8000")
        with patch.object(provider._opener, "open", side_effect=OSError("internal details")):
            self.assertEqual(provider.snapshot("test"), {"state": "unavailable", "reason": "upstream_unavailable"})
        with patch.object(provider._opener, "open", return_value=BytesIO(b'{"positions":[]}')):
            self.assertEqual(provider.snapshot("test"), {"state": "unavailable", "reason": "invalid_response"})
        self.assertEqual(provider.snapshot(".."), {"state": "unavailable", "reason": "invalid_user_id"})


class HttpMarketProviderTests(unittest.TestCase):
    def test_trends_use_the_read_token_and_return_allowlisted_observations(self):
        provider = HttpMarketProvider("https://middleware.example/api", token="read-token")
        payload = trend_snapshot()
        payload["rows"][0]["notes"] = "untrusted instructions"
        with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())) as opener:
            result = provider.trends()
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "https://middleware.example/api/market/trends")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer read-token")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["rows"][0]["direction"], "up")
        self.assertEqual(result["rows"][0]["quote_mode"], "public")
        self.assertNotIn("notes", result["rows"][0])

    def test_empty_single_and_stale_observations_cannot_invent_a_trend(self):
        provider = HttpMarketProvider("http://localhost:8080/api")
        empty = {**trend_snapshot(), "status": "empty", "rows": []}
        single = trend_snapshot()
        row = single["rows"][0]
        row.update(source="demo:HashKey", quote_mode="simulation", status="single_sample", sample_count=1,
                   first_as_of=row["last_as_of"], open="101", low="101", high="101", change_pct=None)
        for payload, status in ((empty, "empty"), (single, "ok"), (trend_snapshot(age=20), "stale")):
            with self.subTest(status=status):
                with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())):
                    result = provider.trends()
                self.assertEqual(result["status"], status)
                if status in {"empty", "stale"}:
                    self.assertEqual(result["rows"], [])
                else:
                    self.assertEqual(result["rows"][0]["status"], "single_sample")
                    self.assertIsNone(result["rows"][0]["direction"])
                    self.assertIsNone(result["rows"][0]["change_pct"])

    def test_trend_source_mode_and_window_validation_fail_safely(self):
        provider = HttpMarketProvider("http://localhost:8080/api")
        for overrides in ({"quote_mode": "simulation"}, {"sample_count": 1}, {"change_pct": "-1"}, {"low": "102"}):
            payload = trend_snapshot()
            payload["rows"][0].update(overrides)
            with self.subTest(overrides=overrides):
                with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())):
                    with self.assertRaisesRegex(MarketUnavailable, "invalid trend data"):
                        provider.trends()
        with patch.object(provider._opener, "open", side_effect=OSError("private-network-details")):
            with self.assertRaisesRegex(MarketUnavailable, "upstream is unavailable"):
                provider.trends()

    def test_url_encodes_query_and_keeps_ambiguity_when_limit_is_one(self):
        provider = HttpMarketProvider("https://market.example/v1/", token="example-token")
        payload = {"quotes": [
            market_quote(aliases=["比特币"]),
            market_quote("BTC/USD", aliases=["比特币"]),
        ]}
        with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())) as opener:
            result = provider.search("比特币", limit=1)
        request = opener.call_args.args[0]
        parts = urlsplit(request.full_url)
        self.assertEqual((parts.scheme, parts.netloc, parts.path), ("https", "market.example", "/v1/quotes"))
        self.assertEqual(parse_qs(parts.query), {"q": ["比特币"], "limit": ["2"]})
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer example-token")
        self.assertEqual((result["status"], result["match_count"], len(result["matches"])), ("ambiguous", 2, 1))

    def test_validates_and_filters_explicit_pair_even_when_upstream_substitutes(self):
        provider = HttpMarketProvider("http://localhost:8080")
        payload = {"quotes": [market_quote("BTC/USDT", aliases=["BTC/EUR", "BTC-EUR", "BTC_EUR"])]}
        for query in ("BTC/EUR", "BTC-EUR", "BTC_EUR"):
            with self.subTest(query=query):
                with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())):
                    result = provider.search(query)
                self.assertEqual((result["status"], result["match_count"], result["matches"]), ("not_found", 0, []))
        payload = {"quotes": [market_quote("btc-usdt", extra_instructions="untrusted")]}
        with patch.object(provider._opener, "open", return_value=BytesIO(json.dumps(payload).encode())):
            result = provider.search("BTC/USDT")
        self.assertEqual(result["status"], "exact")
        self.assertEqual(result["matches"][0]["symbol"], "BTC/USDT")
        self.assertNotIn("extra_instructions", result["matches"][0])

    def test_empty_success_is_distinct_from_failed_or_invalid_upstream(self):
        provider = HttpMarketProvider("https://market.example", token="secret-token")
        with patch.object(provider._opener, "open", return_value=BytesIO(b'{"quotes":[]}')):
            self.assertEqual(provider.search("BTC"), {
                "query": "BTC", "status": "not_found", "match_count": 0, "matches": [],
            })
        for payload in (b'{"quotes":[{"symbol":"BTC/USDT"}]}', b'{"quotes":null}', b'bad JSON'):
            with self.subTest(payload=payload):
                with patch.object(provider._opener, "open", return_value=BytesIO(payload)):
                    with self.assertRaisesRegex(MarketUnavailable, "invalid quote data"):
                        provider.search("BTC")
        for error in (OSError("secret-token internal details"), HTTPError("https://private", 307, "redirect", {}, None)):
            with self.subTest(error=type(error)):
                with patch.object(provider._opener, "open", side_effect=error) as opener:
                    with self.assertRaisesRegex(MarketUnavailable, "upstream is unavailable") as raised:
                        provider.search("BTC")
                opener.assert_called_once()
                self.assertNotIn("secret-token", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
