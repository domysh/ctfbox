#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
import os
import subprocess
import json
import secrets
import shutil
import shlex
import base64
import zlib
import hashlib
import platform
from dataclasses import dataclass, field, asdict, fields
from typing import List, Optional, Dict, Any, Union

try:
    import readline  # For allow any size of input 0_0 Strange python

    readline.set_history_length(0)
except Exception:
    pass

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

pref = "\033["
reset = f"{pref}0m"


@dataclass
class Team:
    id: int
    name: str
    token: str
    nop: bool = False
    image: str = ""


ALL_ROLES = ["control", "vpn", "vm", "checker"]

# Incus can run a team box either as a system container (fast, shares the host
# kernel) or as a real virtual machine (its own kernel, stronger isolation, but
# it needs KVM on the host).
INCUS_MODES = ["incus", "incus-vm"]
VM_MODES = INCUS_MODES + ["privileged", "none"]


def uses_incus(config: "Config") -> bool:
    return config.vm_mode in INCUS_MODES


def incus_instance_type(config: "Config") -> str:
    return "virtual-machine" if config.vm_mode == "incus-vm" else "container"


@dataclass
class Node:
    """One machine of the deployment.

    A configuration without nodes describes a single all-in-one machine, which
    is what `./run.py start` has always produced; declaring nodes splits the
    same game over several machines.
    """

    name: str
    roles: List[str] = field(default_factory=lambda: list(ALL_ROLES))
    address: str = ""
    public_address: str = ""
    ssh: str = ""
    path: str = "~/ctfbox"
    # Deploy this node on the machine running the command, as its own compose
    # project. It is how several nodes can share one host, which is what the
    # bundled simulation does; on a real cluster you want `ssh` instead.
    local: bool = False
    # Overrides the global wireguard_port. Only needed when two VPN nodes share
    # a host and cannot both publish the same port.
    wireguard_port: Optional[int] = None
    weight: int = 1
    checker_concurrency: int = 0
    # Explicit team pinning. `teams` applies to every assignment the node takes
    # part in; `vm_teams` overrides it for the vulnbox placement only, so that
    # tunnels and VMs can be spread differently.
    teams: List[int] = field(default_factory=list)
    vm_teams: List[int] = field(default_factory=list)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def pinned_teams(self, role: str) -> List[int]:
        if role == "vm" and self.vm_teams:
            return list(self.vm_teams)
        return list(self.teams)


@dataclass
class Config:
    gameserver_token: str = ""
    server_addr: str = ""
    wireguard_port: int = 51000
    wireguard_profiles: int = 10
    dns: str = "1.1.1.1"
    tick_time: int = 120
    flag_expire_ticks: int = 5
    initial_service_score: int = 5000
    max_flags_per_request: int = 3000
    submission_timeout: float = 0.03
    network_limit_bandwidth: str = "50mbit"
    max_vm_cpus: str = "1"
    max_vm_mem: str = "2G"
    teams: List[Team] = field(default_factory=list)
    vm_mode: str = "incus"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    scoreboard_freeze_time: Optional[str] = None
    max_disk_size: Optional[str] = None
    gameserver_exposed_port: Optional[str] = None
    credential_server: Optional[str] = None
    debug: bool = False
    grace_time: int = 0
    checker_concurrency: int = 0
    checker_timeout: int = 30
    traffic_monitor: bool = True
    # Full packet capture on the routers. Off by default: it records the
    # players' real traffic, which is a deliberate decision and costs disk.
    pcap: bool = False
    # Size of the capture ring on every router, in MB. The oldest files are
    # dropped when it is reached, so the disk usage is bounded whatever happens.
    pcap_max_size: int = 512
    # Where the checkers live, relative to this file. Handy to run a game with a
    # different set of services without touching the repository.
    checkers_dir: str = "./gameserver/checkers"
    nodes: List[Node] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Config:
        data = dict(data)
        teams_data = data.pop("teams", [])
        teams = [team if isinstance(team, Team) else Team(**team) for team in teams_data]
        nodes_data = data.pop("nodes", []) or []
        nodes = [node if isinstance(node, Node) else Node(**node) for node in nodes_data]
        # Unknown keys are ignored instead of crashing: the game server writes
        # config.json back when the organizers change a setting at runtime.
        known = {f.name for f in fields(cls)}
        unknown = [key for key in data if key not in known]
        for key in unknown:
            data.pop(key)
        config = cls(**data, teams=teams, nodes=nodes)
        return config

    @classmethod
    def from_json_file(cls, filepath: str) -> Config:
        with open(filepath, "r") as f:
            return cls.from_dict(json.load(f))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save_to_file(self, filepath: str, indent: int = 4) -> None:
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=indent)


def file_sha_hash(filename):
    h = hashlib.sha256()
    b = bytearray(128 * 1024)
    mv = memoryview(b)
    with open(filename, "rb", buffering=0) as f:
        for n in iter(lambda: f.readinto(mv), 0):
            h.update(mv[:n])
    return h.hexdigest()


def dir_sha_hash(path: str) -> str:
    if not os.path.isdir(path):
        return ""
    hash_list = []
    for root, _, files in os.walk(path):
        for name in files:
            path = os.path.join(root, name)
            hash_list.append((path, file_sha_hash(path)))
    hash_list.sort(key=lambda x: x[0])
    return hashlib.sha256(
        b":".join(map(lambda a: (a[0] + ":" + a[1]).encode(), hash_list))
    ).hexdigest()


class g:
    keep_file = False
    name = "CTFBox"
    # Overridable so that a second game (the bundled simulation, a staging run)
    # can share the machine with a real one: it namespaces the compose project,
    # the container names and the volumes.
    # Note: the prebuilt VM image name is also derived from it and is hardcoded
    # in vm/Dockerfile, so a non default project cannot build VM images.
    project_name = os.environ.get("CTFBOX_PROJECT", "ctfbox")
    composefile = f".{project_name}-compose.yml"
    container_name = f"{project_name}-gameserver"
    # Overridable so that a second game (the bundled simulation, a staging run)
    # can live next to a real one without ever touching its config.
    config_file = os.environ.get("CTFBOX_CONFIG", "config.json")
    prebuild_image = f"{project_name}-prebuilder"
    prebuilded_container = f"{project_name}-prebuilded"
    prebuilt_image = (
        f"{project_name}-vm-base"  # this is dynamic here, but it needs to be
    )
    # manually changed in the FROM in vm/Dockerfile
    # and in the .gitignore
    secrets_dir = f".{project_name}-secrets-tmp"
    # Generated WireGuard material. Namespaced with the project so that a second
    # game on the same machine can never overwrite the profiles of a running
    # one: those hold private keys that exist nowhere else.
    configs_dir = (
        "./router/configs"
        if project_name == "ctfbox"
        else f"./router/configs-{project_name}"
    )


def is_linux():
    return (
        "linux" in sys.platform and "microsoft-standard" not in platform.uname().release
    )


# Terminal colors


class colors:
    black = "30m"
    red = "31m"
    green = "32m"
    yellow = "33m"
    blue = "34m"
    magenta = "35m"
    cyan = "36m"
    white = "37m"


def dict_to_yaml(
    data,
    indent_spaces: int = 4,
    base_indent: int = 0,
    additional_spaces: int = 0,
    add_text_on_dict: str | None = None,
):
    yaml = ""
    spaces = " " * ((indent_spaces * base_indent) + additional_spaces)
    if isinstance(data, dict):
        for key, value in data.items():
            if add_text_on_dict is not None:
                spaces_len = len(spaces) - len(add_text_on_dict)
                spaces = (" " * max(spaces_len, 0)) + add_text_on_dict
                add_text_on_dict = None
            if isinstance(value, dict) or isinstance(value, list):
                yaml += f"{spaces}{key}:\n"
                yaml += dict_to_yaml(
                    value,
                    indent_spaces=indent_spaces,
                    base_indent=base_indent + 1,
                    additional_spaces=additional_spaces,
                )
            else:
                yaml += f"{spaces}{key}: {value}\n"
            spaces = " " * ((indent_spaces * base_indent) + additional_spaces)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yaml += dict_to_yaml(
                    item,
                    indent_spaces=indent_spaces,
                    base_indent=base_indent,
                    additional_spaces=additional_spaces + 2,
                    add_text_on_dict="- ",
                )
            elif isinstance(item, list):
                yaml += dict_to_yaml(
                    item,
                    indent_spaces=indent_spaces,
                    base_indent=base_indent + 1,
                    additional_spaces=additional_spaces,
                )
            else:
                yaml += f"{spaces}- {item}\n"
    else:
        yaml += f"{data}\n"
    return yaml


def puts(text, *args, color=colors.white, is_bold=False, **kwargs):
    print(f"{pref}{1 if is_bold else 0};{color}" + text + reset, *args, **kwargs)


def sep():
    puts("-----------------------------------", is_bold=True)


def cmd_check(program, get_output=False, print_output=False, no_stderr=False):
    if get_output:
        return subprocess.getoutput(program)
    if print_output:
        return subprocess.call(program, shell=True) == 0
    return (
        subprocess.call(
            program,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL if no_stderr else subprocess.STDOUT,
            shell=True,
        )
        == 0
    )


