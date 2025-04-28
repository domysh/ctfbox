import sys
from enum import Enum
import requests
import os
import hashlib
import json

TOKEN = os.getenv("TOKEN")
SERVICE = os.getenv('SERVICE')

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

def save_flag_data(flag:str, data):
    with open(f'flag_ids/flag_{hashlib.sha256(flag.encode()).hexdigest()}.txt', 'w') as f:
        f.write(json.dumps(data))

def get_flag_data(flag:str):
    with open(f'flag_ids/flag_{hashlib.sha256(flag.encode()).hexdigest()}.txt', 'r') as f:
        return json.loads(f.read())

def get_host():
    if os.getenv('TEAM_IP', None):
        return os.getenv('TEAM_IP')
    return '10.60.' + os.environ['TEAM_ID'] + '.1'

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
        requests.post('http://flagid:8081/postFlagId', json=data)
