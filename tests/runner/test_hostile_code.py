"""
File: test_hostile_code.py
Description: Hostile-code suite (US6 AC4). Each test plays a program
    that attacks the sandbox in the real runner container and checks that
    the attack is blocked or the program is killed. Never weaken these.
Author(s): Richard Hall, Tyler Black
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from textwrap import dedent

from tests.runner.conftest import GradeInSandbox, RunInSandbox

# Counts live processes belonging to slot users, excluding this program.
COUNT_SANDBOX_PROCESSES = dedent(
    """
    import os
    count = 0
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            with open(f"/proc/{name}/status") as handle:
                fields = dict(
                    line.split(":", 1) for line in handle if ":" in line
                )
        except (FileNotFoundError, ProcessLookupError):
            continue
        if fields["State"].split()[0] == "Z":
            continue
        real, _effective, saved, _filesystem = map(int, fields["Uid"].split())
        if any(10001 <= uid <= 10008 for uid in (real, saved)):
            count += 1
    print(count)
    """
)


def test_well_behaved_program_completes(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        while True:
            line = input()
            print(f"pressed {line}")
        """
    )
    result = run_in_sandbox(code, ["q", "a"])
    assert result["status"] == "completed"
    assert result["screens"] == ["", "pressed q", "pressed a"]


def test_program_runs_unprivileged(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os
        status = open("/proc/self/status").read()
        caps = status.split("CapEff:")[1].split()[0]
        print(os.getuid(), os.getgid(), os.getgroups(), caps)
        """
    )
    uid, gid, groups, caps = run_in_sandbox(code)["screens"][0].split()
    assert 10001 <= int(uid) <= 10008
    assert gid == uid
    assert groups == "[]"
    assert int(caps, 16) == 0


def test_network_is_unreachable(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import socket
        opened = []
        for host, port in [("1.1.1.1", 53), ("db", 5432),
                           ("example.com", 80)]:
            try:
                socket.create_connection((host, port), timeout=0.3).close()
                opened.append(host)
            except OSError:
                pass
        print(opened or "BLOCKED")
        """
    )
    assert run_in_sandbox(code)["screens"] == ["BLOCKED"]


def test_environment_has_no_secrets(run_in_sandbox: RunInSandbox):
    code = 'import os\nprint(",".join(sorted(os.environ)))\n'
    assert run_in_sandbox(code)["screens"] == ["HOME,LANG,PATH"]


