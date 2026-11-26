from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from middle_office.service import MiddleOffice
from middle_office.server import Server
from middle_office.validation import BusinessError, iso


class DepositLedgerTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "ledger.sqlite3"
        self.office = MiddleOffice(self.path)
        self.office.create_account("alice", {"initial_balances": {"USDT": "1000"}})
        self.office.create_account("bob", {"initial_balances": {"USDT": "500"}})

    def test_top_up_preserves_reservations_positions_orders_and_trade_history(self):
        self.office.ingest_quotes({"quotes": [{
            "symbol": "BTC/USDT", "price": "100", "source": "demo",
            "as_of": iso(datetime.now(timezone.utc)),
        }]})
        self.office.place_order("alice", {
            "request_id": "limit", "symbol": "BTC/USDT", "side": "buy", "quantity": "0.1",
            "order_type": "limit", "limit_price": "90",
        })
        with self.office.store.transaction() as state:
            before = deepcopy(state)
        receipt = self.office.deposit("alice", {"amount": "25.00000001", "request_id": "top_up"})
        self.assertEqual(receipt["currency"], "USDT")
        self.assertEqual(receipt["amount"], "25.00000001")
        self.assertEqual(receipt["total"], "1025.00000001")
        self.assertEqual(receipt["available"], "1016.00000001")
        self.assertEqual(receipt["mode"], "simulation")
        with self.office.store.transaction() as state:
            self.assertEqual(state["orders"], before["orders"])
            self.assertEqual(state["trades"], before["trades"])
            self.assertEqual(state["accounts"]["alice"]["positions"], before["accounts"]["alice"]["positions"])
            self.assertEqual(state["accounts"]["bob"], before["accounts"]["bob"])

    def test_retry_is_account_scoped_persistent_and_cannot_change_the_amount(self):
        payload = {"amount": "10", "request_id": "same_request"}
        first = self.office.deposit("alice", payload)
        self.office = MiddleOffice(self.path)
        self.assertEqual(self.office.deposit("alice", {**payload, "amount": "10.00"}), first)
        with self.assertRaises(BusinessError) as error:
            self.office.deposit("alice", {**payload, "amount": "11"})
        self.assertEqual((error.exception.code, error.exception.status), ("request_conflict", 409))
        second = self.office.deposit("bob", payload)
        self.assertNotEqual(first["deposit_id"], second["deposit_id"])
        self.assertEqual(second["total"], "510")
        self.assertEqual(self.office.portfolio("alice")["balances"][0]["total"], "1010")
        self.assertEqual(self.office.records("alice", "trades"), [])

    def test_concurrent_retry_is_credited_once_and_distinct_requests_do_not_lose_updates(self):
        payload = {"amount": "1", "request_id": "once"}
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: self.office.deposit("alice", payload), range(8)))
        self.assertTrue(all(result == results[0] for result in results))
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda index: self.office.deposit("alice", {
                "amount": "1", "request_id": f"unique_{index}",
            }), range(8)))
        self.assertEqual(self.office.portfolio("alice")["balances"][0]["total"], "1009")
        deposits = [row for row in self.office.records("alice", "audit") if row["action"] == "simulated_deposit"]
        self.assertEqual(len(deposits), 9)

    def test_invalid_amount_balance_overflow_and_missing_account_leave_state_intact(self):
        with self.office.store.transaction() as state:
            before = deepcopy(state)
        for value in ("0", "-1", "0.000000001", "NaN", "Infinity", True, "1000000000001"):
            with self.subTest(value=value), self.assertRaises(BusinessError):
                self.office.deposit("alice", {"amount": value, "request_id": "invalid"})
        with self.assertRaises(BusinessError):
            self.office.deposit("alice", {"amount": "1000000000000", "request_id": "overflow"})
        with self.assertRaises(BusinessError) as missing:
            self.office.deposit("missing", {"amount": "1", "request_id": "missing"})
        self.assertEqual(missing.exception.status, 404)
        with self.assertRaises(BusinessError):
            self.office.deposit("alice", {"amount": "1", "request_id": "../invalid"})
        with self.office.store.transaction() as state:
            self.assertEqual(state, before)

    def test_failed_audit_rolls_back_balance_and_idempotency_record(self):
        payload = {"amount": "20", "request_id": "retry_after_failure"}
        with patch.object(self.office, "_audit", side_effect=RuntimeError("storage fault")):
            with self.assertRaises(RuntimeError):
                self.office.deposit("alice", payload)
        self.assertEqual(self.office.portfolio("alice")["balances"][0]["total"], "1000")
        self.assertEqual(self.office.deposit("alice", payload)["total"], "1020")


class DepositHTTPTests(unittest.TestCase):
    def test_operator_can_top_up_the_path_account_and_reader_cannot_write(self):
        with TemporaryDirectory() as directory:
            office = MiddleOffice(Path(directory) / "ledger.sqlite3")
            office.create_account("alice", {"initial_balances": {"USDT": "100"}})
            server = Server(("127.0.0.1", 0), office, token="operator", read_token="reader")
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/accounts/alice/deposits"
                opener = build_opener(ProxyHandler({}))
                payload = json.dumps({"amount": "5", "request_id": "http"}).encode()
                for token, expected in (("reader", 403), ("wrong", 401)):
                    request = Request(url, data=payload, headers={
                        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
                    })
                    with self.subTest(token=token), self.assertRaises(HTTPError) as error:
                        opener.open(request)
                    self.assertEqual(error.exception.code, expected)
                    error.exception.close()
                request = Request(url, data=payload, headers={
                    "Authorization": "Bearer operator", "Content-Type": "application/json",
                })
                with opener.open(request) as response:
                    result = json.load(response)
                self.assertEqual((result["amount"], result["total"]), ("5", "105"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
