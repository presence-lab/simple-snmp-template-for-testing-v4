"""Cover .codex/hooks/_run.py, the cross-platform Codex hook launcher.

Why these tests exist: the original bug behind the Backport-1 commit was
silent. Codex hooks were invoked with bare `python`, which doesn't exist
on macOS, so every hook exited rc=127 and `.ai-traces/` froze. Nothing
caught it because there were no tests on the launcher side -- the
existing test_codex_hooks.py exercises the hook scripts themselves
(session_start.py, stop.py, ...) but not the dispatcher in front of
them. If `_run.py`'s venv detection regresses, we need to find out
before another silent freeze.

We invoke `_run.py` as a subprocess (the realistic path) and verify:

1. With no argument: returns rc=0 silently. Codex sometimes triggers
   hooks before the workspace is ready; the launcher must no-op rather
   than fail.

2. With a hook name that doesn't have a script: rc=0 silently. Same
   reason -- a partially-installed `.codex/hooks/` shouldn't break the
   Codex session.

3. With a hook script that exists: the script runs (we observe it via
   a marker file the hook writes).

4. Venv detection: `_running_in_venv()` returns True under a venv,
   False outside one. (Unit-tested on the live module; the re-exec
   branch can't be exercised without spinning up a real venv.)
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = PROJECT_ROOT / ".codex" / "hooks" / "_run.py"


def _make_fake_hooks_dir(root, hook_name, body):
    """Build a tmp .codex/hooks/ dir containing _run.py and one hook
    script. The launcher's PROJECT_ROOT walks up two levels from itself,
    so we must place _run.py at <root>/.codex/hooks/_run.py for the venv
    detection to look for <root>/venv (which won't exist in tmp), so the
    launcher falls through and dispatches the hook directly."""
    hooks_dir = root / ".codex" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "_run.py").write_text(LAUNCHER.read_text())
    (hooks_dir / f"{hook_name}.py").write_text(body)
    return hooks_dir


def test_no_args_returns_zero(tmp_path):
    hooks_dir = _make_fake_hooks_dir(tmp_path, "any", "import sys; sys.exit(99)\n")
    result = subprocess.run(
        [sys.executable, str(hooks_dir / "_run.py")],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        "no-arg invocation should be a silent no-op, not propagate "
        "the inner script's exit code"
    )


def test_unknown_hook_returns_zero(tmp_path):
    hooks_dir = _make_fake_hooks_dir(tmp_path, "session_start", "raise RuntimeError('do not run me')\n")
    result = subprocess.run(
        [sys.executable, str(hooks_dir / "_run.py"), "nonexistent_hook"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "do not run me" not in result.stderr, (
        "unknown hook name should not dispatch any hook, including "
        "lookalikes by accident"
    )


def test_present_hook_dispatches(tmp_path):
    marker = tmp_path / "marker.txt"
    body = (
        "from pathlib import Path\n"
        f"Path(r'{marker}').write_text('ran')\n"
    )
    hooks_dir = _make_fake_hooks_dir(tmp_path, "session_start", body)
    result = subprocess.run(
        [sys.executable, str(hooks_dir / "_run.py"), "session_start"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert marker.exists(), (
        "the launcher should runpy the requested hook script -- the hook "
        "wrote a marker file we should now see on disk"
    )
    assert marker.read_text() == "ran"


def test_running_in_venv_detection_is_correct():
    """_running_in_venv() reads sys.prefix vs sys.base_prefix. We can't
    test the False branch without leaving the venv, but we can confirm
    the True branch in our own pytest process (which IS in the venv)."""
    spec = importlib.util.spec_from_file_location("codex_run_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # If the test suite is being run from the project venv (which the
    # runner enforces), this should be True. assert_in_venv elsewhere
    # in the codebase guarantees the precondition.
    assert module._running_in_venv() is True, (
        "the test suite is supposed to run from venv/bin/python; if this "
        "fails we're running outside the venv and many other things will "
        "be broken too"
    )


def test_venv_python_resolves_to_existing_file(tmp_path, monkeypatch):
    """_venv_python() looks for venv/bin/python (POSIX) or
    venv\\Scripts\\python.exe (Windows) under the project root. When
    that file exists, it returns the Path; when it doesn't, None."""
    spec = importlib.util.spec_from_file_location("codex_run_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Point the launcher's PROJECT_ROOT at our tmp tree.
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)

    # No venv yet -> returns None.
    assert module._venv_python() is None

    # Create the expected interpreter path for the current OS.
    if os.name == "nt":
        target = tmp_path / "venv" / "Scripts" / "python.exe"
    else:
        target = tmp_path / "venv" / "bin" / "python"
    target.parent.mkdir(parents=True)
    target.write_text("")  # presence is what matters; content doesn't

    assert module._venv_python() == target
