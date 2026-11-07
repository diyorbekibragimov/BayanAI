"""Bayan AI · output retention: every per-consultation file lives in one temp folder and is deleted automatically.

Root: $BAYAN_OUTPUT_ROOT, default <tempfile.gettempdir()>/bayan_outputs. One sub-folder per consultation
(<root>/<consult.id>/). Nothing is ever written to the repo, /data or the Hub. purge() deletes one consultation's
folder (e.g. after "Approve & send" + download, or on session end); sweep() deletes folders older than max_age_s;
start_sweeper() runs sweep() hourly in a daemon thread.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

DEFAULT_MAX_AGE_S = 86400.0
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_sweeper: threading.Thread | None = None
_sweeper_lock = threading.Lock()


def root() -> Path:
    """The output root (created if missing), resolved to an absolute path."""
    r = Path(os.environ.get("BAYAN_OUTPUT_ROOT") or Path(tempfile.gettempdir()) / "bayan_outputs").resolve()
    r.mkdir(parents=True, exist_ok=True)
    return r


def _child(name: str) -> Path:
    if not _SAFE_ID.match(name or ""):
        raise ValueError(f"unsafe consultation id: {name!r}")
    r = root()
    p = (r / name).resolve()
    if p.parent != r:
        raise ValueError(f"refusing path outside the output root: {p}")
    return p


def consult_dir(consult) -> Path:
    """<root>/<consult.id>/, created on demand."""
    p = _child(str(consult.id))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _rmtree_child(p: Path, r: Path) -> bool:
    p = p.resolve()
    if p == r or p.parent != r or not p.is_dir() or p.is_symlink():
        return False
    shutil.rmtree(p, ignore_errors=True)
    return not p.exists()


def purge(consult) -> None:
    """Delete this consultation's output folder and drop the wrap-up keys from consult.outputs (other modules'
    keys stay). Safe if already gone."""
    try:
        p = _child(str(consult.id))
    except ValueError:
        p = None
    if p is not None and p.exists():
        _rmtree_child(p, root())
    try:
        from bayan.brain.wrapup import OUTPUT_KEYS
    except Exception:  # noqa: BLE001
        OUTPUT_KEYS = tuple(consult.outputs.keys())

    def _clear():
        for k in OUTPUT_KEYS:
            consult.outputs.pop(k, None)

    lock = getattr(consult, "lock", None)
    if lock is not None:
        with lock:
            _clear()
    else:
        _clear()


def sweep(max_age_s: float = DEFAULT_MAX_AGE_S) -> int:
    """Delete consultation folders (direct children of the root) whose mtime is older than max_age_s.
    Never deletes the root itself, files, symlinks, or anything outside the root. Returns the number deleted."""
    r = root()
    cutoff = time.time() - float(max_age_s)
    n = 0
    for child in r.iterdir():
        try:
            if child.is_symlink() or not child.is_dir():
                continue
            if child.stat().st_mtime < cutoff and _rmtree_child(child, r):
                n += 1
        except OSError:
            continue
    return n


def start_sweeper(interval_s: float = 3600.0, max_age_s: float = DEFAULT_MAX_AGE_S) -> threading.Thread:
    """Start (once per process) a daemon thread that calls sweep(max_age_s) now and then every interval_s."""
    global _sweeper
    with _sweeper_lock:
        if _sweeper is not None and _sweeper.is_alive():
            return _sweeper

        def loop():
            while True:
                try:
                    sweep(max_age_s)
                except Exception:  # noqa: BLE001 - the sweeper must never die
                    pass
                time.sleep(interval_s)

        _sweeper = threading.Thread(target=loop, name="bayan-output-sweeper", daemon=True)
        _sweeper.start()
        return _sweeper
