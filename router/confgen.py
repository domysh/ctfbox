#!/usr/bin/env python3
"""Generates every WireGuard configuration of a CTFBox deployment.

On a single machine this produces exactly what it always did: one server
interface, the player profiles, the admin profiles and one profile per vulnbox.

When more than one node takes part in the game the same run also produces, for
each VPN node, its own server interface (serving only the teams assigned to it),
a mesh interface linking the nodes together, and one profile per remote checker
node so that distributed checkers can reach the vulnboxes.
"""

from typing import List, Optional
from dataclasses import dataclass, field
import os
import sys
import shutil
import subprocess
import json


@dataclass
class Team:
    id: int
    name: str
    nop: bool = False


@dataclass
class Node:
    name: str
    roles: List[str] = field(default_factory=list)
    address: str = ""
    public_address: str = ""
    # Overrides the global port. Two VPN nodes sharing a host cannot both
    # publish the same one.
    wireguard_port: Optional[int] = None
    # Teams whose tunnels terminate here.
    teams: List[int] = field(default_factory=list)
    # Teams whose vulnbox runs here. Independent from `teams`: several VM nodes
    # can hang off a single VPN node.
    vm_teams: List[int] = field(default_factory=list)
    weight: int = 1

    def has_role(self, role: str) -> bool:
        return role in self.roles


@dataclass
class Config:
    teams: List[Team]
    server_addr: str
    wireguard_port: int
    wireguard_profiles: int
    external_servers: bool
    nodes: List[Node]


MESH_PORT_OFFSET = 1
MESH_NET = "10.10.240"
CHECKER_NET = "10.10.1"
# The organizers' own profiles. Hardcoded on the game server too
# (adminVPNNetwork in gameserver/src/admin_api.go): being in this subnet is
# what proves you are an organizer, so the two must agree.
ADMIN_NET = "10.80.253"

generated_pins = set()


def generate_pin():
    """Generate a random 6-digit pin."""
    pin = None
    while pin is None or pin in generated_pins:
        pin = int.from_bytes(os.urandom(6), "big") % (10**6)
    pin = str(pin).rjust(6, "0")
    generated_pins.add(pin)
    return pin


def generate_keypair():
    """Generate a WireGuard private and public key pair."""
    private_key = subprocess.check_output(["wg", "genkey"]).decode("utf-8").strip()
    public_key = (
        subprocess.check_output(["wg", "pubkey"], input=private_key.encode())
        .decode("utf-8")
        .strip()
    )
    return private_key, public_key


def generate_preshared_key():
    """Generate a WireGuard preshared key."""
    return subprocess.check_output(["wg", "genpsk"]).decode("utf-8").strip()


def parse_nodes(raw: str) -> List[Node]:
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Invalid NODES value: {exc}", file=sys.stderr)
        return []
    nodes = []
    for entry in data:
        nodes.append(
            Node(
                name=entry.get("name", "node"),
                roles=entry.get("roles", []),
                address=entry.get("address", ""),
                public_address=entry.get("public_address") or entry.get("address", ""),
                wireguard_port=entry.get("wireguard_port"),
                teams=entry.get("teams") or [],
                vm_teams=entry.get("vm_teams") or [],
                weight=int(entry.get("weight") or 1),
            )
        )
    return nodes


def load_config_from_env():
    """Load configuration from environment variables."""
    team_ids = os.environ.get("TEAM_IDS", "").split(",")
    nop_teams = list(
        map(
            lambda x: int(x.strip()),
            [ele for ele in os.environ.get("NOP_TEAMS", "").split(",") if ele.strip()],
        )
    )
    teams = []

    for team_id in team_ids:
        team_id = team_id.strip()
        if team_id:
            team_id = int(team_id)
            teams.append(
                Team(id=team_id, name=f"Team {team_id}", nop=(team_id in nop_teams))
            )

    return Config(
        teams=teams,
        server_addr=os.environ.get("PUBLIC_IP", ""),
        wireguard_port=int(os.environ.get("PUBLIC_PORT", "51820")),
        wireguard_profiles=int(os.environ.get("CONFIG_PER_TEAM", "1")),
        external_servers=os.environ.get("EXTERNAL_SERVERS", "0").strip().lower() == "1",
        nodes=parse_nodes(os.environ.get("NODES", "")),
    )


def assign_teams_to_nodes(config: Config) -> dict:
    """Returns {node_name: [team_id, ...]}.

    Explicit assignments in the configuration win; the remaining teams are
    spread over the VPN nodes proportionally to their weight, so that a beefier
    machine takes a bigger share of the tunnels.
    """
    vpn_nodes = [n for n in config.nodes if n.has_role("vpn") or n.has_role("router")]
    if not vpn_nodes:
        return {}

    assignment = {node.name: list(node.teams) for node in vpn_nodes}
    already = {team for teams in assignment.values() for team in teams}

    # Weighted round robin over the nodes.
    slots = []
    for node in vpn_nodes:
        slots.extend([node.name] * max(node.weight, 1))

    index = 0
    for team in config.teams:
        if team.id in already:
            continue
        assignment[slots[index % len(slots)]].append(team.id)
        index += 1
    return assignment


