#!/usr/bin/env python3

import argparse
import os
import subprocess
import sys
import random
import time
from pathlib import Path

# Status codes
OK = 101
DOWN = 104
ERROR = 110
KILLED = -1
CRITICAL = 1337

# Action types
CHECK_SLA = "CHECK_SLA"
PUT_FLAG = "PUT_FLAG"
GET_FLAG = "GET_FLAG"

# Colors for output
GREEN = "\033[32m"
RED = "\033[31m"
HIGH_RED = "\033[1;31m"
PURPLE = "\033[35m"
END = "\033[0m"

def gen_flag(length=31):
    """Generates a random flag"""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    flag = ''.join(random.choice(letters) for _ in range(length))
    return flag + "="

def run_checker(service, action, team_ip, team_id="0", round_num="1", flag=""):
    """Runs the checker with specified parameters"""
    
    # Find the path to the checker
    repo_root = Path(__file__).parent.parent
    checker_path = repo_root / "checkers" / service / "checker.py"
    
    if not checker_path.exists():
        print(f"Checker not found: {checker_path}")
        return CRITICAL, "Checker not found"
    
    # Prepare the environment
    env = os.environ.copy()
    env["ACTION"] = action
    env["TEAM_ID"] = team_id
    env["TEAM_IP"] = team_ip
    env["ROUND"] = round_num
    env["FLAG"] = flag
    env["SERVICE"] = service
    env["TERM"] = "xterm"
    env["PRINT_FLAG_ID"] = "1"
    env["PYTHONPATH"] = f"{os.getenv('PYTHONPATH')}:../"
    
    # Execute the command
    try:
        process = subprocess.Popen(
            ["python3", str(checker_path)],
            env=env,
            cwd=str(checker_path.parent),
            text=True
        )
        
        # Wait for completion with timeout
        try:
            process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            return KILLED, "Checker timeout (killed, service is probably down)"
        
        # Get the exit code
        exit_code = process.returncode
        
        # Format the message based on exit code
        color = END
        if exit_code == OK:
            color = GREEN
        elif exit_code == DOWN:
            color = RED
        elif exit_code == ERROR:
            color = HIGH_RED
        elif exit_code == KILLED:
            color = PURPLE
        
        print(f"Checker status {action}: {color}{exit_code}{END} from {team_ip} on {service}")
        
        return exit_code
    
    except Exception as e:
        print(f"Error running checker: {e}")
        return CRITICAL, f"Checker system error: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description='Run checker tests for CTF services')
    parser.add_argument('service', help='Name of the service to test')
    parser.add_argument('--team-ip', help='IP of the team to test', default=os.environ.get('TEAM_IP', '127.0.0.1'))
    parser.add_argument('--team-id', help='ID of the team to test', default='1')
    parser.add_argument('--round', help='Round number', default='1')
    
    args = parser.parse_args()
    
    print(f"Testing service {args.service} at {args.team_ip}")
    
    # Run CHECK_SLA
    print(f"\n{'-'*50}\nRunning CHECK_SLA...\n{'-'*50}")
    sla_status = run_checker(
        args.service, 
        CHECK_SLA, 
        args.team_ip, 
        args.team_id, 
        args.round
    )
    print(f"SLA Status: {sla_status}")
    
    if sla_status != OK:
        print(f"SLA check failed with status {sla_status}, stopping further tests")
        sys.exit(1)
    
    # Generate flag and run PUT_FLAG
    test_flag = gen_flag()
    print(f"\n{'-'*50}\nRunning PUT_FLAG with flag {test_flag}...\n{'-'*50}")
    put_status = run_checker(
        args.service, 
        PUT_FLAG, 
        args.team_ip, 
        args.team_id, 
        args.round, 
        test_flag
    )
    print(f"PUT Status: {put_status}")
    
    if put_status != OK:
        print(f"PUT_FLAG failed with status {put_status}, stopping further tests")
        sys.exit(1)
    
    # Wait a bit before doing GET_FLAG
    time.sleep(1)
    
    # Run GET_FLAG with the same flag
    print(f"\n{'-'*50}\nRunning GET_FLAG for flag {test_flag}...\n{'-'*50}")
    get_status = run_checker(
        args.service, 
        GET_FLAG, 
        args.team_ip, 
        args.team_id, 
        args.round, 
        test_flag
    )
    print(f"GET Status: {get_status}")
    
    # Final result
    if get_status == OK:
        print(f"\n{GREEN}All tests PASSED for service {args.service}{END}")
        sys.exit(0)
    else:
        print(f"\n{RED}Tests FAILED for service {args.service}{END}")
        sys.exit(1)

if __name__ == "__main__":
    main()
