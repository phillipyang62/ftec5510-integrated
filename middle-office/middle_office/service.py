"""Six middle-office modules with a single authoritative simulated ledger."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
import uuid

from .store import Store
from .validation import BusinessError, amount, asset, identifier, iso, number, pair, require, text, timestamp

D = Decimal
DEFAULT_LIMITS = {"max_order_notional": "100000", "concentration_pct": "60", "loss_pct": "10",
                  "aml_large_trade": "10000", "aml_frequency": 5, "aml_window_seconds": 60}


class MiddleOffice:
    def __init__(self, db_path, *, clock=None, max_quote_age=120, product_risks=None, public_sources=()):
        self.store = Store(db_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        require(type(max_quote_age) is int and max_quote_age > 0, "invalid_config", "max_quote_age must be positive")
        self.max_quote_age = max_quote_age
        self.public_sources = frozenset(public_sources)
        self.product_risks = product_risks or {}
        require(isinstance(self.product_risks, dict), "invalid_product_risks", "product risk map must be an object")
        require(all(pair(k) == k and type(v) is int and 1 <= v <= 5 for k, v in self.product_risks.items()),
                "invalid_product_risks", "map normalized pairs to demo risk levels 1-5")

    def _account(self, state, user):
        identifier(user)
        require(user in state["accounts"], "account_not_found", "account does not exist", 404)
        return state["accounts"][user]

    def _audit(self, state, user, action, reference):
        state["audit"].append({"user_id": user, "action": action, "reference": reference,
                               "as_of": iso(self.clock())})

    def _limits(self, payload):
        require(isinstance(payload, dict) and not payload.keys() - DEFAULT_LIMITS.keys(),
                "invalid_limits", "unknown risk parameter")
        limits = DEFAULT_LIMITS.copy()
        for key, value in payload.items():
            if key in {"aml_frequency", "aml_window_seconds"}:
                require(type(value) is int and 1 <= value <= 86400, "invalid_limits", f"invalid {key}")
                limits[key] = value
            else:
                limit = number(value, key, positive=True)
                require(key not in {"concentration_pct", "loss_pct"} or limit <= 100,
                        "invalid_limits", f"{key} must be at most 100")
                limits[key] = amount(limit)
        return limits

    def create_account(self, user, payload):
        identifier(user)
        currency = asset(payload.get("valuation_currency", "USDT"))
        balances = payload.get("initial_balances", {currency: "10000"})
        require(isinstance(balances, dict) and 1 <= len(balances) <= 16, "invalid_balances", "provide 1-16 balances")
        cash = {asset(key): amount(number(value, "initial balance")) for key, value in balances.items()}
        require(set(cash) == {currency}, "invalid_balances", "initial cash must use the account valuation currency")
        positions = {}
        seed = payload.get("initial_positions", [])
        require(isinstance(seed, list) and len(seed) <= 50, "invalid_positions", "at most 50 initial positions")
        for row in seed:
            require(isinstance(row, dict), "invalid_positions", "position must be an object")
            symbol = pair(row.get("symbol"))
            require(symbol.split('/')[1] == currency, "currency_mismatch", "initial position quote currency must match account")
            require(symbol not in positions, "duplicate_position", "initial position repeated")
            qty = number(row.get("quantity"), "quantity", positive=True)
            cost = number(row.get("average_cost"), "average_cost", positive=True)
            positions[symbol] = {"quantity": amount(qty), "cost": amount(qty * cost), "realized_pnl": "0"}
        account = {"user_id": user, "valuation_currency": currency, "balances": cash, "positions": positions,
                   "preferences": {"watchlist": [], "price_alerts": []}, "assessment": None,
                   "limits": self._limits(payload.get("limits", {})), "created_at": iso(self.clock())}
        with self.store.transaction(write=True) as state:
            require(user not in state["accounts"], "account_exists", "account already exists", 409)
            state["accounts"][user] = account
            self._audit(state, user, "account_created", user)
        return {"user_id": user, "valuation_currency": currency, "balances": cash, "mode": "simulation"}

    def preferences(self, user, payload=None):
        with self.store.transaction(write=payload is not None) as state:
            account = self._account(state, user)
            if payload is not None:
                require(not payload.keys() - {"watchlist", "price_alerts"}, "invalid_preferences", "unknown preference field")
                updated = account["preferences"].copy()
                if "watchlist" in payload:
                    watch = payload["watchlist"]
                    require(isinstance(watch, list) and len(watch) <= 50, "invalid_watchlist", "at most 50 symbols")
                    updated["watchlist"] = list(dict.fromkeys(pair(item) for item in watch))
                if "price_alerts" in payload:
                    alerts = payload["price_alerts"]
                    require(isinstance(alerts, list) and len(alerts) <= 50, "invalid_alerts", "at most 50 price rules")
                    clean = []
                    for rule in alerts:
                        require(isinstance(rule, dict), "invalid_alerts", "price rule must be an object")
                        require(isinstance(rule.get("direction"), str) and rule["direction"] in {"above", "below"}, "invalid_direction", "use above or below")
                        clean.append({"symbol": pair(rule.get("symbol")), "direction": rule["direction"],
                                      "price": amount(number(rule.get("price"), "price", positive=True))})
                    updated["price_alerts"] = clean
                account["preferences"] = updated
                self._audit(state, user, "preferences_updated", user)
            return account["preferences"]

    def assessment(self, user, payload=None):
        # Store only the upstream's derived scores; no raw questionnaire answers.
        with self.store.transaction(write=payload is not None) as state:
            account = self._account(state, user)
            if payload is not None:
                assessment = payload.get("assessment")
                require(isinstance(assessment, dict) and isinstance(assessment.get("dimensions"), dict),
                        "invalid_assessment", "derived assessment and dimensions required")
                dims = assessment["dimensions"]
                scores = {}
                for key in ("FC", "RA", "KE", "BD", "OC"):
                    value = dims.get(key)
                    require(type(value) in {int, float} and 0 <= value <= 100, "invalid_score", f"invalid {key}")
                    scores[key] = value
                rai = assessment.get("rai")
                require(type(rai) is int and 0 <= rai <= 100 and rai <= int(scores["FC"] + 20.5),
                        "invalid_rai", "RAI must agree with financial capacity ceiling")
                level = next(i for i, upper in enumerate((24, 44, 64, 79, 100), 1) if rai <= upper)
                require(assessment.get("risk_level") == f"C{level}" and assessment.get("product_cap") == f"R{level}",
                        "invalid_level", "C/R levels must agree with upstream RAI")
                clean = {"dimensions": scores, "rai": rai, "risk_level": f"C{level}", "product_cap": f"R{level}"}
                confidence = assessment.get("confidence")
                if confidence is not None:
                    require(type(confidence) in {int, float} and 0 <= confidence <= 1,
                            "invalid_confidence", "confidence must be between 0 and 1")
                    clean["confidence"] = confidence
                for key in ("flags", "prohibitions"):
                    codes = assessment.get(key, [])
                    require(isinstance(codes, list) and len(codes) <= 16, "invalid_codes", "at most 16 codes")
                    require(all(isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", code)
                                for code in codes), "invalid_codes", "invalid assessment code")
                    clean[key] = codes
                allocation = assessment.get("allocation_range")
                if allocation is not None:
                    require(isinstance(allocation, dict), "invalid_allocation", "allocation must be an object")
                    lo, hi = allocation.get("min_pct"), allocation.get("max_pct")
                    require(type(lo) in {int, float} and type(hi) in {int, float} and 0 <= lo <= hi <= 100,
                            "invalid_allocation", "invalid allocation range")
                    clean["allocation_range"] = {"min_pct": lo, "max_pct": hi}
                record = {"assessment": clean}
                for key, default in (("questionnaire_version", "1.0.0"), ("source", "questionnaire")):
                    code = payload.get(key, default)
                    require(isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", code),
                            "invalid_metadata", "invalid questionnaire metadata")
                    record[key] = code
                band = payload.get("dimensions", {}).get("wealth_band") if isinstance(payload.get("dimensions", {}), dict) else None
                require(band is None or isinstance(band, str) and band in {"low", "medium", "high"}, "invalid_band", "invalid wealth_band")
                if band is not None:
                    record["dimensions"] = {"wealth_band": band}
                if account["assessment"] != record:
                    account["assessment"] = record
                    self._audit(state, user, "assessment_updated", user)
            require(account["assessment"] is not None, "assessment_not_found", "assessment has not been supplied", 404)
            return account["assessment"]

    def _fresh(self, quote, *, at=None):
        age = ((at or self.clock()) - timestamp(quote["as_of"])).total_seconds()
        return -15 <= age <= self.max_quote_age

    def _visible_quote(self, quote):
        return not self.public_sources or (quote["source"] in self.public_sources and "timestamp_source" in quote)

    def _quote(self, state, symbol, venue=None, *, at=None):
        candidates = [q for q in state["quotes"].values() if q["symbol"] == symbol and self._visible_quote(q)
                      and (venue is None or q["source"] == venue) and self._fresh(q, at=at)]
        require(candidates, "quote_unavailable", "no fresh quote for this pair and source", 409)
        # Valuation uses the newest source, with deterministic source tie breaking.
        return max(candidates, key=lambda q: (q["as_of"], q["source"]))

    def ingest_quotes(self, payload):
        batch = payload.get("quotes")
        require(isinstance(batch, list) and 1 <= len(batch) <= 500, "invalid_batch", "provide 1-500 quotes")
        clean = []
        for raw in batch:
            require(isinstance(raw, dict), "invalid_quote", "quote must be an object")
            symbol = pair(raw.get("symbol"))
            source = text(raw.get("source"), "source", 64)
            as_of = timestamp(raw.get("as_of"))
            require((as_of - self.clock()).total_seconds() <= 15, "future_quote", "quote is too far in the future")
            price = number(raw.get("price"), "price", positive=True)
            bid = number(raw.get("bid", price), "bid", positive=True)
            ask = number(raw.get("ask", price), "ask", positive=True)
            require(bid <= ask, "crossed_quote", "bid must not exceed ask")
            raw_fee = raw.get("fee_rate", "0")
            fee = number(raw_fee, "fee_rate") if raw_fee is not None else None
            require(fee is None or fee <= D("0.05"), "invalid_fee", "fee_rate must be between 0 and 0.05")
            aliases = raw.get("aliases", [])
            require(isinstance(aliases, list) and len(aliases) <= 16, "invalid_aliases", "at most 16 aliases")
            quote = {"symbol": symbol, "source": source, "as_of": iso(as_of), "price": amount(price),
                     "bid": amount(bid), "ask": amount(ask), "fee_rate": amount(fee) if fee is not None else None,
                     "name": text(raw.get("name", symbol.split('/')[0]), "name", 80),
                     "aliases": [text(alias, "alias", 80) for alias in aliases]}
            for field in ("bid_size", "ask_size"):
                if field in raw:
                    quote[field] = amount(number(raw[field], field))
            if "timestamp_source" in raw:
                origin = raw["timestamp_source"]
                require(origin in ("exchange", "collected"), "invalid_timestamp_source", "invalid quote timestamp basis")
                quote["timestamp_source"] = origin
            clean.append(quote)
        with self.store.transaction(write=True) as state:
            accepted = 0
            for quote in clean:
                key = quote["symbol"] + "@" + quote["source"]
                previous = state["quotes"].get(key)
                if previous and previous["as_of"] >= quote["as_of"]:
                    continue
                state["quotes"][key] = quote
                accepted += 1
            # Event-driven full-fill simulation also works after restarting the service.
            for order in list(state["orders"].values()):
                if order["status"] == "open":
                    self._try_fill(state, order)
            for user in state["accounts"]:
                self._monitor(state, user)
            return {"accepted": accepted, "ignored": len(clean) - accepted}

    def quotes(self, query="", limit=20, *, all_sources=False):
        require(type(limit) is int and 1 <= limit <= 50, "invalid_limit", "limit must be 1-50")
        require(isinstance(query, str) and len(query) <= 80, "invalid_query", "q must be at most 80 characters")
        key = query.strip().casefold().replace("-", "/").replace("_", "/")
        with self.store.transaction() as state:
            matches = []
            for quote in state["quotes"].values():
                if not self._visible_quote(quote):
                    continue
                terms = [quote["symbol"], quote["symbol"].split('/')[0], quote["name"], *quote["aliases"]]
                if not key or any(key == term.casefold() for term in terms):
                    matches.append({**quote, "freshness": "fresh" if self._fresh(quote) else "stale"})
            if not all_sources:
                # AI's quote book is keyed by pair, so provide ONE valuation source per pair.
                merged = {}
                for quote in sorted(matches, key=lambda q: (self._fresh(q), q["as_of"], q["source"])):
                    merged[quote["symbol"]] = quote
                matches = list(merged.values())
            return {"quotes": sorted(matches, key=lambda q: (q["symbol"], q["source"]))[:limit]}

    def comparison(self, symbol, quantity="1", side="buy"):
        symbol = pair(symbol)
        qty = number(quantity, "quantity", positive=True)
        require(isinstance(side, str) and side in {"buy", "sell"}, "invalid_side", "side must be buy or sell")
        currency = symbol.split('/')[1]
        bid_or_ask = "ask" if side == "buy" else "bid"
        with self.store.transaction() as state:
            venues = []
            excluded = []
            for quote in state["quotes"].values():
                if quote["symbol"] != symbol or not self._visible_quote(quote):
                    continue
                if not self._fresh(quote):
                    excluded.append(quote["source"])
                    continue
                price = D(quote[bid_or_ask])
                value = qty * price
                rate = quote["fee_rate"]
                fee = D(amount(value * D(rate))) if rate is not None else None
                net = amount(D(amount(value)) + (fee if side == "buy" else -fee)) if fee is not None else None
                size = quote.get(bid_or_ask + "_size")
                venues.append({**quote, "execution_price": amount(price), "fee": amount(fee) if fee is not None else None,
                               "total": net, "quote_currency": currency, "notional": amount(value),
                               "quantity_covered": qty <= D(size) if size is not None else None})
            pre_fee = bool(self.public_sources) or any(q["fee_rate"] is None for q in venues)
            if pre_fee:
                direction = 1 if side == "buy" else -1
                venues.sort(key=lambda q: (q["quantity_covered"] is False, direction * D(q["execution_price"]), q["source"]))
            else:
                venues.sort(key=lambda q: (D(q["total"]), q["source"]), reverse=side == "sell")
            eligible = [q for q in venues if q["quantity_covered"] is not False]
            missing = self.public_sources - {q["source"] for q in venues} - set(excluded)
            return {"symbol": symbol, "side": side, "quantity": amount(qty), "mode": "simulation",
                    "market_mode": "public" if self.public_sources else "simulation",
                    "venues": venues, "excluded_sources": sorted(excluded), "missing_sources": sorted(missing),
                    "status": "ok" if len(venues) >= 2 else "insufficient_sources",
                    "recommended_source": eligible[0]["source"] if len(eligible) >= 2 else None,
                    "ranking_basis": "bid_ask_excluding_fees" if pre_fee else "total_with_fees",
                    "slippage_model": "top_of_book_only" if self.public_sources else "none_full_fill_at_bid_ask"}

    def _reserved(self, state, user, currency=None, symbol=None, exclude=None):
        result = D(0)
        for order in state["orders"].values():
            if order["user_id"] != user or order["status"] != "open" or order["order_id"] == exclude:
                continue
            if currency and order["side"] == "buy" and order["symbol"].split('/')[1] == currency:
                result += D(order["reserved_cash"])
            if symbol and order["side"] == "sell" and order["symbol"] == symbol:
                result += D(order["quantity"])
        return result

    def _order_terms(self, payload):
        symbol = pair(payload.get("symbol"))
        side = payload.get("side")
        kind = payload.get("order_type", "market")
        require(isinstance(side, str) and side in {"buy", "sell"}, "invalid_side", "side must be buy or sell")
        require(isinstance(kind, str) and kind in {"market", "limit"}, "invalid_order_type", "use market or limit")
        qty = number(payload.get("quantity"), "quantity", positive=True)
        limit = number(payload.get("limit_price"), "limit_price", positive=True) if kind == "limit" else None
        venue = payload.get("source")
        if venue is not None:
            venue = text(venue, "source", 64)
        return {"symbol": symbol, "side": side, "order_type": kind, "quantity": amount(qty),
                "limit_price": amount(limit) if limit else None, "source": venue}

    def _order_quote(self, state, account, terms):
        self._check_suitability(account, terms)
        return self._execution_quote(state, terms)

    def _check_order(self, state, account, user, terms, quote):
        qty, side, symbol = D(terms["quantity"]), terms["side"], terms["symbol"]
        price = D(terms["limit_price"] or quote["ask" if side == "buy" else "bid"])
        notional = qty * price
        require(notional >= D("0.00000001"), "order_too_small", "notional is below the ledger precision", 409)
        require(notional <= D(account["limits"]["max_order_notional"]), "order_limit", "order exceeds configured notional limit", 409)
        currency = symbol.split('/')[1]
        fee = D(amount(notional * D(quote["fee_rate"] or "0")))
        value = D(amount(notional))
        if side == "buy":
            total = value + fee
            available = D(account["balances"].get(currency, "0")) - self._reserved(state, user, currency=currency)
            require(available >= total, "insufficient_balance", "insufficient available quote currency", 409)
        else:
            total = value - fee
            held = D(account["positions"].get(symbol, {}).get("quantity", "0"))
            available = held - self._reserved(state, user, symbol=symbol)
            require(available >= qty, "insufficient_position", "insufficient available position", 409)
        return {"source": quote["source"], "as_of": quote["as_of"], "fee_rate": quote["fee_rate"],
                "quote_currency": currency, "reference_price": amount(price),
                "notional": amount(value), "fee": amount(fee), "total": amount(total),
                "fee_assumed": quote["fee_rate"] is None}

    def preview_order(self, user, payload):
        terms = self._order_terms(payload)
        with self.store.transaction() as state:
            account = self._account(state, user)
            quote = self._order_quote(state, account, terms)
            estimate = self._check_order(state, account, user, terms, quote)
        return {**terms, **estimate, "mode": "simulation"}

    def place_order(self, user, payload):
        identifier(user)
        request_id = identifier(payload.get("request_id"), "request_id")
        terms = self._order_terms(payload)
        fingerprint = json.dumps([terms[key] for key in
                                  ("symbol", "side", "order_type", "quantity", "limit_price", "source")])
        with self.store.transaction(write=True) as state:
            account = self._account(state, user)
            previous = next((o for o in state["orders"].values() if o["user_id"] == user and o["request_id"] == request_id), None)
            if previous:
                require(previous["fingerprint"] == fingerprint, "request_conflict", "request_id reused with different input", 409)
                return self._public_order(previous)
            order = {"order_id": "ord_" + uuid.uuid4().hex, "user_id": user, "request_id": request_id, **terms,
                     "status": "open", "reserved_cash": "0", "reason": None,
                     "fingerprint": fingerprint, "created_at": iso(self.clock()), "updated_at": iso(self.clock())}
            try:
                quote = self._order_quote(state, account, terms)
                order.update(source=quote["source"], fee_rate=quote["fee_rate"] or "0")
                estimate = self._check_order(state, account, user, terms, quote)
                if terms["side"] == "buy":
                    order["reserved_cash"] = estimate["total"]
            except BusinessError as error:
                order["status"], order["reason"] = "rejected", error.code
            state["orders"][order["order_id"]] = order
            self._audit(state, user, "order_" + order["status"], order["order_id"])
            if order["status"] == "open":
                self._try_fill(state, order)
            self._monitor(state, user)
            return self._public_order(order)

    def _check_suitability(self, account, order):
        require(order["symbol"].split('/')[1] == account["valuation_currency"],
                "currency_mismatch", "order quote currency must match account valuation currency", 409)
        if order["side"] != "buy":
            return
        record = account["assessment"]
        if record:
            require(not record["assessment"]["prohibitions"], "assessment_prohibition", "upstream assessment prohibits new buys", 409)
        risk = self.product_risks.get(order["symbol"])
        if risk is not None:
            require(record is not None, "assessment_required", "this configured product requires an assessment", 409)
            cap = int(record["assessment"]["product_cap"][1])
            require(risk <= cap, "product_cap", "product exceeds questionnaire risk cap", 409)

    def _execution_quote(self, state, order):
        candidates = [q for q in state["quotes"].values() if q["symbol"] == order["symbol"]
                      and self._visible_quote(q) and self._fresh(q)
                      and (order["source"] is None or q["source"] == order["source"])]
        require(candidates, "quote_unavailable", "no fresh execution quote", 409)
        buy = order["side"] == "buy"
        if self.public_sources and order["order_type"] == "market":
            size_key = "ask_size" if buy else "bid_size"
            candidates = [q for q in candidates if D(q.get(size_key, "0")) >= D(order["quantity"])]
            require(candidates, "insufficient_top_size", "top of book cannot cover the simulated quantity", 409)
        def total(q):
            px = D(q["ask"] if buy else q["bid"])
            fee = D(q["fee_rate"] or "0")
            return px * (1 + fee if buy else 1 - fee)
        return sorted(candidates, key=lambda q: (total(q) if buy else -total(q), q["source"]))[0]

    def _try_fill(self, state, order):
        if order["status"] != "open":
            return
        account = state["accounts"][order["user_id"]]
        try:
            self._check_suitability(account, order)
        except BusinessError as error:
            order.update(status="rejected", reason=error.code, reserved_cash="0", updated_at=iso(self.clock()))
            self._audit(state, order["user_id"], "order_rejected", order["order_id"])
            return
        try:
            quote = self._execution_quote(state, order)
        except BusinessError:
            return
        qty = D(order["quantity"])
        if self.public_sources and qty > D(quote.get("ask_size" if order["side"] == "buy" else "bid_size", "0")):
            return
        price = D(quote["ask"] if order["side"] == "buy" else quote["bid"])
        limit = D(order["limit_price"]) if order["limit_price"] else None
        if limit and ((order["side"] == "buy" and price > limit) or (order["side"] == "sell" and price < limit)):
            return
        account = state["accounts"][order["user_id"]]
        value = D(amount(qty * price))
        # Lock fee rate at acceptance, so new quotes cannot exceed a reserved budget.
        fee = D(amount(value * D(order["fee_rate"])))
        symbol = order["symbol"]
        currency = symbol.split('/')[1]
        cash = D(account["balances"].get(currency, "0"))
        position = account["positions"].setdefault(symbol, {"quantity": "0", "cost": "0", "realized_pnl": "0"})
        held, cost = D(position["quantity"]), D(position["cost"])
        if order["side"] == "buy":
            debit = value + fee
            if cash - self._reserved(state, order["user_id"], currency=currency, exclude=order["order_id"]) < debit:
                order.update(status="rejected", reason="insufficient_balance", reserved_cash="0", updated_at=iso(self.clock()))
                self._audit(state, order["user_id"], "order_rejected", order["order_id"])
                return
            cash -= debit
            held += qty
            cost += debit
        else:
            require(held >= qty, "ledger_invariant", "position cannot cover the confirmed fill", 500)
            allocated = cost if held == qty else D(amount(cost * qty / held))
            realized = value - fee - allocated
            position["realized_pnl"] = amount(D(position["realized_pnl"]) + realized)
            held -= qty
            cost -= allocated
            cash += value - fee
        account["balances"][currency] = amount(cash)
        position.update(quantity=amount(held), cost=amount(cost))
        trade_id = "trd_" + order["order_id"][4:]
        order.update(status="filled", reserved_cash="0", filled_quantity=amount(qty),
                     execution_price=amount(price), fee=amount(fee), trade_id=trade_id, updated_at=iso(self.clock()))
        state["trades"][trade_id] = {"trade_id": trade_id, "order_id": order["order_id"], "user_id": order["user_id"],
                                     "symbol": symbol, "side": order["side"], "quantity": amount(qty),
                                     "price": amount(price), "notional": amount(value), "fee": amount(fee),
                                     "source": quote["source"], "as_of": iso(self.clock())}
        self._audit(state, order["user_id"], "fill_booked", trade_id)
        self._aml(state, order["user_id"], state["trades"][trade_id])

    def _public_order(self, order):
        return {key: value for key, value in order.items() if key != "fingerprint"}

    def orders(self, user, *, open_only=False):
        with self.store.transaction() as state:
            self._account(state, user)
            return [self._public_order(o) for o in state["orders"].values()
                    if o["user_id"] == user and (not open_only or o["status"] == "open")]

    def cancel_order(self, user, order_id):
        with self.store.transaction(write=True) as state:
            self._account(state, user)
            order = state["orders"].get(order_id)
            require(order is not None and order["user_id"] == user, "order_not_found", "order not found", 404)
            if order["status"] == "cancelled":
                return self._public_order(order)
            require(order["status"] == "open", "order_final", "only open orders can be cancelled", 409)
            order.update(status="cancelled", reserved_cash="0", updated_at=iso(self.clock()))
            self._audit(state, user, "order_cancelled", order_id)
            return self._public_order(order)

    def _snapshot(self, state, user, *, as_of=None):
        account = self._account(state, user)
        assets = {key: D(value) for key, value in account["balances"].items()}
        for symbol, row in account["positions"].items():
            base = symbol.split('/')[0]
            assets[base] = assets.get(base, D(0)) + D(row["quantity"])
        orders = [{key: o[key] for key in ("order_id", "symbol", "side", "quantity", "limit_price", "status")}
                  for o in state["orders"].values() if o["user_id"] == user and o["status"] == "open"]
        positions = [{"symbol": key, "quantity": amount(value)} for key, value in sorted(assets.items()) if value != 0]
        return {"as_of": iso(as_of or self.clock()), "positions": positions[:50], "open_orders": orders[:50],
                "truncated": len(positions) > 50 or len(orders) > 50}

    def snapshot(self, user):
        with self.store.transaction() as state:
            return self._snapshot(state, user)

    def _portfolio(self, state, user, *, as_of=None):
        as_of = as_of or self.clock()
        account = self._account(state, user)
        currency = account["valuation_currency"]
        rows, reasons, quotes = [], [], {}
        total, unrealized, realized = D(0), D(0), D(0)
        for symbol, holding in account["positions"].items():
            qty, cost = D(holding["quantity"]), D(holding["cost"])
            row = {"symbol": symbol, **holding, "average_cost": amount(cost / qty) if qty else "0"}
            if symbol.split('/')[1] == currency:
                realized += D(holding["realized_pnl"])
            else:
                reasons.append("mixed_cost_currency")
            try:
                quote = self._quote(state, symbol, at=as_of) if qty else None
                if quote:
                    quotes[symbol] = quote.copy()
                value = qty * D(quote["price"]) if quote else D(0)
                row.update(state="valued", market_value=amount(value), unrealized_pnl=amount(value - cost),
                           market_price=quote["price"] if quote else None,
                           as_of=quote["as_of"] if quote else None, source=quote["source"] if quote else None)
                if symbol.split('/')[1] == currency:
                    total += value
                    unrealized += value - cost
            except BusinessError:
                row.update(state="unvalued", market_value=None, unrealized_pnl=None,
                           market_price=None, as_of=None, source=None)
                reasons.append("missing_or_stale_quote")
            rows.append(row)
        for cash_currency, value in account["balances"].items():
            if D(value) == 0:
                continue
            if cash_currency == currency:
                total += D(value)
            else:
                try:
                    symbol = f"{cash_currency}/{currency}"
                    quote = self._quote(state, symbol, at=as_of)
                    quotes[symbol] = quote.copy()
                    total += D(value) * D(quote["price"])
                except BusinessError:
                    reasons.append("unvalued_cash")
        balances = [{"currency": code, "total": value,
                     "reserved": amount(self._reserved(state, user, currency=code)),
                     "available": amount(D(value) - self._reserved(state, user, currency=code))}
                    for code, value in sorted(account["balances"].items())]
        # Include currencies fully consumed by accepted reservations in the account ledger.
        fees = {}
        for trade in state["trades"].values():
            if trade["user_id"] == user:
                code = trade["symbol"].split('/')[1]
                fees[code] = amount(D(fees.get(code, "0")) + D(trade["fee"]))
        return {"user_id": user, "as_of": iso(as_of), "valuation_currency": currency,
                "state": "partial" if reasons else "ok", "reasons": sorted(set(reasons)),
                "total_assets": None if reasons else amount(total), "observed_assets": amount(total),
                "unrealized_pnl": None if reasons else amount(unrealized), "realized_pnl": amount(realized),
                "fees_by_currency": fees, "balances": balances, "positions": rows,
                "valuation_quotes": [quotes[key] for key in sorted(quotes)]}

    def portfolio(self, user):
        with self.store.transaction() as state:
            return self._portfolio(state, user)

    def _position_risk_values(self, portfolio):
        """Use the same unrounded ratios for monitoring and the AI report."""
        if portfolio["state"] != "ok" or D(portfolio["total_assets"]) <= 0:
            return
        total = D(portfolio["total_assets"])
        for row in portfolio["positions"]:
            concentration = D(row["market_value"]) / total * 100
            cost = D(row["cost"])
            loss = -D(row["unrealized_pnl"]) / cost * 100 if cost else D(0)
            yield row["symbol"], "concentration_pct", concentration
            yield row["symbol"], "loss_pct", loss

    def analysis_snapshot(self, user):
        """Read ledger, valuation quotes and official numbers in ONE transaction.

        Consumers must reuse this response when comparing numbers; a second
        HTTP request can legitimately observe a later ledger or quote version.
        """
        with self.store.transaction() as state:
            as_of = self.clock()
            account = self._account(state, user)
            snapshot = self._snapshot(state, user, as_of=as_of)
            portfolio = self._portfolio(state, user, as_of=as_of)
            metrics = []
            for symbol, rule, value in self._position_risk_values(portfolio):
                threshold = D(account["limits"][rule])
                metrics.append({"symbol": symbol, "rule": rule, "value": amount(value),
                                "threshold": amount(threshold), "breached": value >= threshold})
            reasons = portfolio["reasons"] + (["account_truncated"] if snapshot["truncated"] else [])
            report = {"schema_version": 1, "user_id": user, "as_of": iso(as_of),
                      "state": "partial" if reasons else "ok", "reasons": reasons,
                      "account": snapshot, "portfolio": portfolio,
                      "risk": {"state": portfolio["state"], "position_metrics": metrics},
                      "basis": {"ledger": "middle_office", "valuation": "newest_fresh_quote_per_pair",
                                "quote_max_age_seconds": self.max_quote_age,
                                "concentration_denominator": "total_assets_including_cash",
                                "loss_formula": "-unrealized_pnl/cost*100",
                                "decimal_places": 8, "rounding": "ROUND_HALF_EVEN"}}
            encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            report["snapshot_id"] = "ana_" + hashlib.sha256(encoded).hexdigest()
            return report

    def _alert(self, state, user, category, key, evidence):
        existing = next((a for a in state["alerts"].values() if a["user_id"] == user and a["key"] == key
                         and (category == "aml" or a["active"])), None)
        if existing:
            return
        alert_id = "alt_" + uuid.uuid4().hex
        state["alerts"][alert_id] = {"alert_id": alert_id, "user_id": user, "category": category,
            "key": key, "active": True, "status": "pending", "evidence": evidence,
            "created_at": iso(self.clock()), "review": None}
        self._audit(state, user, "alert_created", alert_id)

    def _monitor(self, state, user):
        portfolio = self._portfolio(state, user)
        account = state["accounts"][user]
        active_keys = set()
        for symbol, name, value in self._position_risk_values(portfolio):
            threshold = D(account["limits"][name])
            if value >= threshold:
                key = name + ":" + symbol
                active_keys.add(key)
                self._alert(state, user, "position_risk", key,
                            {"rule": name, "symbol": symbol, "value": amount(value), "threshold": amount(threshold)})
        for index, rule in enumerate(account["preferences"]["price_alerts"]):
            try:
                quote = self._quote(state, rule["symbol"])
            except BusinessError:
                continue
            value, threshold = D(quote["price"]), D(rule["price"])
            if (rule["direction"] == "above" and value >= threshold) or (rule["direction"] == "below" and value <= threshold):
                key = "price:" + str(index) + ":" + json.dumps(rule, sort_keys=True)
                active_keys.add(key)
                self._alert(state, user, "price", key, {**rule, "value": amount(value), "as_of": quote["as_of"]})
        # Missing quotes mean unknown risk, so keep previous position alerts active.
        for alert in state["alerts"].values():
            if alert["user_id"] == user and alert["category"] != "aml" and alert["key"] not in active_keys:
                if alert["category"] != "position_risk" or portfolio["state"] == "ok":
                    alert["active"] = False

    def _aml(self, state, user, trade):
        limits = state["accounts"][user]["limits"]
        if D(trade["notional"]) >= D(limits["aml_large_trade"]):
            self._alert(state, user, "aml", "large:" + trade["trade_id"],
                        {"rule": "large_trade", "trade_ids": [trade["trade_id"]], "value": trade["notional"],
                         "currency": trade["symbol"].split('/')[1], "threshold": limits["aml_large_trade"]})
        recent = [t["trade_id"] for t in state["trades"].values() if t["user_id"] == user
                  and 0 <= (self.clock() - timestamp(t["as_of"])).total_seconds() <= limits["aml_window_seconds"]]
        if len(recent) >= limits["aml_frequency"]:
            self._alert(state, user, "aml", "frequency:" + trade["trade_id"],
                        {"rule": "frequent_trades", "trade_ids": recent, "count": len(recent),
                         "window_seconds": limits["aml_window_seconds"], "threshold": limits["aml_frequency"]})

    def alerts(self, user):
        with self.store.transaction(write=True) as state:
            self._account(state, user)
            self._monitor(state, user)
            return [a for a in state["alerts"].values() if a["user_id"] == user]

    def review_alert(self, user, alert_id, payload):
        reviewer = identifier(payload.get("reviewer"), "reviewer")
        decision = payload.get("decision")
        require(isinstance(decision, str) and decision in {"closed", "escalated"}, "invalid_decision", "use closed or escalated")
        note = text(payload.get("note"), "note", 1000)
        with self.store.transaction(write=True) as state:
            self._account(state, user)
            alert = state["alerts"].get(alert_id)
            require(alert is not None and alert["user_id"] == user, "alert_not_found", "alert not found", 404)
            review = {"reviewer": reviewer, "decision": decision, "note": note}
            if alert["review"]:
                require(all(alert["review"][k] == v for k, v in review.items()),
                        "already_reviewed", "review is already final", 409)
                return alert
            alert.update(status=decision, review={**review, "as_of": iso(self.clock())})
            self._audit(state, user, "alert_reviewed", alert_id)
            return alert

    def records(self, user, kind):
        require(kind in {"trades", "audit"}, "invalid_kind", "invalid record collection")
        with self.store.transaction() as state:
            self._account(state, user)
            rows = state[kind].values() if kind == "trades" else state[kind]
            return [r for r in rows if r["user_id"] == user]
