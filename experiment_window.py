"""
experiment_window.py
--------------------
Fullscreen Tkinter stimulus display engine for the P300 oddball experiment.

Per-trial sequence
------------------
  1. Fixation cross         (fixation_duration_ms)
  2. Stimulus               (stimulus_duration_ms)  → LSL marker sent at onset
  3. Response window        (response_window_ms)     → spacebar captured here
  4. Jittered ITI           (iti_min_ms … iti_max_ms)

Keyboard
--------
  Spacebar  : participant response (logged during response window only)
  Escape    : abort with confirmation dialog

After each block a quality-gate pause is shown.
At session end a summary screen is displayed.
"""

import random
import time
import tkinter as tk
from tkinter import messagebox
from typing import Any, Dict, List, Optional

from trial_generator import Trial, STANDARD, TARGET
from lsl_markers import LSLMarkerStream, MARKER_RESPONSE
from session_logger import SessionLogger, make_trial_record, make_event_record
from utils import get_timestamp_str


# ─────────────────────────────────────────────
# Layout constants
# ─────────────────────────────────────────────

BG_COLOR         = "#000000"   # background
FIX_COLOR        = "#ffffff"   # fixation cross
STANDARD_COLOR   = "#1565c0"   # blue circle
TARGET_COLOR     = "#c62828"   # red circle
CIRCLE_BG_COLOR  = "#2a2a2a"   # gray backing circle
TEXT_COLOR       = "#ffffff"
DIM_COLOR        = "#666666"

CIRCLE_RADIUS    = 120         # px
FIX_SIZE         = 30          # half-length of fixation cross arms
LINE_WIDTH       = 4


# ─────────────────────────────────────────────
# ExperimentWindow
# ─────────────────────────────────────────────

