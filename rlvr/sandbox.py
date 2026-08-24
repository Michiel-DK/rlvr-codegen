"""rlvr.sandbox — sandboxed executor for untrusted, model-generated Python code.

DECLARED SCOPE (docs/07 Phase B.3 discipline)
==============================================

What this blocks / verifies
----------------------------
- **Network egress** is denied two ways, applied together:
  1. macOS ``sandbox-exec`` with a deny-default profile (``deny network*``),
     when available on this machine (probed once at import time — see
     ``SANDBOX_EXEC_AVAILABLE``).
  2. A Python-level preamble, prepended to every run, that monkeypatches
     ``socket.socket.connect``/``connect_ex`` and ``socket.create_connection``/
     ``create_server`` to raise before user code runs. This is applied
     unconditionally, independent of whether layer 1 is active, so network is
     blocked even on a machine without ``sandbox-exec``.
- **Filesystem writes outside the workdir** are denied via the sandbox-exec
  profile's ``file-write*`` allow list, scoped to
  ``(subpath <realpath(workdir)>)``, when sandbox-exec is active. Writing
  inside the workdir is allowed.
- **The workdir is not on ``sys.path``, and user site-packages are off.**
  The child interpreter is invoked with ``-P`` (``PYTHONSAFEPATH``, 3.11+),
  so the script's own directory (and cwd, and ``PYTHONPATH``) is never
  prepended to ``sys.path``, plus ``-s`` (no user site-packages), so a
  reused workdir can't smuggle a shadow module in via
  ``<HOME>/.local/lib/pythonX.Y/site-packages`` either (``HOME`` is set to
  the workdir — see the env dict below). Without ``-P``, code executed
  *from inside* a writable workdir would put that workdir on ``sys.path``,
  and a reused workdir containing an attacker-planted ``socket.py`` (or any
  other stdlib shadow) would silently defeat the network-block preamble
  above — the child would import the planted module instead of the real
  ``socket``. Verified empirically: with ``-P -s``, a planted ``socket.py``
  in the workdir is *not* picked up (``socket.__file__`` resolves to the
  real stdlib path); without it, the shadow wins. See
  ``test_workdir_shadow_module_does_not_bypass_network_block``.
  Deliberately **not** ``-I`` (isolated mode): ``-I`` implies ``-P``/``-s``
  *and* ``-E``, and ``-E`` ignores ``PYTHONHASHSEED`` along with every other
  ``PYTHON*`` env var this module sets — verified empirically that ``-I``
  silently defeats the hash-seed pin below even when the env var is set.
  ``-B`` (no bytecode) and ``-X utf8`` (force UTF-8 mode regardless of
  locale/env) are passed explicitly rather than relied on via env vars, so
  behavior doesn't depend on which env vars happen to be present.
- **Set/dict iteration order is reproducible across runs.** ``PYTHONHASHSEED``
  is pinned to ``"0"`` in the child's environment. Without this, two
  separate ``run_untrusted`` calls of *identical* code that builds a
  ``set``/``dict`` and prints it can produce different stdout, since string
  hash randomization is randomized per-process by default — breaking
  docs/07's "every number reproducible" requirement for anything that
  compares captured stdout across runs. See
  ``test_hash_seed_pinned_for_reproducible_set_dict_ordering``.
- **Wall-clock runaway** (e.g. ``while True: pass``) is killed via a
  process-wait timeout followed by ``os.killpg`` (SIGKILL) on the child's
  process group. The child is started with ``start_new_session=True`` so it
  gets its own process group; killing the group (not just the immediate
  child) means a child that forks/execs its own subprocesses does not
  survive the kill as an orphan.
- **CPU runaway** (fallback layer, always applied in addition to whichever of
  1/2 is active): ``resource.setrlimit(RLIMIT_CPU, ...)`` in a ``preexec_fn``,
  derived from ``timeout_s``. This is belt-and-suspenders alongside the
  wall-clock kill above — for a CPU-bound infinite loop the two fire around
  the same time. A multi-threaded CPU burn (multiple threads calling
  ``hashlib.sha256`` in a loop, which releases the GIL, so real cores run in
  parallel) reliably dies with ``-signal.SIGXCPU`` well before the
  wall-clock timeout on this machine — reproduced consistently at
  ``timeout_s`` values from 2 to 60. This IS surfaced via
  ``ExecResult.cpu_limited`` rather than being reported as an unexplained
  crash, regardless of what delivers it. One caveat: the observed
  time-to-death does **not** scale cleanly with the ``RLIMIT_CPU`` value
  ``_compute_rlimits`` derives from ``timeout_s`` (e.g. ``timeout_s=2.0``
  and ``timeout_s=6.0``, giving CPU limits of 4s and 8s, both die in
  ~0.04-0.09s wall time across repeated trials; ``timeout_s=60.0``, limit
  62s, dies at ~6-13s) — so while ``RLIMIT_CPU`` is the most likely
  mechanism (a plain single-threaded busy-loop dies close to its computed
  limit; the multi-threaded case dies far sooner, consistent with several
  real cores accumulating CPU-seconds much faster than wall-seconds), this
  has not been conclusively isolated from other CPU-accounting paths a
  heavily-parallel, crypto-heavy workload can trigger on Darwin. Treat
  ``cpu_limited=True`` as "died from SIGXCPU, for CPU-limit-shaped reasons,"
  not as proof of exactly which limit fired.
- **Memory** (best-effort — see caveat below): ``resource.setrlimit`` on
  ``RLIMIT_AS`` and ``RLIMIT_DATA`` in the same ``preexec_fn``, derived from
  ``memory_mb`` — plus a userspace watchdog thread that polls the child's
  RSS via ``ps`` and SIGKILLs the process group if it exceeds ``memory_mb``.
  The watchdog is the layer that actually does the work on this machine; see
  below.

Observability of degraded states
---------------------------------
A caller must be able to tell a clean run from a degraded one without
guessing from ``returncode`` alone. ``ExecResult`` carries these fields for
that purpose:

- ``kernel_sandbox_active``: echo of ``SANDBOX_EXEC_AVAILABLE`` *at call
  time*. If this is ``False``, only the fallback layers (Python-level
  network patch, best-effort rlimits, RSS watchdog) were applied — no OS
  filesystem/network confinement.
- ``sandbox_error``: ``sandbox-exec`` itself failed to *launch* the
  interpreter (e.g. a malformed SBPL profile) — as opposed to the
  sandboxed program itself failing/exiting non-zero. Detected via: kernel
  sandboxing was active, the child's stdout is empty, and stderr's first
  line starts with ``"sandbox-exec:"`` (verified empirically: a malformed
  profile produces exactly this shape — ``rc=65``, empty stdout, stderr
  ``"sandbox-exec: unbound variable: ... "``). When this is ``True``,
  nothing about ``returncode``/``oom``/``cpu_limited`` reflects the user's
  code at all — the user's code never ran.
- ``output_truncated``: ``True`` if captured stdout or stderr was cut off
  at the 1 MiB per-stream cap (see Resource safety below), *or* if a
  stdout/stderr reader thread failed to reach EOF within its drain timeout
  (e.g. a process-group-escaping grandchild still holding the pipe's write
  end open) — in the latter case the captured text is a best-effort partial
  read, not a truncated-by-size read, but the caller-facing contract is the
  same: don't trust this text as complete.
- ``cpu_limited``: ``True`` iff the child died from ``-signal.SIGXCPU``.
  See the CPU-runaway paragraph above, including the caveat that the exact
  delivering mechanism (this module's own ``RLIMIT_CPU`` vs. some other
  Darwin CPU-accounting path) is not conclusively isolated for
  heavily-parallel workloads.
- ``mem_watchdog_degraded``: ``True`` if the watchdog thread ran (the
  process was alive for at least one poll attempt) but *every* RSS read
  attempt failed (``ps`` unavailable/erroring/returning nothing parseable).
  In this state the watchdog cannot be trusted to have caught a memory
  bomb — callers must not read ``oom=False`` as "memory was fine" when this
  is also ``True``. A process that exits before the watchdog gets a single
  poll attempt (e.g. trivial ``print()`` code) is *not* degraded — there
  was nothing to poll.

A ``logging.warning`` (module logger ``rlvr.sandbox``) is emitted once at
import time if the ``sandbox-exec`` availability probe fails, including the
actual exception or the probe's stderr/returncode — the previous behavior
(``except Exception: return False``) swallowed the cause entirely. Loud
warnings are also emitted (not swallowed) if the watchdog thread does not
exit within its join timeout, or if a stdout/stderr reader thread does not
reach EOF within its drain timeout.

What this does NOT verify / explicit caveats
---------------------------------------------
- **This is not a security boundary against adversarial native code.** It
  stops the obvious things a code-generation model's Python output might do
  (open a socket, allocate unbounded memory, loop forever, write outside its
  workdir). It is not a hypervisor, a container runtime, or a substitute for
  running fully untrusted/adversarial code on throwaway hardware.
- **``RLIMIT_AS``/``RLIMIT_DATA`` are not just "unreliable" on macOS — on
  this machine they cannot be set at all.** Verified empirically: calling
  ``resource.setrlimit(resource.RLIMIT_AS, (n, n))`` raises
  ``ValueError("current limit exceeds maximum limit")`` for *any* finite
  ``n``, and the same is true of ``RLIMIT_DATA`` and ``RLIMIT_RSS``
  (``RLIMIT_AS`` and ``RLIMIT_RSS`` even share the same numeric resource id
  on Darwin). The ``preexec_fn`` calls are kept — they're harmless, and
  would work on Linux if this code ever runs there — but they are silent
  no-ops on this platform, caught by a broad ``try/except``. The mechanism
  that actually stops a memory bomb here is the userspace RSS-polling
  watchdog thread (``_memory_watchdog``): it kills the process group if
  measured RSS exceeds ``memory_mb``. That is real enforcement, not a
  passive check, but it is still best-effort — poll interval (50ms
  default), the overhead of spawning ``ps`` on each poll, and a pathological
  allocator that blows past the limit between polls are all real gaps.
  Callers must treat ``oom=True`` as a *heuristic classification* (watchdog
  fired, or a ``MemoryError``/"Cannot allocate memory" string in stderr) —
  not a hard guarantee — and must not read ``oom=False`` as proof memory was
  never exceeded, especially when ``mem_watchdog_degraded=True``. A bare
  SIGKILL with no watchdog hit and no MemoryError text is deliberately
  **not** classified as ``oom`` — it is ambiguous (could be the wall-clock
  kill, could be the CPU-rlimit hard-kill after a SIGXCPU handler ignored
  the soft limit, could be something else) and claiming it as oom would be
  a misattribution the caller can't audit.
- **File reads are not confined.** The sandbox-exec profile allows
  ``file-read*`` broadly; only writes are scoped to the workdir. Untrusted
  code can read any file the host process can read. This is a deliberate
  scope choice, not an oversight: restricting reads on macOS sandbox-exec is
  fragile across differing Python/Homebrew installs, and — for this repo's
  use case (executing model-generated candidate solutions against a test
  suite, not running genuinely adversarial input) — unconfined read without
  network egress is a materially smaller risk than unconfined write or
  network access.
- **When ``sandbox-exec`` is unavailable** (probed at import time; see
  ``SANDBOX_EXEC_AVAILABLE``), only the fallback layer applies: no OS-level
  filesystem write confinement and no OS-level network deny. Network
  blocking then rests entirely on the Python-level socket monkeypatch, which
  is an in-process patch, not a kernel boundary — it can be defeated cheaply,
  e.g. ``importlib.reload(socket)`` restores the original, unpatched
  ``connect``/``connect_ex`` (verified: this alone reopens a connection when
  sandbox-exec is off), or via ``ctypes`` calling into libc directly. When
  sandbox-exec *is* active, the kernel-level ``deny network*`` still holds
  even after such a reload — verified with a discriminating test that
  reloads ``socket`` before connecting; see
  ``test_network_blocked_at_kernel_layer`` in the test suite. Callers should
  check ``ExecResult.kernel_sandbox_active`` rather than assume it.
- **The Python-level patch only covers TCP connect paths.** It patches
  ``socket.socket.connect``/``connect_ex`` and ``create_connection``/
  ``create_server`` — UDP sockets that call ``sendto`` without ever calling
  ``connect`` (``socket.socket(AF_INET, SOCK_DGRAM).sendto(...)``) are not
  touched by the preamble at all. This is blocked by the kernel-level
  ``deny network*`` when sandbox-exec is active, but wide open when only the
  fallback layer is active.
- **The memory watchdog polls only the group leader's RSS** (the immediate
  child's ``proc.pid``), not the process group's total RSS. Untrusted code
  that forks off its own allocator subprocesses can spread memory use across
  multiple processes and evade the per-pid check.
- **``memory_mb`` has a practical floor.** A bare CPython interpreter's own
  baseline RSS on this machine is already ~11 MB before user code runs
  anything; requesting a `memory_mb` at or below that will trip the watchdog
  (or an rlimit, where those work) on every run, including ones doing
  nothing memory-intensive.
- **``preexec_fn`` is documented by the ``subprocess`` module as unsafe to
  use when the parent process is multithreaded** (only async-signal-safe
  calls are safe between ``fork()`` and ``exec()``). This module spawns a
  watchdog thread in the parent for every call, i.e. every call to
  ``run_untrusted`` after the first happens with a multithreaded parent.
  ``_preexec`` itself is kept to nothing but ``resource.setrlimit`` calls on
  precomputed values (the ``resource`` module is imported once at module
  load, in the parent, before any fork — not inside ``_preexec`` — since a
  post-fork ``import`` can deadlock on CPython's import lock in a
  multithreaded parent, which this module's own watchdog guarantees every
  call after the first is). That removes the one clearly-unsafe operation
  this module used to perform between fork and exec; the general
  ``preexec_fn``-in-a-multithreaded-parent caveat from the ``subprocess``
  docs still technically applies (``setrlimit`` itself is not formally
  documented as async-signal-safe either), and this did not reproduce a
  failure in this module's own test runs, but it is a latent,
  non-deterministic flakiness source, not something eliminated by this
  design.
- **Not a defense against**: fork-bombs that outrace the timeout+killpg
  window, denial-of-service via extreme thread/process counts, or
  side-channel/timing attacks.
- **``multiprocessing.Pool`` (and friends) do not work under sandbox-exec.**
  Verified empirically: ``multiprocessing.Pool(2).map(...)`` raises
  ``PermissionError: [Errno 1] Operation not permitted`` when creating the
  pool's internal ``SemLock`` — the deny-default profile has no
  ``ipc-posix-sem`` (or ``mach-lookup``) allow rule. This fails cleanly
  (a Python exception, not a hang) rather than silently. This is a
  deliberate scope exclusion, not a bug: this sandbox's use case is running
  model-generated single-process candidate solutions against a test suite,
  and extending the profile to allow POSIX semaphores/Mach lookups would
  widen the sandbox-exec attack surface for a capability nothing here
  currently needs. See ``test_multiprocessing_pool_blocked_under_sandbox``.
- **Preamble shifts user tracebacks by ``PREAMBLE_LINE_OFFSET`` (12) lines.**
  The network-block preamble prepended to every script is 12 lines long
  (including the trailing `# --- user code below ---` marker line before
  the user's own first line). A traceback frame reporting "line N" for code
  the caller supplied is actually the caller's line ``N - PREAMBLE_LINE_OFFSET``.
  Callers translating tracebacks back to the original candidate source must
  subtract this constant. Pinned by
  ``test_preamble_line_offset_matches_constant``.

Public API
----------
``run_untrusted(code, *, timeout_s=5.0, memory_mb=512, workdir=None) -> ExecResult``
"""

