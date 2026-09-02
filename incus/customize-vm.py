import os
import json
import subprocess
import sys
from multiprocessing import Pool

with open("/config.json") as f:
    config = json.load(f)

# Incus can run a team box as a system container (shares the host kernel) or as
# a real virtual machine (its own kernel, needs KVM). run.py decides which one
# through the vm_mode of config.json.
INSTANCE_TYPE = os.environ.get("INCUS_INSTANCE_TYPE", "container").strip() or "container"
IS_VM = INSTANCE_TYPE == "virtual-machine"
INIT_FLAGS = "--vm" if IS_VM else ""
# A virtual machine cannot boot faster than its kernel: give it room, and say
# something useful instead of hanging forever if it never comes up.
BOOT_TIMEOUT = 900 if IS_VM else 300

# Shared shell helpers injected in every incus command below.
SHELL_PRELUDE = f"""
set -o pipefail

wait_ready() {{
    name="$1"
    deadline=$(( $(date +%s) + {BOOT_TIMEOUT} ))
    while ! incus exec "$name" -- bash -c "systemctl is-system-running | grep -q -E 'running|degraded'" 2>/dev/null; do
        if [ "$(date +%s)" -ge "$deadline" ]; then
            echo "Timed out waiting for $name to finish booting" >&2
            incus info --show-log "$name" >&2
            return 1
        fi
        sleep 2
    done
}}

# A virtual machine answers an ACPI shutdown, but a wedged guest may ignore it.
stop_instance() {{
    name="$1"
    incus stop "$name" --timeout 120 && return 0
    echo "Graceful stop of $name timed out, forcing it" >&2
    incus stop "$name" --force
}}
"""


def run_shell(script: str) -> int:
    """Runs a snippet with bash: the helpers above need more than plain sh."""
    return subprocess.call(["bash", "-c", SHELL_PRELUDE + script])

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
# On a distributed deployment each VM node only builds the vulnboxes of the
# teams it was assigned (run.py sets NODE_TEAMS); empty means "all of them".
node_teams = os.environ.get("NODE_TEAMS", "").strip()
if node_teams:
    allowed_teams = {int(t) for t in node_teams.split(",") if t.strip()}
    teams = [team for team in teams if team["id"] in allowed_teams]
    print(f"This node hosts {len(teams)} team VMs: {sorted(allowed_teams)}")

cpu_assigned = int(config["max_vm_cpus"])

# Convert RAM limit to bytes for Incus
ram_assigned_bytes = convert_docker_ram_to_incus(config["max_vm_mem"])
if ram_assigned_bytes is None:
    print(f"Error: Invalid format for max_vm_mem: {config['max_vm_mem']}")
    exit(1)

# Convert disk size (assuming same Docker-style format as RAM) to bytes for Incus
disk_size_bytes = convert_docker_ram_to_incus(config.get("max_disk_size") or "30G")
if disk_size_bytes is None:
    print(f"Error: Invalid format for max_disk_size: {config['max_disk_size']}")
    exit(1)

# A virtual machine gets a real block device of that size, so the pool backing
# it needs a little room on top for its own metadata.
POOL_OVERHEAD = 2 * 1024 * 1024 * 1024
pool_size_bytes = int(disk_size_bytes) + (POOL_OVERHEAD if IS_VM else 0)

if IS_VM and int(ram_assigned_bytes) < 512 * 1024 * 1024:
    print(
        f"Warning: {config['max_vm_mem']} of memory is very little for a real VM, "
        "it may fail to boot. Raise max_vm_mem or use vm_mode 'incus'."
    )

print(
    f"Instance type: {INSTANCE_TYPE}, CPU assigned: {cpu_assigned}, "
    f"RAM assigned: {ram_assigned_bytes} bytes, Disk size: {disk_size_bytes} bytes"
)

def create_base_vm():
    """
    Creates the base instance every team box is later cloned from.
    """
    print(f"Creating the base {INSTANCE_TYPE} with optimized storage settings...")
    # A VM must be told how big its root disk is up front: the 10GiB default is
    # not enough for the services built by build.sh.
    root_device = (
        f"--device root,size={disk_size_bytes}" if IS_VM else ""
    )
    base_vm_command = f"""
        # Launch the base instance with the base storage pool
        incus init images:ubuntu/noble base-vm {INIT_FLAGS} {root_device} || exit 1

        incus start base-vm || ( incus info --show-log base-vm; exit 1 )

        # Wait for systemd to finish booting (and, on a VM, for the incus agent
        # to come up: `incus exec` does not work before that).
        wait_ready base-vm || exit 1

        # Push required files
        incus file push /vmdata/build.sh base-vm/ -r -p || exit 1
        incus file push /vmdata/entry.sh base-vm/ -r -p || exit 1
        incus file push /vmdata/services/ base-vm/ -r -p || exit 1

        # Configure the box for VPN access
        incus exec base-vm -- bash -c "echo '10.10.100.1 router' >> /etc/.extra_hosts" || exit 1

        incus exec base-vm bash /build.sh || exit 1
        incus exec base-vm -- bash -c "mv /services/* /root/ && rm -rf /services" || exit 1

        incus exec base-vm -- /usr/bin/_entry_vm_init prebuild || exit 1

        # Stop it for cloning
        stop_instance base-vm || exit 1
    """

    if run_shell(base_vm_command) != 0:
        print(f"Error: Failed to create and configure the base {INSTANCE_TYPE}")
        exit(1)

    print(f"Base {INSTANCE_TYPE} created successfully and ready for cloning")