def node_endpoint(node: Optional[Node], config: Config) -> str:
    """Where players and vulnboxes dial a node: its public address."""
    if node is None:
        return config.server_addr
    return node.public_address or node.address or config.server_addr


def node_port(node: Optional[Node], config: Config) -> int:
    """The public port of a node's WireGuard interface."""
    if node is None or not node.wireguard_port:
        return config.wireguard_port
    return node.wireguard_port


# Names that only resolve from inside a container. They are the right endpoint
# for a vulnbox or a checker (which run in containers, with the matching
# `extra_hosts` entry) but never for a profile a human imports on their laptop.
CONTAINER_ONLY_HOSTS = {
    "host.docker.internal",
    "host.containers.internal",
    "gateway.docker.internal",
}


def admin_endpoint(node: Optional[Node], config: Config) -> str:
    """Where an organizer dials a node, from their own machine.

    Same as :func:`node_endpoint`, except that a container-only alias is
    rewritten to the loopback address. An all-in-one deployment (the
    simulation, above all) advertises `host.docker.internal` so that the
    containers reach each other through the host gateway, but an admin profile
    is always imported on the host, where that name does not resolve and the
    published port is on 127.0.0.1.

    Only the admin profiles get this treatment: the player and vulnbox
    profiles of such a deployment are consumed by containers, which do need
    the alias.
    """
    endpoint = node_endpoint(node, config)
    if endpoint in CONTAINER_ONLY_HOSTS:
        return "127.0.0.1"
    return endpoint


def mesh_endpoint(node: Node, config: Config) -> str:
    """Where the other nodes dial a node.

    The mesh is infrastructure talking to infrastructure, so it prefers the
    internal address: on a private network between the machines that is both
    faster and one less thing to expose. The public address is only the
    fallback for a node that has no internal address at all.
    """
    return node.address or node.public_address or config.server_addr


def generate_wg_server_interface(private_key, address="10.10.252.252/32", port=51820):
    return f"""[Interface]
Address = {address}
ListenPort = {port}
PrivateKey = {private_key}
MTU = 1280
"""


def generate_server_peer(client_pub, preshared_key, allowed_ips, endpoint=None, keepalive=False):
    peer = f"""
[Peer]
PublicKey = {client_pub}
PresharedKey = {preshared_key}
AllowedIPs = {allowed_ips}
"""
    if endpoint:
        peer += f"Endpoint = {endpoint}\n"
    if keepalive:
        peer += "PersistentKeepalive = 25\n"
    return peer


def generate_client_config(
    client_priv, client_ip, server_pub, preshared_key, server_addr, server_port,
    allowed_ips="10.10.0.0/24, 10.60.0.0/16, 10.80.0.0/16",
):
    return f"""[Interface]
PrivateKey = {client_priv}
Address = {client_ip}/32
MTU = 1280

[Peer]
PublicKey = {server_pub}
PresharedKey = {preshared_key}
AllowedIPs = {allowed_ips}
Endpoint = {server_addr}:{server_port}
PersistentKeepalive = 5
"""


def write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(content)


