from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from utils import load_config_data, wireguard_path, load_pins_info
import os
import time

user_blueprint = Blueprint('user', __name__)

downloaded_configs = {}

@user_blueprint.route('/login', methods=['POST'])
def user_login():
    time.sleep(0.3) # Avoid brute force attacks
    pin = request.json.get('pin')
    
    profile_pin = None
    pin_info = load_pins_info()
    for team_pin_list in pin_info.values():
        for pin_info in team_pin_list:
            if pin_info['pin'] == pin:
                profile_pin = pin_info
                break
    
    if profile_pin:
        access_token = create_access_token(
            identity=f"user_{profile_pin['team_id']}_{profile_pin['profile_id']}",
        )
        return jsonify(access_token=access_token), 200
    
    return jsonify({"msg": "Invalid pin"}), 401

@user_blueprint.route('/team', methods=['GET'])
@jwt_required()
def get_team_info():
    current_user = get_jwt_identity()
    if current_user == "admin":
        return jsonify({"msg": "Forbidden: This endpoint is for users only"}), 422
    
    team_id, user_id = map(int, current_user.split('_')[1:])
    teams_data = load_config_data()

    team = next((team for team in teams_data['teams'] if team['id'] == team_id), None)
    
    if not team or team['id'] != team_id:  
        return jsonify({"msg": "Team not found"}), 404
    
    return jsonify({
        "id": team['id'],
        "team_name": team['name'],
        "profile": user_id,
        "token": team['token'],
        "nop": team['nop']
    }), 200

@user_blueprint.route('/download_config/', methods=['GET'])
@jwt_required()
def download_config():
    current_user = get_jwt_identity()
    if current_user == "admin":
        return jsonify({"msg": "Forbidden: This endpoint is for users only"}), 422

    team_id, user_id = map(int, current_user.split('_')[1:])
    
    profile_path = wireguard_path(team_id, user_id)

    if not os.path.exists(profile_path):
        return jsonify({"msg": "Config file not found"}), 404
    
    return send_file(profile_path,
        as_attachment=True,
        download_name=f"team{team_id}-{user_id}.conf",
    )
