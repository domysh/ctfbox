#!/usr/bin/env python3
from __future__ import annotations
import argparse
import sys
import os
import subprocess
import json
import secrets
import shutil
import base64
import zlib
import hashlib
import platform
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Union
try:
    import readline # For allow any size of input 0_0 Strange python
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
    max_disk_size: Optional[str] = None
    gameserver_exposed_port: Optional[str] = None
    credential_server: Optional[str] = None
    debug: bool = False
    grace_time: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Config:
        teams_data = data.pop('teams', [])
        teams = [Team(**team) for team in teams_data]
        config = cls(**data, teams=teams)
        return config
    
    @classmethod
    def from_json_file(cls, filepath: str) -> Config:
        with open(filepath, 'r') as f:
            return cls.from_dict(json.load(f))
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def save_to_file(self, filepath: str, indent: int = 4) -> None:
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=indent)

def file_sha_hash(filename):
    h  = hashlib.sha256()
    b  = bytearray(128*1024)
    mv = memoryview(b)
    with open(filename, 'rb', buffering=0) as f:
        for n in iter(lambda : f.readinto(mv), 0):
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
    return hashlib.sha256(b":".join(map(lambda a: (a[0]+":"+a[1]).encode(), hash_list))).hexdigest()
    
class g:
    keep_file = False
    name = "CTFBox"
    project_name = "ctfbox"
    composefile = f".{project_name}-compose.yml"
    container_name = f"{project_name}-gameserver"
    config_file = "config.json"
    prebuild_image = f"{project_name}-prebuilder"
    prebuilded_container = f"{project_name}-prebuilded"
    prebuilt_image = f"{project_name}-vm-base" # this is dynamic here, but it needs to be
                                               # manually changed in the FROM in vm/Dockerfile
                                               # and in the .gitignore
    secrets_dir = f".{project_name}-secrets-tmp"

def is_linux():
    return "linux" in sys.platform and 'microsoft-standard' not in platform.uname().release

#Terminal colors

class colors:
    black = "30m"
    red = "31m"
    green = "32m"
    yellow = "33m"
    blue = "34m"
    magenta = "35m"
    cyan = "36m"
    white = "37m"

def dict_to_yaml(data, indent_spaces:int=4, base_indent:int=0, additional_spaces:int=0, add_text_on_dict:str|None=None):
    yaml = ''
    spaces = ' '*((indent_spaces*base_indent)+additional_spaces)
    if isinstance(data, dict):
        for key, value in data.items():
            if add_text_on_dict is not None:
                spaces_len = len(spaces)-len(add_text_on_dict)
                spaces = (' '*max(spaces_len, 0))+add_text_on_dict
                add_text_on_dict = None
            if isinstance(value, dict) or isinstance(value, list):
                yaml += f"{spaces}{key}:\n"
                yaml += dict_to_yaml(value, indent_spaces=indent_spaces, base_indent=base_indent+1, additional_spaces=additional_spaces)
            else:
                yaml += f"{spaces}{key}: {value}\n"
            spaces = ' '*((indent_spaces*base_indent)+additional_spaces)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yaml += dict_to_yaml(item, indent_spaces=indent_spaces, base_indent=base_indent, additional_spaces=additional_spaces+2, add_text_on_dict="- ")
            elif isinstance(item, list):
                yaml += dict_to_yaml(item, indent_spaces=indent_spaces, base_indent=base_indent+1, additional_spaces=additional_spaces)
            else:
                yaml += f"{spaces}- {item}\n"
    else:
        yaml += f"{data}\n"
    return yaml

def puts(text, *args, color=colors.white, is_bold=False, **kwargs):
    print(f'{pref}{1 if is_bold else 0};{color}' + text + reset, *args, **kwargs)

def sep(): puts("-----------------------------------", is_bold=True)

def cmd_check(program, get_output=False, print_output=False, no_stderr=False):
    if get_output:
        return subprocess.getoutput(program)
    if print_output:
        return subprocess.call(program, shell=True) == 0
    return subprocess.call(program, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL if no_stderr else subprocess.STDOUT, shell=True) == 0

