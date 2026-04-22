# P300 Experiment Application

Visual oddball P300 experiment with LSL marker streaming to LabRecorder.

---

## Project structure

```
p300_app/
├── main.py                # Entry point
├── config_window.py       # Setup GUI
├── experiment_window.py   # Stimulus display engine
├── trial_generator.py     # Randomization logic
├── lsl_markers.py         # LSL outlet → LabRecorder
├── session_logger.py      # trials.csv / events.json / metadata.json
├── utils.py               # Paths, timestamps, helpers
└── requirements.txt
```

---

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

---

## LSL / LabRecorder workflow

1. Start **OpenBCI GUI** → enable LSL EEG stream
2. Start **LabRecorder** → it will detect both streams:
   - Your EEG stream (from OpenBCI)
   - `P300Markers` (from this app)
3. Press **Start** in LabRecorder
4. Run `python main.py` and complete the experiment
5. Stop LabRecorder → `.xdf` file contains EEG + markers time-aligned

---

## Marker codes

| Code | Event |
|------|-------|
| 11   | Standard stimulus onset |
| 22   | Target stimulus onset |
| 33   | Participant response |
| 99   | Session start |
| 00   | Session end |

---

## Output files

All saved to `~/P300_data/sub-<ID>_ses-<TIMESTAMP>/`

| File | Content |
|------|---------|
| `trials.csv` | One row per trial — onset, RT, accuracy |
| `events.json` | Chronological LSL event log |
| `metadata.json` | Full config snapshot + session summary |

---

## Default parameters

| Parameter | Default |
|-----------|---------|
| Total trials | 600 |
| Blocks | 6 × 100 trials |
| Target probability | 20% |
| Stimulus duration | 120 ms |
| Fixation duration | 500 ms |
| ITI | 900–1200 ms jittered |
| Practice trials | 30 |