"""Same-origin gateway for one local Harbor Invest demo account."""

import json
import re
from http.client import HTTPConnection, HTTPSConnection, HTTPException
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

from questionnaire import QuestionnaireError, assess, public_bank


MAX_BODY = 64 * 1024
MAX_RESPONSE = 2 * 1024 * 1024
PREVIEW_TTL = 60
ORDER_ID = re.compile(r"ord_[a-f0-9]{32}")


class GatewayError(Exception):
    def __init__(self, status, code, message):
        self.status = status
        self.payload = {"error": {"code": code, "message": message}}


class JsonService:
    def __init__(self, name, base_url, token=None, *, timeout=6):
        url = urlsplit(base_url)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username is not None
                or url.path not in {"", "/"} or url.query or url.fragment):
            raise ValueError(f"{name} must use a bare HTTP or HTTPS service URL")
        self.connection = HTTPSConnection if url.scheme == "https" else HTTPConnection
        self.name, self.host, self.port = name, url.hostname, url.port
        self.token, self.timeout = token, timeout

    def request(self, method, path, body=None):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body, allow_nan=False).encode("utf-8")
        connection = self.connection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE or 300 <= response.status < 400:
                raise ValueError("unexpected upstream response")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            return response.status, data
        except (OSError, HTTPException, ValueError, RecursionError) as error:
            raise GatewayError(502, "upstream_unavailable", f"{self.name} did not return a usable response") from error
        finally:
            connection.close()


def query_string(params, *names):
    selected = {name: params[name][0] for name in names if name in params}
    return "?" + urlencode(selected) if selected else ""


class Gateway:
    def __init__(self, ai, middle, user_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
            raise ValueError("invalid demo account identifier")
        self.ai, self.middle, self.user_id = ai, middle, user_id
        self.account_path = "/api/accounts/" + user_id
        self.profile_path = "/v1/profiles/" + user_id
        self.profile_lock = Lock()
        self.synced_assessment = None
        self.preview_lock = Lock()
        self.previews = {}

    def _health(self):
        services = {}
        for client in (self.ai, self.middle):
            try:
                status, data = client.request("GET", "/health")
                services[client.name] = data if status == 200 else {"status": "unavailable"}
            except GatewayError:
                services[client.name] = {"status": "unavailable"}
        ok = all(service.get("status") == "ok" for service in services.values())
        return (200 if ok else 503), {"status": "ok" if ok else "partial", "mode": "simulation",
                                     "services": services}

    def _sync_profile(self, assessment):
        try:
            status, data = self.ai.request("PUT", self.profile_path, assessment)
        except GatewayError:
            status = 502
        if status != 200:
            raise GatewayError(502, "profile_sync_pending", "Middle office saved the scores; AI sync is pending")
        self.synced_assessment = assessment
        return data

    def _ensure_profile(self):
        # Retry an interrupted two-service update before serving a chat.
        with self.profile_lock:
            status, assessment = self.middle.request("GET", self.account_path + "/assessment")
            if status == 200:
                if assessment != self.synced_assessment:
                    self._sync_profile(assessment)
            elif assessment.get("error", {}).get("code") != "assessment_not_found":
                raise GatewayError(502, "profile_unavailable", "Cannot read the middle-office assessment")

    def _save_profile(self, body):
        with self.profile_lock:
            status, assessment = self.middle.request("PUT", self.account_path + "/assessment", body)
            if status != 200:
                return status, assessment
            self.synced_assessment = None
            return 200, self._sync_profile(assessment)

    def _preview(self, body):
        status, estimate = self.middle.request("POST", self.account_path + "/orders/preview", body)
        if status != 200:
            return status, estimate
        preview_id = uuid4().hex
        terms = {key: estimate[key] for key in ("symbol", "side", "order_type", "quantity", "limit_price", "source")}
        with self.preview_lock:
            now = monotonic()
            self.previews = {key: record for key, record in self.previews.items() if record[0] > now}
            if len(self.previews) >= 256:
                raise GatewayError(429, "too_many_previews", "Wait for earlier previews to expire")
            self.previews[preview_id] = now + PREVIEW_TTL, {**terms, "request_id": preview_id}
        return 200, {**estimate, "preview_id": preview_id, "expires_in": PREVIEW_TTL}

    def _submit(self, body):
        preview_id = body.get("preview_id")
        if set(body) != {"preview_id"} or not isinstance(preview_id, str):
            raise GatewayError(400, "preview_required", "Submit the preview_id returned by order preview")
        with self.preview_lock:
            record = self.previews.get(preview_id)
            if record is None or record[0] <= monotonic():
                raise GatewayError(409, "preview_expired", "Preview the order again before confirming")
            terms = record[1]
        return self.middle.request("POST", self.account_path + "/orders", terms)

    def _order_status(self, order_id):
        status, data = self.middle.request("GET", self.account_path + "/orders")
        if status != 200:
            return status, data
        for order in data["orders"]:
            if order["order_id"] == order_id:
                return 200, order
        raise GatewayError(404, "order_not_found", "This account has no order with that ID")

    def dispatch(self, method, url, body):
        path = url.path
        try:
            params = parse_qs(url.query, keep_blank_values=True, max_num_fields=16)
        except ValueError as error:
            raise GatewayError(400, "invalid_query", "Too many query parameters") from error
        if path == "/api/health" and method == "GET":
            return self._health()
        if path == "/api/questionnaire" and method == "GET":
            return 200, public_bank()
        if path == "/api/questionnaire" and method == "POST":
            try:
                assessment = assess(body)
            except QuestionnaireError as error:
                raise GatewayError(422, error.code, str(error)) from error
            return self._save_profile(assessment)
        if path == "/api/profile" and method == "GET":
            self._ensure_profile()
            return self.ai.request(method, self.profile_path)
        if path == "/api/profile" and method == "PUT":
            return self._save_profile(body)
        if path == "/api/assistant/chat" and method == "POST":
            self._ensure_profile()
            return self.ai.request(method, "/v1/chat", {**body, "user_id": self.user_id})
        if path == "/api/risk" and method == "GET":
            return self.ai.request(method, "/v1/risk/" + self.user_id + query_string(params, "quote_currency"))
        if path == "/api/market/venues" and method == "GET":
            query = query_string(params, "symbol", "quantity", "side")
            return self.middle.request(method, "/api/comparison" + query)
        if path == "/api/account/summary" and method == "GET":
            return self.middle.request(method, self.account_path + "/analysis_snapshot")
        if path == "/api/account/transactions" and method == "GET":
            return self.middle.request(method, self.account_path + "/trades" + query_string(params, "offset", "limit"))
        if path == "/api/orders/preview" and method == "POST":
            return self._preview(body)
        if path == "/api/orders" and method == "POST":
            return self._submit(body)
        if path == "/api/orders" and method == "GET":
            return self.middle.request(method, self.account_path + "/orders" + query_string(params, "status"))
        if path.startswith("/api/orders/"):
            order_id = path.removeprefix("/api/orders/")
            if method == "GET" and ORDER_ID.fullmatch(order_id):
                return self._order_status(order_id)
            order_id = order_id.removesuffix("/cancel")
            if method == "POST" and path.endswith("/cancel") and ORDER_ID.fullmatch(order_id):
                return self.middle.request(method, f"{self.account_path}/orders/{order_id}/cancel", {})
        raise GatewayError(404, "not_found", "Unknown demo endpoint")
