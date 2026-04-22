"""
main.py
-------
Entry point for the P300 Experiment Application.

Flow
----
  1. Show ConfigWindow      → collect parameters
  2. Build session directory → utils.build_session_dir()
  3. Generate trials         → trial_generator
  4. Open SessionLogger      → session_logger
  5. Open LSL outlet         → lsl_markers
  6. Run ExperimentWindow    → experiment_window (in background thread)
  7. Close logger            → write metadata.json
  8. Print session summary   → console

Run
---
    python main.py
"""

import sys
import threading
import traceback

from utils            import build_session_dir, get_timestamp_str
from config_window    import ConfigWindow
from trial_generator  import generate_trials, generate_practice_trials
from session_logger   import SessionLogger
from lsl_markers      import LSLMarkerStream
from experiment_window import ExperimentWindow


# ─────────────────────────────────────────────
# Main controller
# ─────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("  P300 Experiment Application")
    print("  Institut National des Postes et Télécommunication")
    print("=" * 60)

    # ── 1. Configuration window ───────────────
    print("\n[main] Opening configuration window...")
    config_win = ConfigWindow()
    config     = config_win.run()

    if config is None:
        print("[main] Configuration cancelled. Exiting.")
        sys.exit(0)

    print(f"[main] Configuration received for participant: "
          f"{config['participant_id']}")
    _print_config(config)

    # ── 2. Session directory ──────────────────
    session_dir = build_session_dir(config["participant_id"])
    print(f"[main] Session directory: {session_dir}")

    # ── 3. Trial generation ───────────────────
    print("\n[main] Generating trial sequences...")

    practice_trials = generate_practice_trials(
        n_trials                  = config["practice_trials"],
        target_probability        = config["target_probability"],
        max_consecutive_standards = config["max_consecutive_standards"],
    )

    blocks = generate_trials(
        total_trials              = config["total_trials"],
        n_blocks                  = config["n_blocks"],
        target_probability        = config["target_probability"],
        max_consecutive_standards = config["max_consecutive_standards"],
    )

    total_generated = sum(len(b) for b in blocks)
    print(f"[main] Generated {len(blocks)} blocks / "
          f"{total_generated} main trials / "
          f"{len(practice_trials)} practice trials.")

    # ── 4. Session logger ─────────────────────
    logger = SessionLogger(session_dir, config)
    logger.open()

    # ── 5. LSL outlet ─────────────────────────
    lsl = LSLMarkerStream()
    lsl_ok = lsl.open()

    if lsl_ok:
        print("[main] LSL outlet active — LabRecorder can now detect "
              "'P300Markers' stream.")
        print("[main] Waiting 2 s for LabRecorder to register the stream...")
        import time; time.sleep(2)
    else:
        print("[main] WARNING: LSL not available. "
              "Experiment will run without EEG markers.")

    # ── 6. Experiment window (background thread) ──
    print("\n[main] Launching experiment window...")

    try:
        exp = ExperimentWindow(
            config          = config,
            blocks          = blocks,
            practice_trials = practice_trials,
            logger          = logger,
            lsl             = lsl,
        )
        # Run experiment in a separate thread so terminal stays free
        thread = threading.Thread(target=exp.run, daemon=False)
        thread.start()
        thread.join()  # wait for experiment to finish
        results = exp.results

    except Exception as exc:
        print(f"\n[main] UNEXPECTED ERROR during experiment:\n")
        traceback.print_exc()
        results = {
            "aborted":      True,
            "total_trials": 0,
            "accuracy":     0,
            "duration_sec": 0,
            "error":        str(exc),
        }

    # ── 7. Close logger ───────────────────────
    aborted        = results.get("aborted", False)
    operator_notes = "Aborted by operator." if aborted else ""

    logger.close(
        summary        = results,
        aborted        = aborted,
        operator_notes = operator_notes,
    )

    # ── 8. Close LSL ──────────────────────────
    lsl.close()

    # ── 9. Final summary ──────────────────────
    print("\n" + "=" * 60)
    if aborted:
        print("  SESSION ABORTED")
    else:
        print("  SESSION COMPLETE")
    print("=" * 60)
    print(f"  Participant  : {config['participant_id']}")
    print(f"  Operator     : {config['operator_name']}")
    print(f"  Session dir  : {session_dir}")

    if not aborted:
        acc_pct = results.get("accuracy", 0) * 100
        mins    = int(results.get("duration_sec", 0) // 60)
        secs    = int(results.get("duration_sec", 0) %  60)
        print(f"  Total trials : {results.get('total_trials', 0)}")
        print(f"  Accuracy     : {acc_pct:.1f}%")
        print(f"  Duration     : {mins}m {secs}s")

    print(f"\n  Output files:")
    print(f"    {logger.trials_path}")
    print(f"    {logger.events_path}")
    print(f"    {logger.metadata_path}")
    print("=" * 60 + "\n")


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def _print_config(config: dict) -> None:
    print("\n[main] Parameters:")
    skip = {"participant_id", "operator_name"}
    for k, v in config.items():
        if k not in skip:
            print(f"  {k:<32} = {v}")
    print()


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    main()