def gen_args(args_to_parse: list[str]|None = None):                     
    
    #Main parser
    parser = argparse.ArgumentParser(description=f"{g.name} Manager")

    subcommands = parser.add_subparsers(dest="command", help="Command to execute", required=True)
    
    #Compose Command
    parser_compose = subcommands.add_parser('compose', help='Run docker compose command')
    parser_compose.add_argument('compose_args', nargs=argparse.REMAINDER, help='Arguments to pass to docker compose', default=[])
    
    #Start Command
    parser_start = subcommands.add_parser('start', help=f'Start {g.name}')
    parser_start.add_argument('--config-only', '-C', action='store_true', help='Only generate config file')
    
    #Stop Command
    subcommands.add_parser('stop', help=f'Stop {g.name}')
    #Wg config gen command
    subcommands.add_parser('wg-gen', help='Generate wireguard configs if not exists or config changed')
    
    #Restart Command
    parser_restart = subcommands.add_parser('restart', help=f'Restart {g.name}')
    parser_restart.add_argument('--logs', required=False, action="store_true", help=f'Show {g.name} logs', default=False)

    #Clear Command
    parser_clear = subcommands.add_parser('clear', help='Clear data')
    parser_clear.add_argument('--all', '-A', action='store_true', help='Clear everything')
    parser_clear.add_argument('--config', '-c', action='store_true', help='Clear config file')
    parser_clear.add_argument('--team-vms', '-T', action='store_true', help='Clear all VMs related data')
    parser_clear.add_argument('--wireguard', '-W', action='store_true', help='Clear wireguard data')
    parser_clear.add_argument('--checkers-data', '-C', action='store_true', help='Clear checkers data')
    parser_clear.add_argument('--gameserver-data', '-G', action='store_true', help='Clear gameserver data')

    #Status Command
    subcommands.add_parser('status', help='Show status')
    
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

def set_deploy_info(data:dict):
    if not os.path.isfile(".deploy_info"):
        with open(".deploy_info", "w") as f:
            json.dump({}, f)
    with open(".deploy_info", "r+") as f:
        deploy_info = json.load(f)
        deploy_info.update(data)
        f.seek(0)
        f.truncate()
        json.dump(deploy_info, f, indent=4)

def composecmd(cmd, composefile=None):
    if composefile:
        cmd = f"-f {composefile} {cmd}"
    if not cmd_check("docker --version"):
        puts("docker not found! please install docker!", color=colors.red)
        exit(1)
    elif not cmd_check("docker ps"):
        puts("Cannot use docker, the user hasn't the permission or docker isn't running", color=colors.red)
        exit(1)
    elif cmd_check("docker compose --version"):
        if os.system(f"docker compose -p {g.project_name} {cmd}") != 0:
            exit(1)
    elif cmd_check("docker-compose --version"):
        if os.system(f"docker-compose -p {g.project_name} {cmd}") != 0:
            exit(1)
    else:
        puts("docker compose not found! please install docker compose!", color=colors.red)
        exit(1)

def check_already_running():
    return g.container_name in cmd_check(f'docker ps --filter "name=^{g.container_name}$"', get_output=True)

def prebuilder_exists():
    return g.prebuild_image in cmd_check(f'docker image ls --filter "reference={g.prebuild_image}"', get_output=True)

def prebuilt_exists():
    return g.prebuilt_image in cmd_check(f'docker image ls --filter "reference={g.prebuilt_image}"', get_output=True)

def remove_prebuilder():
    return cmd_check(f'docker image rm {g.prebuild_image}')

def remove_prebuilt():
    return cmd_check(f'docker image rm {g.prebuilt_image}')

def remove_prebuilded():
    return cmd_check(f'docker container rm {g.prebuilded_container}')

def remove_database_volume():
    return cmd_check(f'docker volume rm -f {g.project_name}_db-data')

def check_database_volume():
    return f"{g.project_name}_db-data" in cmd_check(f'docker volume ls --filter "name={g.project_name}_db-data"', get_output=True)

def build_prebuilder():
    return cmd_check(f'docker build -t {g.prebuild_image} -f ./vm/Dockerfile.prebuilder ./vm/', print_output=True)

