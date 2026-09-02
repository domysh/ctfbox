# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CTFBox is an Attack/Defense CTF platform (fork of OASIS), modeled on the CyberChallenge.it A/D format. It orchestrates a network of per-team VMs (via incus/LXD or privileged Docker), a WireGuard router, a Go gameserver that runs checkers/scoring, and web frontends — all driven by a single Python CLI (`run.py`) that generates a `docker-compose` file and manages the whole lifecycle.

It runs both as a zero-config single-machine simulator (`./run.py start`) and as a distributed multi-node deployment able to host a real competition (`./run.py deploy`).

## Top-level components

- `run.py` — the orchestrator CLI. Reads/writes `config.json`, generates `.ctfbox-compose.yml` (Docker Compose), builds/manages VM images (incus or privileged mode), manages WireGuard configs, and drives `docker compose` under the hood. This is the entry point for almost everything (`./run.py start|stop|restart|clear|status|listvms|vmshell|compose ...`).
- `gameserver/` — Go service (`src/`) that scores services, ingests flags, schedules checkers and manages network state. Its React/Vite/Mantine frontend in `gameserver/frontend/` serves both the public scoreboard and the organizers' admin panel at `/admin`.
  - `state.go` — runtime game state. `config.json` seeds the DB on first boot, afterwards the `settings`/`teams`/`services` tables are the authority so the admin panel can change things mid-game; changes are mirrored back into `config.json`.
  - `jobs.go` / `worker.go` / `worker_api.go` — the distributed checker system: the round orchestrator submits jobs to a dispatcher, workers (embedded or remote, `CTFBOX_ROLE=worker`) pull them when they have free slots. This is what balances the checker load.
  - `admin_api.go` — `/api/admin/*`, audit log. **No password and no allow list**: authorization is the source address of the request, which must fall in the hardcoded admin WireGuard subnet `10.80.253.0/24` (`adminVPNNetwork`). There is no exception whatsoever — not loopback, not `conf.Debug`. To work on the admin UI, connect to the game with a profile from `router/configs/admins/`. `X-Forwarded-For` is deliberately ignored. `/api/admin/whoami` is the only open endpoint — the scoreboard calls it to decide whether to render the Admin button at all. `router/entry.sh` exempts `10.80.0.0/16 -> 10.10.0.0/16` from the anonymizing MASQUERADE so the tunnel address survives; the exemption is scoped to tunnel sources because a wider one breaks the DNAT of the publicly exposed scoreboard.
  - `traffic.go` — ingest and aggregation of the per team traffic pushed by the router agents.
  - `scoreboard.go` — public API; implements the scoreboard freeze (score fields served from the freeze round, SLA/status from the live round).
  - `ctfroute.go` — network state and bans, broadcast to every router of the deployment (local unix socket + HTTP agents on the remote nodes). The desired state is **persisted** (`network_state` setting) and published on `/cluster/netstate`: a router rebuilds its ruleset from scratch and comes up frozen, so `router/agent.py` pulls that state every `RECONCILE_INTERVAL` seconds and repairs the drift (state, bans, route to the game server). Never assume a push is enough — restarting a single container must not break a running game.
