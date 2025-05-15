import os
import json
import sys
from multiprocessing import Pool

with open("/config.json") as f:
    config = json.load(f)

def convert_docker_ram_to_incus(docker_ram_limit):
    """
    Converts a Docker-style RAM limit string (e.g., "1g", "512m", "2Gi")
    to an Incus-compatible limits.memory value in bytes (e.g., "1073741824").
    This function can also be used for disk sizes if they follow the same Docker-style format.

    Args:
        docker_ram_limit (str): The RAM or disk limit string in Docker format.

    Returns:
        str: The corresponding value in bytes as a string.
             Returns None if the input format is invalid.
    """
    if not isinstance(docker_ram_limit, str): # Basic type check
        return None
    docker_ram_limit = docker_ram_limit.strip().lower()
    multiplier = 1
    value_str = ""

    if docker_ram_limit.endswith(('b', 'k', 'm', 'g', 't', 'p')):
        value_str = docker_ram_limit[:-1]
        unit = docker_ram_limit[-1:]
        if unit == 'k':
            multiplier = 1024
        elif unit == 'm':
            multiplier = 1024 * 1024
        elif unit == 'g':
            multiplier = 1024 * 1024 * 1024
        elif unit == 't':
            multiplier = 1024 * 1024 * 1024 * 1024
        elif unit == 'p':
            multiplier = 1024 * 1024 * 1024 * 1024 * 1024
        # 'b' implies bytes, multiplier remains 1
    elif docker_ram_limit.endswith(('ki', 'mi', 'gi', 'ti', 'pi')):
        value_str = docker_ram_limit[:-2]
        unit = docker_ram_limit[-2:]
        if unit == 'ki':
            multiplier = 1024
        elif unit == 'mi':
            multiplier = 1024 * 1024
        elif unit == 'gi':
            multiplier = 1024 * 1024 * 1024
        elif unit == 'ti':
            multiplier = 1024 * 1024 * 1024 * 1024
        elif unit == 'pi':
            multiplier = 1024 * 1024 * 1024 * 1024 * 1024
    else:
        # Check if it's a plain number (assume bytes)
        if docker_ram_limit.isdigit():
            value_str = docker_ram_limit
            multiplier = 1
        else:
            return None # Invalid format if no recognized unit and not a plain number

    if not value_str: # If value_str ended up empty (e.g. input was just "g")
        return None

    try:
        value = int(value_str)
        return str(value * multiplier)
    except ValueError:
        return None  # Invalid numeric value

teams = config["teams"]
cpu_assigned = int(config["max_vm_cpus"])

# Convert RAM limit to bytes for Incus
ram_assigned_bytes = convert_docker_ram_to_incus(config["max_vm_mem"])
if ram_assigned_bytes is None:
    print(f"Error: Invalid format for max_vm_mem: {config['max_vm_mem']}")
    exit(1)

# Convert disk size (assuming same Docker-style format as RAM) to bytes for Incus
disk_size_bytes = convert_docker_ram_to_incus(config["max_disk_size"])
if disk_size_bytes is None:
    print(f"Error: Invalid format for max_disk_size: {config['max_disk_size']}")
    exit(1)

print(f"CPU assigned: {cpu_assigned}, RAM assigned: {ram_assigned_bytes} bytes, Disk size: {disk_size_bytes} bytes")

