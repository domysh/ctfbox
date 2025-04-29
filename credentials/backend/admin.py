from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from utils import load_config_data, load_pins_info
import time

admin_blueprint = Blueprint('admin', __name__)

pin_digits = 6

@admin_blueprint.route('/login', methods=['POST'])
def admin_login():
    time.sleep(0.3) # Avoid brute force attacks
    data = request.get_json()
    token = data.get('token')

    if token == load_config_data()['gameserver_token']:
        access_token = create_access_token(identity="admin")
        return jsonify(access_token=access_token), 200
    return jsonify({"msg": "Invalid credentials"}), 401

@admin_blueprint.route('/teams', methods=['GET'])
@jwt_required()
def get_teams():
    if get_jwt_identity() != "admin":
        return jsonify({"msg": "Forbidden: Admin access required"}), 403
    
    teams_data = load_config_data()
    pins_info = load_pins_info()

    return jsonify([{
        "id": team['id'],
        "name": team['name'],
        "pins": [{
            "pin": ele['pin'],
            "profile": ele['profile_id'],
        } for ele in pins_info.get(team['id'], [])],
        "token":team['token'],
        "nop":team['nop'],
    } for team in teams_data['teams'] if not team['nop']]), 200
