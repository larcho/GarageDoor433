"""
Signal Recorder - Capture and Replay OOK signals

Capture strategy (see the deep-dive that motivated this design):
- An IRQ on DIO2 records BOTH a timestamp AND the pin level at every edge, into
  pre-allocated arrays (ISR-safe: no heap allocation in the handler). Reading the
  real level makes HIGH/LOW polarity deterministic instead of guessing it from
  timing parity.
- The raw edges are turned into (high_us, low_us) pulse pairs, split into frames
  at the long inter-code sync gap.
- A remote sends the SAME code frame ~20+ times per press, so we MAJORITY-VOTE
  the frames: group them by their quantized bit signature, take the most common,
  and median the per-position timing. This rejects the occasional glitched frame
  and yields one clean, canonical code to save/replay.

Replay bit-bangs DIO2 while the radio is in asynchronous OOK TX mode.
"""

from machine import Pin
import micropython
import array
import time
import json
import os


# Signal processing constants
MIN_PULSE_US = 100        # Merge edges closer than this (noise glitch)
SYNC_GAP_US = 3000        # A low longer than this ends a code frame
SYNC_CAP_US = 20000       # Clamp an over-long trailing gap to this
CAPTURE_TIMEOUT_MS = 5000 # 5 second capture window
MAX_EDGES = 4000          # Size of the edge ring buffer (~20KB, alloc'd lazily)
MIN_FRAME_PAIRS = 8       # Ignore frames shorter than this many pulses
MAX_SLOTS = 5             # Number of save slots
REPLAY_REPEATS = 10       # How many times to repeat code on replay
SIGNALS_DIR = "/signals"
PRESS_GAP_MS = 150        # Silence > 150ms = end of one button press
MULTI_PRESS_TIMEOUT_MS = 30000  # 30s total timeout for multi-press session