- `checkervpn/` — WireGuard sidecar that puts a remote checker node inside the game network; the checker container joins its network namespace.
- `gameserver/checkers/` — Python checker scripts per vulnerable service (e.g. `Pwnzer0tt1Shop-Article`, `Pwnzer0tt1Shop-User`, `PCSS`), plus `checklib.py` (shared checker library) and `checkertest.py`.
- `router/` — the WireGuard + iptables network controller container. `ctfroute.sh` / `ctfroute-handle.sh` implement the freeze/lock/unlock/ban network states; `confgen.py` generates per-team/per-admin/per-node WireGuard configs into `router/configs/` (including the node-to-node mesh and the checker node profiles); `agent.py` exposes `ctfroute` over HTTP for the other nodes and pushes the per team traffic accounting to the control node.
- `vm/` — base VM image build (`build.sh`, `Dockerfile`, `Dockerfile.prebuilder`) and `vm/services/` containing the actual vulnerable services deployed into team VMs (each with its own `compose.yml`, exploit `client.py`, and app code).
- `incus/` — the incus (LXD) container that hosts team VMs when `vm-mode: incus` is used (the default, sandboxed alternative to privileged mode). `customize-vm.py reset <team>` destroys a box and clones it again from the base image, which is what `./run.py resetvm` and the control room's reset button both end up calling; `agent.py` is the tiny token-guarded HTTP server that lets the game server ask for it on the machine it shares with the boxes.
- `credentials/` — optional standalone credential-distribution service: Flask backend (`credentials/backend/`) + React/Vite/Mantine frontend (`credentials/frontend/`). Lets team members look up their WireGuard profile/password/IP via a PIN (PINs generated in `router/configs/team<id>/pins.json`).
- `editor/` — Next.js (app router, Mantine, static export) config editor published at ctfbox.domy.sh/editor. `lib/config.ts` mirrors the `Config`/`Team`/`Node` dataclasses of `run.py` and `lib/topology.ts` reimplements its team assignment and topology validation, both covered by `test/logic.test.ts` — when a config field is added to `run.py`, add it here too.
- `simulation/` — bot driven three node game that runs entirely on one machine (`./simulation/simulate.py up`). Real `run.py deploy`, real tunnels, real checkers; the teams are containers running a deliberately weak service plus a bot that attacks, patches and breaks it. Namespaced under `CTFBOX_PROJECT=ctfbox-sim` + `config.simulation.json` so it never touches a real deployment. It is the fastest way to exercise multi-node coordination.
- `demo/` — the public site (ctfbox.domy.sh), **generated**, never edited by hand. `demo/build.py` builds `gameserver/frontend/`, generates the API fixtures from a small deterministic game (eight teams, three services, seventy rounds, scored with the real formula) and overlays the exported editor at `/editor`. `.github/workflows/static.yml` runs it on every push and deploys from `main`. The fixtures cover `/api/admin/*` too, so the demo shows the control room; `whoami` answers `demo: true`, which is what makes the panel read only. Change the frontend and the demo follows — nothing to regenerate by hand.

## Common commands

Orchestration (from repo root, requires Docker + Python 3):
```bash
./run.py start          # generate config (first run) and start the whole stack
./run.py start -C       # generate config.json only, don't start
./run.py stop
./run.py restart
./run.py clear          # reset gameserver DB + generated data + wg configs
./run.py status
./run.py listvms
./run.py resetvm <team_id>   # rebuild a team box from the base image
./run.py vmshell <team_id>
./run.py compose <docker compose args>   # passthrough to docker compose
./run.py compose exec router ctfroute freeze|lock|unlock   # manual network control
./run.py compose exec router ctfroute ban|unban <team_id>

# Distributed deployments
./run.py node list        # topology + team assignment
./run.py deploy           # control node, then every node with an ssh target
./run.py node sync|up|down|ps|logs <name|all>
```

Gameserver (Go, in `gameserver/src/`):
```bash
go build ./...
go run .
```

Frontends (`gameserver/frontend/`, `credentials/frontend/` — Bun + Vite + React + TypeScript + Mantine):
```bash
bun install
bun run dev       # vite dev server
bun run build     # tsc -b && vite build
bun run lint      # eslint .
```

Public site (`demo/`):
```bash
./demo/build.py               # frontend + fixtures + editor into ./_site
./demo/build.py --skip-build  # reuse gameserver/frontend/dist
```

Config editor (`editor/` — Bun + Next.js + Mantine):
```bash
bun install
bun run dev       # http://localhost:3000/editor
bun test          # config + topology logic
bun run build     # static export into out/
```

