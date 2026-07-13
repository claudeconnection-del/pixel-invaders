"""CompanionServer — a tiny stdlib HTTP + long-poll server the cabinet hosts so
phones on the LAN can be private controllers. No third-party deps (matches
game/netclient.py's stance). Runs on a daemon thread; routes to a
SecretLocalSession.

Routes:
  GET  /                          -> the phone app (one self-contained file)
  GET  /status                    -> session.status()  (lobby readout)
  POST /join   {code,name}        -> {seat,token,code} | {error}
  POST /action {seat,token,kind,..}-> {ok} | {error}
  GET  /poll?seat=&token=&v=<ver>  -> long-poll: {v,view} once the seat's view
                                      advances past <ver>, else {v,changed:false}
                                      after ~POLL_HOLD_S so the phone re-polls.
"""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

POLL_HOLD_S = 25.0     # how long a poll is held open waiting for a change
POLL_TICK_S = 0.1
DEFAULT_PORT = 1983    # arcade golden-age wink; auto-falls back if taken


def lan_ip():
    """Best-effort LAN IP for the QR URL. The UDP 'connect' just picks the
    outbound route; it sends nothing. Falls back to loopback offline."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class CompanionServer:
    def __init__(self, session, *, app_html_path=None, app_html=b"",
                 preferred=DEFAULT_PORT, host="0.0.0.0"):
        self.session = session
        self.app_html_path = app_html_path
        self._app_html = app_html
        self.preferred = preferred
        self.host = host
        self.port = None
        self._httpd = None
        self._thread = None

    # ------------------------------------------------------------- lifecycle
    def start(self, forced_port=None):
        """Bind + serve. With `forced_port` (manual override) tries only that
        port and raises OSError if busy — the cabinet surfaces that as the
        'can't host' state. Otherwise tries the preferred port, then a small
        range, then an OS-assigned free port (so a busy port self-heals)."""
        app_bytes = self._read_app()
        candidates = ([forced_port] if forced_port
                      else [self.preferred]
                      + list(range(self.preferred + 1, self.preferred + 20))
                      + [0])
        last_err = None
        for port in candidates:
            try:
                self._httpd = ThreadingHTTPServer(
                    (self.host, port), _make_handler(self.session, app_bytes))
                break
            except OSError as e:
                last_err, self._httpd = e, None
        if self._httpd is None:
            raise last_err
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="companion-http", daemon=True)
        self._thread.start()
        return self.host, self.port

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def url(self, ip=None):
        ip = ip or lan_ip()
        return f"http://{ip}:{self.port}/?code={self.session.code}"

    # ------------------------------------------------------------- internals
    def _read_app(self):
        if self.app_html_path:
            try:
                with open(self.app_html_path, "rb") as f:
                    return f.read()
            except OSError:
                pass
        return self._app_html or b"<!doctype html><title>Companion</title>ok"


def _make_handler(session, app_bytes):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass  # keep the cabinet's stdout clean

        # -- helpers
        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, (bytes, bytearray)) \
                else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body_json(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            if n <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode())
            except ValueError:
                return {}

        # -- routes
        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                return self._send(200, app_bytes, "text/html; charset=utf-8")
            if u.path == "/status":
                return self._send(200, session.status())
            if u.path == "/poll":
                seat = q.get("seat", [""])[0]
                token = q.get("token", [""])[0]
                try:
                    since = int(q.get("v", ["-1"])[0])
                except ValueError:
                    since = -1
                deadline = time.monotonic() + POLL_HOLD_S
                while True:
                    r = session.poll(seat, token, since)
                    if ("error" in r or r.get("changed") is not False
                            or time.monotonic() >= deadline):
                        return self._send(200, r)
                    time.sleep(POLL_TICK_S)
            return self._send(404, {"error": "not_found"})

        def do_POST(self):
            u = urlparse(self.path)
            body = self._body_json()
            if u.path == "/join":
                r = session.join(body.get("code", ""), body.get("name", ""))
                if r.get("error") == "wrong_code":
                    session.last_error = ("wrong_code", self.client_address[0])
                return self._send(200, r)
            if u.path == "/action":
                r = session.submit(body.get("seat", ""), body.get("token", ""), body)
                return self._send(200, r)
            return self._send(404, {"error": "not_found"})

    return Handler
