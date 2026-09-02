# CTFBox

An Open Attack/Defense CTF platform - from a one-command simulation on a laptop
to a distributed infrastructure

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
git clone https://github.com/domysh/CTFBox
cd CTFBox
```

For running CTFBox, you need docker and have correctly installed.
The default option to run the VMs is using incus (LXD), you don't need to install it, because it will be managed by a CTFBox container that provides an isolated instance.

Now you can run CTFBox using the following command:

```bash
./run.py start
```

You can configure CTFBox from the terminal, or with the web config editor at
[ctfbox.domy.sh/editor](https://ctfbox.domy.sh/editor).It
knows about every option below, including the distributed topology, and shows a
live preview of how the teams will be spread over the nodes.

NOTE: You can use privileged mode instead of incus, but this is not recommended if the VMs are given to untrusted users. The privileged mode gives access to host functionality to the VMs, and container escape is possible.


To connect to the VMs, you need to use one of the wireguard configurations in the wireguard folder.

Instead you can run `python3 run.py compose exec team<team_id> bash` to connect to the VMs.

To manage the game network run:

```bash 
./run.py compose exec router ctfroute freeze|lock|unlock
./run.py compose exec router ctfroute ban|unban <team_id>
./run.py compose exec router ctfroute status
```

(The admin panel does all of this on every router at once, which is what you
want on a distributed deployment.)

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
- `vm-mode`: How the team boxes are run — `incus`, `incus-vm`, `privileged` or `none`. See [Team boxes](#team-boxes).
- `scoreboard_freeze_time`: When to automatically freeze the scoreboard (RFC 3339, `null` to never freeze).
- `checker_timeout`: How long a single checker run may take, in seconds.
- `checker_concurrency`: How many checks a node runs in parallel (`0` = automatic, based on the CPUs).
- `traffic_monitor`: Enables the per team traffic accounting on the routers.
- `pcap`: Records the real game traffic on every router, downloadable from the admin panel. Off by default.
- `pcap_max_size`: Size of the capture ring on each router, in MB (default `512`). The oldest files are dropped when it is reached.
- `nodes`: The machines taking part in the game. Empty or absent means "everything on this machine". See [Distributed deployment](#distributed-deployment).

## Team boxes

`vm_mode` decides what a team actually gets:

| mode | what a team box is | isolation | cost |
| --- | --- | --- | --- |
| `incus` (default) | an Incus **system container** | shares the host kernel | seconds to boot, cheap |
| `incus-vm` | a real Incus **virtual machine** | its own kernel, hardware virtualised | slower to boot, reserves its RAM and disk |
| `privileged` | a privileged Docker container | none worth the name: an escape owns the host | fastest |
| `none` | nothing — you bring your own machines | up to you | none |

`incus-vm` is the one to pick when the players are not trusted and a container
escape would be unacceptable: each box boots its own kernel under QEMU/KVM, so
breaking out of it means breaking out of a virtual machine.

It requires KVM on every node hosting vulnboxes:

```bash
ls /dev/kvm   # must exist on each `vm` node
```

That rules out Docker Desktop on macOS or Windows and any VM without nested
virtualization. The Incus container checks it at startup and stops with a clear
message rather than falling back to a software CPU nobody could play on.

Everything else is unchanged: same WireGuard profiles, same checkers, same
`./run.py vmshell <team_id>`. Switching between `incus` and `incus-vm` rebuilds
the boxes but leaves the player profiles alone, so the credentials you already
handed out stay valid.

Sizing: with `incus-vm` the `max_vm_mem` and `max_disk_size` of each team are
really reserved, so a 20 team game with `2G` / `30G` needs 40 GB of RAM and
600 GB of disk spread over the `vm` nodes. That is exactly the case the
distributed deployment is for.

## Surviving a restart

Restarting a single container used to be dangerous: a router rebuilds its whole
ruleset from scratch and always comes up **frozen**, so restarting it in the
middle of a game left the competition network frozen until the end, without its
bans, and unable to reach the game server until the game server itself was
restarted too.

Routers now converge on the state the control node publishes instead of being
told once. The agent inside each router periodically asks
`/cluster/netstate`, compares it with `ctfroute status` and repairs whatever
drifted: the network state, the team bans and the route to the game server. The
game server, symmetrically, keeps its own routes towards the router fresh, so a
router that comes back with a different address is picked up on its own.

In practice every one of these recovers on its own in a second or two, with the
game running:

```bash
./run.py compose restart router
./run.py compose restart gameserver
./run.py compose restart router gameserver
```

Nothing is re-applied when nothing drifted, so the reconciliation costs one small
request per router every 15 seconds (`RECONCILE_INTERVAL` to change it).

## Trying it without any hardware

There is a bot driven simulation that runs a three node game entirely on your
machine: two nodes terminating player tunnels and meshed together, three
checker workers, and simulated teams that attack each other, patch themselves
and break their own services.

```bash
./simulation/simulate.py up
./simulation/simulate.py status
```

It goes through the same `run.py deploy` a real cluster does, so it is a fair
way to see how the nodes coordinate — and a much better demo than a static
scoreboard. See [simulation/README.md](simulation/README.md).

## Admin panel

CTFBox ships an organizers' control room at `/admin` on the scoreboard server.

**There is no password and nothing to configure.** The panel answers only to the
admin WireGuard profiles generated in `router/configs/admins/` (`10.80.253.0/24`):
WireGuard accepts a packet only if its source address matches the key that signed
it, so holding an admin profile is what proves you are an organizer. Nothing to
type at a competition desk, nothing to leak, nothing to rotate — and no allow
list that could be widened by mistake.

To everybody else the control room does not exist: the **Admin** button is not
rendered at all, and `/admin` shows a short "organizers only" note. Every admin
endpoint answers `403` whatever it is asked, including from the publicly exposed
scoreboard port.

Connect with one of the admin profiles and the button appears on its own.

From there you can, live and without restarting anything:

- watch the round, the network state, the checker workers and the job queue;
- freeze / lock / unlock the game network on **every** router of the deployment;
- pause and resume the game (the clock is shifted forward on resume, so no round is lost);
- freeze the scoreboard now or schedule it for later;
- rename teams, change their logo, rotate their submission token;
- ban a team from flag submission and/or cut it off the game network;
- enable, disable and weight the services;
- publish announcements shown to everybody on the scoreboard;
- inspect the checker jobs of any round, the attack graph and the network traffic;
- read every flag submission with its outcome, and the statistics built on them;
- reset a team box to the state it started the game in;
- suspend a single VPN profile, players' and organizers' alike;
- download a filtered slice of the real network traffic, when capture is on;
- read the audit log of every privileged action.

Everything the panel changes is written back into `config.json`, so a restart
keeps it, and it is recorded in the audit log together with the admin address it
came from (`admin@10.80.253.2`).

The same API is usable from a script, over an admin tunnel:

```bash
curl -X POST http://10.10.0.1/api/admin/network/lock
```

There is no way in from anywhere else: not from the control node itself, not
from the loopback of the game server, and not with `"debug": true` either. The
check has no exception. If you mislay a profile, take another one from
`router/configs/admins/` — they are plain files generated with the rest of the
WireGuard configuration.

The same applies while developing: to work on the control room, connect to the
game with an admin profile and reach the game server through the tunnel, so that
the browser's requests really come from `10.80.253.0/24`.

Note that the router deliberately stops anonymizing the traffic a tunnel sends
*to the game infrastructure*, so that the game server can see which profile is
calling; player traffic towards the vulnboxes is still anonymized as before.


## Scoreboard freeze

At a scheduled moment (or with one click in the admin panel) the scoreboard
stops publishing the ranking: points, stolen and lost flags stay at the freeze
round, while **SLA and service status keep updating live**. Players still see
whether their services are up, but not who is winning.

Set it in `config.json`:

```json
"scoreboard_freeze_time": "2026-05-30T17:00:00+02:00"
```

or from the admin panel, which also lets you unfreeze and reveal everything at
the end of the game.

## Traffic monitoring

Each router accounts the traffic per team pair with a two level iptables
ruleset (one dispatch chain per source team, one counter per destination), so
the cost stays linear in the number of teams. A small agent inside the router
container pushes the deltas to the game server every few seconds.

Accounting happens in the `mangle` table, before the router anonymizes the
traffic with NAT, so the real source is always visible to the counters. On a
distributed deployment each flow is counted once, on the node the attacker is
attached to.

Two counters ride on the same rules: bytes and packets on a plain rule, and
opened connections on a `conntrack --ctstate NEW` rule that only counts and
falls through. Connections are usually the honest attack signal — an exploit
loop opens a flow per attempt whatever its payload weighs.

The admin panel then shows:

- traffic per team over time, as bytes (scaled to KB/MB/GB/TB on its own),
  packets or connections, drawn stacked, overlaid, as bars or as lines,
- a "who is talking to whom" matrix split between player tunnels and vulnboxes,
- the attack graph rebuilt from the accepted flags, which is the ground truth of
  who is actually breaking whom.

Turn it off with `"traffic_monitor": false`.

### Packet capture

With `"pcap": true` every router keeps a rotating capture of the game interface
(one file per minute) inside a size capped ring, `pcap_max_size` MB per router
(512 by default). The oldest files are dropped as new ones arrive, so the disk
usage is bounded whatever happens during the game.

The control node stores nothing: the admin panel asks each router for the slice
you want and streams the answer straight to your browser. You can filter by

- **teams** — every packet with that team on either side, vulnbox and player
  tunnel alike,
- **rounds** — a round range, translated into the matching time window,
- **an interval** or the **last N minutes**,
- **an extra BPF expression** (`tcp port 8000`) on top of the rest,

or ask for everything. The answer is always a single `.pcap`: the captures of
every router are merged in timestamp order while they stream, so a distributed
deployment gives one file to open, exactly like a single machine does.

The download is streamed end to end — the routers copy whole capture files
across untouched and only trim the two that straddle the edges of the range, so
asking for hours of traffic costs no memory anywhere and starts arriving
immediately.

Capture writes the players' real traffic to disk. It is off by default on
purpose: turn it on only if the rules of your game say so.

### VPN profiles

Every profile is one WireGuard peer, and WireGuard counts every byte per peer
on its own. The **VPN profiles** card turns that into per team totals and, when
you expand a team, one row per profile: how much it moved in and out, when it
last handshook, which node terminates it. It is the answer to "who inside that
team is consuming all of this", and it costs nothing — the numbers were already
there.

The same list is where a profile is suspended. Suspending drops that one peer
from the running interface: that laptop loses the game network and the rest of
its team keeps playing, which is what a network ban cannot do — that one takes
the whole team out. Organizers' profiles can be suspended too, except the one
you are connected through, which is refused rather than locking you out.

The suspended set is stored on the control node and every router converges to it
on its reconcile tick, so a router that restarts drops the suspended peers again
on its own.

### Resetting a box

A team that breaks its own machine beyond repair gets it back with

```bash
./run.py resetvm <team_id>          # ask first
./run.py resetvm 3 5 --yes          # several at once, no questions
```

The box is destroyed and cloned again from the base image, exactly the way the
first deployment built it: the services, the WireGuard tunnel and the root
password come back, and everything the team put on it is gone. On a distributed
deployment the work happens on the node hosting that box, over ssh.

The control room has the same button next to each team (Teams tab). It reaches
the box manager of the machine it runs on, so it covers every single machine
deployment; for a box on another node it says which node it is and to use the
command above.

### Submissions

Every submission attempt is logged with its outcome — accepted, duplicate, own
flag, expired, invalid, from a nop team, from a banned team, rate limited or a
server error. The **Submissions** tab shows the raw attempts and the statistics
built on them (outcome breakdown, per team hit rate, accepted vs refused per
round), all filterable by attacker, victim, service, outcome and round range.

Refusals are the interesting half: they are what tells you whether a team is
replaying expired flags, submitting its own, or simply guessing.

## Distributed deployment

A single `./run.py start` keeps working exactly as before: one machine, every
role — and once `config.json` declares nodes, the same command brings the whole
cluster up. To spread the same game over several machines, declare them in
`config.json`:

```json
"nodes": [
    {
        "name": "control",
        "roles": ["control", "vpn", "vm", "checker"],
        "address": "10.0.0.1",
        "public_address": "ctf.example.com",
        "weight": 2
    },
    {
        "name": "vms-2",
        "roles": ["vpn", "vm"],
        "address": "10.0.0.2",
        "public_address": "vms2.example.com",
        "ssh": "root@10.0.0.2",
        "path": "/opt/ctfbox"
    },
    {
        "name": "checker-1",
        "roles": ["checker"],
        "address": "10.0.0.3",
        "ssh": "root@10.0.0.3",
        "checker_concurrency": 64
    }
]
```

Roles:

- `control` - the game server, the database, the scoreboard, the admin panel and
  the credentials service. Exactly one node has it.
- `vpn` - terminates the WireGuard tunnels of the teams assigned to it. VPN nodes
  are linked together by a generated WireGuard mesh, so a player attached to one
  node reaches a vulnbox hosted on another.
- `vm` - hosts the vulnboxes of the teams assigned to it. A VM node does **not**
  need a router of its own: its vulnboxes dial the VPN node that terminates
  their tunnels, so several VM nodes can hang off a single VPN node.
- `checker` - runs the checkers. A dedicated checker node joins the game network
  through a WireGuard sidecar and pulls jobs from the control node.

Teams are spread over the nodes with a weighted round robin. The two placements
are independent: `"teams": [3, 4, 5]` pins which node terminates a team's
tunnels, `"vm_teams": [3, 4]` pins where its vulnbox runs. A node that declares
only `teams` uses it for both.

For example, one public VPN endpoint with three machines running the vulnboxes:

```json
"nodes": [
    { "name": "front", "roles": ["control", "vpn", "checker"], "address": "10.0.0.1", "public_address": "ctf.example.com" },
    { "name": "vms-1", "roles": ["vm"], "address": "10.0.0.2", "ssh": "root@10.0.0.2", "weight": 2 },
    { "name": "vms-2", "roles": ["vm"], "address": "10.0.0.3", "ssh": "root@10.0.0.3" },
    { "name": "vms-3", "roles": ["vm"], "address": "10.0.0.4", "ssh": "root@10.0.0.4" }
]
```

Every tunnel lands on `front`, the vulnboxes are split 2:1:1 over the three VM
nodes, and no mesh is needed because there is a single VPN node.

### Deploying

Everything is driven from the control node; the other machines only need Docker,
an ssh account and nothing else installed.

```bash
./run.py start -C     # write config.json, then add the `nodes` section to it
./run.py node list    # check the topology and how the teams were spread
./run.py start        # brings up the whole cluster
```

`./run.py start` on a config that declares `nodes` deploys every node, not just
the local one: half a cluster is not a game anybody can play. `./run.py deploy`
is the same thing under a name that says so, and stays available for when you
want to redeploy without the checks `start` performs.

Either of them does, in order:

1. generates `config.json`-derived compose files and **every** WireGuard profile
   (player, vulnbox, admin, node mesh, checker) on the control node;
2. builds the vulnboxes it hosts itself and brings up its own containers;
3. for each remaining node with an `ssh` target: `rsync`s the sources, that
   node's own `wg0.conf` / `wgmesh.conf` / checker profile, its compose file and
   `config.json`, then runs `docker compose up -d --build` over ssh.

Every node other than the control one needs to say **who deploys it**:

- `"ssh": "user@host"` (or just `"user"`, taking the host from its internal
  address) — the control node deploys it over ssh;
- `"local": true` — it shares the machine you deploy from, which is how a two
  node setup is simulated on one host. Give each local node its own
  `wireguard_port`, they cannot share a UDP port.

A node with neither is **never deployed**: nothing of it runs, and the game
looks half broken — the game server cannot reach a router that does not exist,
and the players assigned to it have no endpoint to dial. `./run.py node list`
says so per node, and `deploy` says it in red as it skips them.

A node without an `ssh` target is skipped with a message: sync it by hand and run
`./run.py node up <name>` on that machine.

Day to day:

```bash
./run.py node sync <name>       # re-ship sources and secrets
./run.py node up|down <name>    # start / stop one node, or `all`
./run.py node ps|logs <name>
./run.py node exec <name> -- <docker compose args>
```

### What each machine needs

On the machine you deploy **from** (usually the control node): `ssh` and
`rsync`.

On every other node, **only Docker**. Nothing else is installed on them: rsync
itself runs inside a container built on the spot, the same way on every node
whatever each one happens to have. The deploy refuses to start if `docker
version` does not answer, telling you what to fix.

That helper image is a plain `FROM alpine:3` plus `apk add rsync`, so building
it needs the node to reach a package mirror **from inside a build container**.
If it cannot, the deploy stops and says so: fix the node's DNS or its outbound
access, or preload the image from a registry you can reach and tag it
`ctfbox-rsync`.

Set up key based ssh first — a deploy runs a handful of commands per node and
you do not want to type a password for each, let alone during a competition:

```bash
ssh-keygen -t ed25519            # if you do not have a key yet
ssh-copy-id ctf@10.0.0.2         # once per node
ssh ctf@10.0.0.2 docker version  # must work without a password
```

If the ssh user is not root it has to be in the `docker` group
(`sudo usermod -aG docker ctf`, then log in again).

The `ssh` field of a node accepts either `user@host` or just `user`: with a bare
username the host is the node's own `address`, which is the address the rest of
the cluster already uses to reach it.

With `vm_mode: incus-vm`, every `vm` node also needs `/dev/kvm`.

### Addresses

Each node has two, and they are used for different things:

- **`address`** — how the other machines reach it. A private network between
  the nodes is ideal: the node to node mesh, the deploy over ssh and the
  internal APIs all prefer it.
- **`public_address`** — how the *players* reach it, so it has to resolve from
  the internet. Only VPN nodes need one. If you leave it out, `address` is used.

`wireguard_port` can be set per node when two VPN nodes have to share one public
address, or one host.

### What has to be reachable

| from | to | port |
| --- | --- | --- |
| players | every `vpn` node | `wireguard_port`/udp |
| each `vpn` node | every other `vpn` node | `wireguard_port + 1`/udp (the mesh) |
| each vulnbox | the `vpn` node of its team | `wireguard_port`/udp |
| each `checker` node | the control node | `wireguard_port`/udp |

That is the whole list. The cluster API (`:8082`) and the router agents (`:8090`)
are **never** published on a host: nodes reach them through the tunnels, at
`10.10.0.1`. Nothing else needs to be open on the internet, and the game server
is not exposed unless you set `gameserver_exposed_port` yourself.

### How the load is balanced

- **Checkers**: the control node produces one job per (team, service, action) and
  every worker pulls work when it has a free slot. There is no static
  partitioning, so a slower machine simply claims less; if a worker dies its jobs
  are requeued and, if nobody picks them up before the end of the round, they are
  scored as a timeout. The control node always runs an embedded worker, which is
  why a single machine deployment needs no configuration at all. Set
  `CTFBOX_EMBEDDED_WORKER=0` on the game server to make it a pure scheduler.
- **VPN**: the tunnels of each team terminate on the node they were assigned to,
  and when there is more than one VPN node they route each other's team subnets
  over the generated mesh.
- **VMs**: each VM node only builds and runs the vulnboxes it was assigned. A
  vulnbox sitting on the same machine as its VPN endpoint takes the local
  shortcut, any other one dials the VPN node's public address.

Checkers keep working across machines because the per flag scratch space
(`save_flag_data` / `get_flag_data` in `checklib`) is stored on the game server
instead of the local disk: PUT_FLAG and GET_FLAG of the same flag may run on two
different nodes.

### Ports

| Port | Who talks to it |
| --- | --- |
| 80 | scoreboard, public API, admin panel (admin tunnels only) |
| 8080 | flag submission |
| 8081 | flag IDs and checker scratch space |
| 8082 | internal cluster API (workers, traffic ingest) - blocked from the player subnets |
| 8090 | router agent (remote `ctfroute` + traffic) - blocked from the player subnets |
| `wireguard_port` | player, vulnbox and admin tunnels |
| `wireguard_port + 1` | node to node mesh (distributed deployments only) |

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

## Credits

- https://github.com/cmspam/incus-docker/ For the incus docker setup
- https://ad.cyberchallenge.it/rules for the rules and the infrastructure design