def gen_args(args_to_parse: list[str] | None = None):
    # Main parser
    parser = argparse.ArgumentParser(description=f"{g.name} Manager")

    subcommands = parser.add_subparsers(
        dest="command", help="Command to execute", required=True
    )

    # Compose Command
    parser_compose = subcommands.add_parser("compose", help="Run docker compose command")
    parser_compose.add_argument(
        "compose_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to docker compose",
        default=[],
    )

    # Start Command
    parser_start = subcommands.add_parser(
        "start",
        help=f"Start {g.name} (every node of the cluster, if the config declares any)",
    )
    parser_start.add_argument(
        "--config-only", "-C", action="store_true", help="Only generate config file"
    )

    # Stop Command
    subcommands.add_parser("stop", help=f"Stop {g.name}")
    # Wg config gen command
    subcommands.add_parser(
        "wg-gen", help="Generate wireguard configs if not exists or config changed"
    )

    # Restart Command
    parser_restart = subcommands.add_parser("restart", help=f"Restart {g.name}")
    parser_restart.add_argument(
        "--logs",
        required=False,
        action="store_true",
        help=f"Show {g.name} logs",
        default=False,
    )

    # Clear Command
    parser_clear = subcommands.add_parser("clear", help="Clear data")
    parser_clear.add_argument(
        "--all", "-A", action="store_true", help="Clear everything"
    )
    parser_clear.add_argument(
        "--config", "-c", action="store_true", help="Clear config file"
    )
    parser_clear.add_argument(
        "--team-vms", "-T", action="store_true", help="Clear all VMs related data"
    )
    parser_clear.add_argument(
        "--wireguard", "-W", action="store_true", help="Clear wireguard data"
    )
    parser_clear.add_argument(
        "--checkers-data", "-C", action="store_true", help="Clear checkers data"
    )
    parser_clear.add_argument(
        "--gameserver-data", "-G", action="store_true", help="Clear gameserver data"
    )

    subcommands.add_parser("listvms", help="List team VMs")

    parser_resetvm = subcommands.add_parser(
        "resetvm",
        help="Reset a team VM to the state it started the game in",
    )
    parser_resetvm.add_argument(
        "team_id",
        type=int,
        nargs="+",
        help="ID of the team(s) whose VM to reset (use listvms to see the IDs)",
    )
    parser_resetvm.add_argument(
        "--yes", "-y", action="store_true", help="Do not ask for confirmation"
    )

    parser_vmshell = subcommands.add_parser("vmshell", help="Open a shell in the specified team VM")
    parser_vmshell.add_argument(
        "team_id",
        type=int,
        help="ID of the team whose VM to access (use listvms to see the IDs)",
    )
    parser_vmshell.add_argument(
        "vmshell_args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to exec command for team vms",
        default=[],
    )

    # Status Command
    subcommands.add_parser("status", help="Show status")

    # Distributed deployment commands
    parser_node = subcommands.add_parser(
        "node", help="Manage the nodes of a distributed deployment"
    )
    parser_node.add_argument(
        "node_action",
        choices=["list", "sync", "up", "down", "logs", "ps", "exec", "compose-file"],
        help="Action to run on the node(s)",
    )
    parser_node.add_argument(
        "node_name",
        nargs="?",
        default=None,
        help="Node name, or 'all' to act on every node",
    )
    parser_node.add_argument(
        "node_args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Arguments for the 'exec' action (passed to docker compose)",
    )

    subcommands.add_parser(
        "deploy", help="Deploy the whole cluster: control node first, then the others"
    )

    if args_to_parse is None:
        args = sys.argv[1:]
    if not args:
        args = ["start"]
    args = parser.parse_args(args=args)

    return args


if __name__ == "__main__":
    args = gen_args()


def get_deploy_info() -> dict:
    if os.path.isfile(".deploy_info"):
        with open(".deploy_info", "r") as f:
            return json.load(f)
    else:
        return {}


def set_deploy_info(data: dict):
    if not os.path.isfile(".deploy_info"):
        with open(".deploy_info", "w") as f:
            json.dump({}, f)
    with open(".deploy_info", "r+") as f:
        deploy_info = json.load(f)
        deploy_info.update(data)
        f.seek(0)
        f.truncate()
        json.dump(deploy_info, f, indent=4)


def composecmd(cmd, composefile=None, project=None):
    project = project or g.project_name
    if composefile:
        cmd = f"-f {composefile} {cmd}"
    if not cmd_check("docker --version"):
        puts("docker not found! please install docker!", color=colors.red)
        exit(1)
    elif not cmd_check("docker ps"):
        puts(
            "Cannot use docker, the user hasn't the permission or docker isn't running",
            color=colors.red,
        )
        exit(1)
    elif cmd_check("docker compose --version"):
        if os.system(f"docker compose -p {project} {cmd}") != 0:
            exit(1)
    elif cmd_check("docker-compose --version"):
        if os.system(f"docker-compose -p {project} {cmd}") != 0:
            exit(1)
    else:
        puts(
            "docker compose not found! please install docker compose!", color=colors.red
        )
        exit(1)


def check_already_running():
    return g.container_name in cmd_check(
        f'docker ps --filter "name=^{g.container_name}$"', get_output=True
    )


def prebuilder_exists():
    return g.prebuild_image in cmd_check(
        f'docker image ls --filter "reference={g.prebuild_image}"', get_output=True
    )


def prebuilt_exists():
    return g.prebuilt_image in cmd_check(
        f'docker image ls --filter "reference={g.prebuilt_image}"', get_output=True
    )


def remove_prebuilder():
    return cmd_check(f"docker image rm {g.prebuild_image}")


def remove_prebuilt():
    return cmd_check(f"docker image rm {g.prebuilt_image}")


def remove_prebuilded():
    return cmd_check(f"docker container rm {g.prebuilded_container}")


def remove_database_volume():
    return cmd_check(f"docker volume rm -f {g.project_name}_db-data")


def check_database_volume():
    return f"{g.project_name}_db-data" in cmd_check(
        f'docker volume ls --filter "name={g.project_name}_db-data"', get_output=True
    )


def build_prebuilder():
    return cmd_check(
        f"docker build -t {g.prebuild_image} -f ./vm/Dockerfile.prebuilder ./vm/",
        print_output=True,
    )


def build_prebuilt(privileged):
    return cmd_check(
        f"docker run -it --privileged --name {g.prebuilded_container} {g.prebuild_image}",
        print_output=True,
    )


def kill_builder():
    return cmd_check(f"docker kill {g.prebuilded_container}", no_stderr=True)


def commit_prebuilt():
    return cmd_check(
        f"docker commit {g.prebuilded_container} {g.prebuilt_image}:latest",
        print_output=True,
    )


def invalid_vm_mode(do_exit: bool = True):
    puts(
        "Invalid vm mode, please use one of: " + ", ".join(VM_MODES),
        color=colors.red,
    )
    puts(
        "  incus      - team boxes are Incus system containers (default)\n"
        "  incus-vm   - team boxes are real Incus virtual machines (needs KVM)\n"
        "  privileged - team boxes are privileged Docker containers\n"
        "  none       - CTFBox runs no team box at all",
        color=colors.yellow,
    )
    if do_exit:
        exit(1)


def incus_data_exists():
    return cmd_check(
        f"docker volume inspect {g.project_name}_incus-data >/dev/null 2>&1",
        no_stderr=True,
    )


def delete_incus_data():
    cmd_check(
        f"docker volume rm {g.project_name}_incus-data >/dev/null 2>&1", no_stderr=True
    )


# ---------------------------------------------------------------------------
# Cluster topology
# ---------------------------------------------------------------------------


def effective_nodes(config: Config) -> List[Node]:
    """The nodes taking part in the game.

    With no `nodes` in config.json this returns a single machine holding every
    role, which is exactly the classic single host deployment.
    """
    if not config.nodes:
        return [
            Node(
                name="main",
                roles=list(ALL_ROLES),
                address=config.server_addr,
                public_address=config.server_addr,
            )
        ]
    nodes: List[Node] = []
    for node in config.nodes:
        node = node if isinstance(node, Node) else Node(**node)
        if not node.roles:
            node.roles = list(ALL_ROLES)
        if not node.public_address:
            node.public_address = node.address
        nodes.append(node)
    if not any(node.has_role("control") for node in nodes):
        nodes[0].roles = list(nodes[0].roles) + ["control"]
    # The control node always runs a router, whether or not it terminates
    # player tunnels: the game server drives the network through the unix
    # socket that router shares with it, and the exposed scoreboard port is
    # published by it. The `router` role is the one that means "runs a router
    # but takes no team tunnels", so adding it never moves a team.
    for node in nodes:
        if node.has_role("control") and not (
            node.has_role("vpn") or node.has_role("router")
        ):
            node.roles = list(node.roles) + ["router"]
    return nodes


def control_node(config: Config) -> Node:
    nodes = effective_nodes(config)
    for node in nodes:
        if node.has_role("control"):
            return node
    return nodes[0]


