"""Exercise the questionnaire, frontend gateway, ledger, and AI over HTTP."""

import argparse
from decimal import Decimal
from importlib.util import find_spec
from http.cookiejar import CookieJar
import json
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from run_demo import ASSESSMENT, demo_stack
from middle_office.public_market import HK_PAIRS, USDT_PAIRS


USER = "student_demo"


class BrowserClient:
    def __init__(self, url):
        self.url = url
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, method, path, body=None, *, headers=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.url + path, method=method, data=data, headers=headers or {})
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            response = self.opener.open(request, timeout=12)
        except HTTPError as error:
            response = error
        with response:
            payload = json.load(response) if response.headers.get_content_type() == "application/json" else response.read()
            return response.status, payload


def checked(client, method, path, body=None, *, expected=200):
    code, data = client.request(method, path, body)
    if code != expected:
        raise AssertionError(f"{method} {path} returned HTTP {code}, expected {expected}: {data}")
    return data


def check_html(url):
    with urlopen(url, timeout=5) as page:
        html = page.read()
        assert b'<body data-integrated="true">' in html and b'id="account-login-form"' in html
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


def check_sign_in(ui):
    assert checked(ui, "GET", "/api/session") == {"account_name": None}
    for path in ("/api/account/summary", "/api/profile", "/api/orders"):
        assert checked(ui, "GET", path, expected=401)["error"]["code"] == "sign_in_required"
    assert checked(ui, "POST", "/api/session", {"account_name": "../no"}, expected=400)["error"]["code"] == "invalid_account_name"
    assert checked(ui, "POST", "/api/session", {"account_name": f" {USER} "}) == {"account_name": USER}
    assert checked(ui, "GET", "/api/session") == {"account_name": USER}
    cookie = next(iter(ui.cookies))
    assert "HttpOnly" in cookie._rest and cookie._rest["SameSite"] == "Strict" and cookie.value != USER
    assert f'data-account-name="{USER}"'.encode("ascii") in checked(ui, "GET", "/")


def check_account_switch(ui, url):
    buy = {"symbol": "BTC/USDT", "side": "buy", "quantity": "0.01", "order_type": "market"}
    preview = checked(ui, "POST", "/api/orders/preview", buy)
    first_orders = checked(ui, "GET", "/api/orders")["orders"]
    first_ledger = checked(ui, "GET", "/api/account/summary")
    first_profile = checked(ui, "GET", "/api/profile")
    first_cookie = next(iter(ui.cookies))
    other = BrowserClient(url)
    second_name = "student_second"
    checked(other, "GET", "/api/account/summary", expected=401)
    assert checked(other, "POST", "/api/session", {"account_name": second_name})["account_name"] == second_name
    assert checked(ui, "GET", "/api/session")["account_name"] == USER
    assert checked(ui, "DELETE", "/api/session") == {"account_name": None}
    replay = BrowserClient(url)
    replay.cookies.set_cookie(first_cookie)
    checked(replay, "GET", "/api/account/summary", expected=401)
    checked(ui, "GET", "/api/account/summary", expected=401)
    checked(ui, "POST", "/api/session", {"account_name": second_name})
    status, payload = ui.request("POST", "/api/orders/preview", buy, headers={"X-Harbor-Account": USER})
    assert status == 401 and payload["error"]["code"] == "session_changed"
    assert checked(ui, "GET", "/api/orders")["orders"] == []
    assert checked(ui, "GET", "/api/account/summary")["portfolio"]["balances"] != first_ledger["portfolio"]["balances"]
    checked(ui, "GET", "/api/profile", expected=404)
    assert checked(ui, "POST", "/api/orders", {"preview_id": preview["preview_id"]}, expected=409)["error"]["code"] == "preview_expired"
    second_chat = checked(ui, "POST", "/api/assistant/chat", {
        "user_id": USER, "message": "查看我的持仓和挂单", "include_account": True,
    })
    assert second_chat["account"]["state"] == "ok"
    assert {"symbol": "BTC", "quantity": "0.1"} in second_chat["account"]["positions"]
    checked(ui, "POST", "/api/session", {"account_name": USER})
    assert checked(ui, "GET", "/api/orders")["orders"] == first_orders
    assert checked(ui, "GET", "/api/account/summary")["portfolio"]["balances"] == first_ledger["portfolio"]["balances"]
    assert checked(ui, "GET", "/api/profile") == first_profile


