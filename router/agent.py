#!/usr/bin/env python3
"""CTFBox router agent.

Two jobs, both needed to run a competition on more than one machine:

* it exposes the `ctfroute` commands over HTTP so that the game server can drive
  every router of the cluster, not only the one sharing its unix socket;
* it accounts the game traffic per team pair and pushes it to the control node,
  which is what feeds the traffic monitoring of the admin panel.

Only the standard library is used: the router image is a plain alpine with
python3 and no pip.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = os.environ.get("GAMESERVER_TOKEN", "")
NODE = os.environ.get("NODE_NAME", "main")
CONTROL = os.environ.get("CONTROL_ADDR", "")  # e.g. http://gameserver
INTERVAL = int(os.environ.get("TRAFFIC_INTERVAL", "10"))
RECONCILE_INTERVAL = int(os.environ.get("RECONCILE_INTERVAL", "15"))
TEAM_IDS = [int(t) for t in os.environ.get("TEAM_IDS", "").split(",") if t.strip()]
AGENT_PORT = int(os.environ.get("AGENT_PORT", "8090"))
ENABLE_ACCOUNTING = os.environ.get("TRAFFIC_MONITOR", "1").strip() != "0"

# Full packet capture, off unless the organizers asked for it: it is the one
# feature here that writes the players' actual traffic to disk.
PCAP_ENABLED = os.environ.get("PCAP", "0").strip() == "1"
PCAP_DIR = os.environ.get("PCAP_DIR", "/pcap")
PCAP_IFACE = os.environ.get("PCAP_IFACE", "wg0")
PCAP_SNAPLEN = int(os.environ.get("PCAP_SNAPLEN", "0"))  # 0 = whole packet
PCAP_ROTATE = int(os.environ.get("PCAP_ROTATE", "60"))  # seconds per file
PCAP_MAX_MB = int(os.environ.get("PCAP_MAX_SIZE", "512"))  # ring size on disk

IPT = "iptables-nft"
IPT_SAVE = "iptables-nft-save"
IP_CMD = "ip"

# `vm` counts what reaches a team vulnbox, `vpn` what a player tunnel sends.
CHAIN_VM = "ACCT_VM_{}"
CHAIN_PLAYER = "ACCT_PLY_{}"
DISPATCH = "TRAFFIC_ACCT"


def run(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)


def log(msg: str) -> None:
    print(f"[agent] {msg}", flush=True)


# ---------------------------------------------------------------------------
# traffic accounting
# ---------------------------------------------------------------------------


def setup_accounting() -> bool:
    """Two level counters: one jump per source team, one rule per destination.

    A flat team x team ruleset would make every packet walk n^2 rules; with a
    dispatch chain per source the cost stays linear in the number of teams.
    The rules are added one by one (instead of iptables-restore) so that the
    rules entry.sh installed are left untouched.
    """
    if not TEAM_IDS:
        log("no teams configured, traffic accounting disabled")
        return False

    def ensure(table_args: list[str]) -> None:
        if run([IPT, "-t", "mangle", "-C", *table_args]).returncode != 0:
            run([IPT, "-t", "mangle", "-A", *table_args])

    run([IPT, "-t", "mangle", "-N", DISPATCH])
    ensure(["PREROUTING", "-j", DISPATCH])

    for team in TEAM_IDS:
        for src_net, chain in (
            (f"10.60.{team}.0/24", CHAIN_VM.format(team)),
            (f"10.80.{team}.0/24", CHAIN_PLAYER.format(team)),
        ):
            run([IPT, "-t", "mangle", "-N", chain])
            ensure([DISPATCH, "-s", src_net, "-j", chain])
            for dst in TEAM_IDS:
                dst_net = f"10.60.{dst}.0/24"
                # A rule without a target only counts and falls through, so the
                # connection counter rides along the byte counter instead of
                # stealing the first packet of every flow from it.
                ensure([chain, "-d", dst_net, "-m", "conntrack", "--ctstate", "NEW"])
                ensure([chain, "-d", dst_net, "-j", "RETURN"])

    log(f"traffic accounting ready for {len(TEAM_IDS)} teams")
    return True


COUNTER_RE = re.compile(
    r"^\[(\d+):(\d+)\] -A (ACCT_(?:VM|PLY)_(\d+)) -d 10\.60\.(\d+)\.0/24(.*)$"
)


def read_counters() -> dict[tuple[str, int, int], tuple[int, int, int]]:
    """Returns {(kind, src_team, dst_team): (packets, bytes, connections)}.

    Every team pair has two rules: the conntrack one counts how many flows were
    opened, the plain one counts every packet that crossed.
    """
    proc = run([IPT_SAVE, "-c", "-t", "mangle"])
    if proc.returncode != 0:
        log(f"cannot read counters: {proc.stderr.strip()}")
        return {}
    counters: dict[tuple[str, int, int], list[int]] = {}
    for line in proc.stdout.splitlines():
        match = COUNTER_RE.match(line.strip())
        if not match:
            continue
        packets, size, chain, src, dst, tail = match.groups()
        kind = "vm" if chain.startswith("ACCT_VM_") else "vpn"
        entry = counters.setdefault((kind, int(src), int(dst)), [0, 0, 0])
        if "--ctstate NEW" in tail:
            entry[2] = int(packets)
        else:
            entry[0] = int(packets)
            entry[1] = int(size)
    return {key: tuple(value) for key, value in counters.items()}


def diff_counters(previous, current):
    samples = []
    for key, values in current.items():
        old = previous.get(key, (0, 0, 0))
        # A counter that went backwards means the rules were reinstalled.
        deltas = [
            new - was if new >= was else new
            for new, was in zip(values, old)
        ]
        if all(delta <= 0 for delta in deltas):
            continue
        kind, src, dst = key
        samples.append(
            {
                "kind": kind,
                "src_team": src,
                "dst_team": dst,
                "packets": max(deltas[0], 0),
                "bytes": max(deltas[1], 0),
                "conns": max(deltas[2], 0),
            }
        )
    return samples


def diff_peers(previous: dict, current: list[dict]) -> tuple[list[dict], dict]:
    """Per profile deltas. WireGuard counters only ever grow, except across a
    restart, where they start from zero again."""
    samples = []
    latest = {}
    for peer in current:
        key = peer["public_key"]
        latest[key] = (peer["rx"], peer["tx"])
        old_rx, old_tx = previous.get(key, (0, 0))
        rx = peer["rx"] - old_rx if peer["rx"] >= old_rx else peer["rx"]
        tx = peer["tx"] - old_tx if peer["tx"] >= old_tx else peer["tx"]
        if rx <= 0 and tx <= 0:
            continue
        samples.append(
            {
                "team": peer["team"],
                "profile": peer["profile"],
                "address": peer["address"],
                "rx": rx,
                "tx": tx,
                "handshake": peer["handshake"],
            }
        )
    return samples, latest


def push_samples(samples: list[dict], peers: list[dict] | None = None) -> None:
    if not (samples or peers) or not CONTROL:
        return
    payload = json.dumps(
        {"token": TOKEN, "node": NODE, "samples": samples, "peers": peers or []}
    ).encode()
    request = urllib.request.Request(
        f"{CONTROL}:8082/node/traffic",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except (urllib.error.URLError, OSError) as exc:
        log(f"cannot push traffic samples: {exc}")


def traffic_loop() -> None:
    # Per profile accounting comes from WireGuard itself and works even when
    # the per team pair rules could not be installed, so the loop runs either
    # way and only the iptables half is optional.
    accounting = setup_accounting()
    previous: dict = {}
    previous_peers: dict = {}
    while True:
        time.sleep(INTERVAL)
        try:
            samples = []
            if accounting:
                current = read_counters()
                samples = diff_counters(previous, current)
                previous = current
            peers, previous_peers = diff_peers(previous_peers, wireguard_peers())
            push_samples(samples, peers)
        except Exception as exc:  # never let the collector kill the router
            log(f"traffic loop error: {exc}")


# ---------------------------------------------------------------------------
# packet capture
# ---------------------------------------------------------------------------
#
# tcpdump writes a rotating set of files on the game interface; the agent keeps
# the directory under a size cap and serves filtered slices of it. Nothing is
# ever deleted from the middle: files rotate in time order, so their names sort
# chronologically and the oldest is always the one to drop.

PCAP_GLOBAL_HEADER = 24
PCAP_RECORD_HEADER = 16

# The four pcap magics: big/little endian, microsecond/nanosecond resolution.
PCAP_MAGICS = {
    b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
    b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
    b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
    b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
}


def pcap_files() -> list[str]:
    """Capture files, oldest first (the names are strftime, so name order is
    time order)."""
    try:
        names = sorted(n for n in os.listdir(PCAP_DIR) if n.endswith(".pcap"))
    except OSError:
        return []
    return [os.path.join(PCAP_DIR, name) for name in names]


def pcap_header(handle) -> tuple[str, int, int, int] | None:
    """Reads the global header: (endianness, ticks per second, snaplen, link)."""
    header = handle.read(PCAP_GLOBAL_HEADER)
    if len(header) < PCAP_GLOBAL_HEADER:
        return None
    magic = PCAP_MAGICS.get(header[:4])
    if magic is None:
        return None
    endian, resolution = magic
    _, _, _, _, snaplen, link = struct.unpack(endian + "IHHiIII", header)[1:]
    return endian, resolution, snaplen, link


def pcap_start_time(path: str) -> float | None:
    """Timestamp of the first packet, which is when the file's window opens.

    Read from the file rather than parsed out of its name: tcpdump names files
    in local time and the timestamps inside are UTC, and a container that
    disagrees with the control node about its timezone would silently return
    the wrong slice.
    """
    try:
        with open(path, "rb") as handle:
            head = pcap_header(handle)
            if head is None:
                return None
            endian, resolution, _, _ = head
            record = handle.read(PCAP_RECORD_HEADER)
            if len(record) < PCAP_RECORD_HEADER:
                return None
            seconds, fraction = struct.unpack(endian + "II", record[:8])
            return seconds + fraction / resolution
    except OSError:
        return None


def pcap_status() -> dict:
    files = pcap_files()
    sizes = []
    for path in files:
        try:
            sizes.append(os.path.getsize(path))
        except OSError:
            sizes.append(0)
    oldest = pcap_start_time(files[0]) if files else None
    newest = pcap_start_time(files[-1]) if files else None
    free = None
    try:
        free = shutil.disk_usage(PCAP_DIR).free
    except OSError:
        pass
    return {
        "node": NODE,
        "enabled": PCAP_ENABLED,
        "interface": PCAP_IFACE,
        "files": len(files),
        "bytes": sum(sizes),
        "max_bytes": PCAP_MAX_MB * 1024 * 1024,
        "rotate_seconds": PCAP_ROTATE,
        "oldest": oldest,
        "newest": newest,
        "free_bytes": free,
    }


def prune_pcaps() -> None:
    """Keeps the capture directory under its size cap, oldest first. The file
    tcpdump is writing right now is never touched."""
    limit = PCAP_MAX_MB * 1024 * 1024
    files = pcap_files()
    sizes = {}
    total = 0
    for path in files:
        try:
            sizes[path] = os.path.getsize(path)
        except OSError:
            sizes[path] = 0
        total += sizes[path]
    while len(files) > 1 and total > limit:
        oldest = files.pop(0)
        try:
            os.remove(oldest)
            total -= sizes[oldest]
        except OSError:
            break


def capture_loop() -> None:
    os.makedirs(PCAP_DIR, exist_ok=True)
    while True:
        command = [
            "tcpdump",
            "-i", PCAP_IFACE,
            "-n",
            "-p",  # no promiscuous mode: wg0 has nothing to promiscue anyway
            "-s", str(PCAP_SNAPLEN),
            "-G", str(PCAP_ROTATE),
            "-w", os.path.join(PCAP_DIR, "cap-%Y%m%d-%H%M%S.pcap"),
        ]
        try:
            proc = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
            )
        except OSError as exc:
            log(f"cannot start the capture ({exc}), retrying in 15s")
            time.sleep(15)
            continue
        log(f"capturing {PCAP_IFACE} into {PCAP_DIR} (max {PCAP_MAX_MB} MB)")
        while proc.poll() is None:
            time.sleep(10)
            try:
                prune_pcaps()
            except Exception as exc:  # pruning must never kill the capture
                log(f"pcap prune error: {exc}")
        stderr = (proc.stderr.read() if proc.stderr else "") or ""
        log(f"capture stopped ({stderr.strip().splitlines()[-1:] or 'no output'}), restarting in 10s")
        time.sleep(10)


def team_bpf(teams: list[int]) -> str:
    """A team owns two subnets: its vulnbox and its players' tunnels. Either
    side of the conversation counts, so plain `net` (not src/dst) is right."""
    if not teams:
        return ""
    parts = [f"(net 10.60.{team}.0/24 or net 10.80.{team}.0/24)" for team in teams]
    return "(" + " or ".join(parts) + ")"


def select_pcap_files(
    start: float | None, end: float | None
) -> list[tuple[str, float, float | None]]:
    """Files whose window overlaps [start, end], with the window itself.

    A file's window runs from its first packet to the first packet of the file
    after it; the newest file has no upper bound, since tcpdump is still
    writing into it. The bounds come back with the path because they are what
    tells the reader whether a file has to be trimmed packet by packet or can
    simply be copied over.
    """
    files = pcap_files()
    starts = [pcap_start_time(path) for path in files]
    selected = []
    for index, path in enumerate(files):
        opened = starts[index]
        if opened is None:
            continue  # empty or still headerless: nothing to give
        closed = None
        for later in starts[index + 1:]:
            if later is not None:
                closed = later
                break
        if end is not None and opened > end:
            continue
        if start is not None and closed is not None and closed < start:
            continue
        selected.append((path, opened, closed))
    return selected


COPY_BLOCK = 1 << 20
CHUNK_SIZE = 1 << 18


def stream_filtered_pcap(write, files: list[tuple[str, float, float | None]],
                         bpf: str, start: float | None,
                         end: float | None) -> int:
    """Merges the selected files into one pcap, filtered by BPF and trimmed to
    the time range. Returns the number of bytes written.

    The merge is done here rather than with mergecap so the router image stays
    a plain alpine: the files come from the same capture, so they are already
    in chronological order and the records only have to be concatenated under a
    single global header.

    Only the files straddling an edge of the time range are read packet by
    packet. Everything in between is copied over in one megabyte blocks, which
    on a wide download is the difference between a handful of memory copies and
    millions of trips through the Python interpreter.
    """
    written = 0
    out_format = None  # (endianness, resolution) of the header already emitted

    for path, opened, closed in files:
        trim_head = start is not None and opened < start
        trim_tail = end is not None and (closed is None or closed > end)

        command = ["tcpdump", "-r", path, "-w", "-", "-n"]
        if bpf:
            command.append(bpf)
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        try:
            head = pcap_header(proc.stdout)
            if head is None:
                continue
            endian, resolution, snaplen, link = head
            if out_format is None:
                # The first file decides the format of the whole answer, which
                # is what lets the untrimmed ones go through untouched.
                write(struct.pack(endian + "IHHiIII",
                                  0xA1B2C3D4, 2, 4, 0, 0,
                                  snaplen or 262144, link))
                written += PCAP_GLOBAL_HEADER
                out_format = (endian, resolution)

            if not (trim_head or trim_tail) and out_format == (endian, resolution):
                while True:
                    block = proc.stdout.read(COPY_BLOCK)
                    if not block:
                        break
                    write(block)
                    written += len(block)
                continue

            out_endian, out_resolution = out_format
            while True:
                record = proc.stdout.read(PCAP_RECORD_HEADER)
                if len(record) < PCAP_RECORD_HEADER:
                    break
                seconds, fraction, captured, original = struct.unpack(
                    endian + "IIII", record
                )
                payload = proc.stdout.read(captured)
                if len(payload) < captured:
                    break  # truncated tail of the file being written right now
                moment = seconds + fraction / resolution
                if start is not None and moment < start:
                    continue
                if end is not None and moment > end:
                    # A capture file is in time order: nothing after this
                    # packet can qualify either.
                    break
                scaled = int(fraction * out_resolution / resolution)
                write(struct.pack(out_endian + "IIII",
                                  seconds, scaled, captured, original))
                write(payload)
                written += PCAP_RECORD_HEADER + captured
        finally:
            if proc.stdout:
                proc.stdout.close()
            proc.terminate()
            proc.wait()

    if out_format is None:
        write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, 1))
        written += PCAP_GLOBAL_HEADER
    return written


# ---------------------------------------------------------------------------
# convergence on the state the control node wants
# ---------------------------------------------------------------------------
#
# A router rebuilds its whole ruleset from scratch every time it starts, and it
# always comes up frozen. Nothing else would ever tell it that the game is
# running, that a team is banned, or where the game server lives: restarting a
# single container used to leave the competition network frozen until the end
# of the game. So instead of being told once, the router keeps asking the
# control node what the network is supposed to look like and repairs the drift.


def resolve(name: str) -> str | None:
    try:
        return socket.gethostbyname(name)
    except OSError:
        return None


def reconcile_gameserver_route() -> None:
    """Route towards the game server alias (10.10.0.1).

    The game server announces it over the unix socket when it boots, which is
    useless if the router is the one that restarted.
    """
    address = resolve("gameserver")
    if not address:
        return  # a node without a local game server: nothing to route
    run([IP_CMD, "route", "replace", "10.10.0.1/32", "via", address])


AGENT_VERSION = "1"


def sync_with_control(state: str, banned: set[int],
                      suspended: set[str] | None = None) -> dict | None:
    """Heartbeat and state exchange with the control node.

    One call does everything: it says this router is alive and what its ruleset
    looks like right now, and it gets back the state it has to converge to. The
    control node learns the address to reach this agent at from the request
    itself, so nothing has to be configured on either side.
    """
    if not CONTROL or not TOKEN:
        return None
    payload = json.dumps(
        {
            "token": TOKEN,
            "node": NODE,
            "state": state,
            "banned": sorted(banned),
            "suspended": sorted(suspended or ()),
            "version": AGENT_VERSION,
        }
    ).encode()
    request = urllib.request.Request(
        f"{CONTROL}:8082/cluster/node-sync",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        # The control node may simply not be up yet.
        return None


# `ctfroute status` reports the state as an adjective, while the commands that
# reach it are verbs.
STATE_COMMANDS = {"unlocked": "unlock", "locked": "lock", "frozen": "freeze"}


def current_state() -> tuple[str, set[int]]:
    proc = run(["ctfroute", "status"])
    state = "unknown"
    banned: set[int] = set()
    for index, line in enumerate(proc.stdout.split()):
        if line.startswith("banned:"):
            try:
                banned.add(int(line.split(":", 1)[1]))
            except ValueError:
                pass
        elif index == 0:
            state = line
    return state, banned


def reconcile_network_state() -> None:
    state, banned = current_state()
    declared = set(configured_peers())
    live = {peer["address"] for peer in wireguard_peers()}
    desired = sync_with_control(state, banned, declared - live)
    if desired is None:
        return
    wanted_state = desired.get("state") or ""
    wanted_bans = {int(t) for t in desired.get("banned") or []}
    reconcile_peers({str(a) for a in desired.get("suspended") or []})

    if wanted_state and wanted_state != "unknown" and wanted_state != state:
        command = STATE_COMMANDS.get(wanted_state)
        if command is None:
            log(f"control node asked for an unknown network state: {wanted_state}")
        else:
            log(f"network is {state} but should be {wanted_state}, fixing it")
            proc = run(["ctfroute", command])
            if proc.returncode != 0:
                log(f"could not apply {command}: {proc.stderr.strip()}")

    for team in sorted(wanted_bans - banned):
        log(f"restoring the network ban of team {team}")
        run(["ctfroute", "ban", str(team)])
    for team in sorted(banned - wanted_bans):
        log(f"lifting the stale network ban of team {team}")
        run(["ctfroute", "unban", str(team)])


def reconcile_loop() -> None:
    while True:
        try:
            reconcile_gameserver_route()
            reconcile_network_state()
        except Exception as exc:  # never let the reconciler kill the router
            log(f"reconcile error: {exc}")
        time.sleep(RECONCILE_INTERVAL)


# ---------------------------------------------------------------------------
# remote ctfroute control
# ---------------------------------------------------------------------------

ALLOWED_COMMANDS = {"lock", "unlock", "freeze", "status"}
TEAM_COMMANDS = {"ban", "unban"}


def wireguard_status() -> list[dict]:
    proc = run(["wg", "show", "wg0", "dump"])
    if proc.returncode != 0:
        return []
    peers = []
    for index, line in enumerate(proc.stdout.splitlines()):
        if index == 0:  # first line describes the interface itself
            continue
        fields = line.split("\t")
        if len(fields) < 8:
            continue
        peers.append(
            {
                "public_key": fields[0],
                "endpoint": fields[2],
                "allowed_ips": fields[3],
                "last_handshake": int(fields[4] or 0),
                "rx": int(fields[5] or 0),
                "tx": int(fields[6] or 0),
            }
        )
    return peers


# ---------------------------------------------------------------------------
# per profile accounting and suspension
# ---------------------------------------------------------------------------
#
# WireGuard already counts every byte per peer, and a peer is exactly one VPN
# profile. That is a far better answer to "who is consuming what" than any
# iptables rule could give, and it costs nothing: the numbers are already
# there, they only have to be read and turned into deltas.
#
# The same peer list is what makes a single profile suspendable: dropping a
# peer from the running interface cuts that one laptop off without touching the
# rest of its team, and putting it back is the same line of configuration read
# out of wg0.conf.

WG_CONF = os.environ.get("WG_CONF", "/app/configs/wg0.conf")
ADMIN_TEAM_ID = -1
ADMIN_SUBNET = 253


def peer_identity(allowed_ips: str) -> tuple[int, int, str] | None:
    """(team id, profile number, address) of a profile, or None.

    Player profiles live at 10.80.<team>.<profile>, the organizers' at
    10.80.253.<profile>; anything else on the interface (a vulnbox tunnel, the
    node mesh) is not a profile and is left alone.
    """
    for chunk in allowed_ips.split(","):
        address = chunk.strip().split("/")[0]
        parts = address.split(".")
        if len(parts) != 4 or parts[0] != "10" or parts[1] != "80":
            continue
        try:
            third, fourth = int(parts[2]), int(parts[3])
        except ValueError:
            continue
        if third == ADMIN_SUBNET:
            return ADMIN_TEAM_ID, fourth, address
        return third, fourth, address
    return None


def wireguard_peers() -> list[dict]:
    """Every profile currently configured on wg0, with its counters."""
    proc = run(["wg", "show", "wg0", "dump"])
    if proc.returncode != 0:
        return []
    peers = []
    for index, line in enumerate(proc.stdout.splitlines()):
        if index == 0:  # the first line describes the interface itself
            continue
        fields = line.split("\t")
        if len(fields) < 8:
            continue
        identity = peer_identity(fields[3])
        if identity is None:
            continue
        team, profile, address = identity
        peers.append(
            {
                "public_key": fields[0],
                "team": team,
                "profile": profile,
                "address": address,
                "handshake": int(fields[4] or 0),
                "rx": int(fields[5] or 0),
                "tx": int(fields[6] or 0),
            }
        )
    return peers


def configured_peers() -> dict[str, dict]:
    """The profiles wg0.conf declares, by address.

    This is what a suspended peer is restored from: removing it from the
    running interface throws its keys away, and the file is where they live.
    """
    peers: dict[str, dict] = {}
    current: dict[str, str] = {}

    def store(entry: dict[str, str]) -> None:
        if not entry.get("PublicKey") or not entry.get("AllowedIPs"):
            return
        identity = peer_identity(entry["AllowedIPs"])
        if identity is None:
            return
        _, _, address = identity
        peers[address] = entry

    try:
        with open(WG_CONF) as handle:
            in_peer = False
            for raw in handle:
                line = raw.strip()
                if line.startswith("["):
                    if in_peer:
                        store(current)
                    current = {}
                    in_peer = line.lower() == "[peer]"
                    continue
                if not in_peer or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                current[key.strip()] = value.strip()
            if in_peer:
                store(current)
    except OSError as exc:
        log(f"cannot read {WG_CONF}: {exc}")
    return peers


def suspend_peer(address: str, entry: dict) -> bool:
    proc = run(["wg", "set", "wg0", "peer", entry["PublicKey"], "remove"])
    if proc.returncode != 0:
        log(f"could not suspend {address}: {proc.stderr.strip()}")
        return False
    log(f"suspended the VPN profile {address}")
    return True


def resume_peer(address: str, entry: dict) -> bool:
    args = ["wg", "set", "wg0", "peer", entry["PublicKey"],
            "allowed-ips", entry["AllowedIPs"]]
    preshared = entry.get("PresharedKey")
    proc = None
    if preshared:
        # `wg set` reads a preshared key from a file, never from the command
        # line, so it does not end up in the process list.
        path = f"/tmp/psk-{address.replace('.', '-')}"
        try:
            with open(path, "w") as handle:
                handle.write(preshared + "\n")
            os.chmod(path, 0o600)
            proc = run(args + ["preshared-key", path])
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    else:
        proc = run(args)
    if proc is None or proc.returncode != 0:
        log(f"could not resume {address}: {proc.stderr.strip() if proc else 'failed'}")
        return False
    log(f"restored the VPN profile {address}")
    return True


def reconcile_peers(desired_suspended: set[str]) -> None:
    """Makes the running interface match the profiles the organizers suspended.

    Runs on every reconcile tick, so a router that restarts (and comes back
    with every peer from wg0.conf) drops the suspended ones again on its own.
    """
    declared = configured_peers()
    if not declared:
        return
    live = {peer["address"] for peer in wireguard_peers()}
    for address in sorted(desired_suspended & live & set(declared)):
        suspend_peer(address, declared[address])
    for address in sorted((set(declared) - desired_suspended) - live):
        resume_peer(address, declared[address])


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

    def _authorized(self, token: str) -> bool:
        return bool(TOKEN) and token == TOKEN

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            self._send(200, {"node": NODE, "status": "ok"})
            return
        if self.path.startswith("/wireguard"):
            if not self._authorized(self.headers.get("X-Token", "")):
                self._send(401, {"error": "unauthorized"})
                return
            self._send(200, {"peers": wireguard_status()})
            return
        if self.path.startswith("/pcap/status"):
            if not self._authorized(self.headers.get("X-Token", "")):
                self._send(401, {"error": "unauthorized"})
                return
            self._send(200, pcap_status())
            return
        if self.path.startswith("/pcap/download"):
            if not self._authorized(self.headers.get("X-Token", "")):
                self._send(401, {"error": "unauthorized"})
                return
            self._serve_pcap()
            return
        self._send(404, {"error": "not found"})

    def _serve_pcap(self) -> None:
        query = parse_qs(urlparse(self.path).query)

        def number(name):
            raw = (query.get(name) or [""])[0]
            try:
                return float(raw) if raw else None
            except ValueError:
                return None

        start, end = number("from"), number("to")
        teams = []
        for chunk in (query.get("teams") or [""])[0].split(","):
            if chunk.strip().isdigit():
                teams.append(int(chunk.strip()))
        conditions = [part for part in (team_bpf(teams),
                                        (query.get("filter") or [""])[0].strip()) if part]
        bpf = " and ".join(conditions)

        if not PCAP_ENABLED:
            self._send(409, {"error": "capture is not enabled on this node"})
            return
        files = select_pcap_files(start, end)

        # Chunked: a slice of a busy game can be hundreds of megabytes, and
        # nothing here should ever hold one in memory.
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.tcpdump.pcap")
        self.send_header("X-Node", NODE)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        # http.server's wfile is unbuffered: every write is its own syscall.
        # Writing a chunk per packet would mean millions of them on a wide
        # download, which is what made the agent crawl (and everything else it
        # has to do along with it). Pack the output into large chunks instead.
        pending = bytearray()

        def flush() -> None:
            if not pending:
                return
            # One write for the whole chunk: the size line, the payload and the
            # terminator go out together.
            self.wfile.write(
                b"%X\r\n" % len(pending) + bytes(pending) + b"\r\n"
            )
            pending.clear()

        def write(data: bytes) -> None:
            if not data:
                return
            pending.extend(data)
            if len(pending) >= CHUNK_SIZE:
                flush()

        try:
            size = stream_filtered_pcap(write, files, bpf, start, end)
            flush()
            log(f"served {size} bytes from {len(files)} capture files")
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            try:
                self.wfile.write(b"0\r\n\r\n")
            except OSError:
                pass

    def do_POST(self):  # noqa: N802
        if not self.path.startswith("/ctfroute"):
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return
        if not self._authorized(payload.get("token", "")):
            self._send(401, {"error": "unauthorized"})
            return

        parts = str(payload.get("cmd", "")).strip().lower().split()
        if not parts:
            self._send(400, {"error": "missing command"})
            return
        command, args = parts[0], parts[1:]
        if command in ALLOWED_COMMANDS and not args:
            proc = run(["ctfroute", command])
        elif command in TEAM_COMMANDS and len(args) == 1 and args[0].isdigit():
            proc = run(["ctfroute", command, args[0]])
        else:
            self._send(400, {"error": "invalid command"})
            return

        if proc.returncode != 0:
            self._send(500, {"error": proc.stderr.strip() or "command failed"})
            return
        self._send(200, {"output": proc.stdout.strip()})


def serve_agent() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", AGENT_PORT), AgentHandler)
    log(f"agent listening on :{AGENT_PORT}")
    server.serve_forever()


def main() -> int:
    if ENABLE_ACCOUNTING:
        threading.Thread(target=traffic_loop, daemon=True).start()
    else:
        log("traffic monitoring disabled")
    if PCAP_ENABLED:
        threading.Thread(target=capture_loop, daemon=True).start()
    threading.Thread(target=reconcile_loop, daemon=True).start()
    serve_agent()
    return 0


if __name__ == "__main__":
    sys.exit(main())