def build_prebuilt(privileged):
    return cmd_check(f'docker run -it {"--privileged" if privileged else "--runtime=sysbox-runc"} --name {g.prebuilded_container} {g.prebuild_image}', print_output=True)

def kill_builder():
    return cmd_check(f'docker kill {g.prebuilded_container}', no_stderr=True)

def commit_prebuilt():
    return cmd_check(f'docker commit {g.prebuilded_container} {g.prebuilt_image}:latest', print_output=True)

def invalid_vm_mode(do_exit:bool=True):
    puts("Invalid vm mode, please use 'privileged' or 'sysbox' or 'none'", color=colors.red)
    if do_exit:
        exit(1)

def incus_data_exists():
    return os.path.isfile("./incus/data/ready")

def delete_incus_data():
    shutil.rmtree("./incus/data", ignore_errors=True)

def write_compose(
        config: Union[Dict[str, Any], Config],
        incus_unless_stopped: bool = True,
    ):
    # Convert dict to Config object if needed
    if not isinstance(config, Config):
        config = Config.from_dict(config)
        
    is_privileged = False
    spawn_docker_teams = False
    external_wg_server_configs = False
    spawn_incus = False
    if config.vm_mode == "privileged":
        is_privileged = True
        spawn_docker_teams = True
    elif config.vm_mode == "sysbox":
        spawn_docker_teams = True
    elif config.vm_mode == "none":
        external_wg_server_configs = True
    elif config.vm_mode == "incus":
        spawn_incus = len(config.teams) > 0
    else:
        invalid_vm_mode()
    
    cleanup_secrets()
    
    if spawn_docker_teams:
        # Create temporary directory for secrets if it doesn't exist
        if not os.path.exists(g.secrets_dir):
            os.makedirs(g.secrets_dir)
        # Create token secret files for each team
        for team in config.teams:
            with open(f"{g.secrets_dir}/token_{team.id}", "w") as f:
                f.write(team.token)
        
    with open(g.composefile,"wt") as compose:
        compose.write(dict_to_yaml({
            "services": {
                "router": {
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
                        
                    },
                    "volumes": [
                        "unixsk:/unixsk:z",
                        "./router/configs:/app/configs:z"
                    ],
                    "restart": "unless-stopped",
                    "networks": {
                        "gameserver": {
                            "priority": 10,
                            "ipv4_address": "10.10.0.250"
                        },
                        "externalnet": {
                            "priority": 1,
                        },
                        **({f"vm-team{team.id}": {} for team in config.teams} if spawn_docker_teams else {}),
                    },
                    "ports": [
                        f"{config.wireguard_port}:51820/udp",
                        *([
                            f"{config.gameserver_exposed_port}:80"
                        ] if config.gameserver_exposed_port is not None else {}),
                    ],
                },
                "database": {
                    "hostname": f"{g.project_name}-database",
                    "dns": [config.dns],
                    "image": "postgres:17",
                    "restart": "unless-stopped",
                    "environment": {
                        "POSTGRES_USER": "user",
                        "POSTGRES_PASSWORD": "pass",
                        "POSTGRES_DB": "db"
                    },
                    "volumes": [
                        "db-data:/var/lib/postgresql/data"
                    ],
                    "networks": {
                        "internalnet": "",
                    }
                },
                "gameserver": {
                    "hostname": "gameserver",
                    "dns": [config.dns],
                    "build": "./gameserver",
                    "restart": "unless-stopped",
                    "container_name": g.container_name,
                    "cap_add": [
                        "NET_ADMIN"
                    ],
                    "depends_on": [
                        "router",
                        "database",
                    ],
                    "networks": {
                        "internalnet": {
                            "priority": 1
                        },
                        "gameserver": {
                            "priority": 10,
                            "ipv4_address": "10.10.0.1"
                        }
                    },
                    "volumes": [
                        "./gameserver/checkers:/app/checkers:z",
                        "unixsk:/unixsk",
                        f"./{g.config_file}:/app/{g.config_file}:z"
                    ]
                },
                **({
                    "credentials": {
                    "hostname": "credentials",
                    "dns": [config.dns],
                    "build": "./credentials",
                    "restart": "unless-stopped",
                    "ports": [
                        f"{config.credential_server}:4040"
                    ],
                    "depends_on": [ "router" ],
                    "networks": ["internalnet"],
                    "volumes": [
                        "./config.json:/app/config.json:ro",
                        "./router:/app/router:ro"
                    ]
                }} if config.credential_server is not None else {}),
                **({
                    "incus": {
                        "dns": [config.dns],   
                        "build": "./incus",
                        "depends_on": [ "router" ],
                        "networks": ["externalnet"],
                        **({"restart": "unless-stopped"} if incus_unless_stopped else {}),
                        "cgroup": "host",
                        "pid": "host",
                        "security_opt": [
                            "seccomp=unconfined",
                            "apparmor=unconfined",
                        ],
                        "volumes": [
                            "./config.json:/config.json:ro",
                            "./router:/router:ro",
                            "./vm:/vmdata:ro",
                            "/dev:/dev:z",
                            "/lib/modules:/lib/modules:ro",
                            "./incus/data:/var/lib/incus"
                        ],
                        "privileged": True,
                    }
                } if spawn_incus else {}),
                **({
                    f"team{team.id}": {
                        "hostname": f"team{team.id}",
                        "dns": [config.dns],
                        "build": {
                            "context": "./",
                            "dockerfile": "./vm/Dockerfile",
                            "secrets": [
                                f"token_team_{team.id}"
                            ],
                            "args": {
                                "TEAM_ID": team.id,
                                "TEAM_NAME": team.name,
                            }
                        },
                        **({ "storage_opt": {"size":config.max_disk_size} } if config.max_disk_size else {}),
                        **({"privileged": "true"} if is_privileged else { "runtime": "sysbox-runc" }),
                        "restart": "unless-stopped",
                        "depends_on": [
                            "router",
                        ],
                        "networks": [f"vm-team{team.id}"],
                        "deploy":{
                            "resources":{
                                "limits":{
                                    "cpus": f'"{config.max_vm_cpus}"',
                                    "memory": config.max_vm_mem
                                }
                            }
                        }
                    } for team in config.teams
                } if spawn_docker_teams else {}),
            },
            **({ "secrets":{
                **{
                    f"token_team_{team.id}": {
                        "file": f"{g.secrets_dir}/token_{team.id}"
                    } for team in config.teams
                },
            }} if config.teams and spawn_docker_teams else {}),
            "volumes": {
                "unixsk": "",
                "db-data": ""
            },
            "networks": {
                "externalnet": "",
                "internalnet": "",
                "gameserver": {
                    "internal": "true",
                    "driver": "macvlan",
                    "ipam": {
                        "driver": "default",
                        "config": [
                            {
                                "subnet": "10.10.0.0/24",
                                "gateway": "10.10.0.254",
                            }
                        ]
                    }
                },
                **({f"vm-team{team.id}": "" for team in config.teams} if spawn_docker_teams else {}),
            }
        }))

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
        puts("Removing wireguard configs", color=colors.yellow)
        shutil.rmtree("./router/configs", ignore_errors=True)
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
            shutil.rmtree(f"./gameserver/checkers/{service}/flag_ids", ignore_errors=True)
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
            name=f'Team {i}',
            token=secrets.token_hex(32),
            nop=(i == 0 and enable_nop_team),
            image=""
        )
        if i == 0 and enable_nop_team:
            team.name = 'Nop Team'
        teams.append(team)
    return teams

