import sys
from enum import Enum
import requests
import os
import hashlib
import json

TOKEN = os.getenv("TOKEN")
SERVICE = os.getenv('SERVICE')

# Where the game server answers. On the machine running the game server this is
# the loopback alias; on a distributed checker node it is the game server
# address inside the game network.
API = os.getenv('CTFBOX_API', 'http://flagid:8081').rstrip('/')

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), SERVICE))
os.makedirs('flag_ids', exist_ok=True)

class Status(Enum):
    OK = 101
    DOWN = 104
    ERROR = 110
 
class Action(Enum):
    CHECK_SLA = 'CHECK_SLA'
    PUT_FLAG = 'PUT_FLAG'
    GET_FLAG = 'GET_FLAG'

    def __str__(self):
        return str(self.value)

def _flag_data_path(flag:str):
    return f'flag_ids/flag_{hashlib.sha256(flag.encode()).hexdigest()}.txt'

def save_flag_data(flag:str, data):
    """Stores whatever the checker needs to find the flag back later.

    The data is kept on the game server so that PUT_FLAG and GET_FLAG of the
    same flag can run on two different checker machines; the local file is kept
    as a cache and as the offline fallback used by checkertest.py.
    """
    with open(_flag_data_path(flag), 'w') as f:
        f.write(json.dumps(data))
    if not TOKEN:
        return
    try:
        requests.post(f'{API}/flagData', json={
            'token': TOKEN,
            'flag': flag,
            'data': data,
        }, timeout=10).raise_for_status()
    except Exception as exc:
        print(f'Cannot store flag data on the game server: {exc}', file=sys.stderr)

def get_flag_data(flag:str):
    if TOKEN:
        try:
            response = requests.get(f'{API}/flagData', params={
                'token': TOKEN,
                'flag': flag,
            }, timeout=10)
            if response.ok:
                data = response.json().get('data')
                if data is not None:
                    return data
        except Exception as exc:
            print(f'Cannot read flag data from the game server: {exc}', file=sys.stderr)
    with open(_flag_data_path(flag), 'r') as f:
        return json.loads(f.read())

def get_host():
    if os.getenv('TEAM_IP', None):
        return os.getenv('TEAM_IP')
    raise ValueError("TEAM_IP not set")

def get_data():
    data = {
        'action': os.environ['ACTION'],
        'teamId': os.environ['TEAM_ID'],
        'round': os.environ['ROUND'],
        'host': get_host()
    }

    if data['action'] == Action.PUT_FLAG.name or data['action'] == Action.GET_FLAG.name:
        data['flag'] = os.environ['FLAG']

    return data


def quit(exit_code, comment='', debug=''):
    if isinstance(exit_code, Status):
        exit_code = exit_code.value

    print(comment)
    print(debug, file=sys.stderr)
    exit(exit_code)


def post_flag_id(flag_id):
    data = {
        'token': TOKEN,
        'serviceId': SERVICE,
        'teamId': get_host(),
        'round': int(os.environ['ROUND']),
        'flagId': flag_id
    }
    if os.getenv('PRINT_FLAG_ID', None):
        print(f"Flag ID: {flag_id}")
    else:
        requests.post(f'{API}/postFlagId', json=data)
