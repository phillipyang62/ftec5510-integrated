"""HTTP boundary for trusted backends, with a separate read-only AI credential."""
import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
import re
import sqlite3
from urllib.parse import parse_qs, unquote, urlsplit

from .validation import BusinessError, require

LOG = logging.getLogger(__name__)
MAX_BODY = 256 * 1024


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, office, *, token=None, read_token=None):
        host, port = address
        host = "127.0.0.1" if host == "localhost" else host
        require(ip_address(host).version == 4, "invalid_host", "use an IPv4 address")
        require(ip_address(host).is_loopback or bool(token), "token_required", "set MO_API_TOKEN for LAN access")
        require(not read_token or token and not hmac.compare_digest(token, read_token),
                "invalid_token", "AI read token must differ from operator token")
        self.office, self.token, self.read_token = office, token, read_token
        super().__init__((host, port), Handler)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        require(self.headers.get_content_type() == "application/json", "content_type", "use application/json", 415)
        lengths = self.headers.get_all("Content-Length", [])
        require(len(lengths) == 1 and not self.headers.get("Transfer-Encoding")
                and re.fullmatch(r"[0-9]{1,10}", lengths[0]), "invalid_length", "one Content-Length is required")
        length = int(lengths[0])
        require(length <= MAX_BODY, "body_too_large", "maximum body is 256 KiB", 413)
        raw = self.rfile.read(length)
        require(len(raw) == length, "invalid_length", "incomplete request body")
        try:
            def bad_constant(value):
                raise ValueError(value)
            data = json.loads(raw, parse_constant=bad_constant)
        except (ValueError, RecursionError):
            raise BusinessError("invalid_json", "body must be finite JSON") from None
        require(isinstance(data, dict), "invalid_json", "body must be an object")
        return data

    def _authorize(self, path):
        offered = self.headers.get("Authorization", "").encode()
        if self.server.token and hmac.compare_digest(offered, ("Bearer " + self.server.token).encode()):
            return
        read_path = path == "/api/quotes" or re.fullmatch(r"/api/accounts/[A-Za-z0-9_-]{1,64}/(?:snapshot|analysis_snapshot)", path)
        if self.server.read_token and hmac.compare_digest(offered, ("Bearer " + self.server.read_token).encode()):
            require(self.command == "GET" and read_path, "read_only", "AI token only grants quotes and read-only account reports", 403)
            return
        require(not self.server.token, "unauthorized", "valid service bearer token required", 401)

    def _dispatch(self):
        url = urlsplit(self.path)
        path, method = unquote(url.path), self.command
        if (method, path) == ("GET", "/health"):
            feed = getattr(self.server, "public_feed", None)
            return 200, {"status": "ok", "mode": "simulation", "modules": 6, "api_version": 1,
                         "market_mode": "public" if self.server.office.public_sources else "simulation",
                         "public_sources": feed.snapshot() if feed else {}}
        self._authorize(path)
        office = self.server.office
        params = parse_qs(url.query, keep_blank_values=True)
        if path == "/api/quotes":
            if method == "POST":
                return 200, office.ingest_quotes(self._body())
            if method == "GET":
                limit = params.get("limit", ["20"])[0]
                require(limit.isascii() and limit.isdigit() and len(limit) <= 2, "invalid_limit", "limit must be 1-50")
                return 200, office.quotes(params.get("q", [""])[0], int(limit), all_sources=params.get("all_sources") == ["true"])
        if (method, path) == ("GET", "/api/comparison"):
            return 200, office.comparison(params.get("symbol", [None])[0], params.get("quantity", ["1"])[0], params.get("side", ["buy"])[0])
        match = re.fullmatch(r"/api/accounts/([A-Za-z0-9_-]{1,64})(?:/(.*))?", path)
        if match:
            user, action = match.groups()
            if action is None and method == "POST":
                return 201, office.create_account(user, self._body())
            if method == "GET" and action in {"snapshot", "analysis_snapshot", "portfolio", "preferences", "assessment", "alerts"}:
                return 200, getattr(office, action)(user)
            if method == "PUT" and action in {"preferences", "assessment"}:
                return 200, getattr(office, action)(user, self._body())
            if (method, action) == ("POST", "orders/preview"):
                return 200, office.preview_order(user, self._body())
            if action == "orders":
                if method == "POST":
                    return 200, office.place_order(user, self._body())
                if method == "GET":
                    return 200, {"orders": office.orders(user, open_only=params.get("status") == ["open"])}
            cancel = re.fullmatch(r"orders/(ord_[a-f0-9]{32})/cancel", action or "")
            if cancel and method == "POST":
                self._body()
                return 200, office.cancel_order(user, cancel[1])
            review = re.fullmatch(r"alerts/(alt_[a-f0-9]{32})/review", action or "")
            if review and method == "POST":
                return 200, office.review_alert(user, review[1], self._body())
            if action in {"trades", "audit"} and method == "GET":
                offset, limit = params.get("offset", ["0"])[0], params.get("limit", ["100"])[0]
                require(offset.isascii() and offset.isdigit() and len(offset) <= 8 and limit.isascii()
                        and limit.isdigit() and 1 <= int(limit) <= 500, "invalid_page", "invalid offset or limit")
                rows = office.records(user, action)
                return 200, {action: rows[int(offset):int(offset) + int(limit)], "total": len(rows)}
        raise BusinessError("not_found", "unknown endpoint", 404)

    def _handle(self):
        try:
            status, body = self._dispatch()
        except BusinessError as error:
            status, body = error.status, {"error": {"code": error.code, "message": str(error)}}
        except (TimeoutError, ConnectionError):
            status, body = 408, {"error": {"code": "timeout", "message": "request timed out"}}
        except sqlite3.Error:
            LOG.exception("Database operation failed")
            status, body = 503, {"error": {"code": "storage_unavailable", "message": "database operation failed"}}
        except Exception:
            LOG.exception("Request failed")
            status, body = 500, {"error": {"code": "internal_error", "message": "request could not be completed"}}
        try:
            self._send(status, body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = do_POST = do_PUT = _handle
