# src/runner/AGENTS.md: Sandbox rules

The root [AGENTS.md](../../AGENTS.md) still applies. This file adds rules
for the runner, which executes **untrusted player code**. Any change here
is security-sensitive and needs review from the Runner/Security Owner.

## What lives here

| File | Job |
| :--- | :--- |
| `server.py` | Standard-library HTTP front end: `POST /run`, `POST /grade`, `GET /health` on port 9000 |
| `service.py` | Checks a request, borrows slots, runs or grades, and maps failures to replies |
| `grading.py` | `Grader`: runs the player's program and the check script in two slots and relays turns between them |
| `harness.py` | Runs inside the check slot: the `game` object (`screen`, `send`, `finished`, `check`, `fail`), the `Screen` helpers, and the line protocol. Standard library only |
| `session.py` | One run: starts the launcher, reads one screen each time the program asks for input or exits, sends input only when it asks, enforces the deadlines, reaps |
| `launcher.py` | Runs in the child: drops to the slot user, sets rlimits, receives the code, and execs `python -I -u -c BOOTSTRAP <fd>`, which runs `main.py` like `python main.py`. Also the `reap` mode |
| `slots.py` | Eight slots, each a user ID (200001 to 200008) with its own tmpfs at `/sandbox/N`, plus a reaper user ID per slot (210001 to 210008). A grade takes two at once |
| `limits.py` | `SandboxLimits` and the production values |

## API (T15's `RunnerClient` is the only caller)

`POST /run` with `{"code": str, "inputs": [str, ...]}` returns
`{"status", "screens", "finished", "stderr", "exit_code"}`. The first
screen is what the program printed before it asked for input (or
exited), and each input adds the screen that followed it. `finished` is
true once the program has exited. Statuses: `completed`, `crashed`,
`exited`, `turn_timeout`, `run_timeout`, `output_limit`. `400` means a bad request, `503` means every slot is busy,
and `500 {"status": "runner_error"}` means the sandbox failed. A
`runner_error` is never the player's fault, so it must never cost a life.

`POST /grade` with `{"code": str, "check_script": str}` returns the verdict:
`{"verdict": "pass"|"fail", "reason", "rule", "turn", "inputs",
"last_screen", "traceback"}`. `reason` is `null` on a pass, `rule` when
the check script failed the program (`rule` holds its text), or one of
the `/run` failure statuses. `turn` is how many inputs were sent. The
web app's `Verdict` also has `kind` (the same value as `reason`) for
US7 and US10. `500 {"status": "check_error"}` means the check
script itself crashed, hung, or broke the protocol. That is a campaign
bug, so it must never cost a life either.

`GET /health` answers `200 {"ok": true}`, or `503 {"ok": false,
"retired": n}` once any slot is retired.

## How grading works

A stage program is a normal Python script, run like `python main.py`.
It reads input only when the stage's prompt says so, with plain
`input()`. A **screen** is everything it printed since it last asked for
input, or before it exited. Exiting after printing is a normal finish.

To see when the program asks for input, the launcher starts Python with
a small bootstrap (`python -I -u -c BOOTSTRAP <fd>`). The bootstrap wraps
`sys.stdin`, so every read (including `input()`) first writes one byte to
an inherited "waiting" pipe. Then it runs `main.py` with `runpy` as
`__main__`. Tracebacks hide the bootstrap's frames. Hiding this input
plumbing is the only abstraction.

The player's program and the check script each run as a sandboxed
program in their own slot. The check script's `main.py` is `harness.py`
plus `run(<script>)`. The script defines `check(game)`:

- `game.screen()` returns the current screen.
- `game.send(line)` types one input line and returns the next screen.
- `game.finished` is true once the program has exited.
- `game.check(condition, rule)` and `game.fail(rule)` fail with a rule.
- `Screen.rows` and `Screen.find(char)` are helpers.

The harness and the server talk in JSON lines. The server first sends
the program's first screen. Each `game.send(line)` sends `{"send": line}`,
and the server types that line into the player's program and answers
with `{"screen": ..., "finished": bool}`. When the script returns or
calls `game.fail(rule)`, the harness sends `{"done": true, "rule": ...}`.
The two sides never share a process, a folder, or a user, so neither can
read the other's code. Check scripts run sandboxed because US11 has an
LLM write them.

A **turn** runs from one input request (or the start) to the next input
request or exit. Each turn gets about 1 second (`turn_timeout`), and the
whole run about 10 seconds (`run_timeout`). An input line is at most 64
characters, and a run takes at most 2000 inputs.

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

The same two capabilities let the reaper switch to the slot's reaper
user ID. It kills with `setresuid(reaper, slot, reaper)`, so slot
processes can't signal it, and it loops until `/proc` shows no live slot
process. The slot folder goes back to mode `0700` before it's cleared.

## Known limits (class project, not bank-grade)

- The `sandbox` network is internal, so there is no internet, but a
  player program can still reach `web:8000` like any anonymous visitor.
  The `db` container is not on that network.
- `RLIMIT_NPROC` counts per user, and each slot has its own user, so one
  run can't use up another's process budget. `pids_limit` caps the
  container as a whole. It counts per user ID across the whole Docker
  VM, which is why the slot and reaper user IDs use a high range.
- An output cap of 64 KB applies to each screen (stdout waiting to be
  read) and to stderr for the whole run.
- Local non-root connections to the runner (player code) are dropped in
  the accept loop before they get a thread. Idle connections time out
  after 10 s.
- Each sandboxed program may hold 64 open files (`RLIMIT_NOFILE`).
- No IPC between runs: `ipc: none`, zeroed System V IPC sysctls, and
  `RLIMIT_MSGQUEUE=0`, so there is no `/dev/shm`, no message queue, and
  no System V IPC.
- Player processes are preferred OOM victims, but only as a best
  effort.
