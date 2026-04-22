"""
utils.py
--------
Helper functions: paths, timestamps, and directory management.
"""

import os
import time
from datetime import datetime


# ─────────────────────────────────────────────
# Timestamp helpers
# ─────────────────────────────────────────────

def get_timestamp_str() -> str:
    """Return current datetime as a compact string: YYYYMMDD_HHMMSS."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_precise_time() -> float:
    """
    Return a high-resolution monotonic timestamp in seconds.
    Uses time.perf_counter() for ±1 ms accuracy.
    """
    return time.perf_counter()


def perf_to_wall(perf_t: float, perf_origin: float, wall_origin: float) -> float:
    """
    Convert a perf_counter timestamp to a wall-clock (epoch) timestamp.

    Args:
        perf_t      : the perf_counter value to convert
        perf_origin : perf_counter value recorded at session start
        wall_origin : time.time() value recorded at the same moment

    Returns:
        Estimated Unix epoch time (float, seconds).
    """
    return wall_origin + (perf_t - perf_origin)


# ─────────────────────────────────────────────
# Path / directory helpers
# ─────────────────────────────────────────────

def get_data_root() -> str:
    """
    Return the root data directory (~~/P300_data).
    Creates it if it does not exist.
    """
    root = os.path.join(os.path.expanduser("~"), "P300_data")
    os.makedirs(root, exist_ok=True)
    return root


def build_session_dir(participant_id: str) -> str:
    """
    Build and create the session directory.

    Pattern: ~/P300_data/sub-<ID>_ses-<YYYYMMDD_HHMMSS>/

    Args:
        participant_id: alphanumeric participant label (e.g. "P01")

    Returns:
        Absolute path to the newly created session directory.
    """
    folder_name = f"sub-{participant_id}_ses-{get_timestamp_str()}"
    session_dir = os.path.join(get_data_root(), folder_name)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


def session_file(session_dir: str, filename: str) -> str:
    """
    Return the full path for a file inside the session directory.

    Args:
        session_dir : path returned by build_session_dir()
        filename    : e.g. 'trials.csv', 'metadata.json', 'events.json'

    Returns:
        Full absolute file path (file is NOT created here).
    """
    return os.path.join(session_dir, filename)


# ─────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────

def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to the closed interval [lo, hi]."""
    return max(lo, min(hi, value))


def sanitize_participant_id(raw: str) -> str:
    """
    Strip whitespace and replace spaces with underscores.
    Raises ValueError if the result is empty.
    """
    cleaned = raw.strip().replace(" ", "_")
    if not cleaned:
        raise ValueError("Participant ID must not be empty.")
    return cleaned


# ─────────────────────────────────────────────
# Quick self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    pid = sanitize_participant_id("  P 01  ")
    sdir = build_session_dir(pid)
    print(f"[utils] Session directory created: {sdir}")
    print(f"[utils] Trials CSV path          : {session_file(sdir, 'trials.csv')}")
    print(f"[utils] Current perf time        : {get_precise_time():.6f} s")
    print(f"[utils] Timestamp string         : {get_timestamp_str()}")