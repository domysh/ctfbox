# CTFBox configuration editor

The web editor behind [ctfbox.domy.sh/editor](https://ctfbox.domy.sh/editor): it
builds the `config.json` of a competition, from a single machine to a
distributed deployment, and hands it back as JSON or as the compressed string
`./run.py start` accepts.

Everything runs in the browser. Nothing is uploaded; the draft is kept in
`localStorage` until you reset it.

## Development

```bash
bun install
bun run dev        # http://localhost:3000/editor
bun test           # logic + topology tests
bun run build      # static export into out/
```

## How it is published

`.github/workflows/static.yml` builds this app on every push, exports it
statically and copies `out/` into `/editor/` of the GitHub Pages site next to
the prebuilt demo scoreboard in `demo/`. Only `main` is deployed.

The export is configured with `basePath: "/editor"`; set `NEXT_PUBLIC_BASE_PATH`
to serve it from somewhere else.

## Keeping it in sync with run.py

`lib/config.ts` mirrors the `Config` / `Team` / `Node` dataclasses of `run.py`,
and `lib/topology.ts` reimplements `effective_nodes`, `assign_teams` and
`validate_topology` so that the "planned distribution" table shows exactly what
`./run.py node list` will report. `test/logic.test.ts` guards both; when a
configuration field is added to `run.py`, add it here too.
