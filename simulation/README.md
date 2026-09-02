# Bot driven simulation

A whole Attack/Defense game on one machine, played by bots.

Three CTFBox nodes share the load — two terminate the player tunnels and mesh
with each other, all three run checkers — and a handful of simulated teams
attack each other, patch themselves and occasionally break their own service.

It is not a mock: it is `run.py deploy` with a real topology, real WireGuard
tunnels between the nodes, the real checker system, the real flag ID endpoint
and the real submission endpoint. The only thing pretended is that the three
machines are three machines.

```bash
./simulation/simulate.py up          # deploy the nodes, start the teams
./simulation/simulate.py status      # the live scoreboard, in the terminal
./simulation/simulate.py logs player1
./simulation/simulate.py down        # stop; --clean also wipes the database
```

Then open http://127.0.0.1:9090/scoreboard.

## What it is good for

- **Checking that the nodes coordinate.** Team 2's tunnel lands on `edge` while
  its checks run on `front` and `worker`: every green check is the node mesh
  doing its job. Restarting a router, banning a team or locking the network from
  the admin panel are all visible within seconds.
- **Showing the platform.** The scoreboard moves on its own, SLA included.
- **Debugging.** Everything is local, every container logs, and the game can be
  restarted from scratch in a couple of minutes.

## The topology

| node | roles | what it runs |
| --- | --- | --- |
| `front` | control, vpn, checker | game server, database, scoreboard, admin panel, a router, an embedded checker worker |
| `edge` | vpn, checker | a second router meshed with `front`, a checker worker behind its own VPN sidecar |
| `worker` | checker | nothing but checkers, joined to the game network through a WireGuard profile |

Teams are spread over the two VPN nodes by the usual weighted round robin
(`front` has twice the weight), so some teams reach the game through `front` and
some through `edge`.

Everything is namespaced under the `ctfbox-sim` compose project and its own
`config.simulation.json`, so it can run next to a real deployment without
touching it.

## The teams

`vm_mode` is `none`: the simulation brings its own boxes, which is exactly what
that mode is for. Each team is two containers:

- **`box<id>`** — the vulnbox, joined at `10.60.<id>.1`, running *Notes*: you
  register, you store notes, you read them back with your password. The
  authentication compares the password with `startswith`, so an empty password
  is accepted for any user. Deliberate, and switchable.
- **`player<id>`** — the team, joined at `10.80.<id>.1`. It reads the flag IDs,
  exploits the other teams, submits what it steals, and now and then patches its
  own box or breaks it.

Each team has a personality (`skill`, `defense`, `chaos` in `simulate.py`), so
one team attacks relentlessly and never patches, another patches early and
scores little, another keeps deploying broken code and watching its SLA fall.

The NOP team runs a box and never attacks, exactly like in a real game.

## Trying things on it

```bash
# lock the network and watch the banner appear on the scoreboard
./run.py compose exec router ctfroute lock

# ban a team and watch its bot stop scoring
./run.py compose exec router ctfroute ban 2
```

For the admin panel, connect with
`router/configs-ctfbox-sim/admins/admin-1.conf`: like any CTFBox deployment,
the control room answers only to an admin VPN profile. The profile points at
`127.0.0.1` — everything runs on this machine — so you can import it into
WireGuard and open the dashboard straight away.

Prefix those `run.py` calls with the simulation's environment:

```bash
export CTFBOX_CONFIG=config.simulation.json CTFBOX_PROJECT=ctfbox-sim
```