def get_node(config: Config, name: Optional[str]) -> Node:
    if not name:
        return control_node(config)
    for node in effective_nodes(config):
        if node.name == name:
            return node
    puts(f"Unknown node '{name}'", color=colors.red)
    puts(
        "Known nodes: " + ", ".join(n.name for n in effective_nodes(config)),
        color=colors.yellow,
    )
    exit(1)


def assign_teams(config: Config, role: str) -> Dict[str, List[int]]:
    """Spreads the teams over the nodes holding `role`.

    Explicit `teams` lists in the configuration win, the rest is a weighted
    round robin so that a bigger machine takes a bigger share of the load.
    """
    nodes = [node for node in effective_nodes(config) if node.has_role(role)]
    if not nodes:
        return {}

    assignment = {node.name: node.pinned_teams(role) for node in nodes}
    already = {team for teams in assignment.values() for team in teams}

    slots: List[str] = []
    for node in nodes:
        slots.extend([node.name] * max(node.weight, 1))

    index = 0
    for team in config.teams:
        if team.id in already:
            continue
        assignment[slots[index % len(slots)]].append(team.id)
        index += 1
    return assignment


def validate_topology(config: Config) -> List[str]:
    """Returns the problems found in the `nodes` section, as human readable
    warnings. A single machine deployment never produces any."""
    nodes = effective_nodes(config)
    warnings: List[str] = []

    controls = [node.name for node in nodes if node.has_role("control")]
    if len(controls) > 1:
        warnings.append(
            f"{len(controls)} nodes declare the 'control' role ({', '.join(controls)}): "
            "exactly one node owns the database and the game server."
        )

    seen = set()
    for node in nodes:
        if node.name in seen:
            warnings.append(f"Duplicated node name '{node.name}'.")
        seen.add(node.name)

        if not node.has_role("control") and not node.ssh and not node.local:
            warnings.append(
                f"Node '{node.name}' is never deployed: it has no 'ssh' target and is "
                'not marked "local": true, so `deploy` skips it and nothing of it ever '
                f"runs. Add an ssh target, mark it local if it shares this machine, or "
                f"run './run.py node up {node.name}' on that machine yourself."
            )
        if not node.address and not node.public_address:
            warnings.append(f"Node '{node.name}' has no address.")
        elif node.ssh and "@" not in node.ssh and not node.address:
            warnings.append(
                f"Node '{node.name}' gives ssh as a bare username: it will connect to "
                f"'{ssh_target(node)}', falling back to the public address because the "
                "node has no internal address."
            )

    local_ports: Dict[int, List[str]] = {}
    for node in nodes:
        if node.name != control_node(config).name and not node.local:
            continue  # a node on its own machine owns its ports
        if node.has_role("vpn") or node.has_role("router"):
            local_ports.setdefault(node_wireguard_port(config, node), []).append(node.name)
    for port, owners in local_ports.items():
        if len(owners) > 1:
            warnings.append(
                f"Nodes {', '.join(owners)} share this machine and all want UDP {port}: "
                "only one of them can bind it. Give each a different 'wireguard_port'."
            )

    if any(node.has_role("vm") for node in nodes) and not any(
        node.has_role("vpn") or node.has_role("router") for node in nodes
    ):
        warnings.append(
            "Some nodes host VMs but no node has the 'vpn' role: the vulnboxes would "
            "have no endpoint to dial into."
        )

    for node in nodes:
        if (node.has_role("vpn") or node.has_role("router")) and not (
            node.public_address or node.address
        ):
            warnings.append(
                f"VPN node '{node.name}' has no public_address: the players and the "
                "vulnboxes assigned to it would not know where to connect."
            )

    unknown_roles = {
        role
        for node in nodes
        for role in node.roles
        if role not in ALL_ROLES and role != "router"
    }
    if unknown_roles:
        warnings.append(
            f"Unknown roles {sorted(unknown_roles)}: valid roles are {ALL_ROLES}."
        )
    return warnings


def print_topology_warnings(config: Config) -> None:
    for warning in validate_topology(config):
        puts(f"WARNING: {warning}", color=colors.yellow)


def teams_of_node(config: Config, node: Node, role: str) -> List[Team]:
    assigned = assign_teams(config, role).get(node.name, [])
    return [team for team in config.teams if team.id in assigned]


def nodes_payload(config: Config) -> str:
    """The topology handed to the router container so that confgen.py can build
    the per node WireGuard configurations.

    Both assignments travel with it: which node terminates a team's tunnels
    (`teams`) and which node hosts its vulnbox (`vm_teams`). They are
    independent on purpose - several VM nodes may hang off a single VPN node.
    """
    vpn_assignment = assign_teams(config, "vpn")
    vm_assignment = assign_teams(config, "vm")
    payload = []
    for node in effective_nodes(config):
        payload.append(
            {
                "name": node.name,
                "roles": node.roles,
                "address": node.address,
                "public_address": node.public_address or node.address,
                "wireguard_port": node_wireguard_port(config, node),
                "weight": node.weight,
                "teams": sorted(vpn_assignment.get(node.name, [])),
                "vm_teams": sorted(vm_assignment.get(node.name, [])),
            }
        )
    return json.dumps(payload, separators=(",", ":"))


def compose_file_for(node: Node, config: Config) -> str:
    if node.name == control_node(config).name:
        return g.composefile
    return f".{g.project_name}-compose.{node.name}.yml"


# Inside the game network the game server always answers on this address. The
# cluster API (:8082) is never published on any host: a remote node reaches it
# through the tunnels, which is also what keeps it out of reach of the players.
GAMESERVER_GAME_IP = "10.10.0.1"


def control_url(config: Config, node: Node) -> str:
    """How a node reaches the control node.

    On the control node itself that is plain Docker DNS. Everywhere else it goes
    over WireGuard: the node to node mesh for a router, the checker profile for
    a checker node. Using the node's public address instead would need port 8082
    open on the internet, which is exactly what should not happen.
    """
    if node.name == control_node(config).name:
        return "http://gameserver"
    return f"http://{GAMESERVER_GAME_IP}"


def is_multinode(config: Config) -> bool:
    return len(effective_nodes(config)) > 1


