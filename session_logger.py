"""
session_logger.py
-----------------
Handles all data persistence for one experiment session.

Output files
------------
  trials.csv    — one row per trial, appended trial-by-trial (crash-safe)
  events.json   — chronological LSL event log, appended event-by-event
  metadata.json — full session summary, written once at session end

All files live inside the session directory built by utils.build_session_dir().
"""

import csv
import json
import os
import time
from typing import Any, Dict, List, Optional

from utils import session_file, get_timestamp_str


# ─────────────────────────────────────────────
# CSV column order  (must match TrialRecord)
# ─────────────────────────────────────────────

TRIAL_CSV_FIELDS = [
    "trial_id",
    "block_id",
    "stimulus_type",
    "stimulus_onset_sec",
    "response_received",
    "reaction_time_ms",
    "is_correct",
    "is_practice",
    "lsl_marker_sent",
    "wall_time_iso",
]


# ─────────────────────────────────────────────
# Data classes (plain dicts for simplicity)
# ─────────────────────────────────────────────

def make_trial_record(
    trial_id: int,
    block_id: int,
    stimulus_type: str,
    stimulus_onset_sec: float,
    response_received: bool        = False,
    reaction_time_ms: Optional[float] = None,
    is_correct: bool               = False,
    is_practice: bool              = False,
    lsl_marker_sent: bool          = False,
    wall_time_iso: str             = "",
) -> Dict[str, Any]:
    """Return a flat dict representing one completed trial."""
    return {
        "trial_id":           trial_id,
        "block_id":           block_id,
        "stimulus_type":      stimulus_type,
        "stimulus_onset_sec": round(stimulus_onset_sec, 6),
        "response_received":  response_received,
        "reaction_time_ms":   round(reaction_time_ms, 2) if reaction_time_ms is not None else "",
        "is_correct":         is_correct,
        "is_practice":        is_practice,
        "lsl_marker_sent":    lsl_marker_sent,
        "wall_time_iso":      wall_time_iso,
    }


def make_event_record(
    event_code: str,
    trial_id: Optional[int],
    stimulus_type: Optional[str],
    perf_timestamp: float,
    wall_time_iso: str = "",
) -> Dict[str, Any]:
    """Return a flat dict representing one LSL event."""
    return {
        "event_code":     event_code,
        "trial_id":       trial_id,
        "stimulus_type":  stimulus_type,
        "perf_timestamp": round(perf_timestamp, 6),
        "wall_time_iso":  wall_time_iso,
    }


# ─────────────────────────────────────────────
# SessionLogger
# ─────────────────────────────────────────────

