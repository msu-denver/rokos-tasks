"""
File: test_hostile_code.py
Description: Hostile-code suite (US6 AC4). Each test plays a program
    that attacks the sandbox in the real runner container and checks that
    the attack is blocked or the program is killed. Never weaken these.
Author(s): Richard Hall, Tyler Black
"""

import json
from textwrap import dedent

from tests.runner.conftest import GradeInSandbox, RunInSandbox

# Counts live processes belonging to slot users, excluding this program.
COUNT_SANDBOX_PROCESSES = dedent(
    """
    import os
    input()
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
    print("---")
    """
)


def test_well_behaved_program_completes(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        while True:
            line = input()
            print(f"pressed {line}")
            print("---")
        """
    )
    result = run_in_sandbox(code, ["q", "a"])
    assert result["status"] == "completed"
    assert result["frames"] == ["pressed q", "pressed a"]


def test_program_runs_unprivileged(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os
        input()
        status = open("/proc/self/status").read()
        caps = status.split("CapEff:")[1].split()[0]
        print(os.getuid(), os.getgid(), os.getgroups(), caps)
        print("---")
        """
    )
    uid, gid, groups, caps = run_in_sandbox(code)["frames"][0].split()
    assert 10001 <= int(uid) <= 10008
    assert gid == uid
    assert groups == "[]"
    assert int(caps, 16) == 0


def test_network_is_unreachable(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import socket
        input()
        opened = []
        for host, port in [("1.1.1.1", 53), ("db", 5432),
                           ("example.com", 80)]:
            try:
                socket.create_connection((host, port), timeout=0.3).close()
                opened.append(host)
            except OSError:
                pass
        print(opened or "BLOCKED")
        print("---")
        """
    )
    assert run_in_sandbox(code)["frames"] == ["BLOCKED"]


def test_environment_has_no_secrets(run_in_sandbox: RunInSandbox):
    code = 'import os\ninput()\nprint(",".join(sorted(os.environ)))\n'
    code += 'print("---")\n'
    assert run_in_sandbox(code)["frames"] == ["HOME,LANG,PATH"]


def test_writes_outside_own_folder_fail(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os
        input()
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
        print("---")
        """
    )
    assert run_in_sandbox(code)["frames"] == ["NONE"]
    probe = (
        'import os\ninput()\nprint(os.listdir("/dev/mqueue"))\nprint("---")\n'
    )
    assert run_in_sandbox(probe)["frames"] == ["[]"]


def test_system_v_ipc_allocation_is_disabled(
    run_in_sandbox: RunInSandbox,
) -> None:
    """Check that each System V IPC allocator rejects a private object."""
    code = dedent(
        """
        import ctypes
        input()
        libc = ctypes.CDLL(None)
        private = 0
        mode = 0o600
        print(libc.shmget(private, ctypes.c_size_t(1), mode))
        print(libc.msgget(private, mode))
        print(libc.semget(private, 1, mode))
        print("---")
        """
    )
    assert run_in_sandbox(code)["frames"] == ["-1\n-1\n-1"]


def test_player_cannot_call_the_runner_api(
    run_in_sandbox: RunInSandbox,
) -> None:
    """The runner drops a player's connection before reading a request."""
    code = dedent(
        """
        import http.client
        input()
        connection = http.client.HTTPConnection("127.0.0.1", 9000, timeout=5)
        try:
            connection.request("POST", "/run", body=b"{}")
            print(connection.getresponse().status)
        except (OSError, http.client.HTTPException):
            print("dropped")
        finally:
            connection.close()
        print("---")
        """
    )
    assert run_in_sandbox(code)["frames"] == ["dropped"]


def test_idle_connection_flood_cannot_starve_the_runner(
    run_in_sandbox: RunInSandbox, grade_in_sandbox: GradeInSandbox
) -> None:
    """Idle connections to the runner can't use up its threads.

    Each player process may hold 64 file descriptors and the slot may own
    16 processes, so this opens as many idle connections as it can and
    leaves them behind. Refused connections never get a server thread, so
    later runs and grades still work and nothing is left running.
    """
    code = dedent(
        """
        import os, socket, sys
        input()
        print("frame")
        print("---")
        sys.stdout.flush()
        held = []
        for _ in range(8):
            if os.fork() == 0:
                break
        while True:
            try:
                held.append(socket.create_connection(("127.0.0.1", 9000)))
            except OSError:
                break
        input()
        """
    )
    assert run_in_sandbox(code)["frames"] == ["frame"]
    for _ in range(8):
        assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["frames"] == ["0"]
    echo = "import sys\nfor line in sys.stdin:\n    print(line.strip())\n"
    echo += "    print('---')\n"
    check = "def check(game):\n    game.check(game.tick('q') == 'q', 'echo')\n"
    assert grade_in_sandbox(echo, check)["verdict"] == "pass"


def test_open_files_are_capped(run_in_sandbox: RunInSandbox) -> None:
    code = dedent(
        """
        import resource
        input()
        print(resource.getrlimit(resource.RLIMIT_NOFILE))
        print("---")
        """
    )
    assert run_in_sandbox(code)["frames"] == ["(64, 64)"]


def test_player_has_the_preferred_oom_score(
    run_in_sandbox: RunInSandbox,
) -> None:
    """Check that the score survives the switch to the slot user."""
    code = (
        'input()\nwith open("/proc/self/oom_score_adj") as score:\n'
        '    print(score.read().strip())\nprint("---")\n'
    )
    assert run_in_sandbox(code)["frames"] == ["1000"]


