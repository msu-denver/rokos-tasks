# src/runner/AGENTS.md: Sandbox rules

The root [AGENTS.md](../../AGENTS.md) still applies. This file adds rules
for the runner, which executes **untrusted player code**. Any change here
is security-sensitive and needs review from the Runner/Security Owner.

## What lives here

| File | Job |
| :--- | :--- |
| `server.py` | Standard-library HTTP front end: `POST /run`, `POST /grade`, `GET /health` on port 9000 |
| `service.py` | Checks a request, borrows slots, runs or grades, and maps failures to replies |
| `grading.py` | `Grader`: runs the player's program and the check script in two slots and relays ticks between them |
| `harness.py` | Runs inside the check slot: the `game` object (`tick`, `check`, `fail`) and the line protocol. Standard library only |
| `session.py` | One run: starts the launcher, sends a line per tick, reads one frame per tick under the deadlines, reaps |
| `launcher.py` | Runs in the child: drops to the slot user, sets rlimits, receives the code, execs `python -I -u main.py`. Also the `reap` mode |
| `slots.py` | Eight slots, each a uid (10001 to 10008) with its own tmpfs at `/sandbox/N`. A grade takes two at once |
| `limits.py` | `SandboxLimits` and the production values |

## API (T15's `RunnerClient` is the only caller)

`POST /run` with `{"code": str, "inputs": [str, ...]}` returns
`{"status", "frames", "ticks", "stderr", "exit_code"}`. Statuses:
`completed`, `crashed`, `exited`, `tick_timeout`, `run_timeout`,
`output_limit`. `400` means a bad request, `503` means every slot is busy,
and `500 {"status": "runner_error"}` means the sandbox failed. A
`runner_error` is never the player's fault, so it must never cost a life.

`POST /grade` with `{"code": str, "check_script": str}` returns the verdict:
`{"verdict": "pass"|"fail", "reason", "rule", "tick", "inputs",
"last_frame", "traceback"}`. `reason` is `null` on a pass, `rule` when the
check script failed the program (`rule` holds its text), or one of the
`/run` failure statuses. `500 {"status": "check_error"}` means the check
script itself crashed, hung, or broke the protocol. That is a campaign
bug, so it must never cost a life either.

## How grading works

The player's program and the check script each run as a sandboxed
program in their own slot. The check script's `main.py` is `harness.py`
plus `run(<script>)`. Each `game.tick(line)` prints `{"tick": line}` as
one JSON line followed by `---`; the server plays that line on the
player's program and answers with `{"frame": ...}` on one line. When the
script returns or calls `game.fail(rule)`, the harness sends
`{"done": true, "rule": ...}`. The two sides never share a process, a
folder, or a user, so neither can read the other's code. Check scripts
run sandboxed because US11 has an LLM write them.

The check script's run clock gets a 2 s margin over the player's, so when
time runs out the player's program is the one that times out.

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
  player program can still reach every service on it like any anonymous
  visitor: `web:8000`, `web-dev:8001` while `make dev` runs (Flask dev
  server, debugger off, host port bound to 127.0.0.1), and the runner's
  own API on port 9000 (`runner:9000` or `127.0.0.1:9000`, since player
  code runs in that container). The `db` container is not on that
  network.
- `RLIMIT_NPROC` counts per user, and each slot has its own user, so one
  run can't use up another's process budget. `pids_limit` caps the
  container as a whole.
- An output cap of 64 KB applies to each frame (stdout waiting to be
  read) and to stderr for the whole run.
