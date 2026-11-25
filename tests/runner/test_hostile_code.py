"""
File: test_hostile_code.py
Description: Hostile-code suite (US6 AC4). Each test plays a program
    that attacks the sandbox in the real runner container and checks that
    the attack is blocked or the program is killed. Never weaken these.
Author(s): Richard Hall
"""

import json
from textwrap import dedent

from tests.runner.conftest import GradeInSandbox, RunInSandbox

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
        if 10001 <= owner <= 10008:
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