Vulnerable service checkers/exploits are plain Python (`gameserver/checkers/`) — check `requirements.txt` in that directory before running; `checkertest.py` exercises a checker locally.

## Architecture notes

- **Config is the source of truth**: `config.json` (schema defined by the `Config`/`Team` dataclasses in `run.py`) drives compose file generation, router config generation, and gameserver env — always regenerate via `run.py` rather than hand-editing generated files like `.ctfbox-compose.yml` or `router/configs/*`.
- **Network state machine**: the competition network has three states — frozen (before `start_time - grace_time`), locked (grace period and after `end_time`, teams see only their own VM), unlocked (`start_time` to `end_time`, teams see everyone). `gameserver` transitions these automatically based on config; `ctfroute` subcommands are for manual overrides.
- **VM modes**: `incus` (default, Incus system containers in a dedicated sandbox), `incus-vm` (real Incus/QEMU virtual machines — needs `/dev/kvm` on every `vm` node, checked by `incus/start.sh`), `privileged` (direct Docker privileged containers — faster but boxes can escape to the host, only for trusted players), `none`. `run.py` helpers `uses_incus()` / `incus_instance_type()` normalise the two Incus modes; the choice reaches `incus/customize-vm.py` as `INCUS_INSTANCE_TYPE` and only changes how the instances are created (`--vm`, explicit root disk size, bigger storage pool, longer boot wait).
- **Topology**: `config.json` may declare `nodes` with roles `control` / `vpn` / `vm` / `checker`. With no nodes, `run.py` synthesizes a single all-in-one node, so the single machine path is unchanged. `write_compose(config, node=...)` emits a per-node compose file. There are **two independent assignments** — `assign_teams(config, "vpn")` (which node terminates a team's tunnels) and `assign_teams(config, "vm")` (where its vulnbox runs) — both weighted round robins, pinnable with `teams` / `vm_teams`. run.py puts both in the `NODES` payload so `router/confgen.py` never recomputes them; confgen uses the pair to decide whether a vulnbox can take the local `router:51820` shortcut or must dial the VPN node's public address. A `vm`-only node is fully supported.
- **Restart resilience**: a router rebuilds its whole ruleset on boot and comes up frozen, so nothing may depend on being told once. `CtfRoute*` records the desired state *before* broadcasting (the broadcast is best effort) and `router/agent.py` converges on `/cluster/node-sync`, which doubles as the node heartbeat — that heartbeat is also where the game server learns each node's address, so never hardcode it.
- **API caches**: `apiCache` carries a generation counter. Anything that changes *within* a round (network state, freeze) must call `invalidate()`, and renders must pass the generation they started with to `update()`, otherwise an in-flight request re-caches the stale value.
- **Checker distribution**: never partition statically — workers pull. The control node always runs an embedded worker unless `CTFBOX_EMBEDDED_WORKER=0`. Because PUT_FLAG and GET_FLAG of the same flag can land on different machines, `checklib.save_flag_data`/`get_flag_data` go through the game server (`/flagData` on :8081) with the local file only as a cache/offline fallback.
- **Scoreboard freeze**: when frozen, score-derived fields come from `scoreboard_freeze_round` while SLA and per-service check status come from the live round — deliberately, so players still see whether their services are up without learning the ranking.
- **Two independent frontends**: the gameserver scoreboard frontend and the credentials-service frontend are separate Vite apps with separate `package.json`s and Mantine versions — check which one you're in before assuming shared dependencies (gameserver frontend also pulls in `@mantine/charts`, `recharts`, `@tanstack/react-query`, `zustand`, `react-window`; credentials frontend is simpler — core/form/hooks/modals/notifications only).
- **Services under `vm/services/`** are the intentionally-vulnerable apps deployed into team VMs; each has a matching checker in `gameserver/checkers/` and typically an exploit/client script (`client.py`) — these three pieces (service, checker, exploit) must stay consistent with each other.
