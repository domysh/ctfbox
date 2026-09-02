#!/usr/bin/env python3
"""The intentionally weak service every simulated team runs.

Notes: you register, you store notes, you read them back with your password.
The weakness is deliberate and switchable, so a bot can "patch" its own box and
watch the attacks against it stop, or break it and watch its own SLA fall.
"""

from __future__ import annotations

import json
import os
import random
import secrets
import string
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TEAM_ID = os.environ.get("TEAM_ID", "0")
GAME_PORT = int(os.environ.get("SERVICE_PORT", "8000"))
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", "9000"))

state_lock = threading.Lock()
users: dict[str, str] = {}
notes: dict[str, dict] = {}

# Flipped by the bot through the control port.
patched = False
broken = False
slow = False


def log(message: str) -> None:
    print(f"[box {TEAM_ID}] {message}", flush=True)


def authenticate(user: str, password: str) -> bool:
    """The bug: an unpatched box accepts any prefix of the real password.

    An empty string is a prefix of everything, so knowing a username is enough.
    """
    stored = users.get(user)
    if stored is None:
        return False
    if patched:
        return secrets.compare_digest(stored, password)
    return stored.startswith(password)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Notes/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def _guard(self) -> bool:
        """A broken box answers nothing, which is what the checker sees as DOWN."""
        if broken:
            self.close_connection = True
            return False
        if slow:
            time.sleep(20)
        return True

    def do_POST(self):  # noqa: N802
        if not self._guard():
            return
        path = urlparse(self.path).path
        data = self._body()

        if path == "/register":
            user, password = data.get("user", ""), data.get("password", "")
            if not user or not password:
                return self._send(400, {"error": "user and password are required"})
            with state_lock:
                if user in users:
                    return self._send(409, {"error": "already registered"})
                users[user] = password
            return self._send(200, {"user": user})

        if path == "/notes":
            user, password = data.get("user", ""), data.get("password", "")
            if not authenticate(user, password):
                return self._send(401, {"error": "bad credentials"})
            note_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
            with state_lock:
                notes[note_id] = {
                    "owner": user,
                    "title": data.get("title", ""),
                    "content": data.get("content", ""),
                    "at": time.time(),
                }
            return self._send(200, {"id": note_id})

        self._send(404, {"error": "not found"})

    def do_GET(self):  # noqa: N802
        if not self._guard():
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        user = (query.get("user") or [""])[0]
        password = (query.get("password") or [""])[0]

        if parsed.path == "/health":
            return self._send(200, {"ok": True, "patched": patched})

        if parsed.path == "/notes":
            if not authenticate(user, password):
                return self._send(401, {"error": "bad credentials"})
            with state_lock:
                owned = [
                    {"id": note_id, "title": note["title"]}
                    for note_id, note in notes.items()
                    if note["owner"] == user
                ]
            return self._send(200, {"notes": owned})

        if parsed.path.startswith("/notes/"):
            note_id = parsed.path.split("/", 2)[2]
            with state_lock:
                note = notes.get(note_id)
            if note is None:
                return self._send(404, {"error": "no such note"})
            if not authenticate(user, password) or note["owner"] != user:
                return self._send(401, {"error": "bad credentials"})
            return self._send(200, note)

        self._send(404, {"error": "not found"})


class ControlHandler(BaseHTTPRequestHandler):
    """Only the team's own bot talks here, never the game network."""

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def do_POST(self):  # noqa: N802
        global patched, broken, slow
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            data = {}
        for key, value in (("patched", None), ("broken", None), ("slow", None)):
            if key in data:
                globals()[key] = bool(data[key])
        log(f"state: patched={patched} broken={broken} slow={slow}")
        body = json.dumps({"patched": patched, "broken": broken, "slow": slow}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    threading.Thread(
        target=lambda: ThreadingHTTPServer(("0.0.0.0", CONTROL_PORT), ControlHandler).serve_forever(),
        daemon=True,
    ).start()
    log(f"notes service listening on :{GAME_PORT} (control on :{CONTROL_PORT})")
    ThreadingHTTPServer(("0.0.0.0", GAME_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
