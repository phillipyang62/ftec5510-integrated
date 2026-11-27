"""Simulation accounts that start with a preset assessment and holdings."""

from questionnaire import VERSION


def _preset(level, rai, scores, wealth_band, balance, positions):
    return {
        "ledger": {
            "initial_balances": {"USDT": balance},
            "initial_positions": [
                {"symbol": symbol, "quantity": quantity, "average_cost": cost}
                for symbol, quantity, cost in positions
            ],
        },
        "profile": {
            "questionnaire_version": VERSION,
            "source": "demo_preset",
            "dimensions": {"wealth_band": wealth_band},
            "assessment": {
                "dimensions": dict(zip(("FC", "RA", "KE", "BD", "OC"), scores)),
                "rai": rai,
                "risk_level": f"C{level}",
                "product_cap": f"R{level}",
            },
        },
    }


DEMO_ACCOUNTS = {
    "demo_c1": _preset(1, 20, (25, 12.5, 16.67, 25, 20.83), "low", "12000", (
        ("ETH/USDT", "0.2", "3500"),
    )),
    "demo_c2": _preset(2, 35, (37.5, 29.17, 41.67, 33.33, 33.33), "low", "12000", (
        ("BTC/USDT", "0.01", "65000"), ("ETH/USDT", "0.5", "3500"),
    )),
    "demo_c3": _preset(3, 61, (62.5, 58.33, 58.33, 62.5, 62.5), "medium", "15000", (
        ("BTC/USDT", "0.04", "65000"), ("ETH/USDT", "1", "3500"),
    )),
    "demo_c4": _preset(4, 74, (75, 70.83, 75, 83.33, 70.83), "high", "20000", (
        ("BTC/USDT", "0.12", "65000"), ("ETH/USDT", "2", "3500"),
    )),
    "demo_c5": _preset(5, 90, (91.67, 87.5, 87.5, 91.67, 91.67), "high", "30000", (
        ("BTC/USDT", "0.25", "65000"), ("ETH/USDT", "4", "3500"), ("SOL/USDT", "20", "175"),
    )),
    "demo_low_risk": _preset(1, 20, (20, 20, 20, 20, 20), "high", "1000", (
        ("BTC/USDT", "2", "65000"), ("ETH/USDT", "25", "2000"),
    )),
}
