"""
File: test_hostile_code.py
Description: Hostile-code suite (US6 AC4). Each test plays a program
    that attacks the sandbox in the real runner container and checks that
    the attack is blocked or the program is killed. Never weaken these.
Author(s): Tyler Black
"""

from textwrap import dedent

from tests.runner.conftest import RunInSandbox

# Counts processes owned by any slot user other than this program itself.
COUNT_SANDBOX_PROCESSES = dedent(
    """
    import os
    input()
    count = 0
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            owner = os.stat(f"/proc/{name}").st_uid
        except OSError:
            continue
        if 10001 <= owner <= 10004:
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
    assert 10001 <= int(uid) <= 10004
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
        targets += [f"/sandbox/{slot}/x" for slot in range(4)
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


def test_slot_folder_is_empty_for_next_run(run_in_sandbox: RunInSandbox):
    leave_file = 'input()\nopen("left.txt", "w").write("x")\nprint("---")\n'
    list_files = 'import os\ninput()\nprint(os.listdir("."))\nprint("---")\n'
    for _ in range(4):
        run_in_sandbox(leave_file)
    for _ in range(4):
        assert run_in_sandbox(list_files)["frames"] == ["['main.py']"]


def test_fork_bomb_is_stopped_and_cleaned_up(run_in_sandbox: RunInSandbox):
    code = "import os\ninput()\nwhile True:\n    os.fork()\n"
    result = run_in_sandbox(code)
    assert result["status"] in ("crashed", "tick_timeout")
    assert run_in_sandbox(COUNT_SANDBOX_PROCESSES)["frames"] == ["0"]


def test_escaped_child_is_killed_after_run(run_in_sandbox: RunInSandbox):
    code = dedent(
        """
        import os, time
        input()
        if os.fork() == 0:
            os.setsid()
            if os.fork() == 0:
                time.sleep(60)
            os._exit(0)
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
        input()
        with open("big.bin", "wb") as handle:
            while True:
                handle.write(b"x" * 65536)
        """
    )
    assert run_in_sandbox(code)["status"] == "crashed"


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
