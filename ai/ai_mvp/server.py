import hmac
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address
from urllib.parse import parse_qs, unquote, urlsplit

from .assistant import ChatValidationError
from .models import model_options, session_model
from .product_matching import LEVEL_THRESHOLDS, POLICY, catalog_products
from .profiles import ProfileValidationError


MAX_BODY = 256 * 1024
USER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
QUOTE_CURRENCY = re.compile(r"[A-Za-z0-9]{1,20}\Z")


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code


def require_user_id(value):
    if not isinstance(value, str) or not USER_ID.fullmatch(value):
        raise ApiError(400, "invalid_user_id", "user_id must be 1 to 64 ASCII letters, digits, underscores or hyphens")
    return value


class ApiServer(ThreadingHTTPServer):
    def __init__(self, port, assistant, api_token=None, *, host="127.0.0.1"):
        if host == "localhost":
            host = "127.0.0.1"
        try:
            address = IPv4Address(host)
        except ValueError as error:
            raise ValueError("host must be an IPv4 address or localhost") from error
        if not address.is_loopback and not api_token:
            raise ValueError("AI_MVP_API_TOKEN is required when listening outside loopback")
        self.assistant = assistant
        self.api_token = api_token
        super().__init__((str(address), port), ApiHandler)


class ApiHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def log_request(self, code="-", size="-"):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "unsupported_content_type", "use application/json")
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            raise ApiError(400, "invalid_length", "a single Content-Length is required")
        length = self.headers["Content-Length"]
        if not re.fullmatch(r"[0-9]{1,10}", length):
            raise ApiError(400, "invalid_length", "invalid Content-Length")
        length = int(length)
        if length > MAX_BODY:
            raise ApiError(413, "body_too_large", "JSON request exceeds 256 KiB")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, RecursionError) as error:
            raise ApiError(400, "invalid_json", "request body must be a JSON object") from error
        if not isinstance(data, dict):
            raise ApiError(400, "invalid_json", "request body must be a JSON object")
        return data

    def _handle(self):
        try:
            status, payload = self._dispatch()
        except ApiError as error:
            status, payload = error.status, {"error": {"code": error.code, "message": str(error)}}
        except (ChatValidationError, ProfileValidationError) as error:
            status, payload = 400, {"error": {"code": "invalid_input", "message": str(error)}}
        except TimeoutError:
            status, payload = 408, {"error": {"code": "request_timeout", "message": "request body timed out"}}
        try:
            self._send(status, payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _dispatch(self):
        url = urlsplit(self.path)
        method, path = self.command, url.path
        if (method, path) == ("GET", "/health"):
            return 200, {"status": "ok", "model_configured": self.server.assistant.remote_model is not None,
                         "remote_model_configured": self.server.assistant.remote_model is not None,
                         "market_configured": self.server.assistant.market_provider is not None,
                         "trading_configured": self.server.assistant.trading is not None}
        token = self.server.api_token
        if token and not hmac.compare_digest(
            self.headers.get("Authorization", "").encode("utf-8"), f"Bearer {token}".encode("utf-8")
        ):
            raise ApiError(401, "unauthorized", "valid service bearer token required")

        assistant = self.server.assistant
        if (method, path) == ("GET", "/v1/products"):
            return 200, {"products": catalog_products(), "policy": POLICY,
                         "level_thresholds": dict(LEVEL_THRESHOLDS)}
        if path.startswith("/v1/suitability/") and method == "GET":
            user_id = require_user_id(unquote(path.removeprefix("/v1/suitability/")))
            return 200, assistant.suitability(user_id)
        if path == "/v1/model-settings" and method in {"GET", "PUT"}:
            if method == "GET":
                return 200, model_options(assistant.remote_model)
            if not token:
                raise ApiError(403, "model_settings_unavailable", "Configure an AI service token for session models")
            provider, model = self._session_model(self._json_body())
            return 200, {"provider": provider, "model": model.model if model else None}
        if path.startswith("/v1/profiles/") and method in ("GET", "PUT"):
            user_id = require_user_id(unquote(path.removeprefix("/v1/profiles/")))
            if method == "PUT":
                return 200, assistant.profiles.upsert(user_id, self._json_body()).as_dict()
            profile = assistant.profiles.get(user_id)
            if not profile:
                raise ApiError(404, "profile_not_found", "questionnaire profile does not exist")
            return 200, profile.as_dict()
        if (method, path) == ("POST", "/v1/market/quotes"):
            batch = self._json_body().get("quotes")
            if not isinstance(batch, list) or not 1 <= len(batch) <= 500:
                raise ApiError(400, "invalid_batch", "quotes must contain 1 to 500 items")
            try:
                accepted = assistant.quotes.ingest(batch)
            except ValueError as error:
                raise ApiError(400, "invalid_quote", str(error)) from error
            return 200, {"accepted": accepted, "ignored": len(batch) - accepted}
        if (method, path) == ("GET", "/v1/market/quotes"):
            params = parse_qs(url.query, keep_blank_values=True)
            query = params.get("q", [""])[0].strip()
            if not 1 <= len(query) <= 80:
                raise ApiError(400, "invalid_query", "q must contain 1 to 80 characters")
            limit = params.get("limit", ["5"])[0]
            if not re.fullmatch(r"(?:[1-9]|1[0-9]|20)", limit):
                raise ApiError(400, "invalid_limit", "limit must be between 1 and 20")
            return 200, assistant.lookup_market(query, int(limit))
        if path.startswith("/v1/risk/") and method == "GET":
            user_id = require_user_id(unquote(path.removeprefix("/v1/risk/")))
            params = parse_qs(url.query, keep_blank_values=True)
            currency = params.get("quote_currency", ["USDT"])[0]
            if not QUOTE_CURRENCY.fullmatch(currency):
                raise ApiError(400, "invalid_quote_currency", "quote_currency must be a currency code")
            return 200, assistant.risk(user_id, currency.upper())
        if path.startswith("/v1/education/") and method == "GET":
            user_id = require_user_id(unquote(path.removeprefix("/v1/education/")))
            lesson = assistant.education(user_id)
            if lesson is None:
                raise ApiError(404, "assessment_required", "Complete the questionnaire for a tailored lesson")
            return 200, lesson
        if (method, path) == ("POST", "/v1/chat"):
            payload = self._json_body()
            user_id = require_user_id(payload.get("user_id"))
            settings = payload.get("model_settings")
            model = None
            allow_account_sharing = False
            if settings is not None and payload.get("action") != "portfolio_snapshot":
                if not token:
                    raise ApiError(403, "model_settings_unavailable", "Configure an AI service token for session models")
                _, model = self._session_model(settings)
                allow_account_sharing = model is not None and settings.get("allow_account_sharing") is True
            return 200, assistant.respond(user_id, payload, api_model=model,
                                          allow_account_sharing=allow_account_sharing)
        raise ApiError(404, "not_found", "unknown endpoint")

    @staticmethod
    def _session_model(settings):
        try:
            return session_model(settings)
        except ValueError as error:
            raise ApiError(400, "invalid_model_settings", str(error)) from None