def generate_customize_script(team_id: int, token: str):
    """
    Clones the base instance into the box of one team, on its own storage pool.
    """
    print(f"Creating the box of team {team_id} with a dedicated storage pool...")

    # On a VM the root disk is a real block device, so it has to be resized
    # explicitly; on a container the pool quota is enough.
    # `set` works when incus copy already gave the instance its own root
    # device (it does when --storage is used), `override` covers the case where
    # the device is still the one inherited from the profile.
    resize_root = (
        f"incus config device set vm{team_id} root size={disk_size_bytes} 2>/dev/null || "
        f"incus config device override vm{team_id} root size={disk_size_bytes} || exit 1"
        if IS_VM
        else ""
    )

    vm_command = f"""
        incus storage create team{team_id} btrfs size={pool_size_bytes} || exit 1

        # Clone the base instance for this team on its dedicated storage pool
        incus copy base-vm vm{team_id} --storage team{team_id} || exit 1

        # Configure resource limits
        incus config set vm{team_id} limits.cpu={cpu_assigned} || exit 1
        incus config set vm{team_id} limits.memory={ram_assigned_bytes} || exit 1
        {resize_root}

        incus start vm{team_id} || ( incus info --show-log vm{team_id}; exit 1 )

        wait_ready vm{team_id} || exit 1

        # Configure the box with the team specific settings
        echo "Configuring vm{team_id}..."
        incus exec vm{team_id} -- bash -c "rm /etc/ssh/ssh_host* && ssh-keygen -A" || exit 1
        incus exec vm{team_id} -- mkdir -p /etc/wireguard || exit 1
        incus file push /router/configs/servers/server-{team_id}.conf vm{team_id}/etc/wireguard/game.conf || exit 1
        incus exec vm{team_id} -- bash -c 'echo "root:{token}" | chpasswd' || exit 1

        # Enable wireguard
        incus exec vm{team_id} -- systemctl enable wg-quick@game || exit 1
        stop_instance vm{team_id} || exit 1
    """

    if run_shell(vm_command) != 0:
        print(f"Error: Failed to create and configure the box of team {team_id}")
        raise Exception(f"Failed to create the box of team {team_id}")

def destroy_box(team_id: int) -> None:
    """Removes a team box and the storage pool that belongs to it.

    Both are deleted so that the rebuild starts from exactly the same place a
    first deployment does: a leftover pool would make `incus storage create`
    fail and leave the team with no box at all.
    """
    run_shell(f"""
        incus delete vm{team_id} --force 2>/dev/null
        incus storage delete team{team_id} 2>/dev/null
        true
    """)


def reset_box(team_id: int, token: str) -> None:
    """Puts one team back to the state it started the game in.

    The base image is untouched, so this is a clone plus the per team
    configuration, exactly like the first deployment. Everything the team did
    to its box is gone, which is the whole point.
    """
    print(f"Resetting the box of team {team_id}...")
    destroy_box(team_id)
    generate_customize_script(team_id, token)
    if run_shell(f"incus start vm{team_id} || ( incus info --show-log vm{team_id}; exit 1 )") != 0:
        raise Exception(f"Box of team {team_id} was rebuilt but did not start")
    print(f"Box of team {team_id} has been reset")


if "setup" in sys.argv:
    exit(0)

if "reset" in sys.argv:
    wanted = [arg for arg in sys.argv[sys.argv.index("reset") + 1:] if arg.isdigit()]
    if not wanted:
        print("Usage: customize-vm.py reset <team_id> [team_id...]")
        exit(2)
    by_id = {str(team["id"]): team for team in teams}
    unknown = [team_id for team_id in wanted if team_id not in by_id]
    if unknown:
        print(f"No box on this node for team(s) {', '.join(unknown)}")
        print(f"Teams hosted here: {', '.join(sorted(by_id)) or 'none'}")
        exit(2)
    failed = []
    for team_id in wanted:
        try:
            reset_box(int(team_id), by_id[team_id]["token"])
        except Exception as exc:
            print(f"Error resetting the box of team {team_id}: {exc}")
            failed.append(team_id)
    exit(1 if failed else 0)

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
