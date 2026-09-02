#!/usr/bin/env python3
"""Runs a whole Attack/Defense game on this machine, played by bots.

Three CTFBox nodes share the load - two terminate the player tunnels and mesh
with each other, all three run checkers - and a handful of simulated teams
attack each other, patch themselves and occasionally break their own service.

It is the same code path a real deployment takes: `run.py deploy` with a real
topology, real WireGuard tunnels between the nodes, the real checker system and
the real submission endpoint. Only the machines are pretended.

    ./simulation/simulate.py up
    ./simulation/simulate.py status
    ./simulation/simulate.py down
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)

CONFIG_FILE = "config.simulation.json"
# Its own compose project, so the simulation can share the machine with a real
# deployment without either of them noticing the other.
PROJECT = "ctfbox-sim"
TEAMS_COMPOSE = ".ctfbox-sim-teams.yml"
TEAMS_PROJECT = "ctfbox-sim-teams"
# run.py namespaces the generated WireGuard material per project, so that a
# simulation can never touch a real deployment's profiles. Mirror the rule
# here: mounting ./router/configs would hand the simulated boxes the real
# game's keys.
CONFIGS_DIR = f"./router/configs-{PROJECT}"
SCOREBOARD_PORT = "127.0.0.1:9090"
SERVICE_NAME = "Notes"

# Every node lives on this machine, so they reach each other through the host
# gateway rather than through an address only a real network would have.
HOST = "host.docker.internal"

NODES = [
    {
        "name": "front",
        "roles": ["control", "vpn", "checker"],
        "address": HOST,
        "public_address": HOST,
        "wireguard_port": 51500,
        "local": True,
        "weight": 2,
        "checker_concurrency": 6,
    },
    {
        "name": "edge",
        "roles": ["vpn", "checker"],
        "address": HOST,
        "public_address": HOST,
        "wireguard_port": 51510,
        "local": True,
        "weight": 1,
        "checker_concurrency": 6,
    },
    {
        "name": "worker",
        "roles": ["checker"],
        "address": HOST,
        "local": True,
        "checker_concurrency": 8,
    },
]

# Each team plays differently, otherwise the scoreboard is a straight line.
PERSONALITIES = [
    {"name": "Bytewise", "skill": 0.9, "defense": 0.7, "chaos": 0.05},
    {"name": "Segfault", "skill": 0.7, "defense": 0.4, "chaos": 0.25},
    {"name": "Null Deref", "skill": 0.5, "defense": 0.6, "chaos": 0.10},
    {"name": "Off By One", "skill": 0.8, "defense": 0.2, "chaos": 0.30},
    {"name": "Kernel Panic", "skill": 0.4, "defense": 0.8, "chaos": 0.05},
]

pref = "\033["


def puts(text: str, color: str = "37m", bold: bool = False) -> None:
    print(f"{pref}{1 if bold else 0};{color}{text}{pref}0m", flush=True)


def run(cmd: str, env: dict | None = None, check: bool = True) -> int:
    full_env = {**os.environ, **(env or {})}
    code = subprocess.call(cmd, shell=True, cwd=ROOT, env=full_env)
    if check and code != 0:
        puts(f"Command failed: {cmd}", "31m")
        sys.exit(code)
    return code


def ctfbox(args: str, check: bool = True) -> int:
    return run(
        f"./run.py {args}",
        env={"CTFBOX_CONFIG": CONFIG_FILE, "CTFBOX_PROJECT": PROJECT},
        check=check,
    )


def compose(args: str, check: bool = True) -> int:
    return run(f"docker compose -p {TEAMS_PROJECT} -f {TEAMS_COMPOSE} {args}", check=check)


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


def build_config(team_count: int, tick: int) -> dict:
    teams = [
        {"id": 0, "name": "Nop Team", "token": secrets.token_hex(32), "nop": True, "image": ""}
    ]
    for index in range(team_count):
        personality = PERSONALITIES[index % len(PERSONALITIES)]
        teams.append(
            {
                "id": index + 1,
                "name": personality["name"],
                "token": secrets.token_hex(32),
                "nop": False,
                "image": "",
            }
        )

    return {
        "gameserver_token": secrets.token_hex(32),
        "server_addr": HOST,
        "wireguard_port": 51500,
        "wireguard_profiles": 2,
        "dns": "1.1.1.1",
        "tick_time": tick,
        "flag_expire_ticks": 3,
        "initial_service_score": 5000,
        "max_flags_per_request": 500,
        "submission_timeout": 0.05,
        "network_limit_bandwidth": "50mbit",
        "max_vm_cpus": "1",
        "max_vm_mem": "1G",
        "teams": teams,
        # The simulation brings its own team boxes, which is exactly what the
        # `none` mode is for.
        "vm_mode": "none",
        "start_time": None,
        "end_time": None,
        "scoreboard_freeze_time": None,
        "max_disk_size": None,
        "gameserver_exposed_port": SCOREBOARD_PORT,
        "credential_server": None,
        "debug": False,
        "grace_time": 0,
        "checker_concurrency": 4,
        "checker_timeout": 20,
        "traffic_monitor": True,
        # The simulation is also where the capture is exercised: a small ring
        # is plenty to show the download working without filling the disk.
        "pcap": True,
        "pcap_max_size": 128,
        "checkers_dir": "./simulation/checkers",
        "nodes": NODES,
    }


def prepare_checkers() -> None:
    """The checkers directory needs the shared library next to the services."""
    shutil.copyfile(
        os.path.join(ROOT, "gameserver/checkers/checklib.py"),
        os.path.join(HERE, "checkers/checklib.py"),
    )
    shutil.copyfile(
        os.path.join(ROOT, "gameserver/checkers/requirements.txt"),
        os.path.join(HERE, "checkers/requirements.txt"),
    )


# ---------------------------------------------------------------------------
# the simulated teams
# ---------------------------------------------------------------------------


def team_services(config: dict) -> dict:
    services = {}
    for index, team in enumerate(config["teams"]):
        team_id = team["id"]
        personality = PERSONALITIES[(index - 1) % len(PERSONALITIES)]
        common = {
            "build": "./simulation/agent",
            "cap_add": ["NET_ADMIN"],
            "sysctls": ["net.ipv4.conf.all.src_valid_mark=1"],
            "extra_hosts": ["host.docker.internal:host-gateway"],
            "restart": "unless-stopped",
        }

        services[f"box{team_id}"] = {
            **common,
            "hostname": f"box{team_id}",
            "environment": {
                "ROLE": "box",
                "TEAM_ID": str(team_id),
                "SERVICE_PORT": "8000",
                "CONTROL_PORT": "9000",
            },
            "volumes": [
                f"{CONFIGS_DIR}/servers/server-{team_id}.conf:/config/wg.conf:ro"
            ],
        }

        if team["nop"]:
            # The NOP team is a reference box: it never attacks anybody.
            continue

        services[f"player{team_id}"] = {
            **common,
            "hostname": f"player{team_id}",
            "depends_on": [f"box{team_id}"],
            "environment": {
                "ROLE": "player",
                "TEAM_ID": str(team_id),
                "TEAM_TOKEN": team["token"],
                "GAMESERVER": "http://10.10.0.1",
                "SERVICE_NAME": SERVICE_NAME,
                "SERVICE_PORT": "8000",
                "BOX_CONTROL": f"http://box{team_id}:9000/control",
                "BOT_SKILL": str(personality["skill"]),
                "BOT_DEFENSE": str(personality["defense"]),
                "BOT_CHAOS": str(personality["chaos"]),
                "BOT_TICK": str(max(15, config["tick_time"] // 3)),
            },
            "volumes": [
                f"{CONFIGS_DIR}/team{team_id}/team{team_id}-1.conf:/config/wg.conf:ro"
            ],
        }
    return services


def write_teams_compose(config: dict) -> None:
    services = team_services(config)
    # A bind mount whose source does not exist is silently turned into an empty
    # directory by Docker, and the container then comes up with no tunnel at
    # all. Fail loudly instead: it always means the profiles were not generated
    # (or were generated somewhere else).
    for name, service in services.items():
        for mount in service.get("volumes", []):
            source = mount.split(":", 1)[0]
            if not os.path.isfile(os.path.join(ROOT, source)):
                puts(f"Missing WireGuard profile for {name}: {source}", "31m", bold=True)
                puts("Run './simulation/simulate.py down' and start again.", "31m")
                sys.exit(1)
    # Compose reads JSON perfectly well, and it saves hand rolling YAML.
    with open(os.path.join(ROOT, TEAMS_COMPOSE), "w") as handle:
        json.dump({"services": services}, handle, indent=2)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def wait_for(url: str, what: str, timeout: int = 240) -> bool:
    puts(f"Waiting for {what}...", "33m")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(3)
    puts(f"Timed out waiting for {what}", "31m")
    return False


def cmd_up(args) -> None:
    if os.path.exists(os.path.join(ROOT, "config.json")) and not args.force:
        puts(
            "A config.json already exists in the repository: the simulation uses its own "
            f"{CONFIG_FILE} and will not touch it, but a real deployment may be running.",
            "33m",
        )
    config = build_config(args.teams, args.tick)
    with open(os.path.join(ROOT, CONFIG_FILE), "w") as handle:
        json.dump(config, handle, indent=4)
    prepare_checkers()

    puts(f"Simulating {args.teams} teams over {len(NODES)} nodes", "36m", bold=True)
    ctfbox("node list")
    ctfbox("deploy")

    if not wait_for(f"http://{SCOREBOARD_PORT}/api/status", "the game server"):
        sys.exit(1)

    write_teams_compose(config)
    puts("Starting the simulated teams", "33m")
    compose("up -d --build")

    puts("", "37m")
    puts("The game is running.", "32m", bold=True)
    puts(f"  scoreboard   http://{SCOREBOARD_PORT}/scoreboard")
    puts(f"  admin panel  http://{SCOREBOARD_PORT}/admin  (needs an admin VPN profile:")
    puts(f"               {CONFIGS_DIR}/admins/admin-1.conf)")
    puts(f"  teams        ./simulation/simulate.py logs player1")
    puts(f"  stop         ./simulation/simulate.py down")


def cmd_down(args) -> None:
    if os.path.exists(os.path.join(ROOT, TEAMS_COMPOSE)):
        compose("down --remove-orphans", check=False)
    ctfbox("node down all", check=False)
    if args.clean:
        ctfbox("clear", check=False)
        for path in (CONFIG_FILE, TEAMS_COMPOSE):
            try:
                os.remove(os.path.join(ROOT, path))
            except FileNotFoundError:
                pass
    puts("Simulation stopped", "32m")


def cmd_status(args) -> None:
    try:
        with urllib.request.urlopen(f"http://{SCOREBOARD_PORT}/api/status", timeout=5) as r:
            status = json.loads(r.read())
        with urllib.request.urlopen(f"http://{SCOREBOARD_PORT}/api/scoreboard", timeout=5) as r:
            board = json.loads(r.read())
    except (urllib.error.URLError, OSError) as exc:
        puts(f"The game server is not answering: {exc}", "31m")
        return

    puts(
        f"round {status['current_round']}  network {status['network_state']}"
        f"  frozen={status['scoreboard_frozen']}",
        "36m",
        bold=True,
    )
    names = {team["host"]: team["name"] for team in status["teams"]}
    scores = sorted(board.get("scores", []), key=lambda s: -s["score"])
    for position, entry in enumerate(scores, start=1):
        services = " ".join(
            f"{s['service']}:{'up' if s['sla_check'] == 101 else 'DOWN'}"
            f"(sla {s['sla'] * 100:.0f}%)"
            for s in entry["services"]
        )
        puts(f"  {position}. {names.get(entry['team'], entry['team']):<14} "
             f"{entry['score']:>10.1f}  {services}")


def cmd_logs(args) -> None:
    target = f" {args.service}" if args.service else ""
    compose(f"logs -f --tail 60{target}", check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="CTFBox bot driven simulation")
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up", help="deploy the nodes and start the simulated teams")
    up.add_argument("--teams", type=int, default=4, help="playing teams, on top of the NOP team")
    up.add_argument("--tick", type=int, default=60, help="round length in seconds")
    up.add_argument("--force", action="store_true", help="do not warn about an existing config.json")
    up.set_defaults(func=cmd_up)

    down = sub.add_parser("down", help="stop everything")
    down.add_argument("--clean", action="store_true", help="also wipe the database and the profiles")
    down.set_defaults(func=cmd_down)

    status = sub.add_parser("status", help="print the live scoreboard")
    status.set_defaults(func=cmd_status)

    logs = sub.add_parser("logs", help="follow the logs of the simulated teams")
    logs.add_argument("service", nargs="?", help="for example box1 or player2")
    logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
