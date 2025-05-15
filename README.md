# CTFBox

An Open Attack/Defense Infrastructure Simulation Tool - based on containers

<img width="1221" alt="Screenshot 2025-04-29 alle 9 22 05 AM" src="https://github.com/user-attachments/assets/29d8ff13-8523-4c8a-87dc-bf8931c0f490" />

You can see a demo [here](https://ctfbox.domy.sh)

The infrastruture has the same model of <a href="https://ad.cyberchallenge.it/rules">CyberChallenge A/D infrastructure</a> created by <a href="https://cybersecnatlab.it/">CINI Cybersecurity National Lab</a>: also the rules and the network schema are taken from there.

## Introduction
CTFBox is an open-source project designed to provide a simple infrastructure for attack and defense simulations. It facilitates cybersecurity training and testing through various components and services.

The project was initially started as a fork of [OASIS](https://github.com/TheRomanXpl0it/Oasis).

## Installation
To install and set up the CTFBox project, follow these steps:

Clone the repository:

```bash
git clone https://github.com/yourusername/CTFBox.git
cd CTFBox
```

For running CTFBox, you need docker and have correctly installed.
The default option to run the VMs is using incus (LXD), you don't need to install it, because of it will be managed by a CTFBox container that will manage an isolated instance of it. Also CTFBox include the support to run [sysbox](https://github.com/nestybox/sysbox) container. You can follow the instructions in the [Sysbox Setup Guide](./docs/sysbox-setup.md) to install and configure Sysbox.

Now you can run CTFBox using the following command:

```bash
./run.py start
```

You can configure CTFBox using the terminal or using the config editor [here](https://ctfbox.domy.sh/editor) (sources on demo branch).

NOTE: You can avoid to use sysbox by using privileged mode, but this is not recommended if the VMs are given to untrusted users. The privileged mode will give
access to some hosts functionality to the VMs, and escape from container is possible.


To connect to the VMs, you need to use one of the wireguard configurations in the wireguard folder.

Instead you can run `python3 run.py compose exec team<team_id> bash` to connect to the VMs.

To manage the game network run:

```bash 
./run.py compose exec router ctfroute freeze|lock|unlock
```

This will be automatically handled by the game server based on the configuration given (start_time, end_time, grace_time customizable from the ctfbox json). For special cases, you can use this command.

- freeze: freeze the network, no one can connect to the VMs (but only to the gameserver)
- lock: the network is frozen, but now every team can access to their own VM
- unlock: the network is unlocked, every team can access to every VM

Workflow:
- now() < start_time - grace_time: the network is frozen
- start_time - grace_time < now() < start_time: the network is locked (player can access to their own VM)
- start_time < now() < end_time: the network is unlocked (player can access to every VM)
- now() > end_time: the network is locked and the game is finished (players can access to their own VM)

## Configuration

If you want generate the CTFBox json config, edit it and after start CTFBox run:

```bash
./run.py start -C
```

This will generate the config only, you can start ctfbox later

To stop and reset competition run:

```bash
./run.py stop
./run.py clear # This will reset the gameserver db, and all generated data + wg configs
```

Before run the competition, you can customize additional settings in the `config.json` file:

- `wireguard_port`: The port for WireGuard connections.
- `dns`: The DNS server to be used internally in the network.
- `wireguard_profiles`: The number of WireGuard profiles to be created for each team.
- `max_vm_cpus`: The maximum number of CPUs allocated to each VM.
- `max_vm_mem`: The maximum amount of memory allocated to each VM.
- `max_disk_size`: The maximum disk size for each VM (e.g., "30G"). (enable_disk_limit must be true, otherwise it has no effect)
- `enable_disk_limit`: Enable disk size limitations for VMs (requires XFS filesystem).
- `gameserver_token`: The token used for the game server. (It's also the password login for the credential server)
- `gameserver_exposed_port`: The port on which the game server will be exposed.
- `credential_server`: The address of the credential server (null if deactivated).
- `flag_expire_ticks`: The number of ticks after which a flag expires.
- `initial_service_score`: The initial score for each service.
- `max_flags_per_request`: The maximum number of flags that can be submitted in a single request.
- `start_time`: The start time of the competition (can be null of an string with the ISO format).
- `end_time`: The end time of the competition (can be null of an string with the ISO format).
- `grace_time`: The grace time for the competition (in seconds), if start time is not specified it will be now()+grace_time.
- `submission_timeout`: The timeout for flag submissions in seconds.
- `server_addr`: The public address of the server (used for the wireguard config).
- `network_limit_bandwidth`: The bandwidth limit for each server (e.g., "20mbit").
- `vm-mode`: The mode for running the VMs (e.g., "incus", "sysbox", "privileged" or "none").
- `debug`: Enable debug mode for the game server.
- `tick_time`: The time in seconds for each tick.
- `teams`: A list of teams with their respective configurations:
  - `id`: The ID of the team.
  - `name`: The name of the team.
  - `token`: The token for the team (used for flag submission and server password).
  - `nop`: True if the team is marked as NOP team (will not have a wireguard access server).
  - `image`: (Optional) The image used by the team for the scoreboard (more images can be added in the frontend).

## Credential Service

You can also give wireguard profile, password and ip to each team member using a credential distribution service enabling it in the config, that will read pins (generated in router/team\<id\>/pins.json) that can be used to access the competition. The web-platform will require a PIN to login and access to download the wireguard profile and on the team token. Admins can access and read PIN on /admin page, logging-in with the gameserver token.

## Features
- Attack and Defense Simulations: Simulate various cybersecurity attack and defense scenarios.
- Multiple Services: Includes services like Notes and Polls with checkers and exploits for each.
- Infrastructure Setup: Uses Docker Compose for easy setup and management of the infrastructure.
- Extensible: Easily add new services, checkers, and exploits.