from __future__ import annotations

import dataclasses
import logging
import math
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

__all__ = [
    "ExecResult",
    "run_untrusted",
    "SANDBOX_EXEC_AVAILABLE",
    "PREAMBLE_LINE_OFFSET",
]

_LOG = logging.getLogger(__name__)

# Per-stream stdout/stderr capture cap (see Resource safety in the module
# docstring) — `while True: print(x)` must not OOM the parent harness.
_MAX_OUTPUT_BYTES = 1 * 1024 * 1024  # 1 MiB

# How long to wait for the process to actually die after each escalating
# kill attempt, and how long to wait for the stdout/stderr reader threads to
# reach EOF once the process is confirmed dead (or we've given up on it).
_REAP_TIMEOUT_S = 2.0
_DRAIN_TIMEOUT_S = 2.0
_WATCHDOG_JOIN_TIMEOUT_S = 1.0


@dataclasses.dataclass
class ExecResult:
    """Result of running untrusted code via :func:`run_untrusted`.

    See the module docstring's "Observability of degraded states" section
    for what each of the non-obvious fields means and why it exists.
    """

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool
    oom: bool
    duration_s: float
    kernel_sandbox_active: bool
    sandbox_error: bool
    output_truncated: bool
    cpu_limited: bool
    mem_watchdog_degraded: bool