def write_compose(
    config: Union[Dict[str, Any], Config],
    incus_unless_stopped: bool = True,
    node: Optional[Union[str, Node]] = None,
):
    # Convert dict to Config object if needed
    if not isinstance(config, Config):
        config = Config.from_dict(config)

    target = node if isinstance(node, Node) else get_node(config, node)
    control = control_node(config)
    is_control = target.name == control.name
    multinode = is_multinode(config)

    is_privileged = False
    spawn_docker_teams = False
    external_wg_server_configs = False
    spawn_incus = False

    vm_teams = teams_of_node(config, target, "vm") if target.has_role("vm") else []
    run_router = target.has_role("vpn") or target.has_role("router")
    run_checker = target.has_role("checker") and not is_control

    if config.vm_mode == "privileged":
        is_privileged = True
        spawn_docker_teams = bool(vm_teams)
    elif config.vm_mode == "none":
        external_wg_server_configs = True
    elif uses_incus(config):
        spawn_incus = len(vm_teams) > 0
    else:
        invalid_vm_mode()

    cleanup_secrets()

    if spawn_docker_teams:
        # Create temporary directory for secrets if it doesn't exist
        if not os.path.exists(g.secrets_dir):
            os.makedirs(g.secrets_dir)
        # Create token secret files for each team
        for team in vm_teams:
            with open(f"{g.secrets_dir}/token_{team.id}", "w") as f:
                f.write(team.token)

    router_service = {
        "hostname": "router",
        "dns": [config.dns],
        "build": "./router",
        "cap_add": [
            "NET_ADMIN",
            "SYS_MODULE",
            "SYS_ADMIN",
        ],
        "sysctls": [
            "net.ipv4.ip_forward=1",
            "net.ipv4.tcp_timestamps=0",
            "net.ipv4.conf.all.rp_filter=1",
            "net.ipv6.conf.all.forwarding=0",
        ],
        "environment": {
            "PUID": os.getuid() if is_linux() else 0,
            "PGID": os.getgid() if is_linux() else 0,
            "RATE_NET": config.network_limit_bandwidth,
            "TEAM_IDS": ",".join(str(team.id) for team in config.teams),
            "NOP_TEAMS": ",".join(str(team.id) for team in config.teams if team.nop),
            "CONFIG_PER_TEAM": config.wireguard_profiles,
            "PUBLIC_IP": config.server_addr,
            "PUBLIC_PORT": config.wireguard_port,
            "EXTERNAL_SERVERS": "1" if external_wg_server_configs else "0",
            "NODE_NAME": target.name,
            "NODES": f"'{nodes_payload(config)}'" if multinode else "''",
            "GAMESERVER_TOKEN": config.gameserver_token,
            "CONTROL_ADDR": control_url(config, target),
            "TRAFFIC_MONITOR": "1" if config.traffic_monitor else "0",
            "PCAP": "1" if config.pcap else "0",
            "PCAP_MAX_SIZE": config.pcap_max_size,
        },
        "volumes": [
            # `unixsk` is a named volume: SELinux relabel flags like :z are a
            # bind mount option, and compose warns about them here.
            "unixsk:/unixsk",
            # A remote node receives its own interface as `configs/wg0.conf`; a
            # node sharing this machine with the control node reads it straight
            # out of its own directory, so the two do not overwrite each other.
            f"{router_configs_dir(config, target)}:/app/configs:z",
            *(["pcap-data:/pcap"] if config.pcap else []),
        ],
        "restart": "unless-stopped",
        # Lets a node dial another node that lives on the same machine, which is
        # how the bundled simulation runs three of them side by side.
        "extra_hosts": ["host.docker.internal:host-gateway"],
        "networks": {
            "internalnet": {
                "priority": 10,
            },
            "externalnet": {
                "priority": 1,
            },
            **({f"vm-team{team.id}": {} for team in vm_teams} if spawn_docker_teams else {}),
        },
        "ports": [
            f"{node_wireguard_port(config, target)}:51820/udp",
            *(
                [
                    f"{node_wireguard_port(config, target) + 1}:"
                    f"{node_wireguard_port(config, target) + 1}/udp"
                ]
                if multinode
                else []
            ),
            *(
                [f"{config.gameserver_exposed_port}:80"]
                if config.gameserver_exposed_port is not None and is_control
                else []
            ),
        ],
    }

    gameserver_service = {
        "hostname": "gameserver",
        "dns": [config.dns],
        "build": "./gameserver",
        "restart": "unless-stopped",
        "container_name": g.container_name,
        "cap_add": ["NET_ADMIN"],
        "environment": {
            "CTFBOX_NODE": target.name,
            "CTFBOX_ROLE": "control",
        },
        # The game server talks to the router over a unix socket as soon as it
        # starts, so it waits for the router to be ready; the database is
        # awaited in code instead. The dependency is only declared when the
        # router is part of this node's compose file: naming a service that is
        # not there makes the whole project invalid.
        "depends_on": {
            **(
                {"router": {"condition": "service_healthy"}}
                if run_router
                else {}
            ),
            "database": {"condition": "service_started"},
        },
        "networks": ["internalnet"],
        "volumes": [
            f"{config.checkers_dir}:/app/checkers:z",
            "unixsk:/unixsk",
            f"./{g.config_file}:/app/config.json:z",
        ],
    }

    # A dedicated checker node: a WireGuard sidecar puts it inside the game
    # network, the game server binary runs in worker mode next to it.
    checker_services = {
        "checkervpn": {
            "build": "./checkervpn",
            "restart": "unless-stopped",
            "cap_add": ["NET_ADMIN", "SYS_MODULE"],
            "sysctls": ["net.ipv4.conf.all.src_valid_mark=1"],
            "dns": [config.dns],
            # Same reason as the router: it has to be able to dial a node that
            # shares the machine with it.
            "extra_hosts": ["host.docker.internal:host-gateway"],
            "volumes": [
                    f"{g.configs_dir}/checkers/checker-{target.name}.conf:/config/checker.conf:ro",
            ],
            "networks": ["externalnet"],
        },
        "checker": {
            "build": "./gameserver",
            "restart": "unless-stopped",
            "depends_on": ["checkervpn"],
            "network_mode": "service:checkervpn",
            "environment": {
                "CTFBOX_ROLE": "worker",
                "CTFBOX_NODE": target.name,
                "CTFBOX_CONTROL": control_url(config, target),
                "CTFBOX_CONCURRENCY": target.checker_concurrency or config.checker_concurrency,
            },
            "volumes": [
                f"{config.checkers_dir}:/app/checkers:z",
                f"./{g.config_file}:/app/config.json:ro",
            ],
        },
    }

    services: Dict[str, Any] = {}
    if run_router:
        services["router"] = router_service
    if is_control:
        services["database"] = {
            "hostname": f"{g.project_name}-database",
            "dns": [config.dns],
            "image": "postgres:17",
            "restart": "unless-stopped",
            "environment": {
                "POSTGRES_USER": "user",
                "POSTGRES_PASSWORD": "pass",
                "POSTGRES_DB": "db",
            },
            "volumes": ["db-data:/var/lib/postgresql/data"],
            "networks": {
                "internalnet": "",
            },
        }
        services["gameserver"] = gameserver_service
        if config.credential_server is not None:
            services["credentials"] = {
                "hostname": "credentials",
                "dns": [config.dns],
                "build": "./credentials",
                "restart": "unless-stopped",
                "ports": [f"{config.credential_server}:4040"],
                **({"depends_on": ["router"]} if run_router else {}),
                "networks": ["internalnet"],
                "volumes": [
                    f"./{g.config_file}:/app/config.json:ro",
                    f"{g.configs_dir}:/app/router/configs:ro",
                ],
            }
    if run_checker:
        services.update(checker_services)
    if spawn_incus:
        services["incus"] = {
            "hostname": "incus",
            "dns": [config.dns],
            "build": "./incus",
            # `externalnet` keeps the priority it always had, so the default
            # route of the container does not move; `internalnet` is only there
            # so the game server can ask this node to reset one box.
            "networks": {
                "externalnet": {"priority": 10},
                "internalnet": {"priority": 1},
            },
            "stop_signal": "SIGWINCH",
            **({"restart": "unless-stopped"} if incus_unless_stopped else {}),
            "pid": "host",
            "cgroup": "host",
            "environment": {
                "NODE_TEAMS": ",".join(str(team.id) for team in vm_teams),
                "NODE_NAME": target.name,
                "INCUS_INSTANCE_TYPE": incus_instance_type(config),
                "GAMESERVER_TOKEN": config.gameserver_token,
            },
            "security_opt": [
                "seccomp=unconfined",
                "apparmor=unconfined",
                "label=disable",
            ],
            "sysctls": [
                "net.ipv4.ip_forward=1",
            ],
            "volumes": [
                f"./{g.config_file}:/config.json:ro",
                f"{g.configs_dir}:/router/configs:ro",
                "./vm:/vmdata:ro",
                "/dev:/dev:z",
                "/sys/fs/cgroup:/sys/fs/cgroup:z",
                "/lib/modules:/lib/modules:ro",
                "incus-data:/var/lib/incus",
            ],
            "privileged": True,
            "ulimits": {"nofile": {"soft": 1048576, "hard": 1048576}},
        }
    if spawn_docker_teams:
        for team in vm_teams:
            services[f"team{team.id}"] = {
                "hostname": f"team{team.id}",
                "dns": [config.dns],
                "build": {
                    "context": "./",
                    "dockerfile": "./vm/Dockerfile",
                    "secrets": [f"token_team_{team.id}"],
                    "args": {
                        "TEAM_ID": team.id,
                        "TEAM_NAME": team.name,
                    },
                },
                **({"storage_opt": {"size": config.max_disk_size}} if config.max_disk_size else {}),
                **({"privileged": "true"} if is_privileged else {}),
                "restart": "unless-stopped",
                "depends_on": [
                    "router",
                ],
                "networks": [f"vm-team{team.id}"],
                "deploy": {
                    "resources": {
                        "limits": {
                            "cpus": f'"{config.max_vm_cpus}"',
                            "memory": config.max_vm_mem,
                        }
                    }
                },
            }

    compose_path = compose_file_for(target, config)
    with open(compose_path, "wt") as compose:
        compose.write(
            dict_to_yaml(
                {
                    "services": services,
                    **(
                        {
                            "secrets": {
                                f"token_team_{team.id}": {
                                    "file": f"{g.secrets_dir}/token_{team.id}"
                                }
                                for team in vm_teams
                            }
                        }
                        if vm_teams and spawn_docker_teams
                        else {}
                    ),
                    "volumes": {
                        "unixsk": "",
                        "db-data": "",
                        "incus-data": "",
                        **({"pcap-data": ""} if config.pcap else {}),
                    },
                    "networks": {
                        "externalnet": "",
                        "internalnet": "",
                        **(
                            {f"vm-team{team.id}": "" for team in vm_teams}
                            if spawn_docker_teams
                            else {}
                        ),
                    },
                }
            )
        )
    return compose_path


def try_to_remove(file):
    try:
        os.remove(file)
    except FileNotFoundError:
        pass


def clear_data(
    remove_config=True,
    remove_prebuilded_container=True,
    remove_prebuilder_image=True,
    remove_prebuilt_image=True,
    remove_wireguard=True,
    remove_checkers_data=True,
    remove_gameserver_data=True,
    remove_incus_data=True,
):
    if remove_gameserver_data:
        puts("Removing database volume", color=colors.yellow)
        remove_database_volume()
    if remove_wireguard:
        puts(f"Removing wireguard configs ({g.configs_dir})", color=colors.yellow)
        shutil.rmtree(g.configs_dir, ignore_errors=True)
    if remove_config:
        puts("Removing config.json", color=colors.yellow)
        try_to_remove(g.config_file)
    if remove_prebuilded_container:
        puts("Removing prebuilded image", color=colors.yellow)
        remove_prebuilded()
    if remove_prebuilder_image:
        puts("Removing prebuilder image", color=colors.yellow)
        remove_prebuilder()
    if remove_prebuilt_image:
        puts("Removing prebuilt image", color=colors.yellow)
        remove_prebuilt()
    if remove_checkers_data:
        puts("Removing checkers data", color=colors.yellow)
        for service in os.listdir("./gameserver/checkers"):
            shutil.rmtree(
                f"./gameserver/checkers/{service}/flag_ids", ignore_errors=True
            )
    if remove_incus_data:
        puts("Removing incus data", color=colors.yellow)
        delete_incus_data()


