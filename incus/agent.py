#!/usr/bin/env python3
"""Incus node agent.

One job: reset a team box on request from the game server, so that the
organizers can do from the control room what `./run.py resetvm` does from a
terminal. It runs next to the boxes because that is the only place the work can
happen — the reset is a clone of the base image, which lives here.

The only caller is the game server, authenticated with the cluster token, over
the internal docker network. Nothing is exposed outside the node.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("GAMESERVER_TOKEN", "")
NODE = os.environ.get("NODE_NAME", "main")
PORT = int(os.environ.get("INCUS_AGENT_PORT", "8091"))
CUSTOMIZE = os.environ.get("CUSTOMIZE_SCRIPT", "/customize-vm.py")

# A reset takes minutes and must not be started twice for the same box, so the
# agent keeps one worker per team and reports what it is doing.
running: dict[int, str] = {}
lock = threading.Lock()


def log(message: str) -> None:
    print(f"[incus-agent] {message}", flush=True)


def teams_here() -> set[int]:
    raw = os.environ.get("NODE_TEAMS", "")
    return {int(part) for part in raw.split(",") if part.strip().isdigit()}


def reset(team_id: int) -> None:
    log(f"resetting the box of team {team_id}")
    proc = subprocess.run(
        [sys.executable, CUSTOMIZE, "reset", str(team_id)],
        capture_output=True,
        text=True,
    )
    with lock:
        running.pop(team_id, None)
    if proc.returncode == 0:
        log(f"box of team {team_id} is back to its original state")
    else:
        log(f"reset of team {team_id} failed: {proc.stderr.strip()[-500:]}")


class AgentHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter logs
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if not self.path.startswith("/health"):
            self._send(404, {"error": "not found"})
            return
        with lock:
            busy = sorted(running)
        self._send(200, {"node": NODE, "teams": sorted(teams_here()), "resetting": busy})

    def do_POST(self):  # noqa: N802
        if not self.path.startswith("/vm/reset"):
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return
        if not TOKEN or payload.get("token") != TOKEN:
            self._send(401, {"error": "unauthorized"})
            return

        try:
            team_id = int(payload.get("team"))
        except (TypeError, ValueError):
            self._send(400, {"error": "missing team id"})
            return
        if team_id not in teams_here():
            self._send(
                404,
                {"error": f"team {team_id} has no box on node {NODE}"},
            )
            return

        with lock:
            if team_id in running:
                self._send(409, {"error": f"team {team_id} is already being reset"})
                return
            running[team_id] = "running"

        # The rebuild takes minutes: answer straight away and let the panel
        # follow it, rather than holding an HTTP request open that long.
        threading.Thread(target=reset, args=(team_id,), daemon=True).start()
        self._send(202, {"status": "resetting", "team": team_id, "node": NODE})


def main() -> int:
    if not TOKEN:
        log("no cluster token: the agent would accept nobody, not starting")
        return 0
    log(f"listening on :{PORT} for teams {sorted(teams_here()) or 'none'}")
    ThreadingHTTPServer(("0.0.0.0", PORT), AgentHandler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