# --------------------------------------------------------------------------
# sandbox-exec availability probe (run once, at import time)
# --------------------------------------------------------------------------


def _probe_sandbox_exec() -> bool:
    """Return True if ``sandbox-exec`` is present and actually works here.

    A permissive profile is used for the probe itself — this only checks
    that sandbox-exec can wrap and run the interpreter at all (it is known
    to be removed/broken on some macOS configurations), not that the
    deny-default profile used by real runs behaves as expected. That is
    covered by the test suite, not by this probe.

    Every failure path logs the specific cause via ``_LOG.warning`` — the
    previous ``except Exception: return False`` swallowed it entirely.
    """
    if shutil.which("sandbox-exec") is None:
        _LOG.warning(
            "sandbox-exec not found on PATH; kernel-level sandboxing "
            "(network deny, filesystem write confinement) is disabled — "
            "only the Python-level fallback layer will be applied"
        )
        return False
    try:
        proc = subprocess.run(
            [
                "sandbox-exec",
                "-p",
                "(version 1)(allow default)",
                sys.executable,
                "-c",
                "pass",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 — this is exactly what we log
        _LOG.warning(
            "sandbox-exec probe raised %r; kernel-level sandboxing is "
            "disabled — only the Python-level fallback layer will be applied",
            exc,
        )
        return False
    if proc.returncode != 0:
        _LOG.warning(
            "sandbox-exec probe failed (rc=%s stderr=%r); kernel-level "
            "sandboxing is disabled — only the Python-level fallback layer "
            "will be applied",
            proc.returncode,
            proc.stderr,
        )
        return False
    return True


SANDBOX_EXEC_AVAILABLE = _probe_sandbox_exec()


# --------------------------------------------------------------------------
# sandbox-exec profile
# --------------------------------------------------------------------------


def _sbpl_string(path: str) -> str:
    """Render `path` as an SBPL string literal (escaped for double quotes)."""
    escaped = path.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _build_sandbox_profile(workdir_realpath: str) -> str:
    """Deny-default sandbox-exec profile: network denied, writes confined.

    Reads are intentionally left broad (file-read*) — see DECLARED SCOPE.
    """
    workdir_lit = _sbpl_string(workdir_realpath)
    return textwrap.dedent(
        f"""\
        (version 1)
        (deny default)
        (allow process-fork)
        (allow process-exec)
        (allow file-read*)
        (allow file-write* (subpath {workdir_lit}))
        (allow file-write-data (literal "/dev/null"))
        (allow sysctl-read)
        (allow signal (target self))
        (deny network*)
        """
    )


# --------------------------------------------------------------------------
# Python-level network-block preamble (always applied)
# --------------------------------------------------------------------------

#: First thing the preamble writes to stderr, before any user code can run.
#: Its presence proves the interpreter actually started — which is what makes
#: `sandbox_error` unforgeable: candidate code printing "sandbox-exec: ..." to
#: stderr cannot remove an already-flushed marker, while a genuine sandbox-exec
#: launch failure means Python never ran and the marker is absent (verify-gate
#: finding on PR #11 pass 2). The parent strips the marker line from the
#: stderr it reports.
_INTERP_STARTED_MARKER = "__RLVR_INTERP_STARTED__"

# Patches connect-style entry points on the `socket` module rather than
# replacing `socket.socket` itself — replacing the class breaks `ssl`,
# which subclasses `socket.socket` at import time.
_NETWORK_BLOCK_PREAMBLE = textwrap.dedent(
    f"""\
    import sys as _rlvr_sys
    _rlvr_sys.stderr.write("{_INTERP_STARTED_MARKER}\\n")
    _rlvr_sys.stderr.flush()
    del _rlvr_sys
    """
) + textwrap.dedent(
    """\
    import socket as _rlvr_socket

    def _rlvr_network_blocked(*_args, **_kwargs):
        raise OSError("network access is disabled in this sandbox")

    _rlvr_socket.socket.connect = _rlvr_network_blocked
    _rlvr_socket.socket.connect_ex = _rlvr_network_blocked
    _rlvr_socket.create_connection = _rlvr_network_blocked
    _rlvr_socket.create_server = _rlvr_network_blocked
    del _rlvr_socket
    """
)

_USER_CODE_MARKER = "\n# --- user code below ---\n"
_SCRIPT_PREFIX = _NETWORK_BLOCK_PREAMBLE + _USER_CODE_MARKER

#: Number of lines the preamble adds before the user's own first line. A
#: traceback reporting the user's code at file-line N really means the
#: user's own source line N - PREAMBLE_LINE_OFFSET. Derived from the actual
#: prefix text (not hand-counted) so it can't silently drift if the preamble
#: is edited. Pinned by test_preamble_line_offset_matches_constant.
PREAMBLE_LINE_OFFSET = _SCRIPT_PREFIX.count("\n")


# --------------------------------------------------------------------------
# resource limits (fallback layer, always applied in addition)
# --------------------------------------------------------------------------
#
# All `resource` attribute lookups and arithmetic happen here, in the
# parent, well before any fork. `_preexec` (built by `_make_preexec_fn`)
# runs post-fork, pre-exec, in a parent that is guaranteed multithreaded
# after the first call (this module's own watchdog thread) — so it does
# nothing but call `resource.setrlimit` on values computed ahead of time.
# `resource` itself is imported at module load (top of file), not inside
# `_preexec`: a post-fork `import` can deadlock on CPython's import lock in
# a multithreaded parent, and referencing an already-imported module by name
# does not re-trigger the import machinery.


def _compute_rlimits(timeout_s: float, memory_mb: int) -> list[tuple[int, int]]:
    """Compute (resource_id, limit_value) pairs to apply in the child.

    Runs in the parent. Returns plain ints so `_preexec` only has to call
    `resource.setrlimit` — no attribute lookups, no arithmetic, post-fork.
    """
    limits: list[tuple[int, int]] = []

    cpu_limit = max(1, int(math.ceil(timeout_s)) + 1)
    limits.append((resource.RLIMIT_CPU, cpu_limit))

    mem_bytes = memory_mb * 1024 * 1024
    for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
        resource_id = getattr(resource, limit_name, None)
        if resource_id is not None:
            limits.append((resource_id, mem_bytes))

    return limits


def _make_preexec_fn(rlimits: list[tuple[int, int]]):
    """Build the preexec_fn that applies precomputed rlimits in the child.

    Runs in the forked child, before exec — must only use async-signal-safe
    operations. Contains nothing but `setrlimit` calls on values already
    computed in the parent.
    """

    def _preexec():
        # Process-group isolation is handled by Popen's start_new_session=True
        # (equivalent to calling os.setsid() before preexec_fn runs) — do not
        # call it again here, the child is already a session/group leader by
        # this point and a second os.setsid() raises EPERM.
        for resource_id, value in rlimits:
            try:
                resource.setrlimit(resource_id, (value, value))
            except (ValueError, OSError):
                # Best-effort — see DECLARED SCOPE re: RLIMIT_AS on macOS.
                pass

    return _preexec


# --------------------------------------------------------------------------
# process-group teardown
# --------------------------------------------------------------------------


def _kill_process_group(pid: int) -> None:
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


# --------------------------------------------------------------------------
# memory watchdog (userspace RSS polling)
# --------------------------------------------------------------------------
#
# Verified empirically on this machine (macOS/Darwin, arm64): setrlimit()
# raises ValueError("current limit exceeds maximum limit") for RLIMIT_AS,
# RLIMIT_DATA, *and* RLIMIT_RSS regardless of the value requested — the
# kernel does not support lowering these limits at all (RLIMIT_AS and
# RLIMIT_RSS even share the same numeric resource id on Darwin). The
# `_make_preexec_fn` calls above are therefore silently no-ops on this
# platform. Without a second mechanism, a memory bomb would simply succeed
# here, so a userspace watchdog thread polls the child's RSS via `ps` (no
# new dependency — it's a standard system utility, same tier as `/bin/sleep`
# used elsewhere in this module's tests) and SIGKILLs the process group if
# RSS exceeds `memory_mb`. This is still best-effort (poll interval, `ps`
# process itself has overhead, a very fast allocator could exceed the limit
# between polls) but it is a real, working enforcement path on macOS, unlike
# the rlimits above.


def _read_rss_kb(pid: int) -> int | None:
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=1,
        )
    except Exception:
        return None
    text = out.stdout.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _memory_watchdog(
    proc: "subprocess.Popen",
    memory_mb: int,
    stop_event: "threading.Event",
    hit_flag: list,
    stats: dict,
    poll_interval: float = 0.05,
) -> None:
    """Poll `proc`'s RSS and kill its process group if it exceeds the limit.

    Takes the Popen object (not a bare pid) so `proc.poll()` can be checked
    at the top of every iteration — this both stops polling promptly once
    the process has exited *and* means a stale/reused pid is never handed
    to `_read_rss_kb`/`_kill_process_group` after the process we actually
    care about has already gone away.

    `stats` is mutated in place with `attempts` (poll iterations where the
    process was confirmed alive) and `successes` (of those, how many got a
    parseable RSS reading) — used by the caller to compute
    `ExecResult.mem_watchdog_degraded`.
    """
    limit_kb = memory_mb * 1024
    while not stop_event.is_set():
        if proc.poll() is not None:
            return
        stats["attempts"] += 1
        rss_kb = _read_rss_kb(proc.pid)
        if rss_kb is not None:
            stats["successes"] += 1
            if rss_kb > limit_kb:
                hit_flag.append(True)
                _kill_process_group(proc.pid)
                return
        if stop_event.wait(poll_interval):
            return


# --------------------------------------------------------------------------
# capped, non-blocking-forever stdout/stderr capture
# --------------------------------------------------------------------------


class _CappedReader:
    """Reads a pipe on a background thread, retaining at most `cap` bytes.

    Two things this exists to fix at once:
    - `Popen.communicate()`'s internal buffering is unbounded — `while True:
      print(x)` in the sandboxed child can OOM the *parent* harness, not
      just the child. This reader stops retaining bytes past `cap` but
      keeps draining the pipe (must keep reading, not just stop — an unread
      full pipe would make the child block on write, changing timeout
      semantics from "wall-clock limit" to "wall-clock limit, unless it
      fills its stdout buffer first").
    - A process-group-escaping grandchild can hold the pipe's write end
      open after the process we care about has been killed and reaped,
      which makes a bare `communicate()` (or `.read()`) hang forever waiting
      for EOF that will never come. `join(timeout=...)` lets the caller
      detect and give up on that instead of hanging.
    """

    def __init__(self, stream, cap: int = _MAX_OUTPUT_BYTES):
        self._stream = stream
        self._cap = cap
        self._chunks: list[bytes] = []
        self._size = 0
        self.truncated = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            while True:
                chunk = self._stream.read(65536)
                if not chunk:
                    break
                if self._size >= self._cap:
                    self.truncated = True
                    continue
                remaining = self._cap - self._size
                if len(chunk) <= remaining:
                    self._chunks.append(chunk)
                    self._size += len(chunk)
                else:
                    self._chunks.append(chunk[:remaining])
                    self._size += remaining
                    self.truncated = True
        except Exception:
            # Reading a pipe out from under a process we just SIGKILLed can
            # raise (e.g. the fd is invalid by the time we get to it) — this
            # is expected on the kill path, not a bug to propagate.
            pass
        finally:
            try:
                self._stream.close()
            except Exception:
                pass

    def join(self, timeout: float | None = None) -> bool:
        """Wait for EOF. Returns True if the reader actually finished."""
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def text(self) -> str:
        # Decode once, at the end, over the exact captured byte count —
        # avoids splitting a multibyte character mid-stream the way
        # decoding chunk-by-chunk with a byte cap could.
        return b"".join(self._chunks).decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# outcome classification
# --------------------------------------------------------------------------


def _classify_outcome(
    *, returncode: int, stderr: str, watchdog_hit: bool
) -> tuple[bool, bool]:
    """Return (oom, cpu_limited) for a finished/killed process.

    Pulled out as a pure function (no subprocess/timing involved) so the
    classification rules can be pinned with fast, deterministic unit tests
    instead of relying on winning a real-world timing race against the
    wall-clock timeout / watchdog poll interval.

    oom: watchdog_hit is checked unconditionally — NOT gated on `not
    timed_out`. A swap-thrashing memory bomb can trip the watchdog AND
    still be caught by a wall-clock timeout racing to reap it (the
    watchdog's own kill can be slow to actually land under memory
    pressure); discarding a real watchdog hit just because the timeout
    *also* fired was the bug. A bare SIGKILL with no watchdog hit and no
    MemoryError text is deliberately NOT treated as oom evidence — it's
    ambiguous (could be our own wall-clock kill, could be the CPU rlimit's
    hard-kill after a SIGXCPU handler ignored the soft limit) and claiming
    it as oom would be a misattribution.

    cpu_limited: True iff the child died from -signal.SIGXCPU specifically
    — a distinct, identifiable outcome, not folded into oom or left as an
    unexplained crash. Classified on the observed signal alone; see the
    module docstring's CPU-runaway paragraph for the caveat that the exact
    delivering mechanism isn't conclusively isolated for heavily-parallel
    workloads.
    """
    cpu_limited = returncode == -signal.SIGXCPU
    mem_error_text = "MemoryError" in stderr or "Cannot allocate memory" in stderr
    oom = bool(watchdog_hit) or mem_error_text
    return oom, cpu_limited


def _detect_sandbox_error(
    *,
    kernel_sandbox_active: bool,
    returncode: int,
    stdout: str,
    stderr: str,
    interp_started: bool,
) -> bool:
    """True iff sandbox-exec itself failed to launch the interpreter.

    Distinct from the sandboxed *program* failing/exiting non-zero — that's
    ordinary `returncode != 0`, not this. Detected via the shape a malformed
    profile actually produces (verified empirically): kernel sandboxing was
    active, stdout is empty (the interpreter never got to run and print
    anything), and stderr's *first line* starts with the sandbox-exec tool's
    own diagnostic prefix. Requiring returncode != 0 too, and anchoring on
    the first line specifically (not `"sandbox-exec:" in stderr` anywhere),
    keeps this from false-triggering on user code that happens to print that
    substring somewhere in a traceback.
    """
    if interp_started:
        # The preamble's startup marker was seen: the interpreter ran, so any
        # "sandbox-exec:"-shaped stderr is candidate-authored, not a launch
        # failure (verify-gate finding, PR #11 pass 2 — unforgeable veto).
        return False
    if not kernel_sandbox_active:
        return False
    if returncode == 0:
        return False
    if stdout:
        return False
    first_line = stderr.splitlines()[0] if stderr else ""
    return first_line.startswith("sandbox-exec:")


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


def run_untrusted(
    code: str,
    *,
    timeout_s: float = 5.0,
    memory_mb: int = 512,
    workdir: Path | None = None,
    output_cap_bytes: int = _MAX_OUTPUT_BYTES,
) -> ExecResult:
    """Run `code` (untrusted Python source) in a sandboxed subprocess.

    See the module docstring's DECLARED SCOPE for exactly what is and is not
    enforced.

    Everything from process creation through cleanup runs under a single
    try/finally: on any exception path (script write fails, Popen fails,
    thread start fails, ...) the process group is killed, the process is
    reaped, its pipes are closed, and the workdir (if owned by this call) is
    removed — no live child or temp dir is left behind. On the ordinary
    success path the finally-block cleanup is a redundant no-op (the process
    is already dead and reaped by then), which is intentionally cheap and
    safe to repeat.
    """
    owns_workdir = workdir is None
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="rlvr-sandbox-"))
    else:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
    workdir_realpath = os.path.realpath(str(workdir))

    proc: subprocess.Popen | None = None
    watchdog: threading.Thread | None = None
    stdout_reader: "_CappedReader | None" = None
    stderr_reader: "_CappedReader | None" = None
    stop_watchdog = threading.Event()

    try:
        script_path = os.path.join(workdir_realpath, "_rlvr_untrusted.py")
        full_source = _SCRIPT_PREFIX + code
        with open(script_path, "w") as f:
            f.write(full_source)

        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": workdir_realpath,
            "TMPDIR": workdir_realpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            # Pinned so reference/candidate solutions that build sets/dicts
            # (whose iteration order depends on PYTHONHASHSEED when it
            # varies per-process) produce reproducible stdout across
            # separate run_untrusted() calls — see DECLARED SCOPE.
            "PYTHONHASHSEED": "0",
        }

        # -P: keeps the workdir/cwd off sys.path (PYTHONSAFEPATH, 3.11+) —
        # closes the shadow-module bypass (see DECLARED SCOPE). -s: no user
        # site-packages, closing the analogous bypass via a planted
        # ~/.local/.../site-packages under a reused workdir (HOME is set to
        # the workdir below). Deliberately NOT -I/-E: -E also ignores
        # PYTHONHASHSEED (verified empirically — -I silently defeats the
        # hash-seed pin below), and this module needs the env vars it sets
        # to actually take effect. -B/-X utf8 are still passed explicitly
        # rather than relied on via env, to keep behavior identical
        # regardless of what env vars are present.
        python_args = [sys.executable, "-P", "-s", "-B", "-X", "utf8", script_path]

        if SANDBOX_EXEC_AVAILABLE:
            profile = _build_sandbox_profile(workdir_realpath)
            cmd = ["sandbox-exec", "-p", profile, *python_args]
        else:
            cmd = python_args

        kernel_sandbox_active = SANDBOX_EXEC_AVAILABLE
        rlimits = _compute_rlimits(timeout_s, memory_mb)
        preexec_fn = _make_preexec_fn(rlimits)

        start = time.monotonic()
        proc = subprocess.Popen(
            cmd,
            cwd=workdir_realpath,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=preexec_fn,
        )

        # Cap is caller-tunable: protocol drivers with legitimately large
        # outputs (e.g. HumanEval/14's 903 growing-list records, >1 MiB of
        # honest output) raise it; the default stays small so `while True:
        # print(x)` can't OOM the parent (calibration finding, 2026-08-14).
        stdout_reader = _CappedReader(proc.stdout, cap=output_cap_bytes)
        stderr_reader = _CappedReader(proc.stderr, cap=output_cap_bytes)
        stdout_reader.start()
        stderr_reader.start()

        watchdog_hit: list = []
        watchdog_stats = {"attempts": 0, "successes": 0}
        watchdog = threading.Thread(
            target=_memory_watchdog,
            args=(proc, memory_mb, stop_watchdog, watchdog_hit, watchdog_stats),
            daemon=True,
        )
        watchdog.start()

        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(proc.pid)
            try:
                proc.wait(timeout=_REAP_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=_REAP_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    # Third timeout in a row: the process itself won't
                    # reap even after a second SIGKILL (e.g. stuck in an
                    # uninterruptible kernel wait). Report faithfully
                    # instead of hanging — do not attempt a fourth wait.
                    _LOG.warning(
                        "process pid=%s did not reap after repeated "
                        "SIGKILL; giving up waiting on it",
                        proc.pid,
                    )

        returncode = proc.returncode if proc.returncode is not None else -signal.SIGKILL
        duration_s = time.monotonic() - start

        stop_watchdog.set()
        watchdog.join(timeout=_WATCHDOG_JOIN_TIMEOUT_S)
        if watchdog.is_alive():
            _LOG.warning(
                "memory watchdog thread for pid=%s did not exit within "
                "%.1fs of being signaled to stop",
                proc.pid,
                _WATCHDOG_JOIN_TIMEOUT_S,
            )

        out_ok = stdout_reader.join(timeout=_DRAIN_TIMEOUT_S)
        err_ok = stderr_reader.join(timeout=_DRAIN_TIMEOUT_S)
        if not (out_ok and err_ok):
            _LOG.warning(
                "stdout/stderr reader thread(s) for pid=%s did not reach "
                "EOF within %.1fs of process exit — a process-group-"
                "escaping grandchild may still hold the pipe open; "
                "reporting captured output as truncated rather than hanging",
                proc.pid,
                _DRAIN_TIMEOUT_S,
            )
            # Best-effort second sweep in case a straggler grandchild
            # appeared after the first kill.
            _kill_process_group(proc.pid)

        stdout = stdout_reader.text()
        stderr = stderr_reader.text()
        marker_line = _INTERP_STARTED_MARKER + "\n"
        interp_started = False
        if stderr.startswith(marker_line):
            interp_started = True
            stderr = stderr[len(marker_line) :]
        elif _INTERP_STARTED_MARKER in stderr:
            # Marker present but not at the very start (interleaved writes on
            # an unusual buffering path) — still proves startup; leave the
            # text untouched rather than risk mangling user output.
            interp_started = True
        output_truncated = (
            stdout_reader.truncated or stderr_reader.truncated or not out_ok or not err_ok
        )

        mem_watchdog_degraded = (
            watchdog_stats["attempts"] > 0 and watchdog_stats["successes"] == 0
        )

        oom, cpu_limited = _classify_outcome(
            returncode=returncode, stderr=stderr, watchdog_hit=bool(watchdog_hit)
        )
        sandbox_error = _detect_sandbox_error(
            kernel_sandbox_active=kernel_sandbox_active,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            interp_started=interp_started,
        )

        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            timed_out=timed_out,
            oom=oom,
            duration_s=duration_s,
            kernel_sandbox_active=kernel_sandbox_active,
            sandbox_error=sandbox_error,
            output_truncated=output_truncated,
            cpu_limited=cpu_limited,
            mem_watchdog_degraded=mem_watchdog_degraded,
        )
    finally:
        stop_watchdog.set()
        if watchdog is not None and watchdog.is_alive():
            watchdog.join(timeout=_WATCHDOG_JOIN_TIMEOUT_S)
        if proc is not None:
            _kill_process_group(proc.pid)
            try:
                proc.wait(timeout=_REAP_TIMEOUT_S)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=_REAP_TIMEOUT_S)
                except Exception:
                    pass
            for reader, stream in (
                (stdout_reader, proc.stdout),
                (stderr_reader, proc.stderr),
            ):
                if stream is None:
                    continue
                if reader is not None and reader.is_alive():
                    # A background reader thread may still be blocked
                    # inside stream.read() (e.g. a process-group-escaping
                    # grandchild still holding the pipe's write end open).
                    # CPython's io.BufferedReader serializes read/close via
                    # an internal lock, so calling close() here would BLOCK
                    # this thread until that read() call returns — this is
                    # the exact "communicate() hangs forever" failure mode
                    # this module is supposed to avoid, just relocated to a
                    # cleanup path instead of the main read path. Leave it
                    # for the (daemon) reader thread to close its own
                    # stream when it eventually unblocks; it never blocks
                    # process exit or a future run_untrusted call.
                    continue
                try:
                    stream.close()
                except Exception:
                    pass
        if owns_workdir:
            shutil.rmtree(workdir_realpath, ignore_errors=True)