def clear_data_only(
    remove_config=False,
    remove_prebuilded_container=False,
    remove_prebuilder_image=False,
    remove_prebuilt_image=False,
    remove_wireguard=False,
    remove_checkers_data=False,
    remove_gameserver_data=False,
    remove_incus_data=False,
):
    clear_data(
        remove_config=remove_config,
        remove_prebuilded_container=remove_prebuilded_container,
        remove_prebuilder_image=remove_prebuilder_image,
        remove_prebuilt_image=remove_prebuilt_image,
        remove_wireguard=remove_wireguard,
        remove_checkers_data=remove_checkers_data,
        remove_gameserver_data=remove_gameserver_data,
        remove_incus_data=remove_incus_data,
    )


def try_mkdir(path):
    try:
        os.mkdir(path)
    except FileExistsError:
        pass


def generate_teams_array(number_of_teams: int, enable_nop_team: bool) -> List[Team]:
    teams = []
    for i in range(number_of_teams + (1 if enable_nop_team else 0)):
        team = Team(
            id=i,
            name=f"Team {i}",
            token=secrets.token_hex(32),
            nop=(i == 0 and enable_nop_team),
            image="",
        )
        if i == 0 and enable_nop_team:
            team.name = "Nop Team"
        teams.append(team)
    return teams


def get_input(
    prompt: str,
    default=None,
    is_required: bool = False,
    default_prompt: str | None = None,
):
    if is_required:
        prompt += " (REQUIRED, no default): "
    elif default_prompt:
        prompt += f" (default={default_prompt}): "
    else:
        prompt += f" (default={default}): "
    value = input(prompt).strip()
    if value != "":
        return value
    if is_required:
        while value == "":
            value = input(prompt).strip()
        return value
    return default


def config_input() -> Config:
    # Ask if user wants to use the web editor
    use_web_editor = (
        get_input("Do you want to use the web editor?", "yes").lower().startswith("y")
    )

    if use_web_editor:
        puts("Open the web editor at: https://ctfbox.domy.sh/editor", color=colors.green)
        puts(
            "Configure your settings and then click 'Copy Compressed Config'",
            color=colors.green,
        )
        puts("Paste the base64 compressed config below:", color=colors.yellow)

        config_input = input().strip()

        # User provided base64 compressed config
        try:
            # Decode base64 and decompress
            decoded_bytes = base64.b64decode(config_input)
            decompressed_bytes = zlib.decompress(decoded_bytes)
            config_data = json.loads(decompressed_bytes.decode("utf-8"))
            return Config.from_dict(config_data)
        except Exception as e:
            puts(f"Error decoding configuration: {e}", color=colors.red)
            puts(
                "Please try again with valid base64 compressed config", color=colors.red
            )
            exit(1)

    # Original config input flow
    # abs() put for consistency with the other options
    default_configs = Config()
    c = Config()

    number_of_teams = abs(int(get_input("Number of teams, >= 0 and < 250", 4)))
    while number_of_teams < 0 or number_of_teams >= 250:
        number_of_teams = abs(int(get_input("Number of teams, >= 0 and < 250", 4)))
    enable_nop_team = get_input("Enable NOP team?", "yes").lower().startswith("y")

    # abs() put for consistency with the other options
    c.wireguard_port = abs(
        int(
            get_input(
                f"Wireguard port, >= 1 and <= {65535-number_of_teams}",
                default_configs.wireguard_port,
            )
        )
    )
    while c.wireguard_port < 1 or c.wireguard_port > 65535 - number_of_teams:
        c.wireguard_port = abs(
            int(
                get_input(
                    f"Wireguard port, >= 1 and <= {65535-number_of_teams}",
                    default_configs.wireguard_port,
                )
            )
        )

    c.wireguard_profiles = abs(
        int(
            get_input(
                "Number of wireguard profiles for each team",
                default_configs.wireguard_profiles,
            )
        )
    )
    c.server_addr = get_input("Server address", is_required=True)
    c.dns = get_input("DNS", default_configs.dns)

    puts(
        "VM modes: incus (system containers), incus-vm (real virtual machines, "
        "needs KVM on the host), privileged (Docker), none",
        color=colors.yellow,
    )
    while True:
        c.vm_mode = get_input(
            "VM mode (" + "/".join(VM_MODES) + ")", default_configs.vm_mode
        ).lower()
        if c.vm_mode in VM_MODES:
            break
        invalid_vm_mode(do_exit=False)

    if c.vm_mode != "none":
        c.max_vm_cpus = get_input("Max VM CPUs", default_configs.max_vm_cpus)
        c.max_vm_mem = get_input("Max VM Memory", default_configs.max_vm_mem)
        if uses_incus(c) or get_input(
            "Enable disk limit? (REQUIRES XFS FILESYSTEM!)", "yes"
        ).lower().startswith("y"):
            c.max_disk_size = get_input("Max VM disk size", "30G")
        else:
            c.max_disk_size = None

    c.start_time = get_input("Start time, in RFC 3339 (YYYY-mm-dd HH:MM:SS+/-zz:zz)")
    c.end_time = get_input("End time, in RFC 3339 (YYYY-mm-dd HH:MM:SS+/-zz:zz)")
    c.grace_time = abs(
        int(
            get_input(
                "Grace time in seconds (before start_time - grace time the router is fronzen)",
                default_configs.grace_time,
            )
        )
    )
    c.tick_time = abs(int(get_input("Tick time in seconds", default_configs.tick_time)))
    c.flag_expire_ticks = abs(
        int(
            get_input(
                "Number of ticks after which each flag expires",
                default_configs.flag_expire_ticks,
            )
        )
    )

    c.initial_service_score = abs(
        int(get_input("Initial service score", default_configs.initial_service_score))
    )
    c.max_flags_per_request = abs(
        int(get_input("Max flags per request", default_configs.max_flags_per_request))
    )
    c.submission_timeout = abs(
        float(get_input("Submission timeout", default_configs.submission_timeout))
    )
    c.network_limit_bandwidth = get_input(
        "Network limit bandwidth", default_configs.network_limit_bandwidth
    )

    if (
        get_input("Expose externally the gameserver scoreboard?", "no")
        .lower()
        .startswith("y")
    ):
        c.gameserver_exposed_port = get_input(
            "Insert with witch port or ip:port to expose the gameserver scoreboard",
            "127.0.0.1:8888",
        )
    else:
        c.gameserver_exposed_port = None

    if get_input("Enable credential service?", "no").lower().startswith("y"):
        c.credential_server = get_input(
            "Insert the port to expose the credential server", "127.0.0.1:4040"
        )
    else:
        c.credential_server = None

    c.gameserver_token = get_input(
        "Gameserver token",
        default_prompt="randomly generated",
        default=secrets.token_hex(32),
    )
    c.scoreboard_freeze_time = get_input(
        "Scoreboard freeze time, in RFC 3339 (empty = never freeze). "
        "After it the ranking stops updating but the SLA keeps moving"
    )
    c.checker_timeout = abs(
        int(get_input("Checker timeout in seconds", default_configs.checker_timeout))
    )
    c.checker_concurrency = abs(
        int(
            get_input(
                "Checker concurrency (0 = automatic, based on the CPUs)",
                default_configs.checker_concurrency,
            )
        )
    )
    c.traffic_monitor = (
        get_input("Enable per team traffic monitoring?", "yes").lower().startswith("y")
    )

    # Create teams
    c.teams = generate_teams_array(number_of_teams, enable_nop_team)

    # Create and return the Config object
    return c


def create_config(data: Union[Dict[str, Any], Config]) -> Config:
    if not isinstance(data, Config):
        data = Config.from_dict(data)
    data.save_to_file(g.config_file)
    return data


def config_exists():
    return os.path.isfile(g.config_file)


def read_config() -> Config:
    return Config.from_json_file(g.config_file)


def cleanup_secrets():
    if os.path.exists(g.secrets_dir):
        shutil.rmtree(g.secrets_dir)


def vpn_config_hash(config: Config):
    data = []
    for team in config.teams:
        data.append(f"teamid={team.id}&nop={'1' if team.nop else '0'}")
    data.append(f"wg_profiles={config.wireguard_profiles}")
    data.append(f"wg_port={config.wireguard_port}")
    data.append(f"server_addr={config.server_addr}")
    # Only whether the boxes dial in from outside matters here, so switching
    # between Incus containers and Incus VMs leaves the player profiles alone.
    data.append(f"vm_mode={'incus' if uses_incus(config) else config.vm_mode}")
    # The topology changes which node terminates which tunnel, so it has to
    # invalidate the generated WireGuard profiles too. Left out entirely on a
    # single machine, so that existing deployments keep their profiles.
    if config.nodes:
        data.append(f"nodes={nodes_payload(config)}")
    data.sort()
    return hashlib.sha256(("::".join(data)).encode()).hexdigest()


def server_config_hash(config: Config):
    return dir_sha_hash(f"{g.configs_dir}/servers")


