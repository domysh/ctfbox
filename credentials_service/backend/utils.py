import json
import os
from fasteners import InterProcessLock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEBUG = os.getenv('DEBUG', "0").strip() == "1"

CONFIG_DATA_FILE = os.path.join(BASE_DIR, 'config.json' if not DEBUG else '../../config.json')

config_file_lock = InterProcessLock(os.path.join(BASE_DIR, "teams_data.json.lock"))

def load_config_data():
    with open(CONFIG_DATA_FILE, 'r') as f:
        return json.load(f)
        
def wireguard_path(team_id, profile_id):
    if DEBUG:
        return os.path.join(BASE_DIR, f'../../router/conf{team_id}/peer{profile_id}/peer{profile_id}.conf')
    else:
        return os.path.join(BASE_DIR, f'router/configs/team{team_id}/team{team_id}-{profile_id}.conf')

def load_pins_info():
    teams_info = {}
    for team in load_config_data()['teams']:
        if team['nop']:
            continue
        try:
            with open(wireguard_pins_path(team['id']), 'r') as f:
                pins = json.load(f)
        except FileNotFoundError:
            continue
        teams_info[team['id']] = pins
    return teams_info

def wireguard_pins_path(team_id):
    if DEBUG:
        return os.path.join(BASE_DIR, f'../../router/conf{team_id}/pins.json')
    else:
        return os.path.join(BASE_DIR, f'router/configs/team{team_id}/pins.json')