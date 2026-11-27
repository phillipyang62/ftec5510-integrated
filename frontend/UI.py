"""Integrated Harbor Invest gateway and demo launcher."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from bff import DemoSessions, GatewayError, JsonService, MAX_BODY, SESSION_TTL


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PREFERRED_PORT = 5510
STATIC_ASSETS = {"/", "/index.html", "/lucide.min.js", "/integration.js", "/questionnaire.js"}

class AssetHandler(SimpleHTTPRequestHandler):
    """Serve the application's assets without caching."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def send_head(self):
        if urlsplit(self.path).path not in STATIC_ASSETS:
            self.send_error(404)
            return None
        return super().send_head()

    def log_message(self, message_format, *args):
        print(f"[UI] {message_format % args}")


class IntegratedHandler(AssetHandler):
    """Serve only the UI assets and explicitly registered gateway routes."""

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def _check_origin(self):
        host = self.headers.get("Host")
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            allowed_hosts.update({"127.0.0.1", "localhost"})
        origin = self.headers.get("Origin")
        if host not in allowed_hosts or origin not in {None, f"http://{host}"}:
            raise GatewayError(403, "local_only", "Use the local demo from its own origin")

    @property
    def _cookie_name(self):
        return f"harbor_demo_session_{self.server.server_port}"

    def _session_token(self):
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        session = cookies.get(self._cookie_name)
        return session.value if session else None

    def send_head(self):
        try:
            self._check_origin()
        except GatewayError:
            self.send_error(403)
            return None
        path = urlsplit(self.path).path
        if path not in {"/", "/index.html"}:
            return super().send_head()
        session = self.server.sessions.current(self._session_token())
        account_attr = f' data-account-name="{session.account.user_id}"' if session else ""
        body_tag = f'<body data-integrated="true"{account_attr}>'.encode("ascii")
        html = (ROOT / "index.html").read_bytes().replace(b"<body>", body_tag, 1)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        return io.BytesIO(html)

    def _read_json(self):
        if self.headers.get_content_type() != "application/json":
            raise GatewayError(415, "content_type", "Use application/json")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or self.headers.get("Transfer-Encoding") or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
            raise GatewayError(400, "invalid_length", "One Content-Length is required")
        length = int(lengths[0])
        if length > MAX_BODY:
            raise GatewayError(413, "body_too_large", "Maximum request size is 64 KiB")
        try:
            raw = self.rfile.read(length)
            data = json.loads(raw)
            if len(raw) != length or not isinstance(data, dict):
                raise ValueError("expected an object")
            json.dumps(data, allow_nan=False)
            return data
        except (ValueError, RecursionError) as error:
            raise GatewayError(400, "invalid_json", "Use a finite JSON object") from error

    def _api(self):
        cookie = None
        try:
            self._check_origin()
            url = urlsplit(self.path)
            body = self._read_json() if self.command in {"POST", "PUT"} else None
            status, payload, cookie = self._dispatch_api(url, body)
        except GatewayError as error:
            status, payload = error.status, error.payload
        except TimeoutError:
            status, payload = 408, {"error": {"code": "request_timeout", "message": "Request body timed out"}}
        result = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(result)))
            if cookie is not None:
                value, max_age = cookie
                self.send_header("Set-Cookie", f"{self._cookie_name}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}")
            self.end_headers()
            self.wfile.write(result)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _dispatch_api(self, url, body):
        sessions = self.server.sessions
        method, path = self.command, url.path
        if (method, path) == ("GET", "/api/health"):
            return (*sessions.health(), None)
        token = self._session_token()
        if (method, path) == ("POST", "/api/session"):
            new_token, account = sessions.sign_in(body, token)
            return 200, {"account_name": account.user_id}, (new_token, SESSION_TTL)
        session = sessions.current(token)
        account = session.account if session else None
        expected = self.headers.get("X-Harbor-Account")
        if expected is not None and (account is None or expected != account.user_id):
            raise GatewayError(401, "session_changed", "The simulation account has changed; reload to continue")
        if path == "/api/session":
            if method == "GET":
                return 200, {"account_name": account.user_id if account else None}, None
            if method == "DELETE":
                sessions.sign_out(token)
                return 200, {"account_name": None}, ("", 0)
        if account is None:
            raise GatewayError(401, "sign_in_required", "Sign in to a simulation account first")
        return (*account.dispatch(method, url, body, session), None)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._api()
        else:
            super().do_GET()

    do_POST = do_PUT = do_DELETE = _api


def create_server(sessions, *, port=None):
    ports = (port,) if port is not None else range(PREFERRED_PORT, PREFERRED_PORT + 20)
    last_error = None
    for candidate in ports:
        try:
            server = ThreadingHTTPServer((HOST, candidate), IntegratedHandler)
            server.sessions = sessions
            return server, server.server_port
        except OSError as error:
            last_error = error
    raise RuntimeError("No available local port was found.") from last_error


def main():
    parser = argparse.ArgumentParser(description="Run the local Harbor Invest demo.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically.")
    parser.add_argument("--integrated", action="store_true", help="Connect to separately running AI and middle-office services.")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()

    if not args.integrated:
        command = [sys.executable, str(ROOT.parent / "run_demo.py")]
        if not args.no_browser:
            command.append("--open-browser")
        if args.port is not None:
            command.extend(["--port", str(args.port)])
        try:
            raise SystemExit(subprocess.call(command))
        except KeyboardInterrupt:
            return

    try:
        ai = JsonService("ai", os.getenv("HARBOR_AI_URL", "http://127.0.0.1:8000"), os.environ["AI_MVP_API_TOKEN"], timeout=450)
        middle = JsonService("middle_office", os.getenv("HARBOR_MIDDLE_URL", "http://127.0.0.1:8200"), os.environ["MO_API_TOKEN"])
        sessions = DemoSessions(ai, middle)
    except (KeyError, ValueError) as error:
        parser.error(f"invalid integrated configuration: {error}")
    server, port = create_server(sessions, port=args.port)
    url = f"http://{HOST}:{port}/index.html"

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    print("")
    print("Harbor Invest gateway is running.")
    print(f"Open: {url}")
    print("Press Ctrl+C to stop the server.")
    print("")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping preview server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
