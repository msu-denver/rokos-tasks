# src/runner/AGENTS.md: Sandbox rules

The root [AGENTS.md](../../AGENTS.md) still applies. This file adds rules
for the runner, which executes **untrusted player code**. Any change here
is security-sensitive and needs review from the Runner/Security Owner.

## What lives here

| File | Job |
| :--- | :--- |
| `server.py` | Standard-library HTTP front end: `POST /run`, `GET /health` on port 9000 |
| `service.py` | Checks a request, borrows a slot, plays every input line, builds the reply |
| `session.py` | One run: starts the launcher, sends a line per tick, reads one frame per tick under the deadlines, reaps |
| `launcher.py` | Runs in the child: drops to the slot user, sets rlimits, receives the code, execs `python -I -u main.py`. Also the `reap` mode |
| `slots.py` | Four slots, each a uid (10001 to 10004) with its own tmpfs at `/sandbox/N` |
| `limits.py` | `SandboxLimits` and the production values |

## API (T15's `RunnerClient` is the only caller)

`POST /run` with `{"code": str, "inputs": [str, ...]}` returns
`{"status", "frames", "ticks", "stderr", "exit_code"}`. Statuses:
`completed`, `crashed`, `exited`, `tick_timeout`, `run_timeout`,
`output_limit`. `400` means a bad request, `503` means every slot is busy,
and `500 {"status": "runner_error"}` means the sandbox failed. A
`runner_error` is never the player's fault, so it must never cost a life.

## Rules

1. **Standard library only.** No third-party packages in this folder.
   `launcher.py` must not import anything from `src`, because it runs
   as `python -I launcher.py`.
2. **Never weaken a limit or an isolation setting** without a reviewed
   decision. That covers `limits.py`, the `runner` service in
   `docker-compose.yml`, `Dockerfile.runner`, and `tests/runner/`. The
   production limits are pinned by `tests/unit/test_runner_limits_and_slots.py`.
3. **Never run player code outside a slot**, and never as root. The
   launcher refuses uid 0.
4. **Host mode (`Slot(uid=None)`) is for unit tests only.** It runs as
   the developer, so only benign programs belong there. Hostile programs
   go in `tests/runner/`, which runs against the real container.
5. **The runner gets no environment variables and no secrets.** Don't
   add an `environment:` block to the `runner` service.

## Why the server keeps SETUID and SETGID

Everything else is dropped (`cap_drop: ALL`, `no-new-privileges`). If the
server and the player program ran as the same user, a player could write
into other runs' folders, signal the server, or attach to it and fake a
verdict. So the server starts as root with only `SETUID` and `SETGID`,
and the launcher switches each run to its slot user before any player
code runs. A non-root user has no capabilities, so the player program
has none (`tests/runner/` checks `CapEff` is zero).

## Known limits (class project, not bank-grade)

- The `sandbox` network is internal, so there is no internet, but a
  player program can still reach `web:8000` like any anonymous visitor.
  The `db` container is not on that network.
- `RLIMIT_NPROC` counts per user, and each slot has its own user, so one
  run can't use up another's process budget. `pids_limit` caps the
  container as a whole.
- An output cap of 64 KB applies to each frame (stdout waiting to be
  read) and to stderr for the whole run.