def create_base_vm():
    """
    Creates the base VM with optimized storage settings and prepares it for cloning.
    """
    print("Creating base VM with optimized storage settings...")
    # Create and configure base VM using the optimized default storage pool
    base_vm_command = """
        # Launch the base VM with base storage pool
        incus init images:ubuntu/noble base-vm || exit 1
        
        # Start the VM
        incus start base-vm || exit 1
        
        # Push required files
        incus file push /vmdata/build.sh base-vm/ -r -p || exit 1
        incus file push /vmdata/entry.sh base-vm/ -r -p || exit 1
        incus file push /vmdata/services/ base-vm/ -r -p || exit 1
        
        # Execute build script
        incus exec base-vm -- bash -c 'mkdir -p /etc/systemd/ && echo -e "[Resolve]\\\\nDNS=10.10.100.1\\\\nFallbackDNS=1.1.1.1" > /etc/systemd/resolved.conf' || exit 1
        incus exec base-vm -- bash -c 'ln -fsv /run/systemd/resolve/resolv.conf /etc/resolv.conf' || exit 1
        
        incus exec base-vm bash /build.sh || exit 1
        incus exec base-vm -- bash -c "mv /services/* /root/ && rm -rf /services" || exit 1
        
        # Initialize VM
        incus exec base-vm -- /usr/bin/_entry_vm_init prebuild || exit 1
        
        # Stop VM for cloning
        incus stop base-vm || exit 1
    """
    
    if os.system(base_vm_command) != 0:
        print("Error: Failed to create and configure base VM")
        exit(1)
    
    print("Base VM created successfully and ready for cloning")

def generate_customize_script(team_id:int, token:str):
    """
    Creates a new VM for each team using their dedicated storage pool.
    """
    print(f"Creating VM for team {team_id} with dedicated storage pool...")
    
    # Create a new VM using the team's dedicated storage pool
    vm_command = f"""
        incus storage create team{team_id} btrfs size={disk_size_bytes} || exit 1
    
        # Clone the base VM for this team with dedicated storage pool
        incus copy base-vm vm{team_id} --storage team{team_id} || exit 1
        
        # Configure resource limits
        incus config set vm{team_id} limits.cpu={cpu_assigned} || exit 1
        incus config set vm{team_id} limits.memory={ram_assigned_bytes} || exit 1
        
        # Start the VM
        incus start vm{team_id} || exit 1
        
        # Configure VM with team-specific settings
        echo "Configuring vm{team_id}..."
        incus exec vm{team_id} -- bash -c "rm /etc/ssh/ssh_host* && ssh-keygen -A" || exit 1
        incus exec vm{team_id} -- mkdir -p /etc/wireguard || exit 1
        incus file push /router/configs/servers/server-{team_id}.conf vm{team_id}/etc/wireguard/game.conf || exit 1
        incus exec vm{team_id} -- bash -c 'echo "root:{token}" | chpasswd' || exit 1
        
        # Enable wireguard
        incus exec vm{team_id} -- systemctl enable wg-quick@game || exit 1
        incus stop vm{team_id} || exit 1
    """
    
    if os.system(vm_command) != 0:
        print(f"Error: Failed to create and configure VM for team {team_id}")
        raise Exception(f"Failed to create VM for team {team_id}")

if "setup" in sys.argv:
    exit(0)

if "start" in sys.argv:
    # Start all team VMs in a single command
    print("Starting all team VMs...")
    vm_list = " ".join([f"vm{team['id']}" for team in teams])
    result = os.system(f"incus start {vm_list}")
    if result == 0:
        print("All VMs have been started successfully.")
    else:
        print("Error: Failed to start some or all VMs.")
    exit(0)

# Main execution starts here
if not os.path.exists("/var/lib/incus/ready"):
    # Create the base VM
    create_base_vm()

# Import process pool for parallel execution

# Modify the function to return success status instead of exiting
def _generate_customize_script_wrapper(team):
    try:
        generate_customize_script(team["id"], team["token"])
        print(f"VM for team {team['id']} generated successfully.")
        return 0
    except Exception as e:
        print(f"Error generating VM for team {team['id']}: {str(e)}")
        return 1

# Create team VMs in parallel using process pool
with Pool(processes=min(os.cpu_count(), len(teams))) as pool:
    results = pool.map(_generate_customize_script_wrapper, teams)
    
    # Check if any process failed
    if any(result != 0 for result in results):
        print("Error: One or more team VM generation processes failed.")
        exit(1)

print("All VMs generated successfully.")