def test_writes_outside_own_folder_fail(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os
        targets = ["/app/x", "/etc/x", "/tmp/x", "/sandbox/x", "/x"]
        targets += ["/dev/shm/x", "/dev/mqueue/x"]
        targets += [f"/sandbox/{slot}/x" for slot in range(8)
                    if f"/sandbox/{slot}" != os.getcwd()]
        wrote = []
        for target in targets:
            try:
                with open(target, "w") as handle:
                    handle.write("x")
                wrote.append(target)
            except OSError:
                pass
        with open("own.txt", "w") as handle:
            handle.write("allowed")
        print(wrote or "NONE")
        """
    )
    assert run_in_sandbox(code)["screens"] == ["NONE"]
    probe = 'import os\nprint(os.listdir("/dev/mqueue"))\n'
    assert run_in_sandbox(probe)["screens"] == ["[]"]


def test_system_v_ipc_allocation_is_disabled(
    run_in_sandbox: RunInSandbox,
) -> None:
    """Check that each System V IPC allocator rejects a private object."""
    code = dedent(
        """
        import ctypes
        libc = ctypes.CDLL(None)
        private = 0
        mode = 0o600
        print(libc.shmget(private, ctypes.c_size_t(1), mode))
        print(libc.msgget(private, mode))
        print(libc.semget(private, 1, mode))
        """
    )
    assert run_in_sandbox(code)["screens"] == ["-1\n-1\n-1"]


def test_player_cannot_call_the_runner_api(
    run_in_sandbox: RunInSandbox,
) -> None:
    """The runner drops a player's connection before reading a request."""
    code = dedent(
        """
        import http.client
        connection = http.client.HTTPConnection("127.0.0.1", 9000, timeout=5)
        try:
            connection.request("POST", "/run", body=b"{}")
            print(connection.getresponse().status)
        except (OSError, http.client.HTTPException):
            print("dropped")
        finally:
            connection.close()
        """
    )
    assert run_in_sandbox(code)["screens"] == ["dropped"]


def test_idle_connection_flood_cannot_starve_the_runner(
    run_in_sandbox: RunInSandbox, grade_in_sandbox: GradeInSandbox
) -> None:
    """Idle connections to the runner can't use up its threads.

    Each player process may hold 64 file descriptors and the slot may own
    16 processes, so nine children open as many idle connections as they
    can and hold them for a whole turn. Refused connections never get a
    server thread, so another run works while they are held, later runs
    and grades still work, and nothing is left running.
    """
    code = dedent(
        """
        import os, socket, sys, time
        print("ready")
        sys.stdout.flush()
        go_read, go_write = os.pipe()
        for _ in range(9):
            if os.fork() == 0:
                os.read(go_read, 1)
                time.sleep(0.1)  # Let the parent ask for input first.
                held = []
                while True:
                    try:
                        connection = ("127.0.0.1", 9000)
                        held.append(socket.create_connection(connection))
                    except OSError:
                        break
                    if len(held) == 1:
                        sys.stderr.write("connected\\n")
                        sys.stderr.flush()
                time.sleep(60)
        os.write(go_write, b"1" * 9)
        input()
        time.sleep(60)  # The flood runs for the whole next turn.
        """
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        flood = pool.submit(run_in_sandbox, code, [""])
        time.sleep(0.6)  # The children are holding their connections.
        assert run_in_sandbox("print('alive')")["screens"] == ["alive"]
        result = flood.result()
    assert result["screens"] == ["ready"], result["stderr"]
    assert result["status"] == "turn_timeout"
    assert "connected" in result["stderr"]
    for _ in range(8):
        assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["screens"] == ["0"]
    echo = "while True:\n    print(input())\n"
    check = "def check(game):\n    game.check(game.send('q') == 'q', 'echo')\n"
    assert grade_in_sandbox(echo, check)["verdict"] == "pass"


def test_open_files_are_capped(run_in_sandbox: RunInSandbox) -> None:
    code = dedent(
        """
        import resource
        print(resource.getrlimit(resource.RLIMIT_NOFILE))
        """
    )
    assert run_in_sandbox(code)["screens"] == ["(64, 64)"]


def test_player_has_the_preferred_oom_score(
    run_in_sandbox: RunInSandbox,
) -> None:
    """Check that the score survives the switch to the slot user."""
    code = (
        'with open("/proc/self/oom_score_adj") as score:\n'
        "    print(score.read().strip())\n"
    )
    assert run_in_sandbox(code)["screens"] == ["1000"]


def test_other_slots_are_unreadable(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os
        seen = []
        for slot in range(8):
            folder = f"/sandbox/{slot}"
            if folder == os.getcwd():
                continue
            try:
                seen.append(os.listdir(folder))
            except OSError:
                pass
            try:
                open(f"{folder}/main.py").read()
                seen.append(folder)
            except OSError:
                pass
        print(seen or "NONE")
        """
    )
    assert run_in_sandbox(code)["screens"] == ["NONE"]


def test_program_that_never_reads_input_is_stopped(
    run_in_sandbox: RunInSandbox,
):
    # Signals "waiting for input" over and over but never reads any.
    code = dedent(
        """
        import contextlib, os, time
        while True:
            for fd in range(3, 256):
                with contextlib.suppress(OSError):
                    os.write(fd, b"?")
            time.sleep(0.001)
        """
    )
    result = run_in_sandbox(code, ["x" * 64] * 2000)
    assert result["status"] in ("run_timeout", "turn_timeout")
    # The forged signals were taken as screens until stdin filled up.
    assert len(result["screens"]) > 1
    assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["screens"] == ["0"]


def test_slot_folder_is_empty_for_next_run(run_in_sandbox: RunInSandbox):
    leave_file = 'open("left.txt", "w").write("x")\n'
    list_files = 'import os\nprint(os.listdir("."))\n'
    for _ in range(8):
        run_in_sandbox(leave_file)
    for _ in range(8):
        assert run_in_sandbox(list_files)["screens"] == ["['main.py']"]


def test_slot_folder_modes_are_restored(run_in_sandbox: RunInSandbox) -> None:
    """Check mode restoration and successful reuse for all eight slots."""
    probe = (
        "import os, stat\n"
        'print(os.getcwd(), oct(stat.S_IMODE(os.stat(".").st_mode)))\n'
    )
    for mode in (0o000, 0o777):
        chmod = f'import os\nos.chmod(".", {mode})\n'
        for _ in range(8):
            assert run_in_sandbox(chmod)["status"] == "completed"
        screens = set()
        for _ in range(8):
            result = run_in_sandbox(probe)
            assert result["status"] == "completed"
            screens.add(result["screens"][0])
        assert screens == {f"/sandbox/{slot} 0o700" for slot in range(8)}


def test_fork_bomb_is_stopped_and_cleaned_up(run_in_sandbox: RunInSandbox):
    code = "import os\nwhile True:\n    os.fork()\n"
    result = run_in_sandbox(code)
    assert result["status"] in ("crashed", "turn_timeout")
    assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["screens"] == ["0"]


def test_sigstop_flood_cannot_freeze_the_reaper(
    run_in_sandbox: RunInSandbox,
) -> None:
    """A leftover process that SIGSTOPs everything can't hang reaping.

    It runs as the slot user and keeps sending SIGSTOP to every process
    it may signal. The reaper must still kill it, answer the request, and
    leave every slot usable.
    """
    code = dedent(
        """
        import os, signal, sys, time
        print("ready")
        sys.stdout.flush()
        go_read, go_write = os.pipe()
        if os.fork() == 0:
            os.setsid()
            os.read(go_read, 1)
            time.sleep(0.1)  # Let the parent ask for input first.
            stopping = False
            while True:
                try:
                    os.kill(-1, signal.SIGSTOP)
                except OSError:
                    continue
                if not stopping:
                    stopping = True
                    sys.stderr.write("stopping\\n")
                    sys.stderr.flush()
        os.write(go_write, b"1")
        input()
        time.sleep(60)
        """
    )
    # The second turn times out with the SIGSTOP flood still running
    # when the reaper goes in.
    result = run_in_sandbox(code, [""])
    assert result["screens"] == ["ready"], result["stderr"]
    assert result["status"] == "turn_timeout"
    assert "stopping" in result["stderr"]
    for _ in range(8):
        assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["screens"] == ["0"]


def test_escaped_child_is_killed_after_run(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os, time
        read_end, write_end = os.pipe()
        if os.fork() == 0:
            os.close(read_end)
            os.setsid()
            if os.fork() == 0:
                os.write(write_end, b"1")
                os.close(write_end)
                time.sleep(60)
            os._exit(0)
        os.close(write_end)
        assert os.read(read_end, 1) == b"1"
        os.close(read_end)
        print("forked")
        """
    )
    assert run_in_sandbox(code)["status"] == "completed"
    assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["screens"] == ["0"]


def test_memory_bomb_crashes(run_in_sandbox: RunInSandbox):
    code = "hoard = bytearray(1024 ** 3)\n"
    result = run_in_sandbox(code)
    assert result["status"] == "crashed"
    assert "MemoryError" in result["stderr"]


def test_huge_stdout_hits_output_limit(run_in_sandbox: RunInSandbox):
    code = 'while True:\n    print("x" * 1000)\n'
    assert run_in_sandbox(code)["status"] == "output_limit"


def test_huge_stderr_hits_output_limit(run_in_sandbox: RunInSandbox):
    code = 'import sys\nwhile True:\n    sys.stderr.write("x" * 1000)\n'
    assert run_in_sandbox(code)["status"] == "output_limit"


def test_huge_file_is_killed(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import signal
        signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
        with open("big.bin", "wb") as handle:
            while True:
                handle.write(b"x" * 65536)
        """
    )
    result = run_in_sandbox(code)
    assert result["status"] == "crashed"
    assert result["exit_code"] in (-25, 153)  # Linux SIGXFSZ


def test_infinite_loop_times_out(run_in_sandbox: RunInSandbox):
    code = "while True:\n    pass\n"
    assert run_in_sandbox(code)["status"] == "turn_timeout"


def test_slow_run_hits_run_timeout(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import time
        while True:
            input()
            time.sleep(0.9)
        """
    )
    result = run_in_sandbox(code, [""] * 13)
    assert result["status"] == "run_timeout"
    assert len(result["screens"]) < 14


def test_root_processes_are_out_of_reach(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os, signal
        reached = []
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                if os.stat(f"/proc/{name}").st_uid != 0:
                    continue
                os.kill(int(name), 0)
                reached.append(name)
            except (PermissionError, ProcessLookupError, FileNotFoundError):
                pass
            try:
                open(f"/proc/{name}/mem", "rb").close()
                reached.append(name + "/mem")
            except OSError:
                pass
        print(reached or "NONE")
        """
    )
    assert run_in_sandbox(code)["screens"] == ["NONE"]


# Reports what it found back through the screen, so the verdict's rule
# carries it out of the sandbox. Sending the first line makes the player
# snoop only once the check script is running in its own slot.
REPORT_SCREEN = "def check(game):\n    game.fail('SAW:' + game.send())\n"

SNOOP_FOR_CHECK_SCRIPT = dedent(
    """
    import os
    input()
    found = []
    for slot in range(8):
        if f"/sandbox/{slot}" == os.getcwd():
            continue
        try:
            if "def check" in open(f"/sandbox/{slot}/main.py").read():
                found.append(slot)
        except OSError:
            pass
    for name in os.listdir("/proc"):
        try:
            if b"def check" in open(f"/proc/{name}/cmdline", "rb").read():
                found.append(name)
        except OSError:
            pass
    print(found or "NONE")
    """
)


def test_player_cannot_read_the_check_script(grade_in_sandbox: GradeInSandbox):
    verdict = grade_in_sandbox(SNOOP_FOR_CHECK_SCRIPT, REPORT_SCREEN)
    assert verdict["rule"] == "SAW:NONE"


def test_hostile_check_script_is_contained(grade_in_sandbox: GradeInSandbox):
    hostile_check = dedent(
        """
        def check(game):
            os = __import__("os")
            socket = __import__("socket")
            json = __import__("json")
            game.send()
            found = []
            for slot in range(8):
                folder = f"/sandbox/{slot}"
                if folder == os.getcwd():
                    continue
                try:
                    found.append(open(f"{folder}/main.py").read())
                except OSError:
                    pass
            try:
                socket.create_connection(("1.1.1.1", 53), timeout=0.3)
                found.append("network")
            except OSError:
                pass
            game.fail(json.dumps({"found": found, "uid": os.getuid()}))
        """
    )
    player = "while True:\n    print('ok')\n    input()\n"
    report = json.loads(grade_in_sandbox(player, hostile_check)["rule"])
    assert report["found"] == []
    assert 10001 <= report["uid"] <= 10008
