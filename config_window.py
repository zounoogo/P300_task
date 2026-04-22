"""
config_window.py
----------------
Tkinter configuration window.

The operator fills in participant info and experiment parameters,
then clicks "Start Experiment". All values are validated before
the window closes and returns a config dict to main.py.

Returns
-------
    dict  — full config on success
    None  — if the operator closes / cancels the window
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any


# ─────────────────────────────────────────────
# Parameter definitions  (label, key, default, min, max, type)
# ─────────────────────────────────────────────

_PARAM_DEFS = [
    # (label_text,                   key,                          default, lo,    hi,    cast)
    ("Total trials",                 "total_trials",               600,     100,   2000,  int),
    ("Number of blocks",             "n_blocks",                   6,       2,     20,    int),
    ("Target probability (0-1)",     "target_probability",         0.20,    0.05,  0.50,  float),
    ("Max consecutive standards",    "max_consecutive_standards",  5,       1,     10,    int),
    ("Practice trials",              "practice_trials",            30,      10,    100,   int),
    ("Stimulus duration (ms)",       "stimulus_duration_ms",       120,     50,    500,   int),
    ("Fixation duration (ms)",       "fixation_duration_ms",       500,     100,   1000,  int),
    ("ITI minimum (ms)",             "iti_min_ms",                 900,     500,   2000,  int),
    ("ITI maximum (ms)",             "iti_max_ms",                 1200,    500,   2000,  int),
    ("Response window (ms)",         "response_window_ms",         900,     200,   2000,  int),
]

# Preset profiles  {name: {key: value, ...}}
_PRESETS = {
    "Research (default)": {
        "total_trials": 600, "n_blocks": 6, "target_probability": 0.20,
        "max_consecutive_standards": 5, "practice_trials": 30,
        "stimulus_duration_ms": 120, "fixation_duration_ms": 500,
        "iti_min_ms": 900, "iti_max_ms": 1200, "response_window_ms": 900,
    },
    "Quick setup (100 trials)": {
        "total_trials": 100, "n_blocks": 2, "target_probability": 0.20,
        "max_consecutive_standards": 5, "practice_trials": 10,
        "stimulus_duration_ms": 120, "fixation_duration_ms": 500,
        "iti_min_ms": 900, "iti_max_ms": 1200, "response_window_ms": 900,
    },
    "Custom": {},   # user fills everything manually
}


# ─────────────────────────────────────────────
# ConfigWindow
# ─────────────────────────────────────────────

class ConfigWindow:
    """
    Modal Tkinter window that collects experiment configuration.

    Call run() which blocks until the window is closed.
    Retrieve the result via the .result property.
    """

    # ── colours & fonts ──────────────────────
    BG          = "#1a1a2e"
    PANEL_BG    = "#16213e"
    ACCENT      = "#0f3460"
    HIGHLIGHT   = "#e94560"
    TEXT        = "#eaeaea"
    TEXT_DIM    = "#8a8a9a"
    ENTRY_BG    = "#0d1b2a"
    ENTRY_FG    = "#ffffff"
    BTN_BG      = "#e94560"
    BTN_FG      = "#ffffff"
    BTN_HOVER   = "#c73652"
    FONT_TITLE  = ("Courier New", 18, "bold")
    FONT_SUB    = ("Courier New", 10)
    FONT_LABEL  = ("Courier New", 10)
    FONT_ENTRY  = ("Courier New", 11)
    FONT_BTN    = ("Courier New", 12, "bold")

    def __init__(self):
        self.result: Optional[Dict[str, Any]] = None
        self._entries: Dict[str, tk.StringVar] = {}
        self._root: Optional[tk.Tk] = None
        self._record_response_var: Optional[tk.BooleanVar] = None

    # ── public API ───────────────────────────

    def run(self) -> Optional[Dict[str, Any]]:
        """
        Display the window and block until closed.

        Returns:
            Config dict on success, None if cancelled.
        """
        self._root = tk.Tk()
        self._root.title("P300 Experiment — Configuration")
        self._root.configure(bg=self.BG)
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._build_ui()
        self._center_window()

        self._root.mainloop()
        return self.result

    # ── UI construction ──────────────────────

    def _build_ui(self) -> None:
        root = self._root

        # ── title bar ────────────────────────
        title_frame = tk.Frame(root, bg=self.HIGHLIGHT, pady=6)
        title_frame.pack(fill="x")
        tk.Label(
            title_frame, text="▐ P300 EXPERIMENT SETUP ▌",
            font=self.FONT_TITLE, bg=self.HIGHLIGHT, fg=self.BTN_FG,
        ).pack()
        tk.Label(
            title_frame,
            text="Institut National des Postes et Télécommunication de Rabat",
            font=self.FONT_SUB, bg=self.HIGHLIGHT, fg="#f0c0c8",
        ).pack()

        # ── main content ─────────────────────
        content = tk.Frame(root, bg=self.BG, padx=24, pady=16)
        content.pack(fill="both", expand=True)

        # ── preset selector ──────────────────
        preset_frame = tk.Frame(content, bg=self.BG)
        preset_frame.pack(fill="x", pady=(0, 12))

        tk.Label(
            preset_frame, text="PRESET",
            font=self.FONT_LABEL, bg=self.BG, fg=self.TEXT_DIM,
        ).pack(side="left", padx=(0, 8))

        self._preset_var = tk.StringVar(value="Research (default)")
        preset_menu = ttk.Combobox(
            preset_frame,
            textvariable=self._preset_var,
            values=list(_PRESETS.keys()),
            state="readonly",
            width=26,
            font=self.FONT_ENTRY,
        )
        preset_menu.pack(side="left")
        preset_menu.bind("<<ComboboxSelected>>", self._apply_preset)

        # ── two-column grid ──────────────────
        grid = tk.Frame(content, bg=self.BG)
        grid.pack(fill="x")

        # Column headers
        tk.Label(
            grid, text="PARTICIPANT INFO",
            font=("Courier New", 9, "bold"), bg=self.BG, fg=self.HIGHLIGHT,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        tk.Label(
            grid, text="EXPERIMENT PARAMETERS",
            font=("Courier New", 9, "bold"), bg=self.BG, fg=self.HIGHLIGHT,
        ).grid(row=0, column=3, columnspan=2, sticky="w", pady=(0, 4))

        # ── participant ID ────────────────────
        self._pid_var = tk.StringVar()
        self._add_text_row(grid, row=1, label="Participant ID",
                           var=self._pid_var, col=0)

        # ── operator name ─────────────────────
        self._op_var = tk.StringVar()
        self._add_text_row(grid, row=2, label="Operator name",
                           var=self._op_var, col=0)

        # vertical separator
        sep = tk.Frame(grid, bg=self.ACCENT, width=2)
        sep.grid(row=1, column=2, rowspan=len(_PARAM_DEFS) + 1,
                 padx=16, sticky="ns")

        # ── numeric parameter rows ────────────
        for idx, (label, key, default, lo, hi, cast) in enumerate(_PARAM_DEFS):
            var = tk.StringVar(value=str(default))
            self._entries[key] = var
            self._add_numeric_row(
                grid, row=idx + 1, label=label,
                var=var, lo=lo, hi=hi, col=3,
            )

        # ── LSL status indicator ──────────────
        self._lsl_label = tk.Label(
            content, text="● LSL: checking...",
            font=self.FONT_SUB, bg=self.BG, fg=self.TEXT_DIM,
        )
        self._lsl_label.pack(anchor="w", pady=(12, 0))
        self._root.after(300, self._check_lsl)

        # ── record responses option ───────────
        self._record_response_var = tk.BooleanVar(value=True)
        response_check = tk.Checkbutton(
            content, text="Record participant responses (spacebar)",
            variable=self._record_response_var,
            font=self.FONT_SUB, bg=self.BG, fg=self.TEXT,
            selectcolor=self.ENTRY_BG, activebackground=self.BG,
            relief="flat",
        )
        response_check.pack(anchor="w", pady=(8, 0))

        # ── buttons ───────────────────────────
        btn_frame = tk.Frame(content, bg=self.BG)
        btn_frame.pack(fill="x", pady=(16, 0))

        cancel_btn = tk.Button(
            btn_frame, text="CANCEL",
            font=self.FONT_BTN, bg=self.ACCENT, fg=self.TEXT,
            relief="flat", padx=20, pady=8,
            cursor="hand2", command=self._on_cancel,
        )
        cancel_btn.pack(side="left", padx=(0, 8))
        self._bind_hover(cancel_btn, self.ACCENT, "#1e3a5f")

        start_btn = tk.Button(
            btn_frame, text="▶  START EXPERIMENT",
            font=self.FONT_BTN, bg=self.BTN_BG, fg=self.BTN_FG,
            relief="flat", padx=20, pady=8,
            cursor="hand2", command=self._on_start,
        )
        start_btn.pack(side="right")
        self._bind_hover(start_btn, self.BTN_BG, self.BTN_HOVER)

    # ── row builders ─────────────────────────

    def _add_text_row(
        self, parent, row: int, label: str,
        var: tk.StringVar, col: int,
    ) -> None:
        tk.Label(
            parent, text=label, anchor="w",
            font=self.FONT_LABEL, bg=self.BG, fg=self.TEXT,
            width=22,
        ).grid(row=row, column=col, sticky="w", pady=3)

        entry = tk.Entry(
            parent, textvariable=var,
            font=self.FONT_ENTRY, bg=self.ENTRY_BG, fg=self.ENTRY_FG,
            insertbackground=self.HIGHLIGHT, relief="flat",
            width=18, bd=4,
        )
        entry.grid(row=row, column=col + 1, sticky="w", pady=3, padx=(4, 0))

    def _add_numeric_row(
        self, parent, row: int, label: str,
        var: tk.StringVar, lo, hi, col: int,
    ) -> None:
        tk.Label(
            parent, text=label, anchor="w",
            font=self.FONT_LABEL, bg=self.BG, fg=self.TEXT,
            width=28,
        ).grid(row=row, column=col, sticky="w", pady=3)

        tk.Label(
            parent,
            text=f"[{lo}–{hi}]",
            font=("Courier New", 8), bg=self.BG, fg=self.TEXT_DIM,
        ).grid(row=row, column=col + 1, sticky="w")

        entry = tk.Entry(
            parent, textvariable=var,
            font=self.FONT_ENTRY, bg=self.ENTRY_BG, fg=self.ENTRY_FG,
            insertbackground=self.HIGHLIGHT, relief="flat",
            width=8, bd=4,
        )
        entry.grid(row=row, column=col + 1, sticky="e", pady=3)

    # ── preset logic ─────────────────────────

    def _apply_preset(self, event=None) -> None:
        name = self._preset_var.get()
        values = _PRESETS.get(name, {})
        for key, var in self._entries.items():
            if key in values:
                var.set(str(values[key]))

    # ── LSL check ────────────────────────────

    def _check_lsl(self) -> None:
        try:
            import pylsl  # noqa: F401
            self._lsl_label.config(
                text="● LSL: pylsl found — LabRecorder integration active",
                fg="#4caf50",
            )
        except ImportError:
            self._lsl_label.config(
                text="● LSL: pylsl NOT found — experiment will run without markers",
                fg="#ff9800",
            )

    # ── validation ───────────────────────────

    def _validate(self) -> Optional[Dict[str, Any]]:
        errors = []

        # Participant ID
        pid = self._pid_var.get().strip()
        if not pid:
            errors.append("Participant ID is required.")

        # Operator name
        op = self._op_var.get().strip()
        if not op:
            errors.append("Operator name is required.")

        # Numeric parameters
        parsed: Dict[str, Any] = {}
        for label, key, default, lo, hi, cast in _PARAM_DEFS:
            raw = self._entries[key].get().strip()
            try:
                val = cast(raw)
                if not (lo <= val <= hi):
                    errors.append(f"{label}: must be between {lo} and {hi}.")
                else:
                    parsed[key] = val
            except ValueError:
                errors.append(f"{label}: '{raw}' is not a valid {cast.__name__}.")

        # Cross-field: ITI min < ITI max
        if "iti_min_ms" in parsed and "iti_max_ms" in parsed:
            if parsed["iti_min_ms"] >= parsed["iti_max_ms"]:
                errors.append("ITI minimum must be less than ITI maximum.")

        if errors:
            messagebox.showerror(
                "Configuration Error",
                "\n".join(f"• {e}" for e in errors),
            )
            return None

        parsed["participant_id"] = pid
        parsed["operator_name"]  = op
        parsed["record_responses"] = self._record_response_var.get()
        return parsed

    # ── button callbacks ─────────────────────

    def _on_start(self) -> None:
        config = self._validate()
        if config is None:
            return
        self.result = config
        self._root.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self._root.destroy()

    # ── helpers ──────────────────────────────

    def _center_window(self) -> None:
        self._root.update_idletasks()
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self._root.geometry(f"+{x}+{y}")

    @staticmethod
    def _bind_hover(widget, normal_bg: str, hover_bg: str) -> None:
        widget.bind("<Enter>", lambda e: widget.config(bg=hover_bg))
        widget.bind("<Leave>", lambda e: widget.config(bg=normal_bg))


# ─────────────────────────────────────────────
# Quick self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    win = ConfigWindow()
    cfg = win.run()
    if cfg:
        print("\n[config_window] Config collected:")
        for k, v in cfg.items():
            print(f"  {k:<32} = {v}")
    else:
        print("[config_window] Cancelled.")