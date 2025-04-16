# CTFBox

<img width="1002" alt="Screenshot 2025-04-16 alle 11 16 05 PM" src="https://github.com/user-attachments/assets/bc1d15e5-6bde-429b-aeed-ed127a08900b" />

## Introduction
CTFBox is an open-source project designed to provide a simple infrastructure for attack and defense simulations. It facilitates cybersecurity training and testing through various components and services.

This project as initially started as a fork of [OASIS](https://github.com/TheRomanXpl0it/Oasis).

## Installation
To install and set up the CTFBox project, follow these steps:

Clone the repository:

```bash
git clone https://github.com/yourusername/CTFBox.git
cd CTFBox
```

For running CTFBox, you need docker and have correctly installed and configured [sysbox](https://github.com/nestybox/sysbox).

You can install sysbox with the official .deb files in the repository, or using AUR for Arch Linux, or even [using dnf copr](https://copr.fedorainfracloud.org/coprs/karellen/karellen-sysbox/) for Fedora. (The only official supported way is the .deb files, but the other methods are also working)

Remember that after installing you need to enable sysbox services, and also config docker adding the following lines to `/etc/docker/daemon.json`:
```json
{
    "runtimes": {
        "sysbox-runc": {
            "path": "/usr/bin/sysbox-runc"
        }
    }
}
```

After that, restart the docker service.

Now you can run CTFBox using the following command:

```bash
sudo python3 start.py start
```

NOTE: You can avoid to use sysbox by using --privileged mode, but this is not recommended if the VMs are given to untrusted users. The --privileged mode will give
access to some hosts functionality to the VMs, and escape from container is possible. If you want to use it, you can run:

```bash
sudo python3 start.py start --privileged
```

To connect to the VMs, you need to use one of the wireguard configurations in the wireguard folder.

Instead you can run `python3 start.py compose exec team<team_id> bash` to connect to the VMs.

To manage the game network run:

```bash 
python3 start.py compose exec router ctfroute unlock|lock
```

This will be automatically handled by the game server based on the configuration given (start_time, end_time, customizable from the ctfbox json). For special cases, you can use this command.

## Configuration

If you want generate the CTFBox json config, edit it and after start CTFBox run:

```bash
python3 start.py start -C
```

This will generate the config only, you can start ctfbox later

To stop the services run:

```bash
python3 start.py stop
python3 start.py clear --all # Only if you want remove all the volumes and configs
```

Before run the competition, you can customize additional settings in the `config.json` file:

- `wireguard_start_port`: The starting port for WireGuard connections.
- `dns`: The DNS server to be used internally in the network.
- `wireguard_profiles`: The number of WireGuard profiles to be created for each team.
- `max_vm_cpus`: The maximum number of CPUs allocated to each VM.
- `max_vm_mem`: The maximum amount of memory allocated to each VM.
- `max_disk_size`: The maximum disk size for each VM (e.g., "30G"). (enable_disk_limit must be true, otherwise it has no effect)
- `enable_disk_limit`: Enable disk size limitations for VMs (requires XFS filesystem).
- `gameserver_token`: The token used for the game server. (It's also the password login for the credential server)
- `gameserver_exposed_port`: The port on which the game server will be exposed.
- `flag_expire_ticks`: The number of ticks after which a flag expires.
- `initial_service_score`: The initial score for each service.
- `max_flags_per_request`: The maximum number of flags that can be submitted in a single request.
- `start_time`: The start time of the competition (can be null of an string with the ISO format).
- `end_time`: The end time of the competition (can be null of an string with the ISO format).
- `submission_timeout`: The timeout for flag submissions in seconds.
- `server_addr`: The public address of the server (used for the wireguard config).
- `network_limit_bandwidth`: The bandwidth limit for each server (e.g., "20mbit").
- `unsafe_privileged`: If true, runs containers in privileged mode instead of using sysbox.
- `debug`: Enable debug mode for the game server.
- `tick_time`: The time in seconds for each tick.
- `teams`: A list of teams with their respective configurations:
  - `id`: The ID of the team.
  - `name`: The name of the team.
  - `token`: The token for the team (used for flag submission and server password).
  - `wireguard_port`: The port for WireGuard connections for the team.
  - `nop`: True if the team is marked as NOP team (will not have a wireguard access server).
  - `image`: (Optional) The image used by the team for the scoreboard (more images can be added in the frontend).

## Credential Service

You can also give wireguard profile and password and ip to each team member using the credential_service that is a separate
service that could be runned using docker compose, that will read and write pins that can be used to access the competition.
The webplatform will require a PIN to login and access to download the wireguard profile and on the team token.
Admins can access and read PIN on /admin page, loggin in with the gameserver token.

## Features
- Attack and Defense Simulations: Simulate various cybersecurity attack and defense scenarios.
- Multiple Services: Includes services like Notes and Polls with checkers and exploits for each.
- Infrastructure Setup: Uses Docker Compose for easy setup and management of the infrastructure.
- Extensible: Easily add new services, checkers, and exploits.