def get_input(prompt: str, default = None, is_required: bool = False, default_prompt: str = None):
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
    use_web_editor = get_input('Do you want to use the web editor?', 'yes').lower().startswith('y')
    
    if use_web_editor:
        puts("Open the web editor at: https://ctfbox.domy.sh/editor", color=colors.green)
        puts("Configure your settings and then click 'Copy Compressed Config'", color=colors.green)
        puts("Paste the base64 compressed config below:", color=colors.yellow)
        
        config_input = input().strip()
        
        # User provided base64 compressed config
        try:
            # Decode base64 and decompress
            decoded_bytes = base64.b64decode(config_input)
            decompressed_bytes = zlib.decompress(decoded_bytes)
            config_data = json.loads(decompressed_bytes.decode('utf-8'))
            return Config.from_dict(config_data)
        except Exception as e:
            puts(f"Error decoding configuration: {e}", color=colors.red)
            puts("Please try again with valid base64 compressed config", color=colors.red)
            exit(1)
    
    # Original config input flow
    # abs() put for consistency with the other options
    default_configs = Config()
    c = Config()
    
    number_of_teams = abs(int(get_input('Number of teams, >= 0 and < 250', 4)))
    while number_of_teams < 0 or number_of_teams >= 250:
        number_of_teams = abs(int(get_input('Number of teams, >= 0 and < 250', 4)))
    enable_nop_team = get_input('Enable NOP team?', 'yes').lower().startswith('y')

    # abs() put for consistency with the other options
    c.wireguard_port = abs(int(get_input(f'Wireguard port, >= 1 and <= {65535-number_of_teams}', default_configs.wireguard_port)))
    while c.wireguard_port < 1 or c.wireguard_port > 65535-number_of_teams:
        c.wireguard_port = abs(int(get_input(f'Wireguard port, >= 1 and <= {65535-number_of_teams}', default_configs.wireguard_port)))

    c.wireguard_profiles      = abs(int(get_input('Number of wireguard profiles for each team', default_configs.wireguard_profiles)))
    c.server_addr             = get_input('Server address', is_required=True)
    c.dns                     = get_input('DNS', default_configs.dns)
    
    while True:
        c.vm_mode = get_input('VM mode (incus/privileged/sysbox/none)', default_configs.vm_mode)
        if c.vm_mode.lower() == "privileged":
            c.vm_mode = "privileged"
            break
        elif c.vm_mode.lower() == "sysbox":
            c.vm_mode = "sysbox"
            break
        elif c.vm_mode.lower() == "none":
            c.vm_mode = "none"
            break
        elif c.vm_mode.lower() == "incus":
            c.vm_mode = "incus"
            break
        else:
            invalid_vm_mode(do_exit=False)
    
    if c.vm_mode in ["privileged", "sysbox", "incus"]:
        c.max_vm_cpus             = get_input('Max VM CPUs', default_configs.max_vm_cpus)
        c.max_vm_mem              = get_input('Max VM Memory', default_configs.max_vm_mem)
        if c.vm_mode in ["incus"] or get_input('Enable disk limit? (REQUIRES XFS FILESYSTEM)', 'yes').lower().startswith('y'):
            c.max_disk_size       = get_input('Max VM disk size', "30G")
        else:
            c.max_disk_size = None

    c.start_time              = get_input('Start time, in RFC 3339 (YYYY-mm-dd HH:MM:SS+/-zz:zz)')
    c.end_time                = get_input('End time, in RFC 3339 (YYYY-mm-dd HH:MM:SS+/-zz:zz)')
    c.grace_time              = abs(int(get_input('Grace time in seconds (before start_time - grace time the router is fronzen)', default_configs.grace_time)))
    c.tick_time               = abs(int(get_input('Tick time in seconds', default_configs.tick_time)))
    c.flag_expire_ticks       = abs(int(get_input('Number of ticks after which each flag expires', default_configs.flag_expire_ticks)))

    c.initial_service_score   = abs(int(get_input('Initial service score', default_configs.initial_service_score)))
    c.max_flags_per_request   = abs(int(get_input('Max flags per request', default_configs.max_flags_per_request)))
    c.submission_timeout      = abs(float(get_input('Submission timeout', default_configs.submission_timeout)))
    c.network_limit_bandwidth = get_input('Network limit bandwidth', default_configs.network_limit_bandwidth)
    
    if get_input('Expose externally the gameserver scoreboard?', 'no').lower().startswith('y'):
        c.gameserver_exposed_port = get_input('Insert with witch port or ip:port to expose the gameserver scoreboard', "127.0.0.1:8888")
    else:
        c.gameserver_exposed_port = None
    
    if get_input('Enable credential service?', 'no').lower().startswith('y'):
        c.credential_server = get_input('Insert the port to expose the credential server', "127.0.0.1:4040")
    else:
        c.credential_server = None
    
    c.gameserver_token = get_input('Gameserver token', default_prompt='randomly generated', default=secrets.token_hex(32))    
    
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
    data.append(f"vm_mode={config.vm_mode}")
    data.sort()
    return hashlib.sha256(("::".join(data)).encode()).hexdigest()