class ExperimentWindow:
    """
    Runs practice + main experiment blocks in a fullscreen Tkinter window.

    Usage (called by main.py)
    -------------------------
        win = ExperimentWindow(config, blocks, practice_trials, logger, lsl)
        win.run()                  # blocks until done or aborted
        results = win.results      # dict with accuracy, duration, etc.
    """

    def __init__(
        self,
        config:          Dict[str, Any],
        blocks:          List[List[Trial]],
        practice_trials: List[Trial],
        logger:          SessionLogger,
        lsl:             LSLMarkerStream,
    ):
        self._config          = config
        self._blocks          = blocks
        self._practice_trials = practice_trials
        self._logger          = logger
        self._lsl             = lsl

        # Timing (converted to seconds)
        self._stim_dur   = config["stimulus_duration_ms"]  / 1000
        self._fix_dur    = config["fixation_duration_ms"]  / 1000
        self._resp_win   = config["response_window_ms"]    / 1000
        self._iti_min    = config["iti_min_ms"]            / 1000
        self._iti_max    = config["iti_max_ms"]            / 1000

        # State
        self._aborted         = False
        self._response_flag   = False   # set by spacebar handler
        self._response_time   = 0.0
        self._r_key_pressed   = False   # set by R key handler
        self._perf_origin     = time.perf_counter()

        # Results
        self.results: Dict[str, Any] = {}

        # Tkinter
        self._root:   Optional[tk.Tk]     = None
        self._canvas: Optional[tk.Canvas] = None

    # ── public ───────────────────────────────

    def run(self) -> None:
        """Create window, run all phases, destroy window."""
        self._build_window()
        self._root.after(200, self._run_phases)
        self._root.mainloop()

    # ── window setup ─────────────────────────

    def _build_window(self) -> None:
        self._root = tk.Tk()
        self._root.title("P300 Experiment")
        self._root.configure(bg=BG_COLOR)
        self._root.attributes("-fullscreen", True)
        self._root.protocol("WM_DELETE_WINDOW", lambda: None)  # disable close btn

        self._canvas = tk.Canvas(
            self._root,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True)

        # Keyboard bindings
        self._root.bind("<space>",  self._on_spacebar)
        self._root.bind("<Escape>", self._on_escape)
        self._root.bind("<r>",      self._on_r_key)
        self._root.bind("<R>",      self._on_r_key)

        self._root.update()
        self._W = self._root.winfo_width()
        self._H = self._root.winfo_height()
        self._cx = self._W // 2
        self._cy = self._H // 2

    # ── phase controller ─────────────────────

    def _run_phases(self) -> None:
        """Sequentially run practice → main blocks → summary."""
        # Send session-start marker
        t = self._lsl.send_session_start()
        self._logger.log_event(make_event_record(
            "99", None, None, t, get_timestamp_str(),
        ))

        # ── Practice ─────────────────────────
        self._show_instructions(phase="practice")
        if self._aborted:
            self._finish()
            return

        practice_stats = self._run_block(
            self._practice_trials, block_label="PRACTICE"
        )
        if self._aborted:
            self._finish()
            return

        self._logger.log_practice_summary(
            n_trials  = practice_stats["n_trials"],
            n_hits    = practice_stats["n_hits"],
            n_misses  = practice_stats["n_misses"],
            accuracy  = practice_stats["accuracy"],
        )
        self._show_practice_gate(practice_stats)
        if self._aborted:
            self._finish()
            return

        # ── Re-practice loop ─────────────────
        while self._show_repractice_choice():
            if self._aborted:
                self._finish()
                return
            
            practice_stats = self._run_block(
                self._practice_trials, block_label="PRACTICE (REPEAT)"
            )
            if self._aborted:
                self._finish()
                return

            self._logger.log_practice_summary(
                n_trials  = practice_stats["n_trials"],
                n_hits    = practice_stats["n_hits"],
                n_misses  = practice_stats["n_misses"],
                accuracy  = practice_stats["accuracy"],
            )
            self._show_practice_gate(practice_stats)
            if self._aborted:
                self._finish()
                return

        # ── Main experiment ───────────────────
        self._show_instructions(phase="main")
        if self._aborted:
            self._finish()
            return

        all_stats = []
        session_start_perf = time.perf_counter()

        for block_idx, block in enumerate(self._blocks):
            block_stats = self._run_block(
                block, block_label=f"BLOCK {block_idx + 1}/{len(self._blocks)}"
            )
            all_stats.append(block_stats)

            if self._aborted:
                self._finish()
                return

            # Between-block quality gate (skip after last block)
            if block_idx < len(self._blocks) - 1:
                self._show_block_gate(block_idx + 1, block_stats)
                if self._aborted:
                    self._finish()
                    return

        session_duration = time.perf_counter() - session_start_perf

        # ── Session end ───────────────────────
        t = self._lsl.send_session_end()
        self._logger.log_event(make_event_record(
            "00", None, None, t, get_timestamp_str(),
        ))

        total_trials = sum(s["n_trials"] for s in all_stats)
        total_hits   = sum(s["n_hits"]   for s in all_stats)
        accuracy     = total_hits / total_trials if total_trials else 0

        self.results = {
            "total_trials":  total_trials,
            "total_hits":    total_hits,
            "accuracy":      round(accuracy, 4),
            "duration_sec":  round(session_duration, 2),
            "aborted":       False,
        }

        self._show_summary(self.results)
        self._finish()

    # ── block runner ─────────────────────────

    def _run_block(
        self,
        trials: List[Trial],
        block_label: str,
    ) -> Dict[str, Any]:
        """
        Run all trials in *trials*.
        Returns block statistics dict.
        """
        n_hits = 0
        n_misses = 0

        for trial in trials:
            if self._aborted:
                break

            # 1. Fixation cross
            self._show_fixation()
            self._precise_wait(self._fix_dur)

            # 2. Stimulus + LSL marker
            onset_perf = self._show_stimulus(trial)
            marker_sent = onset_perf > 0

            # 3. Response window
            resp, rt_ms = self._collect_response(self._resp_win)

            # 4. Blank / ITI
            self._show_blank()
            iti = random.uniform(self._iti_min, self._iti_max)
            self._precise_wait(iti)

            # 5. Correctness
            is_correct = resp and (trial.stimulus_type == TARGET)
            if trial.stimulus_type == TARGET:
                if resp:
                    n_hits += 1
                else:
                    n_misses += 1

            # 6. Log trial
            self._logger.log_trial(make_trial_record(
                trial_id           = trial.trial_id,
                block_id           = trial.block_id,
                stimulus_type      = trial.stimulus_type,
                stimulus_onset_sec = onset_perf - self._perf_origin,
                response_received  = resp,
                reaction_time_ms   = rt_ms,
                is_correct         = is_correct,
                is_practice        = trial.is_practice,
                lsl_marker_sent    = marker_sent,
                wall_time_iso      = get_timestamp_str(),
            ))

        n_trials = len(trials)
        accuracy = n_hits / max(1, (n_hits + n_misses))

        print(
            f"[experiment] {block_label} done — "
            f"{n_trials} trials | hits {n_hits} | misses {n_misses} | "
            f"acc {accuracy:.1%}"
        )

        return {
            "n_trials": n_trials,
            "n_hits":   n_hits,
            "n_misses": n_misses,
            "accuracy": round(accuracy, 4),
        }

    # ── stimulus display ─────────────────────

    def _show_fixation(self) -> None:
        """Draw white fixation cross on black background."""
        c = self._canvas
        c.delete("all")
        c.configure(bg=BG_COLOR)
        cx, cy = self._cx, self._cy
        s = FIX_SIZE
        c.create_line(cx - s, cy, cx + s, cy,
                      fill=FIX_COLOR, width=LINE_WIDTH)
        c.create_line(cx, cy - s, cx, cy + s,
                      fill=FIX_COLOR, width=LINE_WIDTH)
        c.update()

    def _show_stimulus(self, trial: Trial) -> float:
        """
        Draw stimulus circle, send LSL marker.
        Returns perf_counter() at onset, 0.0 on error.
        """
        c = self._canvas
        c.delete("all")
        c.configure(bg=BG_COLOR)
        cx, cy = self._cx, self._cy
        r = CIRCLE_RADIUS

        # Gray backing circle
        c.create_oval(
            cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10,
            fill=CIRCLE_BG_COLOR, outline="",
        )

        # Blue or red stimulus circle
        color = TARGET_COLOR if trial.stimulus_type == TARGET else STANDARD_COLOR
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      fill=color, outline="")

        # Fixation cross stays visible on top of stimulus
        s = FIX_SIZE
        c.create_line(cx - s, cy, cx + s, cy,
                      fill=FIX_COLOR, width=LINE_WIDTH)
        c.create_line(cx, cy - s, cx, cy + s,
                      fill=FIX_COLOR, width=LINE_WIDTH)

        c.update()   # force immediate render

        # ── LSL marker at frame flip ──────────
        onset_perf = time.perf_counter()
        t = self._lsl.send_marker(str(trial.lsl_code), trial.trial_id)

        self._logger.log_event(make_event_record(
            event_code     = str(trial.lsl_code),
            trial_id       = trial.trial_id,
            stimulus_type  = trial.stimulus_type,
            perf_timestamp = onset_perf,
            wall_time_iso  = get_timestamp_str(),
        ))

        self._precise_wait(self._stim_dur)
        return onset_perf

    def _show_blank(self) -> None:
        """Clear canvas to black (inter-trial interval display)."""
        self._canvas.delete("all")
        self._canvas.configure(bg=BG_COLOR)
        self._canvas.update()

    # ── response collection ──────────────────

    def _collect_response(self, window_sec: float):
        """
        Poll for spacebar press during *window_sec*.

        Returns:
            (response_received: bool, reaction_time_ms: float | None)
        """
        self._response_flag = False
        self._response_time = 0.0
        self._response_onset = time.perf_counter()

        deadline = self._response_onset + window_sec
        while time.perf_counter() < deadline:
            self._root.update()
            if self._response_flag:
                rt_ms = (self._response_time - self._response_onset) * 1000
                return True, round(rt_ms, 2)
            time.sleep(0.001)

        return False, None

    # ── keyboard handlers ────────────────────

    def _on_spacebar(self, event=None) -> None:
        if not self._response_flag:
            self._response_flag = True
            self._response_time = time.perf_counter()
            # Send LSL response marker
            t = self._lsl.send_response()
            self._logger.log_event(make_event_record(
                MARKER_RESPONSE, None, None, t, get_timestamp_str(),
            ))

    def _on_escape(self, event=None) -> None:
        confirmed = messagebox.askyesno(
            "Abort Experiment",
            "Are you sure you want to abort the experiment?\n"
            "Partial data will be saved.",
            parent=self._root,
        )
        if confirmed:
            self._aborted = True
            self.results  = {"aborted": True}

    def _on_r_key(self, event=None) -> None:
        """Handler for R key (repeat practice)."""
        self._r_key_pressed = True

    # ── instruction screens ──────────────────

    def _show_instructions(self, phase: str) -> None:
        """Block until spacebar pressed or Escape aborts."""
        c = self._canvas
        c.delete("all")
        c.configure(bg=BG_COLOR)

        if phase == "practice":
            lines = [
                "PRACTICE BLOCK",
                "",
                "You will see circles appear on screen.",
                "",
                "● Blue circle  →  Standard  (ignore)",
                "● Red  circle  →  Target    (press SPACE)",
                "",
                "Try to stay still and keep your eyes",
                "on the fixation cross (+) at all times.",
                "",
                "Press  SPACE  to begin practice.",
            ]
        else:
            lines = [
                "MAIN EXPERIMENT",
                "",
                "Same rules as practice.",
                "",
                "● Blue circle  →  Standard  (ignore)",
                "● Red  circle  →  Target    (press SPACE)",
                "",
                "Stay still. Keep eyes on the cross.",
                "",
                "Press  SPACE  to begin.",
            ]

        self._draw_text_screen(lines)
        self._wait_for_space()

    def _show_practice_gate(self, stats: Dict[str, Any]) -> None:
        acc_pct = stats["accuracy"] * 100
        lines = [
            "PRACTICE COMPLETE",
            "",
            f"Targets detected: {stats['n_hits']} / "
            f"{stats['n_hits'] + stats['n_misses']}",
            f"Accuracy: {acc_pct:.0f}%",
            "",
            "Operator: check participant is ready.",
            "",
            "Press  SPACE  to start main experiment.",
            "Press  Escape to abort.",
        ]
        self._draw_text_screen(lines)
        self._wait_for_space()

    def _show_repractice_choice(self) -> bool:
        """
        Show choice screen for repeating practice.
        
        Returns:
            True if R pressed (repeat practice), False if SPACE pressed (continue).
        """
        lines = [
            "PRACTICE OPTIONS",
            "",
            "Press  R  to repeat practice",
            "",
            "Press  SPACE  to start main experiment",
        ]
        self._draw_text_screen(lines)
        self._wait_for_repractice_choice()
        
        if self._r_key_pressed:
            self._r_key_pressed = False
            return True
        return False

    def _show_block_gate(self, block_num: int, stats: Dict[str, Any]) -> None:
        acc_pct = stats["accuracy"] * 100
        lines = [
            f"END OF BLOCK {block_num}",
            "",
            f"Targets detected: {stats['n_hits']} / "
            f"{stats['n_hits'] + stats['n_misses']}",
            f"Accuracy: {acc_pct:.0f}%",
            "",
            "Operator checklist:",
            "  ✓ EEG signal quality",
            "  ✓ Electrode impedance",
            "  ✓ Participant comfort",
            "",
            "Press  SPACE  to continue.",
            "Press  Escape to abort.",
        ]
        self._draw_text_screen(lines)
        self._wait_for_space()

    def _show_summary(self, results: Dict[str, Any]) -> None:
        acc_pct  = results["accuracy"] * 100
        mins     = int(results["duration_sec"] // 60)
        secs     = int(results["duration_sec"] %  60)
        lines = [
            "SESSION COMPLETE",
            "",
            f"Total trials : {results['total_trials']}",
            f"Target hits  : {results['total_hits']}",
            f"Accuracy     : {acc_pct:.1f}%",
            f"Duration     : {mins}m {secs}s",
            "",
            "Data saved successfully.",
            "",
            "Press  SPACE  to exit.",
        ]
        self._draw_text_screen(lines)
        self._wait_for_space()

    # ── drawing helpers ──────────────────────

    def _draw_text_screen(self, lines: List[str]) -> None:
        c = self._canvas
        c.delete("all")
        c.configure(bg=BG_COLOR)

        y = self._cy - (len(lines) * 22) // 2
        for i, line in enumerate(lines):
            if i == 0:
                font = ("Courier New", 22, "bold")
                color = "#e94560"
            elif line.startswith("●"):
                font = ("Courier New", 14)
                color = "#4fc3f7" if "Blue" in line else "#ef9a9a"
            elif line.startswith("  ✓"):
                font = ("Courier New", 13)
                color = "#81c784"
            elif line.startswith("Press"):
                font = ("Courier New", 14, "bold")
                color = "#fff176"
            else:
                font = ("Courier New", 14)
                color = TEXT_COLOR

            c.create_text(
                self._cx, y,
                text=line, font=font, fill=color,
                anchor="center",
            )
            y += 36

        c.update()

    # ── wait helpers ─────────────────────────

    def _wait_for_space(self) -> None:
        """Block until spacebar pressed or experiment aborted."""
        self._response_flag = False
        while not self._response_flag and not self._aborted:
            self._root.update()
            time.sleep(0.01)
        self._response_flag = False

    def _wait_for_repractice_choice(self) -> None:
        """Block until R or SPACE pressed (for repractice choice screen)."""
        self._response_flag = False
        self._r_key_pressed = False
        while not self._response_flag and not self._r_key_pressed and not self._aborted:
            self._root.update()
            time.sleep(0.01)
        self._response_flag = False

    def _precise_wait(self, duration_sec: float) -> None:
        """
        High-resolution busy-wait using perf_counter.
        Calls root.update() every ms to keep Tkinter responsive.
        """
        end = time.perf_counter() + duration_sec
        while time.perf_counter() < end:
            self._root.update()
            remaining = end - time.perf_counter()
            if remaining > 0.002:
                time.sleep(0.001)

    # ── finish ───────────────────────────────

    def _finish(self) -> None:
        if self._aborted:
            self.results = {"aborted": True, "total_trials": 0,
                            "accuracy": 0, "duration_sec": 0}
        try:
            self._root.destroy()
        except Exception:
            pass