def router_generate_configs(config: Config, down_after_gen: bool = True):
    info = get_deploy_info()
    old_hash = info.get("vpn_config_hash", None)
    current_hash = vpn_config_hash(config)
    if not os.path.isfile(f"{g.configs_dir}/wg0.conf") or old_hash != current_hash:
        if check_already_running():
            puts(
                f"Can't generate configs if {g.project_name} is already running!",
                color=colors.red,
            )
            exit(1)
        clear_data_only(remove_wireguard=True)
        puts("Generating wireguard configuration", color=colors.yellow)
        composecmd("down router --remove-orphans", g.composefile)
        composecmd("up router -d --build --remove-orphans --wait", g.composefile)
        set_deploy_info({"vpn_config_hash": current_hash})
        if down_after_gen:
            composecmd("down router --remove-orphans", g.composefile)
        return True
    else:
        if not down_after_gen:
            composecmd("up router -d --build --remove-orphans --wait", g.composefile)
        puts("Wireguard configs already generated!")
    return False


def buildvms(config):
    vm_dir_hash = dir_sha_hash("./vm")
    info = get_deploy_info()
    old_vm_dir_hash = info.get("vm_dir_hash", "")
    was_built_with = info.get("vm_mode_build", False)
    vm_router_hash = info.get("vm_router_hash", None)
    current_router_hash = server_config_hash(config)
    if config.vm_mode == "privileged":
        if (
            not prebuilt_exists()
            or vm_dir_hash != old_vm_dir_hash
            or was_built_with != config.vm_mode
        ):
            puts("Need to build the team VM image", color=colors.yellow)
            clear_data_only(
                remove_prebuilded_container=True,
                remove_prebuilt_image=True,
                remove_prebuilder_image=True,
                remove_incus_data=True,
            )
            puts("Building the prebuilder image", color=colors.yellow)
            if not build_prebuilder():
                puts("Error building prebuilder image", color=colors.red)
                exit(1)
            puts(
                "Executing prebuilder to create VMs' base image",
                color=colors.yellow,
            )
            if not build_prebuilt(config.vm_mode == "privileged"):
                puts("Error building prebuilt image", color=colors.red)
                exit(1)
            puts(
                "Saving base VM container as image to be used to build the CTF services\n(this action can take a while and produces no output)",
                color=colors.yellow,
            )
            if not commit_prebuilt():
                puts("Error commiting prebuilt image", color=colors.red)
                exit(1)
            puts("Clear unused images", color=colors.yellow)
            remove_prebuilded()
    elif config.vm_mode == "none":
        puts(
            "VM 'none' mode selected, skipping VM image build",
            color=colors.yellow,
        )
    elif uses_incus(config):
        if (
            not incus_data_exists()
            or vm_dir_hash != old_vm_dir_hash
            or was_built_with != config.vm_mode
            or vm_router_hash != current_router_hash
        ):
            write_compose(config, incus_unless_stopped=False)
            puts("Need to build the incus VMs", color=colors.yellow)
            clear_data_only(
                remove_prebuilded_container=True,
                remove_prebuilt_image=True,
                remove_prebuilder_image=True,
                remove_incus_data=True,
            )
            puts("Building the incus VMs", color=colors.yellow)
            composecmd(
                "up incus --build --remove-orphans --exit-code-from incus",
                g.composefile,
            )
            write_compose(config)
        else:
            puts(
                "Incus VMs already exists, skipping build",
                color=colors.yellow,
            )
    else:
        invalid_vm_mode()
    set_deploy_info(
        {
            "vm_dir_hash": vm_dir_hash,
            "vm_mode_build": config.vm_mode,
            "vm_router_hash": current_router_hash,
        }
    )

# ---------------------------------------------------------------------------
# Remote nodes
# ---------------------------------------------------------------------------

RSYNC_EXCLUDES = [
    ".git",
    "node_modules",
    "dist",
    "__pycache__",
    ".ctfbox-secrets-tmp",
    "demo",
    "router/configs",
    ".ctfbox-compose*.yml",
]


def router_configs_dir(config: Config, node: Node) -> str:
    """The directory a node's router reads its WireGuard interface from."""
    if node.local and node.name != control_node(config).name:
        return f"{g.configs_dir}/nodes/{node.name}"
    return g.configs_dir


def node_wireguard_port(config: Config, node: Node) -> int:
    return node.wireguard_port or config.wireguard_port


def node_project(config: Config, node: Node) -> str:
    """The docker compose project of a node.

    Each node gets its own so that several of them can live on one host without
    fighting over container names; the control node keeps the bare project name
    so that existing deployments are untouched.
    """
    if node.name == control_node(config).name:
        return g.project_name
    return f"{g.project_name}-{node.name}"


def ssh_target(node: Node) -> str:
    """The ssh destination of a node.

    Writing only a username is enough: the host defaults to the node's internal
    address, which is the address the rest of the cluster already uses to reach
    it. A full `user@host` is of course still accepted.
    """
    if not node.ssh:
        return ""
    if "@" in node.ssh:
        return node.ssh
    host = node.address or node.public_address
    return f"{node.ssh}@{host}" if host else node.ssh


def node_is_local(config: Config, node: Node) -> bool:
    """Whether this node runs on the machine we are driving the deploy from."""
    return node.local or not node.ssh


def run_cmd(cmd: str, description: str | None = None) -> bool:
    if description:
        puts(description, color=colors.yellow)
    return os.system(cmd) == 0


def node_compose(config: Config, node: Node, compose_args: str) -> bool:
    """Runs a docker compose command on a node, locally or over ssh."""
    compose_path = compose_file_for(node, config)
    project = node_project(config, node)
    if node_is_local(config, node):
        composecmd(compose_args, compose_path, project=project)
        return True
    remote = f"cd {node.path} && docker compose -p {project} -f {compose_path} {compose_args}"
    return run_cmd(f"ssh {ssh_target(node)} {json.dumps(remote)}")


