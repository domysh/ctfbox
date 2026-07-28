# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CTFBox is an Attack/Defense CTF infrastructure simulator (fork of OASIS), modeled on the CyberChallenge.it A/D format. It orchestrates a network of per-team VMs (via incus/LXD or privileged Docker), a WireGuard router, a Go gameserver that runs checkers/scoring, and optional web frontends — all driven by a single Python CLI (`run.py`) that generates a `docker-compose` file and manages the whole lifecycle.

## Top-level components

- `run.py` — the orchestrator CLI. Reads/writes `config.json`, generates `.ctfbox-compose.yml` (Docker Compose), builds/manages VM images (incus or privileged mode), manages WireGuard configs, and drives `docker compose` under the hood. This is the entry point for almost everything (`./run.py start|stop|restart|clear|status|listvms|vmshell|compose ...`).
- `gameserver/` — Go service (`src/`) that scores services, ingests flags, runs checkers, and manages network freeze/lock/unlock state (`ctfroute.go`) via `run.py compose exec router ctfroute freeze|lock|unlock`. Has its own React/Vite/Mantine frontend in `gameserver/frontend/` (scoreboard UI, uses `@mantine/charts` + `recharts`).
- `gameserver/checkers/` — Python checker scripts per vulnerable service (e.g. `Pwnzer0tt1Shop-Article`, `Pwnzer0tt1Shop-User`, `PCSS`), plus `checklib.py` (shared checker library) and `checkertest.py`.
- `router/` — the WireGuard + iptables network controller container. `ctfroute.sh` / `ctfroute-handle.sh` implement the freeze/lock/unlock network states; `confgen.py` generates per-team/per-admin WireGuard configs into `router/configs/`.
- `vm/` — base VM image build (`build.sh`, `Dockerfile`, `Dockerfile.prebuilder`) and `vm/services/` containing the actual vulnerable services deployed into team VMs (each with its own `compose.yml`, exploit `client.py`, and app code).
- `incus/` — the incus (LXD) container that hosts team VMs when `vm-mode: incus` is used (the default, sandboxed alternative to privileged mode).
- `credentials/` — optional standalone credential-distribution service: Flask backend (`credentials/backend/`) + React/Vite/Mantine frontend (`credentials/frontend/`). Lets team members look up their WireGuard profile/password/IP via a PIN (PINs generated in `router/configs/team<id>/pins.json`).
- `demo/` — static build of the public demo site (ctfbox.domy.sh) — prebuilt assets, not source to edit directly for app logic.

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
./run.py vmshell <team_id>
./run.py compose <docker compose args>   # passthrough to docker compose
./run.py compose exec router ctfroute freeze|lock|unlock   # manual network control
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

Vulnerable service checkers/exploits are plain Python (`gameserver/checkers/`) — check `requirements.txt` in that directory before running; `checkertest.py` exercises a checker locally.

## Architecture notes

- **Config is the source of truth**: `config.json` (schema defined by the `Config`/`Team` dataclasses in `run.py`) drives compose file generation, router config generation, and gameserver env — always regenerate via `run.py` rather than hand-editing generated files like `.ctfbox-compose.yml` or `router/configs/*`.
- **Network state machine**: the competition network has three states — frozen (before `start_time - grace_time`), locked (grace period and after `end_time`, teams see only their own VM), unlocked (`start_time` to `end_time`, teams see everyone). `gameserver` transitions these automatically based on config; `ctfroute` subcommands are for manual overrides.
- **VM modes**: `incus` (default, sandboxed via a dedicated incus/LXD container) vs `privileged` (direct Docker privileged containers — faster but VMs can escape to the host, only for trusted players) vs `none`.
- **Two independent frontends**: the gameserver scoreboard frontend and the credentials-service frontend are separate Vite apps with separate `package.json`s and Mantine versions — check which one you're in before assuming shared dependencies (gameserver frontend also pulls in `@mantine/charts`, `recharts`, `@tanstack/react-query`, `zustand`, `react-window`; credentials frontend is simpler — core/form/hooks/modals/notifications only).
- **Services under `vm/services/`** are the intentionally-vulnerable apps deployed into team VMs; each has a matching checker in `gameserver/checkers/` and typically an exploit/client script (`client.py`) — these three pieces (service, checker, exploit) must stay consistent with each other.