def generate_mesh(config: Config, assignment: dict,
                  entry_node: Optional[Node] = None) -> None:
    """Links the VPN nodes so that a player attached to node A can reach a
    vulnbox hosted on node B.

    Cryptokey routing is the only routing table WireGuard has: an address that
    appears in no peer's AllowedIPs simply has nowhere to go, and the packet is
    dropped without a word. So every subnet that lives behind a node has to be
    listed on the peers pointing at it - the teams it terminates, and, on the
    entry node, the organizers' and the checkers' own subnets.
    """
    mesh_nodes = [n for n in config.nodes if n.has_role("vpn") or n.has_role("router")]
    if len(mesh_nodes) < 2:
        return

    keys = {}
    for index, node in enumerate(mesh_nodes, start=1):
        private_key, public_key = generate_keypair()
        keys[node.name] = {
            "private": private_key,
            "public": public_key,
            "ip": f"{MESH_NET}.{index}",
        }

    def mesh_port_of(node: Node) -> int:
        return node_port(node, config) + MESH_PORT_OFFSET

    psk_matrix = {}
    for i, first in enumerate(mesh_nodes):
        for second in mesh_nodes[i + 1:]:
            psk_matrix[(first.name, second.name)] = generate_preshared_key()

    def psk(a: str, b: str) -> str:
        return psk_matrix.get((a, b)) or psk_matrix[(b, a)]

    for node in mesh_nodes:
        own = keys[node.name]
        content = generate_wg_server_interface(
            own["private"], address=f"{own['ip']}/24", port=mesh_port_of(node)
        )
        for peer in mesh_nodes:
            if peer.name == node.name:
                continue
            peer_keys = keys[peer.name]
            routes = [f"{peer_keys['ip']}/32"]
            if peer.has_role("control"):
                # The game server lives on the control node and everybody
                # addresses it as 10.10.0.1. The player profiles only allow
                # 10.10.0.0/24, so that is exactly what has to cross the mesh -
                # and it does not overlap the mesh addresses themselves.
                routes.append("10.10.0.0/24")
            if entry_node is not None and peer.name == entry_node.name:
                # The admin and the checker profiles are all issued for the
                # entry node, so their addresses live behind it. Without these
                # the request reaches the game server and the answer has no way
                # back: the organizer sees a tunnel that is up and a network
                # that does not respond.
                routes.append(f"{ADMIN_NET}.0/24")
                routes.append(f"{CHECKER_NET}.0/24")
            for team in sorted(assignment.get(peer.name, [])):
                routes.append(f"10.60.{team}.0/24")
                routes.append(f"10.80.{team}.0/24")
            endpoint = mesh_endpoint(peer, config)
            content += generate_server_peer(
                peer_keys["public"],
                psk(node.name, peer.name),
                ", ".join(routes),
                endpoint=f"{endpoint}:{mesh_port_of(peer)}" if endpoint else None,
                keepalive=True,
            )
        write(f"configs/nodes/{node.name}/wgmesh.conf", content)

    print(f"Generated mesh configuration for {len(mesh_nodes)} nodes.")


def generate_checker_profiles(
    config: Config, server_public_key: str, entry_node: Optional[Node] = None
) -> List[str]:
    """One VPN profile per remote checker node, so that a checker running
    anywhere can reach every vulnbox."""
    peers = []
    checker_nodes = [
        n for n in config.nodes if n.has_role("checker") and not n.has_role("control")
    ]
    for index, node in enumerate(checker_nodes, start=1):
        private_key, public_key = generate_keypair()
        preshared_key = generate_preshared_key()
        client_ip = f"{CHECKER_NET}.{index}"
        peers.append(generate_server_peer(public_key, preshared_key, f"{client_ip}/32"))
        write(
            f"configs/checkers/checker-{node.name}.conf",
            generate_client_config(
                private_key,
                client_ip,
                server_public_key,
                preshared_key,
                node_endpoint(entry_node, config),
                node_port(entry_node, config),
                allowed_ips="10.10.0.0/16, 10.60.0.0/16",
            ),
        )
    if checker_nodes:
        print(f"Generated {len(checker_nodes)} checker node profiles.")
    return peers