def questionnaire_form(ui, middle, ai):
    checked(ui, "GET", "/api/profile", expected=404)
    assert checked(ui, "GET", "/api/education", expected=404)["error"]["code"] == "assessment_required"
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
    lesson = checked(ui, "GET", "/api/education")
    assert lesson["title"]["zh"] == "市价单和限价单" and lesson["focus"]["score"] == 50
    assert all(lesson["content"][lang] for lang in ("zh", "en"))

    leveraged = [{"qid": row["id"], "value": ["E"] if row["multiple"] else "B" if row["id"] == "OC5" else "E"}
                 for row in bank["questions"]]
    capped = checked(ui, "POST", "/api/questionnaire", {**payload, "answers": leveraged})
    assert capped["assessment"]["rai"] == 44 and "LEVERAGE_USE" in capped["assessment"]["flags"]
    assert checked(ui, "GET", "/api/education")["title"]["zh"] == "杠杆风险"
    chat = checked(ui, "POST", "/api/assistant/chat", {"message": "帮我做一个模拟配置"})
    assert chat["mode"] == "clarify" and "杠杆" in chat["reply"]


def derived_profile_api(ui, middle, ai):
    beginner = {**ASSESSMENT, "assessment": {**ASSESSMENT["assessment"],
                "dimensions": {**ASSESSMENT["assessment"]["dimensions"], "KE": 30}}}
    checked(middle, "PUT", f"/api/accounts/{USER}/assessment", beginner)
    assert checked(ui, "GET", "/api/education")["focus"]["score"] == 30
    education = checked(ui, "POST", "/api/assistant/chat", {"message": "什么是滑点？"})
    assert education["mode"] == "education" and education["reply"]

    profile = {**ASSESSMENT, "assessment": {**ASSESSMENT["assessment"], "rai": 66, "risk_level": "C4", "product_cap": "R4"}}
    result = checked(ui, "PUT", "/api/profile", profile)
    actual = checked(ui, "GET", "/api/profile")["assessment"]
    authoritative = checked(middle, "GET", f"/api/accounts/{USER}/assessment")["assessment"]
    assert actual == {"allocation_range": None, **authoritative}
    assert actual == result["assessment"] == checked(ai, "GET", f"/v1/profiles/{USER}")["assessment"]
    assert actual["risk_level"] == "C4" and actual["product_cap"] == "R4"
    assert checked(ui, "GET", "/api/education")["title"]["zh"] == "期限与流动性"
    assert checked(ui, "PUT", "/api/profile", {"assessment": {}}, expected=400)["error"]["code"] == "invalid_assessment"