def ssh_capture(node: Node, remote_cmd: str) -> Optional[str]:
    """Runs a command on a node and returns its output, or None if it failed."""
    result = subprocess.run(
        ["ssh", ssh_target(node), remote_cmd],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


# Docker is the only thing a node has to have installed: everything else the
# deployment needs is carried in containers, rsync included.
RSYNC_IMAGE = f"{g.project_name}-rsync"
RSYNC_DOCKERFILE = "FROM alpine:3\nRUN apk add --no-cache rsync\n"


def check_remote_docker(node: Node) -> bool:
    # Separate "the machine is not there" from "docker is not usable there":
    # they look identical in the output and need completely different fixes.
    if ssh_capture(node, "echo ok") is None:
        puts(
            f"Node '{node.name}' is unreachable: ssh {ssh_target(node)} does not answer.",
            color=colors.red,
            is_bold=True,
        )
        puts(
            "  Is the machine up, is its address still the one in config.json, and does\n"
            "  ssh work without a password from here (ssh-copy-id)?",
            color=colors.yellow,
        )
        return False
    version = ssh_capture(node, "docker version --format '{{.Server.Version}}'")
    if version is None:
        puts(
            f"Node '{node.name}' answers on ssh but cannot run docker.",
            color=colors.red,
        )
        puts(
            "  Install docker there and let the ssh user use it "
            "(usually: usermod -aG docker <user>).",
            color=colors.yellow,
        )
        return False
    puts(f"  docker {version} on {node.name}", color=colors.green)
    return True


def ensure_remote_rsync(node: Node) -> bool:
    """Makes sure the node can run rsync, without installing anything on it.

    rsync has to exist on both ends of a transfer, and asking every machine of a
    deployment to have it is exactly the kind of prerequisite that bites during
    a competition. So the remote side runs it out of a two line image built with
    the docker we already require — the same way on every node, whatever each
    one happens to have installed.
    """
    if ssh_capture(node, f"docker image inspect {RSYNC_IMAGE} >/dev/null 2>&1 && echo ok"):
        return True
    puts(f"  building the rsync helper image on {node.name}", color=colors.yellow)
    result = subprocess.run(
        ["ssh", ssh_target(node), f"docker build -q -t {RSYNC_IMAGE} -"],
        input=RSYNC_DOCKERFILE,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        puts(
            f"Cannot build the rsync helper image on {node.name}: "
            f"{result.stderr.strip()}",
            color=colors.red,
        )
        puts(
            "  The image is a plain `FROM alpine:3` plus `apk add rsync`, so this "
            "almost always\n"
            "  means the node cannot reach a package mirror from inside a build "
            "container:\n"
            "  check its DNS and its outbound access, or preload the image there with\n"
            f"  `docker pull` from a registry you can reach and tag it {RSYNC_IMAGE}.",
            color=colors.yellow,
        )
        return False
    return True


def remote_rsync_path(node: Node, remote_root: str, user: str) -> str:
    """The rsync command the remote end runs, wrapped in a container.

    The destination is mounted at the very same path it has on the host, so the
    paths rsync exchanges mean the same thing on both sides, and the container
    runs as the ssh user so the files do not end up owned by root.
    """
    return (
        f"docker run --rm -i --user {user} "
        f"-v {shlex.quote(remote_root)}:{shlex.quote(remote_root)} "
        f"{RSYNC_IMAGE} rsync"
    )


def node_sync(config: Config, node: Node) -> bool:
    """Ships the repository and the node specific secrets to a remote node."""
    if node_is_local(config, node):
        puts(f"Node {node.name} is local, nothing to sync", color=colors.yellow)
        return True
    if not cmd_check("rsync --version"):
        puts(
            "rsync is needed on this machine to deploy the other nodes "
            "(the nodes themselves only need docker)",
            color=colors.red,
        )
        return False

    target = ssh_target(node)
    puts(f"Preparing {node.name} ({target})", color=colors.yellow)
    if not check_remote_docker(node):
        return False

    # Resolve the destination once: `~` means nothing inside a container mount.
    remote_root = ssh_capture(node, f"mkdir -p {node.path} && cd {node.path} && pwd")
    if not remote_root:
        puts(f"Cannot create {node.path} on {node.name}", color=colors.red)
        return False
    remote_user = ssh_capture(node, "echo $(id -u):$(id -g)")
    if not remote_user:
        puts(f"Cannot read the remote user of {node.name}", color=colors.red)
        return False
    if not ensure_remote_rsync(node):
        return False

    rsync_path = remote_rsync_path(node, remote_root, remote_user)
    rsync_opts = f"-az --rsync-path={shlex.quote(rsync_path)}"

    def push(source: str, destination: str, extra: str = "") -> bool:
        return run_cmd(
            f"rsync {rsync_opts} {extra} {shlex.quote(source)} "
            f"{target}:{shlex.quote(remote_root + '/' + destination)}"
        )

    excludes = " ".join(f"--exclude {json.dumps(pattern)}" for pattern in RSYNC_EXCLUDES)
    if not run_cmd(
        f"rsync {rsync_opts} --delete {excludes} ./ {target}:{shlex.quote(remote_root + '/')}",
        f"Syncing sources to {node.name}",
    ):
        return False

    # Per node secrets: its own WireGuard server interface, the mesh link, the
    # vulnbox profiles it has to serve and its checker profile.
    node_dir = f"{g.configs_dir}/nodes/{node.name}"
    files = []
    if os.path.isfile(f"{node_dir}/wg0.conf"):
        files.append((f"{node_dir}/wg0.conf", "router/configs/wg0.conf"))
    if os.path.isfile(f"{node_dir}/wgmesh.conf"):
        files.append((f"{node_dir}/wgmesh.conf", "router/configs/wgmesh.conf"))
    checker_conf = f"{g.configs_dir}/checkers/checker-{node.name}.conf"
    if os.path.isfile(checker_conf):
        files.append((checker_conf, f"router/configs/checkers/checker-{node.name}.conf"))

    directories = {os.path.dirname(remote) for _, remote in files}
    directories.add("router/configs/servers")
    ssh_capture(
        node,
        " && ".join(f"mkdir -p {shlex.quote(remote_root + '/' + d)}" for d in sorted(directories)),
    )

    for local_path, remote_path in files:
        if not push(local_path, remote_path):
            return False

    if os.path.isdir(f"{g.configs_dir}/servers"):
        if not push(f"{g.configs_dir}/servers/", "router/configs/servers/"):
            return False

    compose_path = compose_file_for(node, config)
    write_compose(config, node=node)
    if not push(compose_path, compose_path):
        return False
    if not push(g.config_file, g.config_file):
        return False

    puts(f"Node {node.name} synced", color=colors.green)
    return True


def node_status(config: Config, node: Node) -> None:
    roles = ",".join(node.roles)
    location = ssh_target(node) or "local"
    vm_teams = sorted(assign_teams(config, "vm").get(node.name, []))
    vpn_teams = sorted(assign_teams(config, "vpn").get(node.name, []))
    puts(f"- {node.name} [{roles}] {location}", is_bold=True)
    puts(f"    address: {node.address or '(none)'} public: {node.public_address or '(none)'}")
    if node.has_role("vm"):
        puts(f"    vm teams : {vm_teams if vm_teams else 'none'}")
    if node.has_role("vpn"):
        puts(f"    vpn teams: {vpn_teams if vpn_teams else 'none'}")
    if node.has_role("checker"):
        puts(f"    checker concurrency: {node.checker_concurrency or 'auto'}")
    if node.name != control_node(config).name:
        if node.local:
            puts("    deployed by: this machine ('local': true)")
        elif node.ssh:
            puts(f"    deployed by: ssh {ssh_target(node)}")
        else:
            puts(
                f"    deployed by: NOBODY — '{sys.argv[0]} deploy' skips it: give it "
                'an "ssh" target, or "local": true if it shares this machine',
                color=colors.red,
            )


def handle_node_command(args) -> None:
    if not config_exists():
        puts(f"Config file not found! please run {sys.argv[0]} start", color=colors.red)
        return
    config = read_config()
    action = args.node_action

    if action == "list":
        puts(f"{g.name} topology ({len(effective_nodes(config))} node(s))", is_bold=True)
        for node in effective_nodes(config):
            node_status(config, node)
        print_topology_warnings(config)
        return

    if action == "compose-file":
        for node in effective_nodes(config):
            path = write_compose(config, node=node)
            puts(f"{node.name}: {path}", color=colors.green)
        return

    targets = (
        effective_nodes(config)
        if args.node_name in (None, "all")
        else [get_node(config, args.node_name)]
    )

    for node in targets:
        if action == "sync":
            node_sync(config, node)
        elif action == "up":
            write_compose(config, node=node)
            node_compose(config, node, "up -d --build --remove-orphans")
        elif action == "down":
            write_compose(config, node=node)
            node_compose(config, node, "down --remove-orphans")
        elif action == "logs":
            node_compose(config, node, "logs --tail 100")
        elif action == "ps":
            node_compose(config, node, "ps")
        elif action == "exec":
            node_compose(config, node, " ".join(args.node_args))


def vm_node_of_team(config: Config, team_id: int) -> Optional[Node]:
    """The node whose incus (or docker) hosts a team's box."""
    for name, teams in assign_teams(config, "vm").items():
        if team_id in teams:
            return get_node(config, name)
    return None


def reset_vm(config: Config, team_id: int) -> bool:
    """Puts one team box back to the state it started the game in.

    The work happens on the node that hosts the box, which is not necessarily
    this one: on a distributed deployment the command is forwarded over ssh,
    the same way every other node operation is.
    """
    team = next((team for team in config.teams if team.id == team_id), None)
    if team is None:
        puts(f"No team with id {team_id} in {g.config_file}", color=colors.red)
        return False

    if config.vm_mode == "none":
        puts(
            "vm_mode is 'none': there is no box to reset, the teams bring their own.",
            color=colors.yellow,
        )
        return False

    node = vm_node_of_team(config, team_id)
    if node is None:
        puts(f"No node hosts the box of team {team_id}", color=colors.red)
        return False

    where = f" on node '{node.name}'" if is_multinode(config) else ""
    puts(
        f"Resetting the box of team {team_id} ({team.name}){where}",
        color=colors.yellow,
        is_bold=True,
    )

    if uses_incus(config):
        # -T because this runs unattended as often as not, and a tty would make
        # it fail over ssh.
        command = f"exec -T incus python3 /customize-vm.py reset {team_id}"
    elif config.vm_mode == "privileged":
        # No named volumes on a team container, so recreating it from the image
        # is exactly the reset: everything the team changed lived in its
        # writable layer.
        command = f"up -d --force-recreate --no-deps team{team_id}"
    else:
        puts(f"Unknown vm_mode '{config.vm_mode}'", color=colors.red)
        return False

    if not node_compose(config, node, command):
        puts(f"Reset of team {team_id} failed", color=colors.red)
        return False
    puts(f"Team {team_id} is back to its original box", color=colors.green)
    return True


def deploy_cluster(config: Config) -> None:
    """Brings the whole cluster up: control node first (it owns the database and
    generates every WireGuard profile), then the other nodes."""
    print_topology_warnings(config)
    control = control_node(config)
    nodes = [node for node in effective_nodes(config) if node.name != control.name]

    puts(f"Deploying control node '{control.name}'", color=colors.yellow, is_bold=True)
    write_compose(config)
    router_generate_configs(config, down_after_gen=False)
    if teams_of_node(config, control, "vm"):
        buildvms(config)
    composecmd("up -d --build --remove-orphans", g.composefile)

    for node in nodes:
        puts(f"Deploying node '{node.name}'", color=colors.yellow, is_bold=True)
        if node.local:
            write_compose(config, node=node)
            node_compose(config, node, "up -d --build --remove-orphans")
            continue
        if not node.ssh:
            puts(
                f"Node '{node.name}' was NOT deployed: it has no ssh target and is not "
                'marked "local". Nothing of it is running — no router, no vulnbox, no '
                "checker — so the game will look half broken until you fix it.",
                color=colors.red,
                is_bold=True,
            )
            puts(
                f"  Give it an \"ssh\" target, or \"local\": true if it shares this "
                f"machine, or run './run.py node up {node.name}' on that machine.",
                color=colors.yellow,
            )
            continue
        if not node_sync(config, node):
            puts(f"Sync of node {node.name} failed", color=colors.red)
            continue
        node_compose(config, node, "up -d --build --remove-orphans")

    puts("Cluster deployed", color=colors.green, is_bold=True)


def main():
    if args.command == "start":
        if args.config_only:
            if config_exists():
                puts(
                    f"Config file already exists! please edit {g.config_file}",
                    color=colors.red,
                )
                return
            config = config_input()
            create_config(config)
            puts(
                f"Config file generated!, you can customize it by editing {g.config_file}",
                color=colors.green,
            )
            return

    if not cmd_check("docker --version"):
        puts("docker not found! please install docker!", color=colors.red)
    if not cmd_check("docker ps"):
        puts(
            "docker is not running, please install docker and docker compose!",
            color=colors.red,
        )
        exit()
    elif not cmd_check("docker-compose --version") and not cmd_check(
        "docker compose --version"
    ):
        puts(
            "docker compose not found! please install docker compose!", color=colors.red
        )
        exit()

    if args.command:
        match args.command:
            case "wg-gen":
                if not config_exists():
                    puts(
                        "Config file not found! please create config.json first",
                        color=colors.red,
                    )
                else:
                    puts(f"{g.name} is starting!", color=colors.yellow)
                    config = read_config()
                    write_compose(config)
                    router_generate_configs(config)
            case "buildvms":
                if not config_exists():
                    puts(
                        "Config file not found! please create config.json first",
                        color=colors.red,
                    )
                else:
                    config = read_config()
                if len(config.teams) > 0:
                    buildvms(config)
            case "start":
                if check_already_running():
                    puts(f"{g.name} is already running!", color=colors.yellow)
                if not config_exists():
                    config = config_input()
                    create_config(config)
                else:
                    config = read_config()
                if args.config_only:
                    puts(
                        f"Config file generated!, you can customize it by editing {g.config_file}",
                        color=colors.green,
                    )
                    return
                if check_database_volume():
                    puts(
                        "The database volume already exists, you need to clear it before starting a new game",
                        color=colors.red,
                    )
                    if (
                        get_input("Do you want to clear it before starting?", "no")
                        .lower()
                        .startswith("y")
                    ):
                        clear_data_only(
                            remove_gameserver_data=True, remove_checkers_data=True
                        )

                if not config_exists():
                    puts(
                        f"Config file not found! please run {sys.argv[0]} start",
                        color=colors.red,
                    )
                    exit(1)
                else:
                    puts(f"{g.name} is starting!", color=colors.yellow)
                    config = read_config()
                    if not is_multinode(config):
                        print_topology_warnings(config)
                        write_compose(config)
                        router_generate_configs(config, down_after_gen=False)

                if is_multinode(config):
                    # A distributed config means the whole cluster: starting
                    # only the control node would leave a game that cannot be
                    # played, and nobody asked for half a deployment.
                    deploy_cluster(config)
                else:
                    if teams_of_node(config, control_node(config), "vm"):
                        buildvms(config)
                    puts(
                        "Running 'docker compose up -d --build\n", color=colors.green
                    )
                    composecmd("up -d --build --remove-orphans", g.composefile)
            case "compose":
                if not config_exists():
                    puts(
                        f"Config file not found! please run {sys.argv[0]} start",
                        color=colors.red,
                    )
                else:
                    write_compose(read_config())
                    compose_cmd = " ".join(args.compose_args)
                    puts(f"Running 'docker compose {compose_cmd}'\n", color=colors.green)
                    composecmd(compose_cmd, g.composefile)
            case "resetvm":
                if not config_exists():
                    puts(
                        f"Config file not found! please run {sys.argv[0]} start",
                        color=colors.red,
                    )
                elif not check_already_running():
                    puts(
                        f"{g.name} is not running!",
                        color=colors.red,
                        is_bold=True,
                        flush=True,
                    )
                else:
                    config = read_config()
                    write_compose(config)
                    wanted = sorted(set(args.team_id))
                    names = ", ".join(
                        f"{team.id} ({team.name})"
                        for team in config.teams
                        if team.id in wanted
                    ) or ", ".join(str(team) for team in wanted)
                    puts(
                        "Resetting a box wipes everything the team did to it: "
                        "patches, tools and exploits included.",
                        color=colors.yellow,
                    )
                    if not args.yes and not get_input(
                        f"Reset the box of team {names}?", "no"
                    ).lower().startswith("y"):
                        puts("Nothing was reset", color=colors.yellow)
                        return
                    failed = [
                        team_id for team_id in wanted if not reset_vm(config, team_id)
                    ]
                    if failed:
                        exit(1)
            case "vmshell":
                if not config_exists():
                    puts(
                        f"Config file not found! please run {sys.argv[0]} start",
                        color=colors.red,
                    )
                elif check_already_running():
                    config = read_config()
                    if config.vm_mode == "privileged":
                        compose_cmd = f"exec team{args.team_id}"
                    elif uses_incus(config):
                        compose_cmd = f"exec incus incus exec vm{args.team_id} --"
                    elif config.vm_mode == "none":
                        puts(
                            "VM 'none' mode selected",
                            color=colors.yellow,
                        )

                    if args.vmshell_args:
                        compose_cmd += f" {' '.join(args.vmshell_args)}"
                    else:
                        compose_cmd += " /bin/bash"

                    write_compose(config)
                    puts(f"Running 'docker compose {compose_cmd}'\n", color=colors.green)
                    composecmd(compose_cmd, g.composefile)
                else:
                    puts(
                        f"{g.name} is not running!",
                        color=colors.red,
                        is_bold=True,
                        flush=True,
                    )
            case "restart":
                if not config_exists():
                    puts(
                        f"Config file not found! please run {sys.argv[0]} start",
                        color=colors.red,
                    )
                elif check_already_running():
                    write_compose(read_config())
                    puts("Running 'docker compose restart'\n", color=colors.green)
                    composecmd("restart", g.composefile)
                else:
                    puts(
                        f"{g.name} is not running!",
                        color=colors.red,
                        is_bold=True,
                        flush=True,
                    )
            case "stop":
                if not config_exists():
                    # Foolish config (--remove-orphans will delete what is needed)
                    write_compose(Config())
                else:
                    write_compose(read_config())
                puts("Running 'docker compose down'\n", color=colors.green)
                composecmd("down --remove-orphans", g.composefile)
            case "clear":
                if check_already_running():
                    puts(
                        f"{g.name} is running! please stop it before clearing the data",
                        color=colors.red,
                    )
                    exit(1)
                if True not in vars(args).values():
                    clear_data(
                        remove_config=False,
                        remove_prebuilded_container=False,
                        remove_prebuilt_image=False,
                    )
                if args.all:
                    puts(
                        "This will clear everything, EVEN THE CONFIG JSON, are you sure? (y/N): ",
                        end="",
                    )
                    if input().lower() != "y":
                        return
                    puts("Clearing everything (even config!!)", color=colors.yellow)
                    clear_data()
                if args.config:
                    clear_data_only(remove_config=True)
                if args.team_vms:
                    clear_data_only(
                        remove_prebuilded_container=True,
                        remove_prebuilt_image=True,
                        remove_prebuilder_image=True,
                        remove_incus_data=True,
                    )
                if args.wireguard:
                    clear_data_only(remove_wireguard=True)
                if args.checkers_data:
                    clear_data_only(remove_checkers_data=True)
                if args.gameserver_data:
                    clear_data_only(remove_gameserver_data=True)
                puts(
                    "Whatever you specified has been cleared!",
                    color=colors.green,
                    is_bold=True,
                )
            case "node":
                handle_node_command(args)
            case "deploy":
                if not config_exists():
                    puts(
                        f"Config file not found! please run {sys.argv[0]} start -C",
                        color=colors.red,
                    )
                    exit(1)
                deploy_cluster(read_config())
            case "status":
                if check_already_running():
                    puts(f"{g.name} is running!", color=colors.green)
                if config_exists():
                    config = read_config()
                    if is_multinode(config):
                        puts(
                            f"Distributed deployment with {len(effective_nodes(config))} nodes:",
                            is_bold=True,
                        )
                        for node in effective_nodes(config):
                            node_status(config, node)
            case "listvms":
                if not config_exists():
                    puts(
                        f"Config file not found! please run {sys.argv[0]} start",
                        color=colors.red,
                    )
                config = read_config()
                if config.vm_mode == "none":
                    puts(
                        "VM 'none' mode selected, no VMs to list",
                        color=colors.yellow,
                    )
                    return
                vm_assignment = assign_teams(config, "vm")
                node_of_team = {
                    team: name
                    for name, teams in vm_assignment.items()
                    for team in teams
                }
                for team in config.teams:
                    if team.nop:
                        continue
                    location = node_of_team.get(team.id)
                    suffix = f" (node {location})" if is_multinode(config) and location else ""
                    puts(f"Team {team.id} - {team.name}{suffix}")

    if "logs" in args and args.logs:
        if config_exists():
            write_compose(read_config())
        else:
            puts(
                f"Config file not found! please run {sys.argv[0]} start",
                color=colors.red,
            )
        composecmd("logs -f")


if __name__ == "__main__":
    try:
        try:
            main()
        finally:
            kill_builder()
            cleanup_secrets()
    except KeyboardInterrupt:
        print()
