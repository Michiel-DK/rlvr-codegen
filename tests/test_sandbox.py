"""Tests for rlvr.sandbox — the sandboxed executor for untrusted, model-
generated Python code (docs/07 Phase A).

Each guard test (network, timeout, fork survival, memory, filesystem,
observability, isolation, resource-safety) was verified RED before GREEN
during development — see the pass-2 PR comment for the red output
(discriminating controls, injected defects, or reverted fixes, run and
captured for each defect in the pass-2 review). Test 2 below bakes its RED
control (plain, unsandboxed subprocess.run) into the test itself, per the
build-flow A2 requirement.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

import rlvr.sandbox as sandbox_module
from rlvr.sandbox import (
    PREAMBLE_LINE_OFFSET,
    SANDBOX_EXEC_AVAILABLE,
    ExecResult,
    _classify_outcome,
    _detect_sandbox_error,
    run_untrusted,
)


def test_normal_execution():
    """Stdout is captured and returncode is 0 for ordinary code."""
    result = run_untrusted("print('hello from sandbox')")
    assert result.returncode == 0
    assert "hello from sandbox" in result.stdout
    assert result.timed_out is False
    assert result.oom is False


def test_network_blocked_with_red_control():
    """Sandboxed code cannot open a TCP socket or fetch via urllib.

    RED DEMONSTRATION (build-flow A2): a control that performs the identical
    connect attempt via plain `subprocess.run` — no sandbox — is run against
    the same listener and MUST succeed. If it didn't, the "blocked" result
    above wouldn't prove the sandbox did the blocking (the listener could
    just be broken/unreachable for unrelated reasons).
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def accept_loop() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                return

    acceptor = threading.Thread(target=accept_loop, daemon=True)
    acceptor.start()
    try:
        sandboxed_code = f"""
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(("127.0.0.1", {port}))
    print("SOCKET-CONNECTED")
except Exception as e:
    print("socket-blocked:", type(e).__name__)

import urllib.request
try:
    urllib.request.urlopen("http://127.0.0.1:{port}/", timeout=1)
    print("URLLIB-CONNECTED")
except Exception as e:
    print("urllib-blocked:", type(e).__name__)
"""
        result = run_untrusted(sandboxed_code, timeout_s=5.0)
        assert "SOCKET-CONNECTED" not in result.stdout, result.stdout
        assert "URLLIB-CONNECTED" not in result.stdout, result.stdout
        assert "socket-blocked" in result.stdout, result.stdout
        assert "urllib-blocked" in result.stdout, result.stdout

        # RED control — identical connect, no sandbox: must SUCCEED.
        control_code = f"""
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", {port}))
print("CONTROL-CONNECTED")
s.close()
"""
        control = subprocess.run(
            [sys.executable, "-c", control_code],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert "CONTROL-CONNECTED" in control.stdout, (
            "discriminating control failed to connect outside the sandbox — "
            "this test no longer proves the block comes from the sandbox. "
            f"stdout={control.stdout!r} stderr={control.stderr!r}"
        )
    finally:
        stop.set()
        srv.close()
        acceptor.join(timeout=2)


@pytest.mark.skipif(
    not SANDBOX_EXEC_AVAILABLE,
    reason=(
        "this test specifically isolates the sandbox-exec kernel-level "
        "network deny from the Python-level preamble; without sandbox-exec "
        "there is nothing to isolate — the preamble is the only layer, and "
        "it is already covered by test_network_blocked_with_red_control"
    ),
)
def test_network_blocked_at_kernel_layer():
    """The sandbox-exec `deny network*` blocks network even if the
    in-process Python preamble is undone.

    `test_network_blocked_with_red_control` above only proves the Python
    monkeypatch blocks the connection — the code never reaches the kernel
    layer, since the preamble raises first. This test reloads `socket`
    inside the sandboxed child (undoing the preamble's patched
    connect/connect_ex) before attempting to connect, forcing the block (if
    any) to come from sandbox-exec's `deny network*` instead. The error
    string differs from the preamble's own OSError text, which is itself
    evidence of which layer produced it.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def accept_loop() -> None:
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                return

    acceptor = threading.Thread(target=accept_loop, daemon=True)
    acceptor.start()
    try:
        code = f"""
import importlib, socket
importlib.reload(socket)  # undo the Python-level preamble patch
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(("127.0.0.1", {port}))
    print("KERNEL-LAYER-CONNECTED")
except Exception as e:
    print("kernel-layer-blocked:", type(e).__name__, str(e))
"""
        result = run_untrusted(code, timeout_s=5.0)
        assert "KERNEL-LAYER-CONNECTED" not in result.stdout, result.stdout
        assert "kernel-layer-blocked" in result.stdout, result.stdout
        # The reload genuinely restored the unpatched socket — the block
        # came from the OS, not from the preamble's own error text.
        assert "network access is disabled in this sandbox" not in result.stdout
    finally:
        stop.set()
        srv.close()
        acceptor.join(timeout=2)


def test_infinite_loop_timed_out():
    """`while True: pass` is killed; timed_out=True; duration within margin."""
    wall_start = time.monotonic()
    result = run_untrusted("while True:\n    pass\n", timeout_s=2.0)
    wall_elapsed = time.monotonic() - wall_start

    assert result.timed_out is True
    assert wall_elapsed <= 2.0 + 2.0, f"wall clock exceeded timeout+margin: {wall_elapsed}"
    assert result.duration_s <= 2.0 + 2.0, f"reported duration exceeded timeout+margin: {result.duration_s}"


def test_fork_child_does_not_survive_timeout_kill():
    """A subprocess spawned by the sandboxed code does not outlive the kill.

    The sandboxed code spawns `sleep 30` and prints its pid, then hangs
    itself so the wall-clock timeout fires. After run_untrusted returns, the
    `sleep` process must be dead — proving the whole process GROUP was
    killed, not just the immediate child (which would leave `sleep` as an
    orphan still running for its remaining ~28s).
    """
    code = """
import subprocess, time
p = subprocess.Popen(["/bin/sleep", "30"])
print(p.pid, flush=True)
time.sleep(30)
"""
    result = run_untrusted(code, timeout_s=2.0)
    assert result.timed_out is True

    pid_text = result.stdout.strip()
    assert pid_text, f"child pid was never printed before the kill; stderr={result.stderr!r}"
    child_pid = int(pid_text)

    deadline = time.monotonic() + 2.0
    alive = True
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            alive = False
            break
        time.sleep(0.1)
    assert not alive, f"orphaned 'sleep 30' (pid {child_pid}) survived the timeout kill"


def test_memory_bomb_terminated_not_hanging():
    """Unbounded allocation is stopped, not allowed to succeed or hang.

    Accepts either an oom-kill (ExecResult.oom True) or a MemoryError raised
    inside the child and printed to stdout — but must fail if the allocation
    completes successfully, and must not hang the suite.

    The loop is bounded (not `while True`) so "the allocation completed" is
    a *reachable* outcome the assertion can actually catch. A `while True`
    loop followed by an unconditional `print("ALLOCATION-SUCCEEDED")` is
    unreachable code — the assertion on it is vacuous no matter what memory
    enforcement does. 4096 * 10 MiB = 40 GiB, far past `memory_mb=128`, so
    if enforcement is somehow completely absent the loop would still finish
    (proving the gap) rather than hang the suite forever.
    """
    code = """
data = bytearray()
try:
    for _ in range(4096):
        data.extend(bytes(10 * 1024 * 1024))
    print("ALLOCATION-SUCCEEDED")
except MemoryError:
    print("MemoryError-in-child")
"""
    wall_start = time.monotonic()
    result = run_untrusted(code, timeout_s=10.0, memory_mb=128)
    wall_elapsed = time.monotonic() - wall_start

    assert wall_elapsed < 10.0 + 2.0, "memory bomb was not terminated before timeout+margin"
    assert "ALLOCATION-SUCCEEDED" not in result.stdout, "unbounded allocation completed — memory was not enforced"
    accepted = result.oom or "MemoryError-in-child" in result.stdout
    assert accepted, f"expected oom-kill or in-child MemoryError; got {result!r}"


@pytest.mark.skipif(
    not SANDBOX_EXEC_AVAILABLE,
    reason=(
        "filesystem write confinement is enforced only by the sandbox-exec "
        "layer; on this machine only the fallback layer is active, and the "
        "fallback does not confine writes (see DECLARED SCOPE in "
        "rlvr/sandbox.py) — skipping rather than asserting something the "
        "current layer cannot provide"
    ),
)
def test_filesystem_confinement():
    """Writes inside the workdir succeed; writes outside it are denied."""
    workdir = Path(tempfile.mkdtemp(prefix="rlvr-fs-test-"))
    outside_target = os.path.join(tempfile.gettempdir(), "rlvr_sandbox_outside_test.txt")
    if os.path.exists(outside_target):
        os.remove(outside_target)
    try:
        inside = run_untrusted(
            "open('inside.txt', 'w').write('ok')\nprint('wrote-inside')",
            workdir=workdir,
        )
        assert inside.returncode == 0, inside.stderr
        assert "wrote-inside" in inside.stdout
        assert (workdir / "inside.txt").exists()

        outside_code = f"""
try:
    open({outside_target!r}, "w").write("bad")
    print("WROTE-OUTSIDE")
except Exception as e:
    print("write-blocked:", type(e).__name__)
"""
        outside = run_untrusted(outside_code, workdir=workdir)
        assert "WROTE-OUTSIDE" not in outside.stdout, outside.stdout
        assert "write-blocked" in outside.stdout, outside.stdout
        assert not os.path.exists(outside_target)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        if os.path.exists(outside_target):
            os.remove(outside_target)


# ---------------------------------------------------------------------------
# Pass-2: observability of degraded states (A1, A2)
# ---------------------------------------------------------------------------


def test_probe_logs_specific_cause_on_subprocess_exception(monkeypatch, caplog):
    """The sandbox-exec availability probe must log the actual cause of
    failure, not swallow it silently (`except Exception: return False`
    gave no signal at all about *why* kernel sandboxing ended up off)."""

    def boom(*args, **kwargs):
        raise OSError("injected: sandbox-exec probe exploded")

    monkeypatch.setattr(sandbox_module.subprocess, "run", boom)
    with caplog.at_level("WARNING", logger="rlvr.sandbox"):
        available = sandbox_module._probe_sandbox_exec()
    assert available is False
    assert any(
        "injected: sandbox-exec probe exploded" in record.getMessage()
        or "injected: sandbox-exec probe exploded" in str(record.args)
        for record in caplog.records
    ), f"probe failure cause was not logged: {[r.getMessage() for r in caplog.records]}"


def test_probe_logs_specific_cause_on_nonzero_returncode(monkeypatch, caplog):
    """Same as above, for the other silent-failure path: sandbox-exec ran
    but returned non-zero."""

    class _FakeCompletedProcess:
        returncode = 1
        stderr = "injected: profile rejected"

    monkeypatch.setattr(
        sandbox_module.subprocess, "run", lambda *a, **k: _FakeCompletedProcess()
    )
    with caplog.at_level("WARNING", logger="rlvr.sandbox"):
        available = sandbox_module._probe_sandbox_exec()
    assert available is False
    assert any("injected: profile rejected" in str(r.args) for r in caplog.records), (
        f"probe rc!=0 cause was not logged: {[r.getMessage() for r in caplog.records]}"
    )


def test_kernel_sandbox_active_echoes_availability():
    """ExecResult.kernel_sandbox_active reflects SANDBOX_EXEC_AVAILABLE."""
    result = run_untrusted("print('x')")
    assert result.kernel_sandbox_active is SANDBOX_EXEC_AVAILABLE


@pytest.mark.skipif(
    not SANDBOX_EXEC_AVAILABLE,
    reason="sandbox_error detection only applies when sandbox-exec is the active launcher",
)
def test_sandbox_error_detected_on_malformed_profile(monkeypatch):
    """A malformed SBPL profile is reported via sandbox_error=True, not
    misread as an ordinary non-zero exit from the user's code.

    Verified empirically (see pass-2 PR comment): a malformed profile
    produces rc=65, empty stdout, and stderr starting with "sandbox-exec:".
    """
    monkeypatch.setattr(
        sandbox_module,
        "_build_sandbox_profile",
        lambda workdir_realpath: "(version 1)(deny defaultZZZ)",
    )
    result = run_untrusted("print('should never run')")
    assert result.sandbox_error is True
    assert result.stdout == ""
    assert result.stderr.startswith("sandbox-exec:")
    assert "should never run" not in result.stdout


def test_sandbox_error_false_on_ordinary_nonzero_exit():
    """A user script that exits non-zero on its own is NOT sandbox_error —
    that field is specifically about sandbox-exec failing to launch."""
    result = run_untrusted("import sys\nsys.exit(65)")
    assert result.returncode == 65
    assert result.sandbox_error is False


@pytest.mark.skipif(
    not SANDBOX_EXEC_AVAILABLE,
    reason="sandbox_error detection only applies when sandbox-exec is the active launcher",
)
def test_sandbox_error_not_forgeable_by_candidate_stderr():
    """Verify-gate finding (PR #11 pass 2): candidate code printing
    "sandbox-exec: ..." as its FIRST stderr line with empty stdout and a
    non-zero exit exactly mimics a launch failure's shape. The preamble's
    startup marker (written before any user code runs) must veto the
    misclassification — a reward-hacking policy must not be able to get its
    failing run reclassified as an infra failure."""
    forgery = (
        "import sys\n"
        'print("sandbox-exec: fake failure that is not a launch failure", file=sys.stderr)\n'
        "sys.exit(1)"
    )
    result = run_untrusted(forgery, timeout_s=10.0)
    assert result.returncode == 1
    assert result.sandbox_error is False
    assert result.stderr.startswith("sandbox-exec: fake failure")


def test_interp_started_marker_stripped_from_reported_stderr():
    """The startup marker is sandbox plumbing, not candidate output — callers
    must never see it in ExecResult.stderr."""
    result = run_untrusted('import sys\nprint("real stderr line", file=sys.stderr)')
    assert "__RLVR_INTERP_STARTED__" not in result.stderr
    assert "real stderr line" in result.stderr
    result_clean = run_untrusted("print('ok')")
    assert result_clean.stderr == ""


def test_output_truncated_caps_large_stdout():
    """Unbounded stdout is capped, not allowed to OOM the parent harness."""
    code = """
chunk = "x" * 65536
for _ in range(64):
    print(chunk, end="")
"""
    result = run_untrusted(code, timeout_s=10.0)
    assert result.output_truncated is True
    # capped at 1 MiB per stream; allow a little slack for the final chunk
    # boundary but it must not be anywhere near the ~4 MiB of real output.
    assert len(result.stdout.encode("utf-8", errors="replace")) <= 1024 * 1024 + 1


def test_output_not_truncated_for_small_stdout():
    result = run_untrusted("print('small')")
    assert result.output_truncated is False


def test_mem_watchdog_not_degraded_on_fast_clean_exit():
    """A trivial, fast-exiting run must not be flagged as watchdog-degraded

    just because it exited before the watchdog got a poll in — that is not
    a degraded state, there was nothing to poll.
    """
    result = run_untrusted("print('hello')")
    assert result.mem_watchdog_degraded is False


def test_mem_watchdog_degraded_when_rss_reads_all_fail(monkeypatch):
    """If every RSS read attempt fails while the process is alive, that must
    be surfaced — not silently presumed fine."""
    monkeypatch.setattr(sandbox_module, "_read_rss_kb", lambda pid: None)
    result = run_untrusted("import time\ntime.sleep(0.3)", timeout_s=5.0)
    assert result.mem_watchdog_degraded is True


# ---------------------------------------------------------------------------
# Pass-2: misattributed outcomes (B3, B4)
# ---------------------------------------------------------------------------


def test_cpu_limited_on_sigxcpu():
    """A child that dies from -signal.SIGXCPU is classified cpu_limited=True,

    not reported as an unexplained crash. Multi-threaded CPU burn
    (hashlib.sha256, which releases the GIL, so real cores run in parallel)
    reliably dies with SIGXCPU well before the wall-clock timeout — verified
    empirically and repeatably at ~0.04-0.09s wall against timeouts from 2s
    to 60s. Note: the exact delivering mechanism (this module's own
    RLIMIT_CPU vs. some other Darwin CPU-accounting path) is not
    conclusively isolated for this heavily-parallel workload — see the
    module docstring's CPU-runaway paragraph. The classification is based
    on the observed SIGXCPU signal itself, not on an assumption about which
    limit fired.
    """
    code = """
import threading, hashlib, os

def burn():
    data = os.urandom(1 << 20)
    while True:
        hashlib.sha256(data).digest()

threads = [threading.Thread(target=burn, daemon=True) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
"""
    result = run_untrusted(code, timeout_s=6.0, memory_mb=2048)
    assert result.returncode == -signal.SIGXCPU
    assert result.cpu_limited is True
    assert result.timed_out is False
    assert result.oom is False, "a CPU-limit death must not also be misclassified as oom"


def test_classify_outcome_bare_sigkill_is_not_oom():
    """A bare SIGKILL with no watchdog hit and no MemoryError text is
    ambiguous (could be our own wall-clock kill, could be a CPU-rlimit
    hard-kill after user code installed a SIGXCPU handler that ignored the
    soft limit) and must NOT be claimed as oom evidence."""
    oom, cpu_limited = _classify_outcome(
        returncode=-signal.SIGKILL, stderr="", watchdog_hit=False
    )
    assert oom is False
    assert cpu_limited is False


def test_classify_outcome_watchdog_hit_is_oom_regardless_of_timeout():
    """`_classify_outcome` doesn't take a `timed_out` argument at all — by
    construction, nothing can gate its watchdog_hit check on whether the
    wall-clock timeout also fired. This pins that (deliberately timeout-
    unaware) contract at the unit level. The scenario this actually guards
    against -- a swap-thrashing memory bomb tripping BOTH the watchdog and
    the wall-clock timeout -- is exercised end-to-end below, through the
    real run_untrusted() call path."""
    oom, _cpu_limited = _classify_outcome(
        returncode=-signal.SIGKILL, stderr="", watchdog_hit=True
    )
    assert oom is True


def test_watchdog_hit_survives_concurrent_wall_clock_timeout(monkeypatch):
    """Integration-level reproduction of the race the review named directly
    (swap-thrashing memory bombs typically trip both the watchdog and the
    wall-clock timeout): the watchdog is replaced with a fake that records
    a hit (as if RSS genuinely exceeded the limit) WITHOUT itself killing
    the process, so the real wall-clock timeout below fires and lands
    independently, landing second. Before the fix, run_untrusted computed
    oom with `if not timed_out: check watchdog_hit`, which silently
    discarded a real watchdog finding whenever this exact interleaving
    happened -- see the pass-2 PR comment for the revert-fix-rerun RED/GREEN
    pair against this test.
    """

    def fake_watchdog(proc, memory_mb, stop_event, hit_flag, stats, poll_interval=0.05):
        stats["attempts"] += 1
        stats["successes"] += 1
        hit_flag.append(True)
        stop_event.wait(poll_interval)

    monkeypatch.setattr(sandbox_module, "_memory_watchdog", fake_watchdog)
    result = run_untrusted("while True:\n    pass\n", timeout_s=0.5, memory_mb=4096)
    assert result.timed_out is True, "the wall-clock timeout must have fired too"
    assert result.oom is True, "a real watchdog hit must not be discarded just because timed_out is also True"


def test_classify_outcome_mem_error_text_is_oom():
    oom, _cpu_limited = _classify_outcome(
        returncode=1, stderr="MemoryError: out of memory", watchdog_hit=False
    )
    assert oom is True


# ---------------------------------------------------------------------------
# Pass-2: resource safety at scale (C5-C9)
# ---------------------------------------------------------------------------


def test_cleanup_on_mid_run_exception_leaves_no_live_process(monkeypatch):
    """If something after Popen() raises (here: the stderr reader thread
    failing to start), the process group must still be killed and reaped —
    not leaked. Captures the real child pid (via a Popen wrapper) and checks
    it directly with os.kill(pid, 0), rather than only checking that the
    exception path didn't hang."""

    original_init = sandbox_module._CappedReader.__init__
    call_count = {"n": 0}

    def flaky_init(self, stream, cap=sandbox_module._MAX_OUTPUT_BYTES):
        call_count["n"] += 1
        original_init(self, stream, cap)
        if call_count["n"] == 2:  # the stderr reader (second construction)
            raise RuntimeError("injected failure after Popen")

    monkeypatch.setattr(sandbox_module._CappedReader, "__init__", flaky_init)

    captured_pid = {}
    original_popen = sandbox_module.subprocess.Popen

    def capturing_popen(*args, **kwargs):
        proc = original_popen(*args, **kwargs)
        captured_pid["pid"] = proc.pid
        return proc

    monkeypatch.setattr(sandbox_module.subprocess, "Popen", capturing_popen)

    workdir = Path(tempfile.mkdtemp(prefix="rlvr-cleanup-test-"))
    try:
        with pytest.raises(RuntimeError, match="injected failure after Popen"):
            run_untrusted("import time\ntime.sleep(5)", workdir=workdir, timeout_s=5.0)

        assert "pid" in captured_pid, "Popen was never called — test setup is wrong"
        pid = captured_pid["pid"]

        deadline = time.monotonic() + 3.0
        alive = True
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                alive = False
                break
            time.sleep(0.05)
        assert not alive, f"child pid {pid} was still alive after a mid-run exception — leaked"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_cleanup_removes_owned_workdir_on_mid_run_exception(monkeypatch):
    """Same as above, but with an rlvr-owned (auto-created) workdir: it must
    be removed by the finally block even though an exception propagates."""

    original_init = sandbox_module._CappedReader.__init__
    call_count = {"n": 0}

    def flaky_init(self, stream, cap=sandbox_module._MAX_OUTPUT_BYTES):
        call_count["n"] += 1
        original_init(self, stream, cap)
        if call_count["n"] == 2:
            raise RuntimeError("injected failure after Popen")

    monkeypatch.setattr(sandbox_module._CappedReader, "__init__", flaky_init)

    captured_workdir = {}
    original_mkdtemp = tempfile.mkdtemp

    def capturing_mkdtemp(*args, **kwargs):
        path = original_mkdtemp(*args, **kwargs)
        captured_workdir["path"] = path
        return path

    monkeypatch.setattr(sandbox_module.tempfile, "mkdtemp", capturing_mkdtemp)

    with pytest.raises(RuntimeError, match="injected failure after Popen"):
        run_untrusted("import time\ntime.sleep(5)", timeout_s=5.0)

    assert "path" in captured_workdir
    assert not os.path.exists(captured_workdir["path"]), (
        "workdir owned by run_untrusted must be removed even on a "
        "mid-run exception path"
    )


def test_stuck_watchdog_logs_loudly_instead_of_silently_returning(monkeypatch, caplog):
    """If the watchdog thread doesn't exit within its join timeout after
    being signaled to stop, that must be logged loudly, not silently
    ignored — a stuck watchdog thread is itself a degraded state."""

    def stuck_watchdog(proc, memory_mb, stop_event, hit_flag, stats, poll_interval=0.05):
        # Deliberately ignores stop_event -- simulates a watchdog that
        # doesn't exit promptly (e.g. stuck inside a slow `ps` call).
        time.sleep(3.0)

    monkeypatch.setattr(sandbox_module, "_memory_watchdog", stuck_watchdog)
    with caplog.at_level("WARNING", logger="rlvr.sandbox"):
        result = run_untrusted("print('done')", timeout_s=5.0)
    assert result.returncode == 0
    assert any(
        "did not exit" in record.getMessage() for record in caplog.records
    ), f"stuck watchdog was not logged: {[r.getMessage() for r in caplog.records]}"


def test_watchdog_stops_polling_once_proc_exited(monkeypatch):
    """The watchdog checks proc.poll() at the top of every iteration and
    returns immediately once it's not None — it must never call
    _read_rss_kb/_kill_process_group using the pid after the process it
    cares about has already exited (which is exactly what would let a
    stale/reused pid get killed). Verified directly against
    _memory_watchdog with a fake Popen-like object, rather than trying to
    force genuine OS-level pid reuse (not practical to induce on demand)."""

    class FakeProc:
        pid = 424242  # deliberately not a real pid

        def poll(self):
            return 0  # already exited

    read_calls = []
    kill_calls = []
    monkeypatch.setattr(
        sandbox_module, "_read_rss_kb", lambda pid: read_calls.append(pid) or 999999999
    )
    monkeypatch.setattr(
        sandbox_module, "_kill_process_group", lambda pid: kill_calls.append(pid)
    )

    stop_event = threading.Event()
    hit_flag: list = []
    stats = {"attempts": 0, "successes": 0}
    sandbox_module._memory_watchdog(FakeProc(), memory_mb=1, stop_event=stop_event, hit_flag=hit_flag, stats=stats)

    assert read_calls == [], "must not read RSS for a pid whose process has already exited"
    assert kill_calls == [], "must not issue a kill against a pid whose process has already exited"
    assert stats["attempts"] == 0


def test_watchdog_survives_pid_reuse_guard():
    """The watchdog is passed the Popen object (not a bare numeric pid) and
    checks proc.poll() at the top of every iteration before touching the
    pid — so once the process it cares about has exited, it never issues a
    kill against whatever pid happens to be reused next. Regression test
    for the watchdog lifecycle fix: run a fast, harmless script under a
    generous memory limit and confirm no kill/oom fires purely from stale
    polling."""
    result = run_untrusted("print('done')", memory_mb=4096, timeout_s=5.0)
    assert result.returncode == 0
    assert result.oom is False


def test_pipe_reader_does_not_hang_on_escaped_grandchild():
    """A grandchild that escapes the process group (its own setsid) and
    holds the stdout pipe's write end open must not hang run_untrusted
    forever waiting for EOF -- the drain timeout must fire, output must be
    reported as truncated/partial, and the call must return within a bounded
    time."""
    code = """
import os, sys, time

pid = os.fork()
if pid == 0:
    os.setsid()
    time.sleep(20)
    os._exit(0)
else:
    while True:
        pass
"""
    start = time.monotonic()
    result = run_untrusted(code, timeout_s=1.0)
    elapsed = time.monotonic() - start
    # bounded: wall timeout (1s) + reap retries (2s, 2s) + drain retries
    # (2s, 2s) + generous scheduling slack -- must NOT wait out the
    # grandchild's full 20s sleep.
    assert elapsed < 15.0, f"pipe read hung waiting on an escaped grandchild: {elapsed}s"
    assert result.timed_out is True
    assert result.output_truncated is True


# ---------------------------------------------------------------------------
# Pass-2: reproducibility (item 14 — PYTHONHASHSEED pin)
# ---------------------------------------------------------------------------


def test_hash_seed_pinned_for_reproducible_set_dict_ordering():
    """Reference/candidate solutions that build sets or dicts have iteration
    order that depends on PYTHONHASHSEED when it isn't pinned -- two
    separate run_untrusted() calls of the identical code must produce
    identical stdout (docs/07's "every number reproducible" requirement)."""
    code = "print(list({'a', 'b', 'c', 'd', 'e', 'f', 'g'}))"
    first = run_untrusted(code)
    second = run_untrusted(code)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout, (
        f"non-deterministic set ordering across separate sandbox runs: "
        f"{first.stdout!r} != {second.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Pass-2: isolation bypass (D10)
# ---------------------------------------------------------------------------


def test_workdir_shadow_module_does_not_bypass_network_block():
    """A planted socket.py in a REUSED workdir must not shadow the real
    stdlib socket module (which would silently defeat the network-block
    preamble, since the preamble patches the real socket.socket). Verifies
    -I keeps the workdir off sys.path.
    """
    workdir = Path(tempfile.mkdtemp(prefix="rlvr-shadow-test-"))
    try:
        shadow_path = workdir / "socket.py"
        shadow_path.write_text(
            "# malicious shadow module: none of these should ever run\n"
            "def connect(*a, **k):\n"
            "    return None\n"
        )
        code = """
import socket
print("SOCKET-FILE:", socket.__file__)
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", 1))
    print("CONNECT-SUCCEEDED")
except Exception as e:
    print("connect-blocked:", type(e).__name__)
"""
        result = run_untrusted(code, workdir=workdir)
        assert result.returncode == 0, result.stderr
        assert "CONNECT-SUCCEEDED" not in result.stdout, result.stdout
        assert "connect-blocked" in result.stdout, result.stdout
        # Strongest, most direct assertion: the real stdlib socket module
        # was imported, not the planted shadow sitting right next to the
        # script in the same (reused) workdir.
        assert str(workdir) not in result.stdout, (
            "socket module resolved from inside the workdir -- shadowed "
            f"by the planted socket.py: {result.stdout!r}"
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Pass-2: test honesty (E11, D13)
# ---------------------------------------------------------------------------


def test_sandbox_exec_required_on_darwin():
    """The suite must FAIL (not silently skip everything) when sandbox-exec
    is unavailable on Darwin -- kernel-level sandboxing being silently
    disabled is a real degradation, not a shrug. RLVR_ALLOW_NO_SANDBOX_EXEC=1
    is the explicit, opt-in escape hatch for a genuinely constrained
    machine. See the pass-2 PR comment for the RED demonstration (this test
    made to fail hard against a monkeypatched-False availability flag,
    instead of the old suite's "5 passed, 2 skipped").
    """
    if sys.platform != "darwin":
        pytest.skip("this assertion is specific to darwin, where sandbox-exec ships by default")
    if os.environ.get("RLVR_ALLOW_NO_SANDBOX_EXEC") == "1":
        pytest.skip(
            "RLVR_ALLOW_NO_SANDBOX_EXEC=1 set -- explicit operator "
            "acknowledgment that this machine lacks sandbox-exec"
        )
    assert SANDBOX_EXEC_AVAILABLE is True, (
        "sandbox-exec is unavailable on this Darwin machine -- kernel-level "
        "network deny and filesystem write confinement are silently "
        "disabled, leaving only the Python-level fallback layer. If this "
        "machine is genuinely constrained, set RLVR_ALLOW_NO_SANDBOX_EXEC=1 "
        "to explicitly acknowledge and skip this check."
    )


def test_preamble_line_offset_matches_constant():
    """PREAMBLE_LINE_OFFSET is derived from the actual assembled prefix, not
    hand-counted -- pin its current value so a preamble edit that changes
    the offset is a visible, deliberate test change, not silent drift."""
    # 12 -> 16 when the interp-started marker block (4 lines) was added to the
    # preamble (verify-gate fix, PR #11 pass 3).
    assert PREAMBLE_LINE_OFFSET == 16


def test_traceback_line_number_is_shifted_by_preamble_offset():
    """A real traceback's reported line number for user code equals the
    user's own source line plus PREAMBLE_LINE_OFFSET."""
    # user code: line 1 is blank, line 2 raises -- so this is the user's
    # own line 2.
    user_code = "\nraise ValueError('boom')\n"
    result = run_untrusted(user_code)
    assert result.returncode != 0
    expected_line = 2 + PREAMBLE_LINE_OFFSET
    assert f"line {expected_line}" in result.stderr, result.stderr


@pytest.mark.skipif(
    not SANDBOX_EXEC_AVAILABLE,
    reason=(
        "this test documents multiprocessing's outcome specifically under "
        "the sandbox-exec kernel layer; without it there is no profile to "
        "characterize"
    ),
)
def test_multiprocessing_pool_blocked_under_sandbox():
    """multiprocessing.Pool is expected to fail under the deny-default
    sandbox-exec profile (no ipc-posix-sem/mach-lookup allow rule) --
    verified empirically: PermissionError creating the pool's SemLock. This
    pins that outcome explicitly (DECLARED SCOPE) rather than leaving it as
    an undocumented silent gap. If the profile is ever extended to allow
    multiprocessing, this test's expectations should be updated deliberately
    alongside that change -- not left to silently start passing/failing.
    """
    code = """
import multiprocessing as mp

def worker(x):
    return x * x

if __name__ == "__main__":
    with mp.Pool(2) as pool:
        result = pool.map(worker, [1, 2, 3])
    print("MP-RESULT:", result)
"""
    result = run_untrusted(code, timeout_s=10.0)
    assert result.timed_out is False, "multiprocessing must fail cleanly, not hang"
    assert "MP-RESULT" not in result.stdout, (
        "multiprocessing.Pool unexpectedly succeeded under sandbox-exec -- "
        "DECLARED SCOPE's documented exclusion is stale, update it"
    )
    assert result.returncode != 0
    assert "PermissionError" in result.stderr, result.stderr
