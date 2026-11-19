"""Exercise the questionnaire, frontend gateway, ledger, and AI over HTTP."""

import argparse
from decimal import Decimal
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from run_demo import ASSESSMENT, USER, demo_stack


def checked(client, method, path, body=None, *, expected=200):
    code, data = client.request(method, path, body)
    if code != expected:
        raise AssertionError(f"{method} {path} returned HTTP {code}, expected {expected}: {data}")
    return data


def check_html(url):
    with urlopen(url, timeout=5) as page:
        assert b'<body data-integrated="true">' in page.read()
    with urlopen(url + "/integration.js", timeout=5) as script:
        assert b"/api/assistant/chat" in script.read()
    for private_file in ("/.env.example", "/question-bank.json"):
        try:
            urlopen(url + private_file, timeout=5)
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("the demo served a non-public file")
    try:
        urlopen(Request(url + "/api/profile", headers={"Origin": "http://example.test"}), timeout=5)
    except HTTPError as error:
        assert error.code == 403
    else:
        raise AssertionError("the demo accepted a foreign origin")


def questionnaire_form(ui, middle, ai):
    checked(ui, "GET", "/api/profile", expected=404)
    bank = checked(ui, "GET", "/api/questionnaire")
    assert len(bank["questions"]) == 30
    assert [row["id"] for row in bank["questions"] if row["multiple"]] == ["KE2"]
    assert all("score" not in option for row in bank["questions"] for option in row["options"])
    # The example in 03_数据结构设计.md is also the questionnaire team's acceptance fixture.
    selections = {"FC": "CCDDDC", "RA": "DCDDDD", "KE": ["C", ["B", "C"], "D", "C", "C", "B"],
                  "BD": "CCCDCC", "OC": "CDDBDC"}
    answers = [{"qid": f"{code}{i}", "value": value} for code, group in selections.items()
               for i, value in enumerate(group, 1)]
    payload = {"questionnaire_version": bank["questionnaire_version"], "answers": answers,
               "consent": {"assessment": True, "ai_processing": True},
               "quality_signals": {"answer_changes": 3, "median_item_seconds": 14.2}}
    failed = checked(ui, "POST", "/api/questionnaire", {**payload, "answers": answers[:-1]}, expected=422)
    assert failed["error"]["code"] == "incomplete"
    checked(ui, "GET", "/api/profile", expected=404)
    result = checked(ui, "POST", "/api/questionnaire", payload)
    assessment = result["assessment"]
    assert assessment["dimensions"] == {"FC": 62.5, "RA": 70.83, "KE": 50, "BD": 54.17, "OC": 58.33}
    assert (assessment["rai"], assessment["risk_level"], assessment["product_cap"], assessment["confidence"]) == (61, "C3", "R3", 0.94)
    stored = checked(middle, "GET", f"/api/accounts/{USER}/assessment")
    assert "answers" not in stored and stored["assessment"] == {key: value for key, value in assessment.items() if key != "allocation_range"}
    assert assessment == checked(ai, "GET", f"/v1/profiles/{USER}")["assessment"]

    leveraged = [{"qid": row["id"], "value": ["E"] if row["multiple"] else "B" if row["id"] == "OC5" else "E"}
                 for row in bank["questions"]]
    capped = checked(ui, "POST", "/api/questionnaire", {**payload, "answers": leveraged})
    assert capped["assessment"]["rai"] == 44 and "LEVERAGE_USE" in capped["assessment"]["flags"]
    chat = checked(ui, "POST", "/api/assistant/chat", {"message": "帮我做一个模拟配置"})
    assert chat["mode"] == "clarify" and "杠杆" in chat["reply"]


def derived_profile_api(ui, middle, ai):
    beginner = {**ASSESSMENT, "assessment": {**ASSESSMENT["assessment"],
                "dimensions": {**ASSESSMENT["assessment"]["dimensions"], "KE": 30}}}
    checked(middle, "PUT", f"/api/accounts/{USER}/assessment", beginner)
    education = checked(ui, "POST", "/api/assistant/chat", {"message": "什么是滑点？"})
    assert education["mode"] == "education" and education["reply"]

    profile = {**ASSESSMENT, "assessment": {**ASSESSMENT["assessment"], "rai": 66, "risk_level": "C4", "product_cap": "R4"}}
    result = checked(ui, "PUT", "/api/profile", profile)
    actual = checked(ui, "GET", "/api/profile")["assessment"]
    authoritative = checked(middle, "GET", f"/api/accounts/{USER}/assessment")["assessment"]
    assert actual == {"allocation_range": None, **authoritative}
    assert actual == result["assessment"] == checked(ai, "GET", f"/v1/profiles/{USER}")["assessment"]
    assert actual["risk_level"] == "C4" and actual["product_cap"] == "R4"
    assert checked(ui, "PUT", "/api/profile", {"assessment": {}}, expected=400)["error"]["code"] == "invalid_assessment"