class SessionLogger:
    """
    Manages writing of trials.csv, events.json, and metadata.json
    for a single experiment session.

    Usage
    -----
        logger = SessionLogger(session_dir, config)
        logger.open()

        # after each trial:
        logger.log_trial(make_trial_record(...))

        # after each LSL marker:
        logger.log_event(make_event_record(...))

        # at session end:
        logger.close(summary)
    """

    def __init__(self, session_dir: str, config: Dict[str, Any]):
        """
        Args:
            session_dir : path from utils.build_session_dir()
            config      : full configuration dict from ConfigWindow
        """
        self._session_dir = session_dir
        self._config      = config

        self._trials_path   = session_file(session_dir, "trials.csv")
        self._events_path   = session_file(session_dir, "events.json")
        self._metadata_path = session_file(session_dir, "metadata.json")

        self._csv_writer:  Optional[csv.DictWriter] = None
        self._csv_file:    Optional[Any]             = None
        self._events:      List[Dict[str, Any]]      = []

        self._session_start_iso = ""
        self._open = False

    # ── lifecycle ────────────────────────────

    def open(self) -> None:
        """
        Create output files and write CSV header.
        Must be called before any log_* method.
        """
        self._session_start_iso = get_timestamp_str()

        # --- trials.csv ---
        self._csv_file = open(self._trials_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(
            self._csv_file,
            fieldnames=TRIAL_CSV_FIELDS,
        )
        self._csv_writer.writeheader()
        self._csv_file.flush()

        # --- events.json (start with empty list) ---
        with open(self._events_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        self._open = True
        print(f"[session_logger] Session opened → {self._session_dir}")

    def close(
        self,
        summary: Optional[Dict[str, Any]] = None,
        aborted: bool = False,
        operator_notes: str = "",
    ) -> None:
        """
        Flush and close CSV, finalize events.json, write metadata.json.

        Args:
            summary        : dict with keys like total_trials, accuracy, duration_sec
            aborted        : True if operator pressed Escape
            operator_notes : free-text notes from the post-session dialog
        """
        if not self._open:
            return

        # Close CSV
        if self._csv_file:
            self._csv_file.flush()
            self._csv_file.close()
            self._csv_file   = None
            self._csv_writer = None

        # Finalize events.json
        self._flush_events()

        # Write metadata.json
        metadata = self._build_metadata(
            summary        = summary or {},
            aborted        = aborted,
            operator_notes = operator_notes,
        )
        with open(self._metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        self._open = False
        print(f"[session_logger] Session closed. Files saved to {self._session_dir}")

    # ── per-trial logging ────────────────────

    def log_trial(self, record: Dict[str, Any]) -> None:
        """
        Append one trial row to trials.csv immediately.
        Safe to call even after a partial crash — data already on disk.
        """
        if not self._open or self._csv_writer is None:
            return

        self._csv_writer.writerow(record)
        self._csv_file.flush()          # flush after every row — crash safety

    # ── per-event logging ────────────────────

    def log_event(self, record: Dict[str, Any]) -> None:
        """
        Buffer one LSL event. Flushed to events.json periodically and at close.
        """
        if not self._open:
            return

        self._events.append(record)

        # Flush every 10 events for crash safety
        if len(self._events) % 10 == 0:
            self._flush_events()

    # ── practice outcomes ────────────────────

    def log_practice_summary(
        self,
        n_trials: int,
        n_hits: int,
        n_misses: int,
        accuracy: float,
    ) -> None:
        """Store practice block outcomes in the config dict for metadata."""
        self._config["practice_outcomes"] = {
            "n_trials":  n_trials,
            "n_hits":    n_hits,
            "n_misses":  n_misses,
            "accuracy":  round(accuracy, 4),
        }

    # ── internal helpers ─────────────────────

    def _flush_events(self) -> None:
        """Overwrite events.json with the current in-memory list."""
        try:
            with open(self._events_path, "w", encoding="utf-8") as f:
                json.dump(self._events, f, indent=2)
        except Exception as exc:
            print(f"[session_logger] WARNING: could not flush events — {exc}")

    def _build_metadata(
        self,
        summary: Dict[str, Any],
        aborted: bool,
        operator_notes: str,
    ) -> Dict[str, Any]:
        return {
            "session": {
                "participant_id":  self._config.get("participant_id", ""),
                "operator_name":   self._config.get("operator_name", ""),
                "session_start":   self._session_start_iso,
                "session_end":     get_timestamp_str(),
                "aborted":         aborted,
                "operator_notes":  operator_notes,
            },
            "equipment": {
                "device":      "OpenBCI Cyton",
                "sample_rate": 250,
                "reference":   "Cz",
                "montage":     "10-20",
            },
            "config_snapshot": self._config,
            "practice_outcomes": self._config.get("practice_outcomes", {}),
            "session_summary": summary,
            "output_files": {
                "trials_csv":   os.path.basename(self._trials_path),
                "events_json":  os.path.basename(self._events_path),
                "metadata_json": os.path.basename(self._metadata_path),
            },
        }

    # ── properties ───────────────────────────

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def session_dir(self) -> str:
        return self._session_dir

    @property
    def trials_path(self) -> str:
        return self._trials_path

    @property
    def events_path(self) -> str:
        return self._events_path

    @property
    def metadata_path(self) -> str:
        return self._metadata_path

    def __repr__(self) -> str:
        status = "OPEN" if self._open else "CLOSED"
        return f"<SessionLogger [{status}] dir={self._session_dir}>"


# ─────────────────────────────────────────────
# Quick self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from utils import build_session_dir

    config = {
        "participant_id":           "TEST01",
        "operator_name":            "Operator",
        "total_trials":             600,
        "n_blocks":                 6,
        "target_probability":       0.20,
        "stimulus_duration_ms":     120,
        "fixation_duration_ms":     500,
        "iti_min_ms":               900,
        "iti_max_ms":               1200,
        "max_consecutive_standards": 5,
        "practice_trials":          30,
    }

    sdir   = build_session_dir("TEST01")
    logger = SessionLogger(sdir, config)
    logger.open()

    # Simulate 3 trials
    for i in range(1, 4):
        stim = "target" if i == 2 else "standard"
        logger.log_trial(make_trial_record(
            trial_id           = i,
            block_id           = 1,
            stimulus_type      = stim,
            stimulus_onset_sec = time.perf_counter(),
            response_received  = (i == 2),
            reaction_time_ms   = 342.5 if i == 2 else None,
            is_correct         = (i == 2),
            is_practice        = False,
            lsl_marker_sent    = True,
            wall_time_iso      = get_timestamp_str(),
        ))
        logger.log_event(make_event_record(
            event_code     = "22" if stim == "target" else "11",
            trial_id       = i,
            stimulus_type  = stim,
            perf_timestamp = time.perf_counter(),
            wall_time_iso  = get_timestamp_str(),
        ))

    logger.log_practice_summary(30, 25, 5, 0.833)

    logger.close(
        summary = {"total_trials": 3, "accuracy": 0.90, "duration_sec": 12.5},
        aborted = False,
        operator_notes = "Self-test run.",
    )

    print(f"\n[self-test] Files written to: {sdir}")
    print(f"  trials  : {logger.trials_path}")
    print(f"  events  : {logger.events_path}")
    print(f"  metadata: {logger.metadata_path}")