class SignalRecorder:
    def __init__(self, radio, dio2_pin=32):
        micropython.alloc_emergency_exception_buf(200)
        self.radio = radio
        self.dio2_pin_num = dio2_pin
        self.dio2 = Pin(dio2_pin, Pin.IN)

        self.recording = False
        self.replaying = False

        # Edge buffers written from the ISR. Allocated lazily on first record so
        # boot-time BLE init is not starved of the large contiguous RAM block it
        # needs (allocating ~20KB here breaks NimBLE's controller init).
        self._ts = None   # timestamps (ticks_us)
        self._lv = None   # pin level after edge
        self._idx = 0

        self.pulses = []       # Canonical frame: [(high_us, low_us), ...]
        self.pulse_count = 0
        self.capture_start = 0

        # Ensure signals directory exists
        try:
            os.mkdir(SIGNALS_DIR)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Edge capture
    # ------------------------------------------------------------------

    def _irq_handler(self, pin):
        """ISR: store (timestamp, level) at each edge. No allocation here."""
        i = self._idx
        if i < MAX_EDGES:
            self._ts[i] = time.ticks_us()
            self._lv[i] = pin.value()
            self._idx = i + 1

    def _ensure_buffers(self):
        """Allocate the edge buffers on first use (kept for reuse afterwards)."""
        if self._ts is None:
            self._ts = array.array('i', [0] * MAX_EDGES)
            self._lv = array.array('b', [0] * MAX_EDGES)

    def _attach_irq(self):
        self.dio2 = Pin(self.dio2_pin_num, Pin.IN)
        self.dio2.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
                      handler=self._irq_handler)

    def start_recording(self):
        """Begin capturing OOK signal from DIO2."""
        self._ensure_buffers()
        self.recording = True
        self.pulses = []
        self.pulse_count = 0
        self.capture_start = time.ticks_ms()

        self.radio.start_rx()
        time.sleep_ms(100)  # Let RX and OOK threshold settle

        self._idx = 0       # Drain settle-period noise
        self._attach_irq()

    def stop_recording(self):
        """Stop capturing and process the recorded edges into a frame."""
        self.dio2.irq(handler=None)
        self.recording = False
        self.radio.stop()
        self.pulses = self._consensus(self._frames_from(0, self._idx))
        self.pulse_count = len(self.pulses)

    # ------------------------------------------------------------------
    # Edge -> pulses -> frames -> consensus
    # ------------------------------------------------------------------

    def _merge_intervals(self, start, end):
        """Turn edges [start:end] into merged (duration, level) intervals.

        level is the pin level HELD during the interval preceding each edge.
        Sub-MIN_PULSE glitches and stray same-level runs are merged away.
        """
        merged = []
        for i in range(start + 1, end):
            d = time.ticks_diff(self._ts[i], self._ts[i - 1])
            if d < 0:
                d += (1 << 30)
            l = self._lv[i - 1]
            if merged and (d < MIN_PULSE_US or merged[-1][1] == l):
                merged[-1][0] += d
                continue
            merged.append([d, l])
        return merged

    def _frames_from(self, start, end):
        """Build a list of frames (each a list of (high,low) pairs)."""
        merged = self._merge_intervals(start, end)
        frames = []
        cur = []
        i = 0
        n = len(merged)
        while i < n:
            d, l = merged[i]
            if l == 1:  # HIGH interval starts a pulse
                high = d
                low = 0
                if i + 1 < n and merged[i + 1][1] == 0:
                    low = merged[i + 1][0]
                    i += 2
                else:
                    i += 1
                if low > SYNC_GAP_US:
                    cur.append((high, SYNC_CAP_US))
                    if len(cur) >= MIN_FRAME_PAIRS:
                        frames.append(cur)
                    cur = []
                else:
                    cur.append((high, low))
            else:
                i += 1
        return frames

    def _consensus(self, frames):
        """Majority-vote a set of repeated frames into one clean frame."""
        if not frames:
            return []
        if len(frames) == 1:
            return list(frames[0])

        # High-pulse split threshold from all body pulses (quartile midpoint).
        highs = sorted(h for f in frames for (h, _) in f[:-1])
        if not highs:
            return list(frames[0])
        hi_t = (highs[len(highs) // 4] + highs[3 * len(highs) // 4]) / 2

        # Group frames by their quantized bit signature.
        groups = {}
        for f in frames:
            sig = "".join("1" if h > hi_t else "0" for (h, _) in f[:-1])
            groups.setdefault(sig, []).append(f)

        # Pick the most common signature.
        best = max(groups.values(), key=len)

        # Per-position median of the winning frames.
        L = min(len(f) for f in best)
        canon = []
        for pos in range(L):
            hs = sorted(f[pos][0] for f in best)
            ls = sorted(f[pos][1] for f in best)
            canon.append((hs[len(hs) // 2], ls[len(ls) // 2]))
        return canon

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def is_capture_timeout(self):
        if not self.recording:
            return False
        return time.ticks_diff(time.ticks_ms(), self.capture_start) >= CAPTURE_TIMEOUT_MS

    def get_elapsed_ms(self):
        if not self.recording:
            return 0
        return time.ticks_diff(time.ticks_ms(), self.capture_start)

    def get_live_pulse_count(self):
        return self._idx // 2

    def has_signal(self):
        return len(self.pulses) >= 4

    def extract_single_frame(self):
        """The stored pulses are already one canonical frame."""
        return self.pulses

    def detect_protocol(self):
        """Try to identify the signal protocol."""
        if not self.pulses or len(self.pulses) < 4:
            return "unknown"

        short_pulses = []
        long_pulses = []
        for high, low in self.pulses[:50]:
            if high > 0:
                if high < 600:
                    short_pulses.append(high)
                else:
                    long_pulses.append(high)

        if short_pulses and long_pulses:
            avg_short = sum(short_pulses) / len(short_pulses)
            avg_long = sum(long_pulses) / len(long_pulses)
            if avg_short > 0:
                ratio = avg_long / avg_short
                if 1.8 < ratio < 3.8:
                    n = len(self.pulses)
                    if 22 <= n <= 30:
                        return "EV1527"
                    if 11 <= n <= 14:
                        return "PT2262"
                    return "PT2262/EV1527"
        return "unknown"

    # ------------------------------------------------------------------
    # Multi-press averaging
    # ------------------------------------------------------------------

    def start_recording_multi(self, count):
        """Initialize a multi-press session and begin recording."""
        self._multi_target = count
        self._multi_frames = []
        self._multi_last_edge_count = 0
        self._multi_press_start_idx = 0
        self._multi_in_silence = False
        self.start_recording()
        self._multi_last_edge_time = time.ticks_ms()

    def check_press_complete(self):
        """Poll from the main loop during multi-press recording.

        Returns True when a new press has been fully captured and added.
        A press = a burst of edges followed by > PRESS_GAP_MS of silence.
        """
        current = self._idx
        now = time.ticks_ms()

        if current > self._multi_last_edge_count:
            self._multi_last_edge_count = current
            self._multi_last_edge_time = now
            self._multi_in_silence = False
            return False

        if self._multi_in_silence:
            return False
        if current <= self._multi_press_start_idx + 16:
            return False
        if time.ticks_diff(now, self._multi_last_edge_time) < PRESS_GAP_MS:
            return False

        # Press complete: extract its frames, then reset the buffer.
        frames = self._frames_from(self._multi_press_start_idx, current)
        frame = self._consensus(frames)

        self.dio2.irq(handler=None)
        self._idx = 0
        self._multi_press_start_idx = 0
        self._multi_last_edge_count = 0
        self._multi_in_silence = True
        self._attach_irq()

        if len(frame) >= 4:
            self._multi_frames.append(frame)
            return True
        return False

    def get_multi_captured(self):
        return len(self._multi_frames)

    def get_multi_target(self):
        return self._multi_target

    def finish_multi_recording(self):
        """Stop recording and vote across the per-press frames."""
        self.dio2.irq(handler=None)
        self.recording = False
        self.radio.stop()
        self.pulses = self._consensus(self._multi_frames)
        self.pulse_count = len(self.pulses)
        self._multi_frames = []

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    @micropython.native
    def _replay_frame(self, dio2, pulses):
        """Replay one frame of pulses. Native code for timing accuracy."""
        for i in range(len(pulses)):
            high_us = pulses[i][0]
            low_us = pulses[i][1]
            dio2.value(1)
            time.sleep_us(high_us)
            dio2.value(0)
            if low_us > 0:
                time.sleep_us(low_us)

    def replay(self, pulses=None, repeats=REPLAY_REPEATS, progress_cb=None):
        """Replay a signal by toggling DIO2 in TX continuous (async OOK) mode."""
        if pulses is None:
            pulses = self.extract_single_frame()
        if not pulses:
            return False

        self.replaying = True
        print("Replay: {} pulses, {} repeats".format(len(pulses), repeats))

        self.radio.start_tx()
        time.sleep_ms(10)  # Let TX settle

        dio2 = Pin(self.dio2_pin_num, Pin.OUT, value=0)

        for rep in range(repeats):
            if progress_cb:
                progress_cb(rep + 1, repeats)
            self._replay_frame(dio2, pulses)
            dio2.value(0)
            time.sleep_ms(10)  # Inter-frame gap

        dio2.value(0)
        self.radio.stop()
        self.replaying = False
        return True

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def save_signal(self, slot, name="signal"):
        if slot < 1 or slot > MAX_SLOTS:
            return False
        if not self.pulses:
            return False

        frame = self.extract_single_frame()
        data = {
            "name": name,
            "pulses": frame,
            "protocol": self.detect_protocol(),
            "pulse_count": len(frame),
        }
        path = "{}/slot_{}.json".format(SIGNALS_DIR, slot)
        with open(path, "w") as f:
            json.dump(data, f)
        return True

    def load_signal(self, slot):
        """Load pulses from a saved slot. Returns (name, pulses) or None."""
        path = "{}/slot_{}.json".format(SIGNALS_DIR, slot)
        try:
            with open(path, "r") as f:
                data = json.load(f)
            pulses = [(h, l) for h, l in data["pulses"]]
            return data.get("name", "signal"), pulses
        except (OSError, ValueError, KeyError):
            return None

    def load_signal_full(self, slot):
        path = "{}/slot_{}.json".format(SIGNALS_DIR, slot)
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def delete_signal(self, slot):
        path = "{}/slot_{}.json".format(SIGNALS_DIR, slot)
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def list_signals(self):
        signals = []
        for slot in range(1, MAX_SLOTS + 1):
            path = "{}/slot_{}.json".format(SIGNALS_DIR, slot)
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                signals.append((slot, data.get("name", "?"),
                                data.get("pulse_count", 0),
                                data.get("protocol", "?")))
            except (OSError, ValueError):
                pass
        return signals

    def get_all_slots(self):
        slots = []
        for slot, name, pulse_count, protocol in self.list_signals():
            slots.append({
                "slot": slot,
                "name": name,
                "pulse_count": pulse_count,
                "protocol": protocol,
            })
        return slots