def trade(ui):
    buy = {"symbol": "BTC/USDT", "side": "buy", "quantity": "0.01", "order_type": "market"}
    before = checked(ui, "GET", "/api/account/summary")
    checked(ui, "POST", "/api/orders", buy, expected=400)
    declined = checked(ui, "POST", "/api/orders/preview", {**buy, "quantity": "0.5"}, expected=409)
    assert declined["error"]["code"] == "insufficient_balance"
    estimate = checked(ui, "POST", "/api/orders/preview", buy)
    assert estimate["source"] == "demo:HashKey" and estimate["reference_price"] == "68001"
    assert checked(ui, "GET", "/api/orders")["orders"] == []
    assert checked(ui, "GET", "/api/account/summary")["portfolio"]["balances"] == before["portfolio"]["balances"]
    ticket = {"preview_id": estimate["preview_id"]}
    checked(ui, "POST", "/api/orders", {**ticket, "quantity": "0.02"}, expected=400)
    filled = checked(ui, "POST", "/api/orders", ticket)
    assert filled["status"] == "filled"
    assert filled == checked(ui, "POST", "/api/orders", ticket)
    assert checked(ui, "GET", f"/api/orders/{filled['order_id']}")["status"] == "filled"
    assert checked(ui, "GET", "/api/account/transactions?limit=20")["total"] == 1
    sell = {**buy, "side": "sell", "order_type": "limit", "limit_price": "70000", "quantity": "0.005"}
    estimate = checked(ui, "POST", "/api/orders/preview", sell)
    pending = checked(ui, "POST", "/api/orders", {"preview_id": estimate["preview_id"]})
    assert pending["status"] == "open"
    return pending["order_id"]


def offline_checks():
    with demo_stack(ui_port=0) as (ui, middle, ai, reader, url):
        check_html(url)
        health = checked(ui, "GET", "/api/health")
        assert set(health["services"]) == {"middle_office", "ai"}
        assert not health["services"]["ai"]["remote_model_configured"]
        print("PASS frontend assets, loopback origin, and both backend health checks")

        questionnaire_form(ui, middle, ai)
        print("PASS original 30 questions, example RAI 61/C3/R3, incomplete answers, leverage cap and AI follow-up")

        derived_profile_api(ui, middle, ai)
        print("PASS questionnaire scores and product cap persist in middle office and AI")

        query = urlencode({"symbol": "BTC/USDT", "quantity": "0.01", "side": "buy"})
        venue_report = checked(ui, "GET", "/api/market/venues?" + query)
        assert venue_report["status"] == "ok" and len(venue_report["venues"]) == 2
        assert {row["source"] for row in venue_report["venues"]} == {"demo:HashKey", "demo:OSL"}
        assert all(row["quote_currency"] == "USDT" and row["price"] and row["as_of"] for row in venue_report["venues"])
        print("PASS frontend receives both venues with currency, price, and timestamp")

        order_id = trade(ui)
        print("PASS read-only preview, insufficient funds, simulated fill, duplicate submit, pending order")

        chat = checked(ui, "POST", "/api/assistant/chat", {
            "user_id": "untrusted_browser_id", "message": "查一下比特币报价、我的持仓和挂单",
            "include_account": True, "market_queries": ["BTC/USDT"],
        })
        assert chat["reply"] and "模拟报价" in chat["reply"]
        assert chat["generation"] == "template" and chat["mode"] == "advisory" and chat["product_cap"] == "R4"
        assert chat["market"][0]["status"] == "exact" and chat["market"][0]["matches"][0]["freshness"] == "fresh"
        assert chat["account"]["state"] == "ok"
        assert {"symbol": "BTC", "quantity": "0.11"} in chat["account"]["positions"]
        assert chat["account"]["open_orders"][0]["side"] == "sell"
        assert chat["account"]["open_orders"][0]["quantity"] == "0.005"
        assert "BTC/USDT 卖出 0.005" in chat["reply"]
        print("PASS chat uses confirmed profile, exact quote, holdings, and open order")

        risk = checked(ui, "GET", "/api/risk?quote_currency=USDT")
        ledger = checked(ui, "GET", "/api/account/summary")
        assert risk["state"] == "ok" and risk["summary"]["open_order_count"] == 1
        assert ledger["snapshot_id"] and ledger["portfolio"]["state"] == "ok"
        assert ledger["account"]["open_orders"][0]["order_id"] == order_id
        cancelled = checked(ui, "POST", f"/api/orders/{order_id}/cancel", {})
        assert cancelled["status"] == "cancelled"
        assert checked(ui, "GET", "/api/account/summary")["account"]["open_orders"] == []
        checked(reader, "POST", f"/api/accounts/{USER}/orders", {}, expected=403)
        checked(reader, "POST", f"/api/accounts/{USER}/orders/preview", {}, expected=403)
        print("PASS account snapshot, AI risk, order cancellation, and read-only AI permissions")


def live_checks():
    pairs = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
    with demo_stack(ui_port=0, live_market=True) as (ui, middle, ai, _, url):
        check_html(url)
        questionnaire_form(ui, middle, ai)
        deadline = monotonic() + 22
        for symbol in pairs:
            query = urlencode({"symbol": symbol, "quantity": "0.01", "side": "buy"})
            while True:
                report = checked(ui, "GET", "/api/market/venues?" + query)
                if len(report["venues"]) >= 2:
                    break
                if monotonic() >= deadline:
                    raise AssertionError(f"Expected at least two current venues for {symbol}: {report}")
                sleep(0.6)
            assert report["market_mode"] == "public" and report["ranking_basis"] == "bid_ask_excluding_fees"
            for quote in report["venues"]:
                assert quote["quote_currency"] == "USDT" and quote["fee_rate"] is None and quote["total"] is None
                assert Decimal(quote["ask"]) >= Decimal(quote["bid"]) > 0 and quote["as_of"]
            print(f"PASS public {symbol}: " + ", ".join(quote["source"] for quote in report["venues"]))

        chat = checked(ui, "POST", "/api/assistant/chat", {"message": "比较 BTC/USDT 的报价", "market_queries": ["BTC/USDT"]})
        assert len([row for row in chat["market"][0]["venues"] if row["freshness"] == "fresh"]) >= 2
        assert "多来源买卖报价" in chat["reply"]
        print("PASS live venue quotes reach the assistant through middle office")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-market", action="store_true", help="also query the public exchange feeds")
    args = parser.parse_args()
    offline_checks()
    if args.live_market:
        live_checks()


if __name__ == "__main__":
    main()