def test_other_slots_are_unreadable(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os
        input()
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
        print("---")
        """
    )
    assert run_in_sandbox(code)["frames"] == ["NONE"]


def test_program_that_never_reads_input_is_stopped(
    run_in_sandbox: RunInSandbox,
):
    code = (
        "import time\nwhile True:\n    print('---')\n    time.sleep(0.001)\n"
    )
    result = run_in_sandbox(code, ["x" * 64] * 2000)
    assert result["status"] in ("run_timeout", "tick_timeout")
    assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["frames"] == ["0"]


def test_slot_folder_is_empty_for_next_run(run_in_sandbox: RunInSandbox):
    leave_file = 'input()\nopen("left.txt", "w").write("x")\nprint("---")\n'
    list_files = 'import os\ninput()\nprint(os.listdir("."))\nprint("---")\n'
    for _ in range(8):
        run_in_sandbox(leave_file)
    for _ in range(8):
        assert run_in_sandbox(list_files)["frames"] == ["['main.py']"]


def test_slot_folder_modes_are_restored(run_in_sandbox: RunInSandbox) -> None:
    """Check mode restoration and successful reuse for all eight slots."""
    probe = (
        "import os, stat\ninput()\n"
        'print(os.getcwd(), oct(stat.S_IMODE(os.stat(".").st_mode)))\n'
        'print("---")\n'
    )
    for mode in (0o000, 0o777):
        chmod = f'import os\ninput()\nos.chmod(".", {mode})\nprint("---")\n'
        for _ in range(8):
            assert run_in_sandbox(chmod)["status"] == "completed"
        frames = set()
        for _ in range(8):
            result = run_in_sandbox(probe)
            assert result["status"] == "completed"
            frames.add(result["frames"][0])
        assert frames == {f"/sandbox/{slot} 0o700" for slot in range(8)}


def test_fork_bomb_is_stopped_and_cleaned_up(run_in_sandbox: RunInSandbox):
    code = "import os\ninput()\nwhile True:\n    os.fork()\n"
    result = run_in_sandbox(code)
    assert result["status"] in ("crashed", "tick_timeout")
    assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["frames"] == ["0"]


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
        import os, signal, sys
        input()
        print("frame")
        print("---")
        sys.stdout.flush()
        if os.fork() == 0:
            os.setsid()
            while True:
                try:
                    os.kill(-1, signal.SIGSTOP)
                except OSError:
                    pass
        input()
        """
    )
    result = run_in_sandbox(code)
    assert result["frames"] == ["frame"]
    for _ in range(8):
        assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["frames"] == ["0"]


def test_escaped_child_is_killed_after_run(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os, time
        input()
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
        print("---")
        """
    )
    assert run_in_sandbox(code)["status"] == "completed"
    assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["frames"] == ["0"]


def test_memory_bomb_crashes(run_in_sandbox: RunInSandbox):
    code = "input()\nhoard = bytearray(1024 ** 3)\nprint('---')\n"
    result = run_in_sandbox(code)
    assert result["status"] == "crashed"
    assert "MemoryError" in result["stderr"]


def test_huge_stdout_hits_output_limit(run_in_sandbox: RunInSandbox):
    code = 'input()\nwhile True:\n    print("x" * 1000)\n'
    assert run_in_sandbox(code)["status"] == "output_limit"


def test_huge_stderr_hits_output_limit(run_in_sandbox: RunInSandbox):
    code = (
        'import sys\ninput()\nwhile True:\n    sys.stderr.write("x" * 1000)\n'
    )
    assert run_in_sandbox(code)["status"] == "output_limit"


def test_huge_file_is_killed(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import signal
        input()
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
    code = "input()\nwhile True:\n    pass\n"
    assert run_in_sandbox(code)["status"] == "tick_timeout"


def test_slow_run_hits_run_timeout(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import time
        while True:
            input()
            time.sleep(0.9)
            print("---")
        """
    )
    result = run_in_sandbox(code, [""] * 13)
    assert result["status"] == "run_timeout"
    assert result["ticks"] < 13


def test_root_processes_are_out_of_reach(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os, signal
        input()
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
        print("---")
        """
    )
    assert run_in_sandbox(code)["frames"] == ["NONE"]


# Reports what it found back through the frame, so the verdict's rule
# carries it out of the sandbox.
REPORT_FRAME = "def check(game):\n    game.fail('SAW:' + game.tick())\n"

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
    print("---")
    """
)


def test_player_cannot_read_the_check_script(grade_in_sandbox: GradeInSandbox):
    verdict = grade_in_sandbox(SNOOP_FOR_CHECK_SCRIPT, REPORT_FRAME)
    assert verdict["rule"] == "SAW:NONE"


def test_hostile_check_script_is_contained(grade_in_sandbox: GradeInSandbox):
    hostile_check = dedent(
        """
        def check(game):
            os = __import__("os")
            socket = __import__("socket")
            json = __import__("json")
            game.tick()
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
    player = "import sys\nfor line in sys.stdin:\n    print('ok')\n"
    player += "    print('---')\n"
    report = json.loads(grade_in_sandbox(player, hostile_check)["rule"])
    assert report["found"] == []
    assert 10001 <= report["uid"] <= 10008
