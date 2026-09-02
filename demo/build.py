#!/usr/bin/env python3
"""Assembles the public CTFBox site.

The demo is not a snapshot committed by hand any more: it is the real
scoreboard frontend, built from source, served against a set of API fixtures
generated here. A GitHub action runs this on every push, so the demo shows
whatever the frontend currently looks like, admin panel included.

    ./demo/build.py                 # into ./_site
    ./demo/build.py --out /tmp/site # somewhere else

The fixtures come out of a small deterministic simulation of a game: eight
teams with different skill and different luck, three services (one of them
weighted), seventy rounds of history. Deterministic so that a rebuild does not
reshuffle the scoreboard for no reason.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)

SEED = 20260901
ROUNDS = 70
TICK = 120
INITIAL_SCORE = 5000.0
FLAG_EXPIRE = 5
NODES = ["front", "edge", "arena"]

TEAM_NAMES = [
    "Nop Team",
    "Bytewise",
    "Segfault",
    "Null Deref",
    "Off By One",
    "Race Condition",
    "Heap Spray",
    "Stack Smash",
    "Format String",
]

SERVICES = [
    {
        "name": "Pwnzer0tt1Shop-User",
        "weight": 1.0,
        "description": "Accounts and sessions of the shop.",
    },
    {
        "name": "Pwnzer0tt1Shop-Article",
        "weight": 1.0,
        "description": "Catalogue, orders and the notes attached to them.",
    },
    {
        "name": "PCSS",
        "weight": 2.0,
        "description": "Custom stylesheet compiler. Worth double.",
    },
]

# The scoring formula of the game server, kept identical so the demo numbers
# behave the way the rules page says they do.
SCALE = 15 * math.sqrt(5.0)
NORM = math.log(math.log(5.0)) / 12.0


def offense_points(attacker: float, victim: float) -> float:
    return SCALE / (1 + math.exp((math.sqrt(max(attacker, 0)) - math.sqrt(max(victim, 0))) * NORM))


# ---------------------------------------------------------------------------
# the game itself
# ---------------------------------------------------------------------------


class Team:
    def __init__(self, index: int, rng: random.Random):
        self.id = index
        self.name = TEAM_NAMES[index]
        self.nop = index == 0
        self.ip = f"10.60.{index}.1"
        self.node = NODES[index % len(NODES)]
        self.token = "".join(rng.choice("0123456789abcdef") for _ in range(64))
        # What kind of team this is: how often it lands an exploit, and how
        # often it breaks its own service while patching.
        self.skill = 0.0 if self.nop else rng.uniform(0.10, 0.55)
        self.clumsiness = 0.0 if self.nop else rng.uniform(0.01, 0.10)


class ServiceState:
    def __init__(self):
        self.score = INITIAL_SCORE
        self.offense = 0.0
        self.defense = 0.0
        self.stolen = 0
        self.lost = 0
        self.ticks_up = 0
        self.ticks_down = 0
        self.down_for = 0
        self.sla_check = 101
        self.put_flag = 101
        self.get_flag = 101
        self.sla_msg = "Everything is ok"
        self.put_msg = "Everything is ok"
        self.get_msg = "Everything is ok"


def simulate(rng: random.Random):
    """Plays the whole game and returns a snapshot per round."""
    teams = [Team(index, rng) for index in range(len(TEAM_NAMES))]
    state = {
        team.id: {service["name"]: ServiceState() for service in SERVICES}
        for team in teams
    }
    attacks: dict[tuple[int, int, str], dict] = {}
    submissions: list[dict] = []
    history = []

    for round_number in range(ROUNDS + 1):
        for team in teams:
            for service in SERVICES:
                entry = state[team.id][service["name"]]
                if entry.down_for > 0:
                    entry.down_for -= 1
                    entry.ticks_down += 1
                    entry.sla_check = 104
                    entry.sla_msg = "Connection refused"
                    entry.put_flag = 104
                    entry.put_msg = "Could not store the flag: service is down"
                    entry.get_flag = 104
                    entry.get_msg = "Could not read the flag back"
                    continue
                # A team that just patched sometimes breaks what it patched.
                if round_number > 2 and rng.random() < team.clumsiness:
                    entry.down_for = rng.randint(1, 4)
                    entry.ticks_down += 1
                    entry.sla_check = 110
                    entry.sla_msg = "Unexpected answer: the service is mumbling"
                    entry.put_flag = 110
                    entry.put_msg = "Wrong answer while storing the flag"
                    entry.get_flag = 110
                    entry.get_msg = "The flag came back wrong"
                    continue
                entry.ticks_up += 1
                entry.sla_check = 101
                entry.sla_msg = "Everything is ok"
                entry.put_flag = 101
                entry.put_msg = "Everything is ok"
                # In the first rounds there is nothing stored to look for yet:
                # the check does not run, and the scoreboard shows it grey.
                if round_number == 0:
                    entry.get_flag = 100
                    entry.get_msg = "There was no flag to check"
                else:
                    entry.get_flag = 101
                    entry.get_msg = "Everything is ok"

        # Attacks, resolved against the scores of the round before.
        for attacker in teams:
            if attacker.nop:
                continue
            for victim in teams:
                if victim.id == attacker.id:
                    continue
                for service in SERVICES:
                    name = service["name"]
                    victim_state = state[victim.id][name]
                    if victim_state.down_for > 0 or victim_state.sla_check != 101:
                        continue  # cannot steal from a service that is down
                    if rng.random() > attacker.skill * (0.25 if victim.nop else 0.6):
                        continue
                    attacker_state = state[attacker.id][name]
                    points = offense_points(attacker_state.score, victim_state.score)
                    attacker_state.score += points
                    attacker_state.offense += points
                    attacker_state.stolen += 1
                    if not victim.nop:
                        lost = min(victim_state.score, points)
                        victim_state.score -= lost
                        victim_state.defense -= lost
                        victim_state.lost += 1
                    key = (attacker.id, victim.id, name)
                    edge = attacks.setdefault(
                        key,
                        {
                            "from_team": attacker.id,
                            "to_team": victim.id,
                            "service": name,
                            "flags": 0,
                            "points": 0.0,
                        },
                    )
                    edge["flags"] += 1
                    edge["points"] += points
                    if round_number >= ROUNDS - 3:
                        submissions.append(
                            {
                                "round": round_number,
                                "team_id": attacker.id,
                                "victim_id": victim.id,
                                "service": name,
                                "points": points,
                            }
                        )

        history.append(snapshot(teams, state, round_number))

    return teams, state, history, attacks, submissions


def snapshot(teams, state, round_number):
    """The scoreboard as it looked at the end of one round."""
    scores = []
    for team in teams:
        services = []
        total = 0.0
        for service in SERVICES:
            entry = state[team.id][service["name"]]
            ticks = entry.ticks_up + entry.ticks_down
            sla = entry.ticks_up / ticks if ticks else 1.0
            score = max(0.0, entry.score)
            final = score * sla * service["weight"]
            total += final
            services.append(
                {
                    "service": service["name"],
                    "stolen_flags": entry.stolen,
                    "lost_flags": entry.lost,
                    "offensive_points": round(entry.offense, 4),
                    "defensive_points": round(entry.defense, 4),
                    "sla": round(sla, 6),
                    "score": round(score, 4),
                    "ticks_up": entry.ticks_up,
                    "ticks_down": entry.ticks_down,
                    "put_flag": entry.put_flag,
                    "put_flag_msg": entry.put_msg,
                    "get_flag": entry.get_flag,
                    "get_flag_msg": entry.get_msg,
                    "sla_check": entry.sla_check,
                    "sla_check_msg": entry.sla_msg,
                    "final_score": round(final, 4),
                }
            )
        scores.append(
            {"team": team.ip, "score": round(total, 4), "services": services}
        )
    return {"round": round_number, "scores": scores}


def with_diffs(current: dict, previous: dict | None) -> dict:
    """The scoreboard carries the movement since the round before."""
    fields = [
        ("stolen_flags", "diff_stolen_flags"),
        ("lost_flags", "diff_lost_flags"),
        ("offensive_points", "diff_offensive_points"),
        ("defensive_points", "diff_defensive_points"),
        ("sla", "diff_sla"),
        ("score", "diff_score"),
        ("final_score", "diff_final_score"),
    ]
    out = {"round": current["round"], "scores": []}
    for index, team in enumerate(current["scores"]):
        services = []
        for position, service in enumerate(team["services"]):
            entry = dict(service)
            for field, diff in fields:
                before = (
                    previous["scores"][index]["services"][position][field]
                    if previous
                    else 0
                )
                entry[diff] = round(service[field] - before, 4)
            services.append(entry)
        out["scores"].append(
            {"team": team["team"], "score": team["score"], "services": services}
        )
    return out


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(out: str, path: str, payload, as_dir: bool = False) -> None:
    """Writes one fixture.

    `as_dir` is for the few endpoints that are both a path and a prefix
    (/traffic and /traffic/matrix): a static host cannot have the same name be
    a file and a directory, so those are written as `index.html` inside the
    directory. The host redirects the bare path there, and fetch follows the
    redirect; the content type does not matter, `response.json()` parses the
    body either way.
    """
    relative = path.lstrip("/") + ("/index.html" if as_dir else "")
    target = os.path.join(out, relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w") as handle:
        json.dump(payload, handle)


def sample_pcap(out: str) -> None:
    """A handful of real looking packets, so the download button in the admin
    panel hands back something a capture tool will actually open."""
    body = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, 101)
    now = int(datetime.now(timezone.utc).timestamp())
    rng = random.Random(SEED)
    for index in range(40):
        payload = bytes(
            [0x45, 0, 0, 60, 0, 0, 0x40, 0, 64, 6, 0, 0]
        ) + bytes([10, 80, rng.randint(1, 8), 1]) + bytes(
            [10, 60, rng.randint(1, 8), 1]
        ) + bytes(rng.randrange(256) for _ in range(40))
        body += struct.pack("<IIII", now - 60 + index, index * 1000, len(payload), len(payload))
        body += payload
    target = os.path.join(out, "api/admin/pcap/download")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(body)


def build_fixtures(out: str) -> None:
    rng = random.Random(SEED)
    teams, state, history, attacks, submissions = simulate(rng)
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=ROUNDS * TICK)

    # --- public API ----------------------------------------------------
    write_json(out, "api/status", {
        "teams": [
            {
                "id": team.id,
                "name": team.name,
                "shortname": team.name.lower().replace(" ", "_"),
                "host": team.ip,
                "image": "",
                "nop": team.nop,
                "banned": False,
            }
            for team in teams
        ],
        "services": [
            {"name": service["name"], "enabled": True, "weight": service["weight"]}
            for service in SERVICES
        ],
        "start": iso(start),
        "start_grace": iso(start - timedelta(seconds=600)),
        "end": None,
        "roundTime": TICK,
        "flag_expire_ticks": FLAG_EXPIRE,
        "submitter_flags_limit": 500,
        # No rate limit in the demo: there is nobody to protect from a
        # submitter here, and it shows what the "No limit" case looks like.
        "submitter_rate_limit": None,
        "current_round": ROUNDS,
        "flag_regex": "[A-Z0-9]{31}=",
        "init_service_points": INITIAL_SCORE,
        "scoreboard_frozen": False,
        "scoreboard_freeze_time": None,
        "freeze_round": -1,
        "game_paused": False,
        "network_state": "unlocked",
    })

    final = with_diffs(history[-1], history[-2])
    write_json(out, "api/scoreboard", {
        "round": ROUNDS,
        "frozen": False,
        "freeze_round": -1,
        "scores": final["scores"],
    })

    write_json(out, "api/chart", [
        {
            "round": entry["round"],
            "scores": [
                {"team": team["team"], "score": team["score"]}
                for team in entry["scores"]
            ],
        }
        for entry in history
    ])

    for index, team in enumerate(teams):
        rounds = []
        for position, entry in enumerate(history):
            previous = history[position - 1] if position else None
            rounds.append({
                "round": entry["round"],
                "score": with_diffs(entry, previous)["scores"][index],
            })
        write_json(out, f"api/team/{team.id}", rounds)

    write_json(out, "api/announcements", [
        {
            "id": 2,
            "at": iso(now - timedelta(minutes=18)),
            "title": "PCSS is worth double",
            "body": "PCSS carries a weight of 2: every point it makes counts twice in the total.",
            "severity": "info",
            "visible": True,
            "author": "admin@10.80.253.1",
        },
        {
            "id": 1,
            "at": iso(now - timedelta(hours=2)),
            "title": "Welcome to the CTFBox demo",
            "body": "This is a static demo of the real scoreboard, rebuilt from source on every change. The admin control room is open too, read only.",
            "severity": "info",
            "visible": True,
            "author": "admin@10.80.253.1",
        },
    ])

    build_admin_fixtures(out, rng, teams, state, history, attacks, submissions, now, start)
    sample_pcap(out)


def build_admin_fixtures(out, rng, teams, state, history, attacks, submissions, now, start):
    write_json(out, "api/admin/whoami", {
        "admin": True,
        "ip": "10.80.253.1",
        # Only the demo sets this: it turns the panel read only and says so.
        "demo": True,
    })

    settings = {
        "tick_time": TICK,
        "flag_expire_ticks": FLAG_EXPIRE,
        "initial_service_score": INITIAL_SCORE,
        "max_flags_per_request": 500,
        "submission_timeout": None,
        "grace_time": 600,
        "checker_timeout": 30,
        "flag_regex": "[A-Z0-9]{31}=",
        "start_time": iso(start),
        "end_time": None,
        "scoreboard_freeze_time": None,
        "scoreboard_frozen": False,
        "scoreboard_freeze_round": -1,
        "game_paused": False,
    }

    write_json(out, "api/admin/overview", {
        "round": ROUNDS,
        "settings": settings,
        "network_state": "unlocked",
        "node": "front",
        "nodes": [
            {
                "name": name,
                "address": f"10.10.240.{index + 1}",
                "roles": roles,
                "network_state": "unlocked",
                "banned_teams": [],
                "version": "1",
                "first_seen": iso(start),
                "last_seen": iso(now - timedelta(seconds=4)),
                "alive": True,
                "seen": True,
            }
            for index, (name, roles) in enumerate(
                [
                    ("front", ["control", "vpn", "checker"]),
                    ("edge", ["vpn", "vm", "checker"]),
                    ("arena", ["vm", "checker"]),
                ]
            )
        ],
        "workers": [
            {
                "id": "embedded",
                "name": "front",
                "address": "local",
                "capacity": 16,
                "embedded": True,
                "version": "1",
                "running": 3,
                "completed": 4120,
                "failed": 61,
                "last_seen": iso(now - timedelta(seconds=2)),
                "alive": True,
            },
            {
                "id": "w120455-1",
                "name": "edge",
                "address": "10.10.250.1",
                "capacity": 12,
                "embedded": False,
                "version": "1",
                "running": 5,
                "completed": 3980,
                "failed": 44,
                "last_seen": iso(now - timedelta(seconds=3)),
                "alive": True,
            },
            {
                "id": "w120455-2",
                "name": "arena",
                "address": "10.10.250.2",
                "capacity": 12,
                "embedded": False,
                "version": "1",
                "running": 4,
                "completed": 3877,
                "failed": 39,
                "last_seen": iso(now - timedelta(seconds=5)),
                "alive": True,
            },
        ],
        "queue": {"pending": 7, "running": 12, "last_job_id": 12043},
        "capacity": 40,
        "teams": len(teams),
        "services": len(SERVICES),
        "next_round_at": iso(now + timedelta(seconds=TICK)),
        "server_time": iso(now),
    })

    write_json(out, "api/admin/teams", [
        {
            "id": team.id,
            "name": team.name,
            "image": "",
            "nop": team.nop,
            "game_banned": False,
            "network_banned": False,
            "ban_reason": "",
            "node": team.node,
            "ip": team.ip,
            "token": team.token,
        }
        for team in teams
    ])

    write_json(out, "api/admin/services", [
        {
            "name": service["name"],
            "enabled": True,
            "weight": service["weight"],
            "description": service["description"],
            "present": True,
        }
        for service in SERVICES
    ])

    actions = ["CHECK_SLA", "PUT_FLAG", "GET_FLAG"]
    jobs = []
    for index in range(120):
        team = rng.choice(teams)
        service = rng.choice(SERVICES)
        entry = state[team.id][service["name"]]
        status = entry.sla_check if index % 3 == 0 else 101
        started = now - timedelta(seconds=rng.randint(5, TICK * 2))
        jobs.append({
            "id": 12043 - index,
            "round": ROUNDS - (index // 30),
            "team_id": team.id,
            "team": team.ip,
            "service": service["name"],
            "action": actions[index % 3],
            "flag": "",
            "state": "done" if index > 8 else rng.choice(["running", "queued"]),
            "worker": rng.choice(NODES),
            "status": status if index > 8 else 0,
            "message": entry.sla_msg if status != 101 else "Everything is ok",
            "created_at": iso(started),
            "started_at": iso(started + timedelta(seconds=1)),
            "finished_at": iso(started + timedelta(seconds=rng.randint(1, 8))),
            "duration_ms": rng.randint(120, 7000),
        })
    write_json(out, "api/admin/jobs", jobs)

    write_json(out, "api/admin/attack-graph", sorted(
        [
            {**edge, "points": round(edge["points"], 2)}
            for edge in attacks.values()
        ],
        key=lambda edge: -edge["flags"],
    )[:120])

    write_json(out, "api/admin/audit", [
        {
            "id": 12 - index,
            "at": iso(now - timedelta(minutes=index * 7 + 2)),
            "actor": "admin@10.80.253.1",
            "action": action,
            "target": target,
            "details": details,
        }
        for index, (action, target, details) in enumerate([
            ("announcement.create", "PCSS is worth double", "severity=info"),
            ("service.update", "PCSS", "weight"),
            ("pcap.download", "", "minutes=10&teams=3,5"),
            ("network.unlock", "", "every router"),
            ("team.update", "5", "name"),
            ("settings.update", "", "tick_time"),
            ("worker.join", "arena", "capacity=12"),
            ("network.lock", "", "every router"),
        ])
    ])

    # Traffic: one point per bucket per team, with the attackers busier than
    # the quiet ones so the chart has a shape.
    minutes = 60
    bucket = minutes * 60 // 120
    points = []
    for step in range(120):
        moment = now - timedelta(seconds=(119 - step) * bucket)
        for team in teams:
            if team.nop:
                continue
            base = team.skill * 900_000
            wobble = rng.uniform(0.45, 1.55)
            packets = int(base * wobble / 320)
            points.append({
                "at": iso(moment),
                "team": team.id,
                "kind": "vpn",
                "bytes": int(base * wobble),
                "packets": packets,
                "conns": max(1, packets // 14),
            })
    write_json(out, "api/admin/traffic", {
        "minutes": minutes,
        "bucket_seconds": bucket,
        "points": points,
    }, as_dir=True)

    edges = []
    for attacker in teams:
        if attacker.nop:
            continue
        for victim in teams:
            if victim.id == attacker.id:
                continue
            volume = int(attacker.skill * rng.uniform(4e6, 2.5e7))
            packets = volume // 380
            edges.append({
                "src_team": attacker.id,
                "dst_team": victim.id,
                "kind": "vpn",
                "bytes": volume,
                "packets": packets,
                "conns": max(1, packets // 12),
            })
    edges.sort(key=lambda edge: -edge["bytes"])
    write_json(out, "api/admin/traffic/matrix", {"minutes": 15, "edges": edges})

    # Submissions: the accepted ones come from the simulation, the refusals are
    # the usual mix any real game produces.
    events = []
    identifier = 90_000
    for entry in reversed(submissions[-160:]):
        identifier += 1
        events.append({
            "id": identifier,
            "at": iso(now - timedelta(seconds=(len(events) + 1) * 3)),
            "round": entry["round"],
            "team_id": entry["team_id"],
            "team": f"10.60.{entry['team_id']}.1",
            "victim_id": entry["victim_id"],
            "victim": f"10.60.{entry['victim_id']}.1",
            "service": entry["service"],
            "flag": "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(31)) + "=",
            "status": "ACCEPTED",
            "reason": "accepted",
            "points": round(entry["points"], 4),
        })
    refusals = ["duplicate", "expired", "own", "invalid", "nop", "rate-limited"]
    for index in range(340):
        identifier += 1
        team = rng.choice([team for team in teams if not team.nop])
        victim = rng.choice([other for other in teams if other.id != team.id])
        reason = rng.choices(refusals, weights=[46, 18, 12, 14, 8, 2])[0]
        events.append({
            "id": identifier,
            "at": iso(now - timedelta(seconds=(index + 1) * 4)),
            "round": ROUNDS - rng.randint(0, 3),
            "team_id": team.id,
            "team": team.ip,
            "victim_id": victim.id if reason not in ("invalid", "rate-limited") else -1,
            "victim": victim.ip if reason not in ("invalid", "rate-limited") else "",
            "service": rng.choice(SERVICES)["name"] if reason not in ("invalid", "rate-limited") else "",
            "flag": "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(31)) + "=",
            "status": "DENIED",
            "reason": reason,
            "points": 0,
        })
    events.sort(key=lambda event: event["at"], reverse=True)
    write_json(out, "api/admin/submissions", {
        "total": len(events),
        "limit": 300,
        "events": events[:300],
    }, as_dir=True)

    reasons: dict[str, int] = {}
    per_team: dict[int, dict] = {}
    per_round: dict[int, dict] = {}
    for event in events:
        reasons[event["reason"]] = reasons.get(event["reason"], 0) + 1
        team_stat = per_team.setdefault(
            event["team_id"], {"team_id": event["team_id"], "total": 0, "accepted": 0, "points": 0.0}
        )
        team_stat["total"] += 1
        round_stat = per_round.setdefault(
            event["round"], {"round": event["round"], "total": 0, "accepted": 0}
        )
        round_stat["total"] += 1
        if event["reason"] == "accepted":
            team_stat["accepted"] += 1
            team_stat["points"] += event["points"]
            round_stat["accepted"] += 1
    write_json(out, "api/admin/submissions/stats", {
        "reasons": sorted(
            [{"reason": name, "count": count} for name, count in reasons.items()],
            key=lambda row: -row["count"],
        ),
        "teams": sorted(per_team.values(), key=lambda row: -row["total"]),
        "rounds": sorted(per_round.values(), key=lambda row: row["round"]),
    })

    # Per profile accounting: two or three laptops per team, one of them doing
    # most of the work, plus the organizers' own profiles.
    profiles = []
    totals = []
    for team in teams:
        if team.nop:
            continue
        count = rng.randint(2, 3)
        team_rx = team_tx = 0
        active = 0
        for number in range(1, count + 1):
            share = (0.7 if number == 1 else 0.3 / max(count - 1, 1))
            rx = int(team.skill * rng.uniform(3e7, 9e7) * share)
            tx = int(rx * rng.uniform(0.3, 0.8))
            online = number == 1 or rng.random() < 0.6
            active += 1 if online else 0
            profiles.append({
                "team_id": team.id,
                "profile": number,
                "address": f"10.80.{team.id}.{number}",
                "node": NODES[team.id % len(NODES)],
                "rx": rx,
                "tx": tx,
                "handshake": int((now - timedelta(
                    seconds=rng.randint(5, 100) if online else rng.randint(600, 9000)
                )).timestamp()),
            })
            team_rx += rx
            team_tx += tx
        totals.append({
            "team_id": team.id,
            "rx": team_rx,
            "tx": team_tx,
            "profiles": count,
            "active": active,
        })
    admin_rx = admin_tx = 0
    for number in (1, 2):
        rx = int(rng.uniform(2e6, 6e6))
        tx = int(rx * 0.4)
        profiles.append({
            "team_id": -1,
            "profile": number,
            "address": f"10.80.253.{number}",
            "node": "front",
            "rx": rx,
            "tx": tx,
            "handshake": int((now - timedelta(seconds=rng.randint(5, 90))).timestamp()),
        })
        admin_rx += rx
        admin_tx += tx
    totals.append({
        "team_id": -1, "rx": admin_rx, "tx": admin_tx, "profiles": 2, "active": 2,
    })
    # One suspended profile, so the demo shows what that looks like.
    suspended = ["10.80.4.2"]
    write_json(out, "api/admin/traffic/peers", {
        "minutes": 60,
        "profiles": profiles,
        "teams": totals,
        "suspended": suspended,
    })
    write_json(out, "api/admin/vpn/profiles", {
        "suspended": [
            {
                "address": address,
                "team_id": int(address.split(".")[2]),
                "profile": int(address.split(".")[3]),
                "suspended": True,
                "admin": False,
            }
            for address in suspended
        ],
    })

    write_json(out, "api/admin/pcap/status", {
        "enabled": True,
        "bytes": 402_653_184,
        "nodes": [
            {
                "node": "front",
                "enabled": True,
                "interface": "wg0",
                "files": 214,
                "bytes": 224_395_264,
                "max_bytes": 536_870_912,
                "rotate_seconds": 60,
                "oldest": (now - timedelta(hours=3, minutes=34)).timestamp(),
                "newest": (now - timedelta(seconds=12)).timestamp(),
                "free_bytes": 91_268_055_040,
            },
            {
                "node": "edge",
                "enabled": True,
                "interface": "wg0",
                "files": 198,
                "bytes": 178_257_920,
                "max_bytes": 536_870_912,
                "rotate_seconds": 60,
                "oldest": (now - timedelta(hours=3, minutes=18)).timestamp(),
                "newest": (now - timedelta(seconds=9)).timestamp(),
                "free_bytes": 74_309_393_408,
            },
        ],
    })


# ---------------------------------------------------------------------------
# assembling the site
# ---------------------------------------------------------------------------


def run(command: list[str], cwd: str) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def build_frontend(skip: bool) -> str:
    dist = os.path.join(ROOT, "gameserver/frontend/dist")
    if skip:
        if not os.path.isdir(dist):
            sys.exit("--skip-build was given but gameserver/frontend/dist does not exist")
        return dist
    frontend = os.path.join(ROOT, "gameserver/frontend")
    run(["bun", "install", "--frozen-lockfile"], frontend)
    run(["bun", "run", "build"], frontend)
    return dist


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(ROOT, "_site"))
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="reuse gameserver/frontend/dist instead of building it",
    )
    parser.add_argument(
        "--editor",
        default=os.path.join(ROOT, "editor/out"),
        help="the exported config editor, overlaid at /editor (skipped if missing)",
    )
    args = parser.parse_args()

    dist = build_frontend(args.skip_build)

    out = args.out
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(dist, out)

    # The app is a single page behind client side routing, and a static host
    # knows nothing about that. The known routes get a real index.html of their
    # own so any static server can serve them; 404.html covers the rest (a team
    # detail page, say), which GitHub Pages serves for unmatched paths.
    index = os.path.join(out, "index.html")
    shutil.copyfile(index, os.path.join(out, "404.html"))
    for route in ("rules", "scoreboard", "admin"):
        os.makedirs(os.path.join(out, route), exist_ok=True)
        shutil.copyfile(index, os.path.join(out, route, "index.html"))

    for extra in ("CNAME",):
        source = os.path.join(HERE, extra)
        if os.path.exists(source):
            shutil.copyfile(source, os.path.join(out, extra))

    build_fixtures(out)

    if os.path.isdir(args.editor):
        editor_out = os.path.join(out, "editor")
        shutil.copytree(args.editor, editor_out, dirs_exist_ok=True)
        print(f"editor overlaid at {editor_out}")
    else:
        print(f"no editor export at {args.editor}, skipping it")

    total = sum(
        os.path.getsize(os.path.join(base, name))
        for base, _, names in os.walk(out)
        for name in names
    )
    print(f"site assembled in {out} ({total // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
