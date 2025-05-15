#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
from typing import List
from dataclasses import dataclass
import json

@dataclass
class Team:
    id: int
    name: str
    nop: bool = False

@dataclass
class Config:
    teams: List[Team]
    server_addr: str
    wireguard_port: int
    wireguard_profiles: int
    external_servers: bool

generated_pins = set()

def generate_pin():
    """Generate a random 6-digit pin."""
    pin = None
    while pin is None or pin in generated_pins:
        pin = int.from_bytes(os.urandom(6), 'big') % (10 ** 6)
    pin = str(pin).rjust(6, '0')
    generated_pins.add(pin)
    return pin

def generate_keypair():
    """Generate a WireGuard private and public key pair."""
    private_key = subprocess.check_output(["wg", "genkey"]).decode("utf-8").strip()
    public_key = subprocess.check_output(["wg", "pubkey"], input=private_key.encode()).decode("utf-8").strip()
    return private_key, public_key

def generate_preshared_key():
    """Generate a WireGuard preshared key."""
    preshared_key = subprocess.check_output(["wg", "genpsk"]).decode("utf-8").strip()
    return preshared_key

def load_config_from_env():
    """Load configuration from environment variables."""
    team_ids = os.environ.get("TEAM_IDS", "").split(",")
    nop_teams = map(lambda x: int(x.strip()), [ele for ele in os.environ.get("NOP_TEAMS", "").split(",") if ele.strip()])
    teams = []
    
    for team_id in team_ids:
        team_id = team_id.strip()
        if team_id:
            team_id = int(team_id)
            teams.append(Team(id=team_id, name=f"Team {team_id}", nop=(team_id in nop_teams)))
    
    return Config(
        teams=teams,
        server_addr=os.environ.get("PUBLIC_IP", ""),
        wireguard_port=int(os.environ.get("PUBLIC_PORT", "51820")),
        wireguard_profiles=int(os.environ.get("CONFIG_PER_TEAM", "1")),
        external_servers=os.environ.get("EXTERNAL_SERVERS", "0").strip().lower() == "1"
    )

def generate_wg_server_interface(private_key):
    return f"""[Interface]
Address = 10.10.252.252/32
ListenPort = 51820
PrivateKey = {private_key}
MTU = 1400
"""

def generate_server_peer(client_priv, preshared_key, client_ip):
    return f"""
[Peer]
PublicKey = {client_priv}
PresharedKey = {preshared_key}
AllowedIPs = {client_ip}/32
"""

def generate_client_config(client_priv, client_ip, server_pub, preshared_key, server_addr, server_port):
    return f"""[Interface]
PrivateKey = {client_priv}
Address = {client_ip}/32
MTU = 1400

[Peer]
PublicKey = {server_pub}
PresharedKey = {preshared_key}
AllowedIPs = 10.10.0.0/24, 10.60.0.0/16, 10.80.0.0/16
Endpoint = {server_addr}:{server_port}
PersistentKeepalive = 15
"""


def main():
    
    if os.path.exists("configs/wg0.conf"):
        print("Configuration already generated. Exiting.")
        return
    
    shutil.rmtree("configs", ignore_errors=True)
    os.makedirs("configs", exist_ok=True)
    
    try:
        # Load config from environment variables
        config = load_config_from_env()

        # Generate server keys
        server_private_key, server_public_key = generate_keypair()
        # Create server config
        server_config = generate_wg_server_interface(server_private_key)
        
        # Generate configs for each team
        for team in config.teams:
            if team.nop:
                continue
            pins_config = []
            team_dir = f"configs/team{team.id}"
            os.makedirs(team_dir, exist_ok=True)
            
            # Create peer configs for this team
            for profile_id in range(1, config.wireguard_profiles + 1):
                client_private_key, client_public_key = generate_keypair()
                preshared_key = generate_preshared_key()
                client_ip = f"10.80.{team.id}.{profile_id}"
                
                # Add peer to server config
                server_config += generate_server_peer(client_public_key, preshared_key, client_ip)
                
                # Create client config
                client_config = generate_client_config(client_private_key, client_ip, server_public_key, preshared_key, config.server_addr, config.wireguard_port)
                
                # Save client config
                with open(os.path.join(team_dir, f"team{team.id}-{profile_id}.conf"), 'w') as f:
                    f.write(client_config)
                
                pins_config.append({
                    "team_id": team.id,
                    "profile_id": profile_id,
                    "pin": generate_pin(),
                    "client_ip": client_ip,
                })
            # Save pins config
            with open(os.path.join(team_dir, "pins.json"), 'w') as f:
                json.dump(pins_config, f, indent=4)
        
        team_dir = "configs/admins"
        os.makedirs(team_dir, exist_ok=True)
        for profile_id in range(1, config.wireguard_profiles + 1):
            client_private_key, client_public_key = generate_keypair()
            preshared_key = generate_preshared_key()
            client_ip = f"10.80.253.{profile_id}"
            
            # Add peer to server config
            server_config += generate_server_peer(client_public_key, preshared_key, client_ip)
            # Create client config
            client_config = generate_client_config(client_private_key, client_ip, server_public_key, preshared_key, config.server_addr, config.wireguard_port)
            
            # Save client config
            with open(os.path.join(team_dir, f"admin-{profile_id}.conf"), 'w') as f:
                f.write(client_config)
                
        wg_server_ip = config.server_addr if config.external_servers else "router"
        wg_server_port = config.wireguard_port if config.external_servers else 51820
        
        for team in config.teams:
            os.makedirs("configs/servers", exist_ok=True)
            client_private_key, client_public_key = generate_keypair()
            preshared_key = generate_preshared_key()
            client_ip = f"10.60.{team.id}.1"
            # Add peer to server config
            server_config += generate_server_peer(client_public_key, preshared_key, client_ip)
            # Create client config
            client_config = generate_client_config(client_private_key, client_ip, server_public_key, preshared_key, wg_server_ip, wg_server_port)  
            # Save client config
            with open(f"./configs/servers/server-{team.id}.conf", 'w') as f:
                f.write(client_config)
        
        # Save server config
        with open("configs/wg0.conf", 'w') as f:
            f.write(server_config)
            
        print("WireGuard configurations successfully generated in configs directory.")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