def check_suitability_warnings(url):
    ui = BrowserClient(url)
    checked(ui, "POST", "/api/session", {"account_name": "student_risk_notice"})
    buy = {"symbol": "BTC/USDT", "side": "buy", "quantity": "0.01", "order_type": "market"}
    preview = checked(ui, "POST", "/api/orders/preview", buy)
    missing = {"code": "assessment_required", "risk_level": None, "product_cap": None, "product_risk": "R4"}
    assert preview["suitability_warning"] == missing
    filled = checked(ui, "POST", "/api/orders", {"preview_id": preview["preview_id"]})
    assert filled["status"] == "filled" and filled["suitability_warning"] == missing

    checked(ui, "PUT", "/api/profile", ASSESSMENT)
    limit = {**buy, "order_type": "limit", "limit_price": "65000"}
    preview = checked(ui, "POST", "/api/orders/preview", limit)
    excess = {"code": "product_cap", "risk_level": "C3", "product_cap": "R3", "product_risk": "R4"}
    assert preview["suitability_warning"] == excess
    pending = checked(ui, "POST", "/api/orders", {"preview_id": preview["preview_id"]})
    assert pending["status"] == "open" and pending["suitability_warning"] == excess
    within_cap = checked(ui, "POST", "/api/orders/preview", {**buy, "symbol": "ETH/USDT"})
    assert "suitability_warning" not in within_cap

    revised = {**ASSESSMENT, "assessment": {**ASSESSMENT["assessment"], "rai": 66, "risk_level": "C4", "product_cap": "R4"}}
    checked(ui, "PUT", "/api/profile", revised)
    assert "suitability_warning" not in checked(ui, "POST", "/api/orders/preview", buy)


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
    with demo_stack(ui_port=0) as (middle, ai, reader, url):
        ui = BrowserClient(url)
        check_html(url)
        health = checked(ui, "GET", "/api/health")
        assert set(health["services"]) == {"middle_office", "ai"}
        assert not health["services"]["ai"]["remote_model_configured"]
        print("PASS frontend assets, loopback origin, and both backend health checks")

        check_sign_in(ui)
        print("PASS account-name sign-in, session cookie, and anonymous access check")

        questionnaire_form(ui, middle, ai)
        print("PASS questionnaire, example RAI 61/C3/R3, risk caps and profile-based education")

        derived_profile_api(ui, middle, ai)
        print("PASS questionnaire scores and product cap persist in middle office and AI")

        check_suitability_warnings(url)
        print("PASS simulated buys remain available with assessment warnings, and updated grades change the warning")

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

        check_account_switch(ui, url)
        print("PASS logout, account switching, isolated balances, profiles, orders, previews and AI context")


def live_comparison(ui, symbol, deadline, *, required_sources=(), minimum=2):
    query = urlencode({"symbol": symbol, "quantity": "0.01", "side": "buy"})
    while True:
        report = checked(ui, "GET", "/api/market/venues?" + query)
        sources = {quote["source"] for quote in report["venues"]}
        if len(sources) >= minimum and sources.issuperset(required_sources):
            break
        if monotonic() >= deadline:
            raise AssertionError(f"Incomplete live quotes for {symbol}: {report}")
        sleep(0.6)
    assert report["market_mode"] == "public" and report["ranking_basis"] == "bid_ask_excluding_fees"
    for quote in report["venues"]:
        assert quote["quote_currency"] == symbol.split("/")[1] and quote["fee_rate"] is None
        assert quote["total"] is None and Decimal(quote["ask"]) >= Decimal(quote["bid"]) > 0 and quote["as_of"]
    assert not (set(report["missing_sources"]) & set(required_sources))
    print(f"PASS public {symbol}: " + ", ".join(sorted(sources)))


def live_checks():
    with demo_stack(ui_port=0, live_market=True) as (middle, ai, _, url):
        ui = BrowserClient(url)
        check_html(url)
        check_sign_in(ui)
        questionnaire_form(ui, middle, ai)
        deadline = monotonic() + 22
        for symbol in USDT_PAIRS:
            live_comparison(ui, symbol, deadline)
        hk_sources = {"HashKey", "OSL"} if find_spec("websockets") else {"HashKey"}
        if "OSL" not in hk_sources:
            print("SKIP OSL comparison (install requirements-live.txt)")
        for symbol in HK_PAIRS:
            live_comparison(ui, symbol, deadline, required_sources=hk_sources, minimum=len(hk_sources))

        chat = checked(ui, "POST", "/api/assistant/chat", {"message": "比较 BTC/USDT 的报价", "market_queries": ["BTC/USDT"]})
        assert len([row for row in chat["market"][0]["venues"] if row["freshness"] == "fresh"]) >= 2
        assert "多来源买卖报价" in chat["reply"]
        print("PASS live venue quotes reach the assistant through middle office")
        if "OSL" in hk_sources:
            hk_chat = checked(ui, "POST", "/api/assistant/chat", {"message": "比较 BTC/HKD 的报价", "market_queries": ["BTC/HKD"]})
            venues = {row["source"] for row in hk_chat["market"][0]["venues"] if row["freshness"] == "fresh"}
            assert venues == hk_sources
            print("PASS the assistant reads both Hong Kong venues in HKD")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-market", action="store_true", help="also query the public exchange feeds")
    args = parser.parse_args()
    offline_checks()
    if args.live_market:
        live_checks()


if __name__ == "__main__":
    main()
