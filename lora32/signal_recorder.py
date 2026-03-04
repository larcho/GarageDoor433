"""
Signal Recorder - Capture and Replay OOK signals
Uses GPIO interrupts on DIO2 to capture pulse timings,
stores signals as JSON, and replays via DIO2 in TX mode.
"""

from machine import Pin, Timer
import micropython
import time
import json
import os


# Signal processing constants
MIN_PULSE_US = 100        # Ignore pulses shorter than 100us (noise)
MAX_GAP_US = 20000        # 20ms gap = end of one code word
CAPTURE_TIMEOUT_MS = 5000 # 5 second capture window
MAX_PULSES = 500          # Max pulses to capture per recording
MAX_SLOTS = 5             # Number of save slots
REPLAY_REPEATS = 8        # How many times to repeat code on replay
SIGNALS_DIR = "/signals"
PRESS_GAP_MS = 150        # Silence > 150ms = end of one button press
MULTI_PRESS_TIMEOUT_MS = 30000  # 30s total timeout for multi-press session


class SignalRecorder:
    def __init__(self, radio, dio2_pin=32):
        self.radio = radio
        self.dio2_pin_num = dio2_pin
        self.dio2 = Pin(dio2_pin, Pin.IN)

        self.recording = False
        self.replaying = False
        self._edges = []       # Raw edge timestamps (us)
        self._last_edge_us = 0
        self.pulses = []       # Processed [(high_us, low_us), ...]
        self.pulse_count = 0
        self.capture_start = 0

        # Ensure signals directory exists
        try:
            os.mkdir(SIGNALS_DIR)
        except OSError:
            pass

    def _irq_handler(self, pin):
        """GPIO interrupt handler - capture edge timestamps only.

        We intentionally do NOT read pin.value() here because MicroPython ISR
        latency means the pin may have already changed state by the time we read
        it, producing unreliable polarity data. Instead we record only timestamps
        and reconstruct polarity from timing in _process_edges().
        """
        now = time.ticks_us()
        if len(self._edges) < MAX_PULSES * 2:
            self._edges.append(now)

    def start_recording(self):
        """Begin capturing OOK signal from DIO2."""
        self.recording = True
        self.pulses = []
        self._edges = []
        self.pulse_count = 0
        self.capture_start = time.ticks_ms()

        # Start radio in RX mode
        self.radio.start_rx()
        time.sleep_ms(100)  # Let RX and OOK threshold settle

        # Drain any noise edges from the settle period
        self._edges = []

        # Set up interrupts on DIO2 for both edges
        self.dio2 = Pin(self.dio2_pin_num, Pin.IN)
        self.dio2.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
                      handler=self._irq_handler)

    def stop_recording(self):
        """Stop capturing and process the recorded edges into pulses."""
        self.dio2.irq(handler=None)
        self.recording = False
        self.radio.stop()
        self._process_edges()

    def _compute_pulses(self, raw):
        """Convert raw edge timestamps into (high_us, low_us) pulse pairs.

        Since pin.value() is unreliable in MicroPython ISRs (latency causes
        misreads), we work with timestamps only. Strategy:
        1. Compute intervals between consecutive edges
        2. Merge glitch clusters back into real intervals using parity:
           - Odd-count cluster: fragments of a split real pulse → save sum
           - Even-count cluster: cancelled glitch pair → merge into next interval
        3. Find sync gap to anchor HIGH/LOW polarity
        4. Pair alternating intervals into (high, low) tuples
        """
        pulses = []
        if len(raw) < 4:
            return pulses

        # Step 1: Compute intervals between consecutive edge timestamps
        intervals = []
        for i in range(1, len(raw)):
            intervals.append(time.ticks_diff(raw[i], raw[i - 1]))

        # Step 2: Reconstruct clean intervals by merging glitch clusters.
        MERGE_THRESH = 250
        clean = []
        acc = 0
        gc = 0

        for interval in intervals:
            if interval < MERGE_THRESH:
                acc += interval
                gc += 1
            else:
                if gc == 0:
                    clean.append(interval)
                elif gc % 2 == 1:
                    if acc >= MIN_PULSE_US:
                        clean.append(acc)
                    clean.append(interval)
                else:
                    clean.append(acc + interval)
                acc = 0
                gc = 0

        if gc > 0 and gc % 2 == 1 and acc >= MIN_PULSE_US:
            clean.append(acc)

        # Step 3: Find sync gap to anchor polarity.
        start = 0
        for i in range(len(clean)):
            if clean[i] > MAX_GAP_US // 2:
                start = i + 1
                break

        # Step 4: Pair intervals into (high, low) starting from anchor
        i = start
        while i + 1 < len(clean):
            high_us = clean[i]
            low_us = clean[i + 1]
            if high_us >= MIN_PULSE_US:
                pulses.append((high_us, low_us))
            i += 2

        return pulses

    def _process_edges(self):
        """Process self._edges into self.pulses."""
        self.pulses = self._compute_pulses(self._edges)
        self.pulse_count = len(self.pulses)

    def is_capture_timeout(self):
        """Check if capture window has expired."""
        if not self.recording:
            return False
        elapsed = time.ticks_diff(time.ticks_ms(), self.capture_start)
        return elapsed >= CAPTURE_TIMEOUT_MS

    def get_elapsed_ms(self):
        """Get elapsed recording time in ms."""
        if not self.recording:
            return 0
        return time.ticks_diff(time.ticks_ms(), self.capture_start)

    def get_live_pulse_count(self):
        """Get current number of captured edges (for live display)."""
        return len(self._edges) // 2

    def has_signal(self):
        """Check if a valid signal was captured."""
        return len(self.pulses) >= 4

    def detect_protocol(self):
        """Try to identify the signal protocol."""
        if not self.pulses or len(self.pulses) < 4:
            return "unknown"

        # PT2262: uses fixed ratio pulses, typically 12 data bits + sync
        # Short pulse ~350us, long pulse ~1050us (3:1 ratio)
        # EV1527: similar to PT2262 but 20 data bits

        short_pulses = []
        long_pulses = []

        for high, low in self.pulses[:50]:  # Check first 50 pulses
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
                if 2.5 < ratio < 3.5:
                    # Count total data pulses per frame
                    # Find sync gap (longest low period)
                    lows = [low for _, low in self.pulses[:50] if low > 0]
                    if lows:
                        max_low = max(lows)
                        avg_low = sum(lows) / len(lows)
                        if max_low > avg_low * 5:
                            # Count pulses in first frame
                            frame_pulses = 0
                            for _, low in self.pulses:
                                frame_pulses += 1
                                if low > max_low * 0.7:
                                    break
                            if 11 <= frame_pulses <= 14:
                                return "PT2262"
                            elif 19 <= frame_pulses <= 22:
                                return "EV1527"
                    return "PT2262/EV1527"

        return "unknown"

    def _extract_single_frame_from(self, pulses):
        """Extract one complete code frame from a pulse list."""
        if not pulses or len(pulses) < 4:
            return pulses

        lows = [(low, i) for i, (_, low) in enumerate(pulses) if low > 0]
        if not lows:
            return pulses

        lows.sort(reverse=True)
        avg_low = sum(l for l, _ in lows) / len(lows)
        sync_indices = [i for low, i in lows if low > avg_low * 3]
        sync_indices.sort()

        if len(sync_indices) >= 2:
            start = sync_indices[0] + 1
            end = sync_indices[1] + 1
            return pulses[start:end]
        elif len(sync_indices) == 1:
            return pulses[:sync_indices[0] + 1]

        return pulses

    def extract_single_frame(self):
        """Extract one complete code frame from self.pulses."""
        return self._extract_single_frame_from(self.pulses)

    # ------------------------------------------------------------------
    # Multi-press averaging
    # ------------------------------------------------------------------

    def _extract_frame_from_edges(self, edges):
        """Process a slice of raw edges into a single code frame."""
        pulses = self._compute_pulses(edges)
        return list(self._extract_single_frame_from(pulses))

    def _average_frames(self, frames):
        """Average pulse timings across multiple captured frames."""
        if not frames:
            return []
        if len(frames) == 1:
            return list(frames[0])

        # Find most common frame length and keep only matching frames
        lengths = {}
        for f in frames:
            n = len(f)
            lengths[n] = lengths.get(n, 0) + 1
        target_len = max(lengths, key=lengths.get)
        valid = [f for f in frames if len(f) == target_len]

        n = len(valid)
        averaged = []
        for i in range(target_len):
            avg_high = sum(f[i][0] for f in valid) // n
            avg_low = sum(f[i][1] for f in valid) // n
            averaged.append((avg_high, avg_low))
        return averaged

    def start_recording_multi(self, count):
        """Initialize a multi-press averaging session and begin recording."""
        self._multi_target = count
        self._multi_frames = []
        self._multi_last_edge_count = 0
        self._multi_press_start_idx = 0
        self._multi_in_silence = False
        self.start_recording()
        # Set timer AFTER start_recording's 100ms settle delay
        self._multi_last_edge_time = time.ticks_ms()

    def check_press_complete(self):
        """Call from the main loop during multi-press recording.

        Returns True when a new press has been fully captured and added.
        Detects a complete press as: enough edges followed by > PRESS_GAP_MS silence.
        """
        current_count = len(self._edges)
        now = time.ticks_ms()

        if current_count > self._multi_last_edge_count:
            # New edges arriving — reset silence tracking
            self._multi_last_edge_count = current_count
            self._multi_last_edge_time = now
            self._multi_in_silence = False
            return False

        if self._multi_in_silence:
            return False  # Already processed this silence window

        if current_count <= self._multi_press_start_idx + 8:
            return False  # Not enough edges for a valid press

        if time.ticks_diff(now, self._multi_last_edge_time) < PRESS_GAP_MS:
            return False  # Silence not long enough yet

        # Press complete — snapshot and reset the edge buffer
        press_edges = self._edges[self._multi_press_start_idx:current_count]

        # Briefly disable IRQ to safely reset the buffer
        self.dio2.irq(handler=None)
        self._edges = list(self._edges[current_count:])
        self._multi_press_start_idx = 0
        self._multi_last_edge_count = 0
        self._multi_in_silence = True
        self.dio2.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
                      handler=self._irq_handler)

        frame = self._extract_frame_from_edges(press_edges)
        if len(frame) >= 4:
            self._multi_frames.append(frame)
            return True
        return False

    def get_multi_captured(self):
        return len(self._multi_frames)

    def get_multi_target(self):
        return self._multi_target

    def finish_multi_recording(self):
        """Stop recording and set self.pulses to the averaged result."""
        self.dio2.irq(handler=None)
        self.recording = False
        self.radio.stop()
        self.pulses = self._average_frames(self._multi_frames)
        self.pulse_count = len(self.pulses)
        self._multi_frames = []

    # ------------------------------------------------------------------

    @micropython.native
    def _replay_frame(self, dio2, pulses):
        """Replay a single frame of pulses. Runs as native code for timing accuracy."""
        for i in range(len(pulses)):
            high_us = pulses[i][0]
            low_us = pulses[i][1]
            dio2.value(1)
            time.sleep_us(high_us)
            dio2.value(0)
            if low_us > 0:
                time.sleep_us(low_us)

    def replay(self, pulses=None, repeats=REPLAY_REPEATS, progress_cb=None):
        """Replay a signal by toggling DIO2 in TX continuous mode."""
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

            # Inter-frame gap
            dio2.value(0)
            time.sleep_ms(10)

        dio2.value(0)
        self.radio.stop()
        self.replaying = False
        return True

    def save_signal(self, slot, name="signal"):
        """Save extracted single frame to a numbered slot."""
        if slot < 1 or slot > MAX_SLOTS:
            return False
        if not self.pulses:
            return False

        # Save just one frame, not the entire raw capture
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
            # Convert lists back to tuples
            pulses = [(h, l) for h, l in data["pulses"]]
            return data.get("name", "signal"), pulses
        except (OSError, ValueError, KeyError):
            return None

    def load_signal_full(self, slot):
        """Load complete signal data from a saved slot. Returns raw dict or None."""
        path = "{}/slot_{}.json".format(SIGNALS_DIR, slot)
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def delete_signal(self, slot):
        """Delete a saved signal slot."""
        path = "{}/slot_{}.json".format(SIGNALS_DIR, slot)
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def list_signals(self):
        """List all saved signals. Returns [(slot, name, pulse_count, protocol), ...]."""
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
        """Return all saved signals as a list of dicts for JSON API."""
        slots = []
        for slot, name, pulse_count, protocol in self.list_signals():
            slots.append({
                "slot": slot,
                "name": name,
                "pulse_count": pulse_count,
                "protocol": protocol,
            })
        return slots