def server_config_hash(config: Config):
    return dir_sha_hash("./router/configs/servers") 

def router_generate_configs(config: Config, down_after_gen: bool = True):
    info = get_deploy_info()
    old_hash = info.get("vpn_config_hash", None)
    current_hash = vpn_config_hash(config)
    if not os.path.isfile("./router/configs/wg0.conf") \
        or old_hash != current_hash:
        if check_already_running():
            puts(f"Can't generate configs if {g.project_name} is already running!", color=colors.red)
            exit(1)
        clear_data_only(remove_wireguard=True)
        puts("Generating wireguard configuration", color=colors.yellow)
        composecmd("down router --remove-orphans", g.composefile)
        composecmd("up router -d --build --remove-orphans --wait", g.composefile)
        set_deploy_info({ "vpn_config_hash": current_hash })
        if down_after_gen:
            composecmd("down router --remove-orphans", g.composefile)
        return True
    else:
        if not down_after_gen:
            composecmd("up router -d --build --remove-orphans --wait", g.composefile)
        puts("Wireguard configs already generated!")
    return False

def main():
    
    if args.command == "start":
        if args.config_only:
            if config_exists():
                puts(f"Config file already exists! please edit {g.config_file}", color=colors.red)
                return
            config = config_input()
            create_config(config)
            puts(f"Config file generated!, you can customize it by editing {g.config_file}", color=colors.green)
            return

    if not cmd_check("docker --version"):
        puts("docker not found! please install docker!", color=colors.red)
    if not cmd_check("docker ps"):
        puts("docker is not running, please install docker and docker compose!", color=colors.red)
        exit()
    elif not cmd_check("docker-compose --version") and not cmd_check("docker compose --version"):
        puts("docker compose not found! please install docker compose!", color=colors.red)
        exit()
    
    if args.command:
        match args.command:
            case "wg-gen":
                if not config_exists():
                    puts("Config file not found! please create config.json first", color=colors.red)
                else:
                    puts(f"{g.name} is starting!", color=colors.yellow)
                    config = read_config()
                    write_compose(config)
                    router_generate_configs()
            case "start":
                if check_already_running():
                    puts(f"{g.name} is already running!", color=colors.yellow)
                if not config_exists():
                    config = config_input()
                    create_config(config)
                else:
                    config = read_config()
                if args.config_only:
                    puts(f"Config file generated!, you can customize it by editing {g.config_file}", color=colors.green)
                    return
                if check_database_volume():
                    puts("The database volume already exists, you need to clear it before starting a new game", color=colors.red)
                    if get_input('Do you want to clear it before starting?', 'no').lower().startswith('y'):
                        clear_data_only(remove_gameserver_data=True, remove_checkers_data=True)
                
                if not config_exists():
                    puts(f"Config file not found! please run {sys.argv[0]} start", color=colors.red)
                    exit(1)
                else:
                    puts(f"{g.name} is starting!", color=colors.yellow)
                    config = read_config()
                    write_compose(config)
                    router_generate_configs(config, down_after_gen=False)
                    
                if len(config.teams) > 0:
                    vm_dir_hash = dir_sha_hash("./vm")
                    info = get_deploy_info()
                    old_vm_dir_hash = info.get("vm_dir_hash", "")
                    was_built_with = info.get("vm_mode_build", False)
                    vm_router_hash = info.get("vm_router_hash", None)
                    current_router_hash = server_config_hash(config)
                    if config.vm_mode == "privileged" or config.vm_mode == "sysbox":
                        if not prebuilt_exists() or vm_dir_hash != old_vm_dir_hash or was_built_with != config.vm_mode:
                            puts("Need to build the team VM image", color=colors.yellow)
                            clear_data_only(remove_prebuilded_container=True, remove_prebuilt_image=True, remove_prebuilder_image=True, remove_incus_data=True)
                            puts("Building the prebuilder image", color=colors.yellow)
                            if not build_prebuilder():
                                puts("Error building prebuilder image", color=colors.red)
                                exit(1)
                            puts("Executing prebuilder to create VMs' base image", color=colors.yellow)
                            if not build_prebuilt(config.vm_mode == "privileged"):
                                puts("Error building prebuilt image", color=colors.red)
                                exit(1)
                            puts("Saving base VM container as image to be used to build the CTF services\n(this action can take a while and produces no output)", color=colors.yellow)
                            if not commit_prebuilt():
                                puts("Error commiting prebuilt image", color=colors.red)
                                exit(1)
                            puts("Clear unused images", color=colors.yellow)
                            remove_prebuilded()
                    elif config.vm_mode == "none":
                        puts("VM 'none' mode selected, skipping VM image build", color=colors.yellow)
                    elif config.vm_mode == "incus":
                        if not incus_data_exists() or vm_dir_hash != old_vm_dir_hash or was_built_with != config.vm_mode or vm_router_hash != current_router_hash:
                            write_compose(config, incus_unless_stopped=False)
                            puts("Need to build the incus VMs", color=colors.yellow)
                            clear_data_only(remove_prebuilded_container=True, remove_prebuilt_image=True, remove_prebuilder_image=True, remove_incus_data=True)
                            puts("Building the incus VMs", color=colors.yellow)
                            composecmd("up incus --build --remove-orphans --exit-code-from incus", g.composefile)
                            write_compose(config)
                        else:
                            puts("Incus VMs already exists, skipping build", color=colors.yellow)
                    else:
                        invalid_vm_mode()
                    set_deploy_info({"vm_dir_hash": vm_dir_hash, "vm_mode_build": config.vm_mode, "vm_router_hash": current_router_hash})
                puts("Running 'docker compose up -d --build\n", color=colors.green)
                composecmd("up -d --build --remove-orphans", g.composefile)
            case "compose":
                if not config_exists():
                    puts(f"Config file not found! please run {sys.argv[0]} start", color=colors.red)
                else:
                    write_compose(read_config())
                    compose_cmd = " ".join(args.compose_args)
                    puts(f"Running 'docker compose {compose_cmd}'\n", color=colors.green)
                    composecmd(compose_cmd, g.composefile)
            case "restart":
                if not config_exists():
                    puts(f"Config file not found! please run {sys.argv[0]} start", color=colors.red)
                elif check_already_running():
                    write_compose(read_config())
                    puts("Running 'docker compose restart'\n", color=colors.green)
                    composecmd("restart", g.composefile)
                else:
                    puts(f"{g.name} is not running!" , color=colors.red, is_bold=True, flush=True)
            case "stop":
                if not config_exists():
                    #Foolish config (--remove-orphans will delete what is needed)
                    write_compose(Config())
                else:
                    write_compose(read_config())
                puts("Running 'docker compose down'\n", color=colors.green)
                composecmd("down --remove-orphans", g.composefile)
            case "clear":
                if check_already_running():
                    puts(f"{g.name} is running! please stop it before clearing the data", color=colors.red)
                    exit(1)
                if True not in vars(args).values():
                    clear_data(remove_config=False, remove_prebuilded_container=False, remove_prebuilt_image=False)
                if args.all:
                    puts("This will clear everything, EVEN THE CONFIG JSON, are you sure? (y/N): ", end="")
                    if input().lower() != 'y':
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
                puts("Whatever you specified has been cleared!", color=colors.green, is_bold=True)
            case "status":
                if check_already_running():
                    puts(f"{g.name} is running!", color=colors.green)

    if "logs" in args and args.logs:
        if config_exists():
            write_compose(read_config())
        else:
            puts(f"Config file not found! please run {sys.argv[0]} start", color=colors.red)
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

