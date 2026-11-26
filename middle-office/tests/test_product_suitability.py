from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from middle_office.public_market import BINANCE_PAIRS, PROVIDER_MARKETS
from middle_office.service import MiddleOffice
from middle_office.validation import BusinessError, iso


class ProductSuitabilityTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "ledger.sqlite3"
        self.now = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
        self.office = MiddleOffice(
            self.path, clock=lambda: self.now, suitability_advisory=True,
            product_risks={"BTC/USDT": 4},
            product_requirements={"BTC/USDT": {"FC": 70, "KE": 60}},
        )
        self.office.create_account("user", {"initial_balances": {"USDT": "10000"}})
        self.office.ingest_quotes({"quotes": [{
            "symbol": "BTC/USDT", "source": "test", "price": "100", "as_of": iso(self.now),
        }]})
        self.order = {"symbol": "BTC/USDT", "side": "buy", "quantity": "1"}

    def assessment(self, *, rai=80, cap="R5", prohibitions=None, **dimensions):
        scores = {"FC": 90, "RA": 90, "KE": 40, "BD": 80, "OC": 80, **dimensions}
        self.office.assessment("user", {"assessment": {
            "dimensions": scores, "rai": rai, "risk_level": "C" + cap[1],
            "product_cap": cap, "prohibitions": prohibitions or [],
        }})

    def test_within_cap_buy_carries_dimension_warning_through_fill(self):
        self.assessment()
        preview = self.office.preview_order("user", self.order)
        expected = {
            "code": "profile_dimensions", "risk_level": "C5", "product_cap": "R5",
            "product_risk": "R4", "unmet_dimensions": ["KE"],
        }
        self.assertEqual(preview["suitability_warning"], expected)
        filled = self.office.place_order("user", {**self.order, "request_id": "dimensions"})
        self.assertEqual(filled["status"], "filled")
        self.assertEqual(filled["suitability_warning"], expected)
        self.assertNotIn("suitability_warning", self.office.preview_order("user", {**self.order, "side": "sell"}))

    def test_existing_warning_priorities_are_preserved(self):
        missing = self.office.preview_order("user", self.order)["suitability_warning"]
        self.assertEqual(missing["code"], "assessment_required")
        self.assertNotIn("unmet_dimensions", missing)
        self.assessment(rai=60, cap="R3")
        self.assertEqual(self.office.preview_order("user", self.order)["suitability_warning"]["code"], "product_cap")
        self.assessment(prohibitions=["no_buys"])
        self.assertEqual(self.office.preview_order("user", self.order)["suitability_warning"]["code"], "assessment_prohibition")
        self.assessment(KE=60)
        self.assertNotIn("suitability_warning", self.office.preview_order("user", self.order))

    def test_strict_configuration_rejects_unmet_dimensions(self):
        self.assessment()
        self.office.suitability_advisory = False
        with self.assertRaises(BusinessError) as error:
            self.office.preview_order("user", self.order)
        self.assertEqual(error.exception.code, "profile_dimensions")
        rejected = self.office.place_order("user", {**self.order, "request_id": "strict"})
        self.assertEqual((rejected["status"], rejected["reason"]), ("rejected", "profile_dimensions"))

    def test_thresholds_are_optional_for_existing_callers_and_validate_new_config(self):
        self.assessment()
        standalone = MiddleOffice(self.path, clock=lambda: self.now, product_risks={"BTC/USDT": 4})
        self.assertNotIn("suitability_warning", standalone.preview_order("user", self.order))
        for requirements in ({"KE": True}, {"KE": 101}, {"other": 10}):
            with self.subTest(requirements=requirements), self.assertRaises(BusinessError):
                MiddleOffice(self.path, product_requirements={"BTC/USDT": requirements})

    def test_monad_is_registered_only_on_okx(self):
        self.assertIn("MON/USDT", PROVIDER_MARKETS["OKX"])
        self.assertNotIn("MONUSDT", BINANCE_PAIRS)
        self.assertEqual(
            [source for source, pairs in PROVIDER_MARKETS.items() if "MON/USDT" in pairs], ["OKX"],
        )


if __name__ == "__main__":
    unittest.main()
