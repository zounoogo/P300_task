"""
lsl_markers.py
--------------
LSL outlet for real-time marker streaming to LabRecorder.

Stream spec
-----------
  Name            : P300Markers
  Type            : Markers
  Channel count   : 1
  Nominal rate    : 0  (irregular / event-driven)
  Channel format  : string
  Source ID       : p300_experiment

LabRecorder will auto-detect this stream alongside the EEG stream
and record both into a single time-aligned .xdf file.

Marker codes
------------
  "11"  standard stimulus onset  (blue circle)
  "22"  target stimulus onset    (red circle)
  "33"  participant response      (spacebar press)
  "99"  session start
  "00"  session end
"""

import time
from typing import Optional

# pylsl is imported inside the class so the app can run without it
# (graceful degradation).
try:
    from pylsl import StreamInfo, StreamOutlet
    _LSL_AVAILABLE = True
except ImportError:
    _LSL_AVAILABLE = False


# ─────────────────────────────────────────────
# Marker code constants
# ─────────────────────────────────────────────

MARKER_STANDARD        = "11"   # standard stimulus onset
MARKER_TARGET          = "22"   # target stimulus onset
MARKER_RESPONSE        = "33"   # participant spacebar press
MARKER_SESSION_START   = "99"   # experiment begins
MARKER_SESSION_END     = "00"   # experiment ends


# ─────────────────────────────────────────────
# LSLMarkerStream
# ─────────────────────────────────────────────

class LSLMarkerStream:
    """
    Wraps a pylsl StreamOutlet.

    Usage
    -----
        stream = LSLMarkerStream()
        stream.open()
        stream.send_marker(MARKER_TARGET, trial_id=5)
        stream.close()

    If pylsl is not installed the object silently becomes a no-op,
    allowing the experiment to run without EEG hardware.
    """

    STREAM_NAME      = "P300Markers"
    STREAM_TYPE      = "Markers"
    CHANNEL_COUNT    = 1
    NOMINAL_RATE     = 0          # irregular stream
    CHANNEL_FORMAT   = "string"
    SOURCE_ID        = "p300_experiment"

    def __init__(self):
        self._outlet: Optional[object] = None
        self._available: bool = _LSL_AVAILABLE
        self._open: bool = False

    # ── lifecycle ────────────────────────────

    def open(self) -> bool:
        """
        Create and advertise the LSL outlet.

        Returns True if the outlet was created successfully,
        False if pylsl is unavailable or creation failed.
        """
        if not self._available:
            print(
                "[lsl_markers] pylsl not installed — "
                "running WITHOUT marker streaming."
            )
            return False

        try:
            info = StreamInfo(
                name           = self.STREAM_NAME,
                type           = self.STREAM_TYPE,
                channel_count  = self.CHANNEL_COUNT,
                nominal_srate  = self.NOMINAL_RATE,
                channel_format = self.CHANNEL_FORMAT,
                source_id      = self.SOURCE_ID,
            )

            # Add channel metadata (visible in LabRecorder / MoBILAB)
            channels = info.desc().append_child("channels")
            ch = channels.append_child("channel")
            ch.append_child_value("label",  "EventMarker")
            ch.append_child_value("type",   "Markers")
            ch.append_child_value("unit",   "code")

            self._outlet = StreamOutlet(info)
            self._open   = True

            print(
                f"[lsl_markers] Outlet '{self.STREAM_NAME}' created. "
                "LabRecorder should now detect this stream."
            )
            return True

        except Exception as exc:
            print(f"[lsl_markers] ERROR creating outlet: {exc}")
            self._available = False
            return False

    def close(self) -> None:
        """Destroy the LSL outlet and release resources."""
        if self._outlet is not None:
            # pylsl outlets are garbage-collected; explicit del is enough
            del self._outlet
            self._outlet = None
        self._open = False
        print("[lsl_markers] Outlet closed.")

    # ── marker sending ───────────────────────

    def send_marker(
        self,
        code: str,
        trial_id: Optional[int] = None,
    ) -> float:
        """
        Push one marker sample to LabRecorder.

        Args:
            code     : one of the MARKER_* constants defined above
            trial_id : optional trial number for console logging

        Returns:
            time.perf_counter() value at the moment the sample was pushed,
            or 0.0 if LSL is unavailable.
        """
        t = time.perf_counter()

        if self._outlet is not None and self._open:
            self._outlet.push_sample([code])
            label = _code_label(code)
            print(
                f"[lsl_markers] Marker {code} ({label}) "
                f"sent at {t:.6f} s"
                + (f"  [trial {trial_id}]" if trial_id is not None else "")
            )
        else:
            # Silently skip — experiment continues without markers
            pass

        return t

    # ── convenience wrappers ─────────────────

    def send_standard(self, trial_id: Optional[int] = None) -> float:
        """Send marker 11 — standard stimulus onset."""
        return self.send_marker(MARKER_STANDARD, trial_id)

    def send_target(self, trial_id: Optional[int] = None) -> float:
        """Send marker 22 — target stimulus onset."""
        return self.send_marker(MARKER_TARGET, trial_id)

    def send_response(self, trial_id: Optional[int] = None) -> float:
        """Send marker 33 — participant spacebar response."""
        return self.send_marker(MARKER_RESPONSE, trial_id)

    def send_session_start(self) -> float:
        """Send marker 99 — experiment session begins."""
        return self.send_marker(MARKER_SESSION_START)

    def send_session_end(self) -> float:
        """Send marker 00 — experiment session ends."""
        return self.send_marker(MARKER_SESSION_END)

    # ── state ────────────────────────────────

    @property
    def is_open(self) -> bool:
        """True if the outlet is active and ready to stream."""
        return self._open

    @property
    def lsl_available(self) -> bool:
        """True if pylsl is installed and outlet creation succeeded."""
        return self._available and self._open

    def __repr__(self) -> str:
        status = "OPEN" if self._open else "CLOSED"
        avail  = "pylsl OK" if self._available else "pylsl MISSING"
        return f"<LSLMarkerStream [{status}] [{avail}]>"


# ─────────────────────────────────────────────
# Internal helper
# ─────────────────────────────────────────────

def _code_label(code: str) -> str:
    return {
        MARKER_STANDARD:      "standard onset",
        MARKER_TARGET:        "target onset",
        MARKER_RESPONSE:      "response",
        MARKER_SESSION_START: "session start",
        MARKER_SESSION_END:   "session end",
    }.get(code, "unknown")


# ─────────────────────────────────────────────
# Quick self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    stream = LSLMarkerStream()
    ok = stream.open()

    if ok:
        print("Waiting 2 s so LabRecorder can detect the stream...")
        time.sleep(2)

        stream.send_session_start()
        time.sleep(0.5)
        stream.send_standard(trial_id=1)
        time.sleep(0.5)
        stream.send_target(trial_id=2)
        time.sleep(0.5)
        stream.send_response(trial_id=2)
        time.sleep(0.5)
        stream.send_session_end()

        stream.close()
    else:
        print("LSL not available — no markers were sent.")