def main():
    if os.path.exists("configs/wg0.conf"):
        print("Configuration already generated. Exiting.")
        return

    shutil.rmtree("configs", ignore_errors=True)
    os.makedirs("configs", exist_ok=True)

    try:
        config = load_config_from_env()
        assignment = assign_teams_to_nodes(config)
        node_by_team = {
            team: next(n for n in config.nodes if n.name == node_name)
            for node_name, teams in assignment.items()
            for team in teams
        }

        # One server keypair per node running a router (a single machine keeps a
        # single one). `router` is the role of a node that runs one without
        # terminating any player tunnel - the control node, most of the time.
        vpn_nodes = [n for n in config.nodes if n.has_role("vpn") or n.has_role("router")]
        if not vpn_nodes:
            vpn_nodes = [Node(name="main", roles=["vpn"], address=config.server_addr,
                              public_address=config.server_addr)]
            assignment = {"main": [team.id for team in config.teams]}
            node_by_team = {team.id: vpn_nodes[0] for team in config.teams}

        # Where a person or a checker dials in. A node that only carries a
        # router for the game server is a poor entry point: it terminates no
        # tunnel and may not even be meant to face anybody. Prefer a real vpn
        # node and fall back to whatever runs a router.
        entry_nodes = [n for n in vpn_nodes if n.has_role("vpn")] or vpn_nodes

        server_keys = {}
        for node in vpn_nodes:
            private_key, public_key = generate_keypair()
            server_keys[node.name] = {"private": private_key, "public": public_key}

        # Peers are collected per node: a player only exists on the node that
        # terminates its tunnel.
        peers = {node.name: "" for node in vpn_nodes}

        def node_of(team_id: int) -> Node:
            return node_by_team.get(team_id, entry_nodes[0])

        for team in config.teams:
            if team.nop:
                continue
            pins_config = []
            team_dir = f"configs/team{team.id}"
            os.makedirs(team_dir, exist_ok=True)
            team_node = node_of(team.id)
            endpoint = node_endpoint(team_node, config)

            for profile_id in range(1, config.wireguard_profiles + 1):
                client_private_key, client_public_key = generate_keypair()
                preshared_key = generate_preshared_key()
                client_ip = f"10.80.{team.id}.{profile_id}"

                peers[team_node.name] += generate_server_peer(
                    client_public_key, preshared_key, f"{client_ip}/32"
                )
                write(
                    os.path.join(team_dir, f"team{team.id}-{profile_id}.conf"),
                    generate_client_config(
                        client_private_key,
                        client_ip,
                        server_keys[team_node.name]["public"],
                        preshared_key,
                        endpoint,
                        node_port(team_node, config),
                    ),
                )
                pins_config.append(
                    {
                        "team_id": team.id,
                        "profile_id": profile_id,
                        "pin": generate_pin(),
                        "client_ip": client_ip,
                        "node": team_node.name,
                    }
                )
            with open(os.path.join(team_dir, "pins.json"), "w") as f:
                json.dump(pins_config, f, indent=4)

        # Admin profiles exist on every node so that the organizers can always
        # get in, whichever endpoint they pick.
        os.makedirs("configs/admins", exist_ok=True)
        for profile_id in range(1, config.wireguard_profiles + 1):
            client_private_key, client_public_key = generate_keypair()
            preshared_key = generate_preshared_key()
            client_ip = f"{ADMIN_NET}.{profile_id}"
            # Only on the node the profile dials. The same address behind two
            # nodes would leave the rest of the cluster with two ways back and
            # no way to choose, which is worse than one way in.
            peers[entry_nodes[0].name] += generate_server_peer(
                client_public_key, preshared_key, f"{client_ip}/32"
            )
            write(
                os.path.join("configs/admins", f"admin-{profile_id}.conf"),
                generate_client_config(
                    client_private_key,
                    client_ip,
                    server_keys[entry_nodes[0].name]["public"],
                    preshared_key,
                    admin_endpoint(entry_nodes[0], config),
                    node_port(entry_nodes[0], config),
                ),
            )

        # Where each vulnbox physically runs, which is not necessarily the node
        # terminating its tunnel.
        vm_node_of_team = {
            team_id: node.name
            for node in config.nodes
            for team_id in node.vm_teams
        }

        # Vulnbox tunnels: each VM dials the node that terminates its tunnel.
        for team in config.teams:
            os.makedirs("configs/servers", exist_ok=True)
            team_node = node_of(team.id)
            client_private_key, client_public_key = generate_keypair()
            preshared_key = generate_preshared_key()
            client_ip = f"10.60.{team.id}.1"
            peers[team_node.name] += generate_server_peer(
                client_public_key, preshared_key, f"{client_ip}/32"
            )
            # `router` is the container name of the local router, so it can only
            # be used when the vulnbox runs on the very machine that terminates
            # its tunnel. Everything else dials the VPN node over the internet.
            vm_node_name = vm_node_of_team.get(team.id, team_node.name)
            colocated = vm_node_name == team_node.name and (
                team_node.has_role("vpn") or team_node.has_role("router")
            )
            if colocated and not config.external_servers:
                wg_server_ip = "router"
                wg_server_port = 51820
            else:
                wg_server_ip = node_endpoint(team_node, config)
                wg_server_port = node_port(team_node, config)
            write(
                f"configs/servers/server-{team.id}.conf",
                generate_client_config(
                    client_private_key,
                    client_ip,
                    server_keys[team_node.name]["public"],
                    preshared_key,
                    wg_server_ip,
                    wg_server_port,
                ),
            )

        checker_peers = generate_checker_profiles(
            config, server_keys[entry_nodes[0].name]["public"], entry_nodes[0]
        )
        # The checker profiles dial the entry node, so that is where their
        # peers have to live.
        for peer in checker_peers:
            peers[entry_nodes[0].name] += peer

        # Server interfaces
        for node in vpn_nodes:
            content = generate_wg_server_interface(server_keys[node.name]["private"])
            content += peers[node.name]
            write(f"configs/nodes/{node.name}/wg0.conf", content)

        generate_mesh(config, assignment, entry_nodes[0])

        # The local node uses configs/wg0.conf directly; the other nodes get
        # their directory shipped by `run.py node push`.
        local_node = os.environ.get("NODE_NAME", vpn_nodes[0].name)
        if local_node not in server_keys:
            local_node = vpn_nodes[0].name
        shutil.copyfile(f"configs/nodes/{local_node}/wg0.conf", "configs/wg0.conf")
        mesh_path = f"configs/nodes/{local_node}/wgmesh.conf"
        if os.path.exists(mesh_path):
            shutil.copyfile(mesh_path, "configs/wgmesh.conf")

        with open("configs/assignment.json", "w") as f:
            json.dump(assignment, f, indent=4)

        print("WireGuard configurations successfully generated in configs directory.")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
