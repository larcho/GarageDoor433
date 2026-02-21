"""
Garage Door 433MHz Signal Recorder - Main Application
LILYGO T3 LoRa32 V1.6.1 (433MHz) + MicroPython

Coordinates BLE commands, signal capture/replay, display updates,
button input, and LED status.
"""

from machine import Pin, ADC
import time
import lora32

from sx1276_ook import SX1276OOK
from signal_recorder import SignalRecorder
from display import Display
from ble_service import BLEService


# Hardware pins
BUTTON_PIN = 0

# Application states
STATE_IDLE = 0
STATE_RECORDING = 1
STATE_CAPTURED = 2
STATE_REPLAYING = 3

# Display refresh interval
DISPLAY_UPDATE_MS = 200


class App:
    def __init__(self):
        self.state = STATE_IDLE
        self.last_slot = 1  # Last played/saved slot for button replay

        # Initialize board hardware via lora32 firmware module
        print("Initializing board...")
        self.board = lora32.Lora32()

        # LED (from board config)
        self.led = self.board.led
        self.led.value(0)

        # Button (active low with internal pullup)
        self.button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self._btn_last = 1
        self._btn_debounce = 0

        # Battery ADC (GPIO35 on T3 boards, voltage divider)
        try:
            self._adc = ADC(Pin(35))
            self._adc.atten(ADC.ATTN_11DB)
            self._adc.width(ADC.WIDTH_12BIT)
        except Exception:
            self._adc = None

        # Initialize display using board's OLED
        print("Initializing display...")
        self.display = Display(self.board)
        self.display.screen_splash()

        # Initialize SX1276 using board's pin config
        print("Initializing SX1276...")
        self.radio = SX1276OOK(
            sck=self.board.LORA_SCLK,
            mosi=self.board.LORA_MOSI,
            miso=self.board.LORA_MISO,
            cs=self.board.LORA_CS,
            rst=self.board.LORA_RST,
        )
        self.radio.init()
        print("SX1276 OK")

        # Initialize signal recorder
        self.recorder = SignalRecorder(self.radio)

        # Initialize BLE
        print("Initializing BLE...")
        self.ble = BLEService(name="GarageDoor433", on_command=self._handle_command)
        print("BLE advertising")

        # Pending command from BLE (processed in main loop)
        self._pending_cmd = None

        self._display_timer = time.ticks_ms()

    def _read_battery(self):
        """Read battery voltage via ADC."""
        if self._adc is None:
            return 0.0
        raw = self._adc.read()
        # T3 board has 100k/100k voltage divider, so multiply by 2
        # ADC 12-bit (0-4095), 3.3V reference
        return (raw / 4095.0) * 3.3 * 2

    def _handle_command(self, cmd):
        """BLE command callback - queue for main loop processing."""
        self._pending_cmd = cmd.upper().strip()

    def _process_command(self, cmd):
        """Process a BLE text command."""
        parts = cmd.split()
        verb = parts[0] if parts else ""

        if verb == "RECORD":
            if self.state == STATE_IDLE or self.state == STATE_CAPTURED:
                self.state = STATE_RECORDING
                self.recorder.start_recording()
                self.ble.send_line("OK Recording started")
                self.led.value(1)
            else:
                self.ble.send_line("ERR Busy")

        elif verb == "STOP":
            if self.state == STATE_RECORDING:
                self.recorder.stop_recording()
                if self.recorder.has_signal():
                    self.state = STATE_CAPTURED
                    proto = self.recorder.detect_protocol()
                    self.ble.send_line(
                        "OK Captured {} pulses ({})".format(
                            self.recorder.pulse_count, proto
                        )
                    )
                    self.display.screen_captured(self.recorder.pulse_count, proto)
                else:
                    self.state = STATE_IDLE
                    self.ble.send_line("WARN No signal detected")
                    self.display.screen_error("No signal detected")
                self.led.value(0)
            else:
                self.ble.send_line("ERR Not recording")

        elif verb == "PLAY":
            if len(parts) < 2:
                self.ble.send_line("ERR Usage: PLAY <slot>")
                return
            try:
                slot = int(parts[1])
            except ValueError:
                self.ble.send_line("ERR Invalid slot")
                return

            result = self.recorder.load_signal(slot)
            if result is None:
                self.ble.send_line("ERR Slot {} empty".format(slot))
                self.display.screen_error("Slot {} empty".format(slot))
                return

            name, pulses = result
            self.state = STATE_REPLAYING
            self.last_slot = slot
            self.ble.send_line("OK Playing slot {} ({})".format(slot, name))
            self.led.value(1)

            def progress(current, total):
                self.display.screen_replaying(slot, current, total)

            self.recorder.replay(pulses, progress_cb=progress)
            self.led.value(0)
            self.state = STATE_IDLE
            self.ble.send_line("OK Playback complete")

        elif verb == "SAVE":
            if len(parts) < 2:
                self.ble.send_line("ERR Usage: SAVE <slot> [name]")
                return
            try:
                slot = int(parts[1])
            except ValueError:
                self.ble.send_line("ERR Invalid slot")
                return
            name = parts[2] if len(parts) > 2 else "signal"

            if not self.recorder.has_signal():
                self.ble.send_line("ERR No signal to save")
                return

            try:
                if self.recorder.save_signal(slot, name):
                    self.last_slot = slot
                    self.state = STATE_IDLE
                    self.ble.send_line("OK Saved to slot {} as '{}'".format(slot, name))
                else:
                    self.ble.send_line("ERR Save failed (slot 1-5)")
            except Exception as e:
                self.state = STATE_IDLE
                self.ble.send_line("ERR Save error: {}".format(e))

        elif verb == "LIST":
            signals = self.recorder.list_signals()
            if signals:
                for slot, name, count, proto in signals:
                    self.ble.send_line(
                        "  {}: {} ({} pulses, {})".format(slot, name, count, proto)
                    )
                self.display.screen_signal_list(signals)
            else:
                self.ble.send_line("No saved signals")

        elif verb == "DELETE":
            if len(parts) < 2:
                self.ble.send_line("ERR Usage: DELETE <slot>")
                return
            try:
                slot = int(parts[1])
            except ValueError:
                self.ble.send_line("ERR Invalid slot")
                return
            if self.recorder.delete_signal(slot):
                self.ble.send_line("OK Deleted slot {}".format(slot))
            else:
                self.ble.send_line("ERR Slot {} not found".format(slot))

        elif verb == "STATUS":
            states = {STATE_IDLE: "Idle", STATE_RECORDING: "Recording",
                      STATE_CAPTURED: "Captured", STATE_REPLAYING: "Replaying"}
            signals = self.recorder.list_signals()
            self.ble.send_line("State: {}".format(states.get(self.state, "?")))
            self.ble.send_line("BLE: Connected")
            self.ble.send_line("Signals: {}".format(len(signals)))
            self.ble.send_line("Battery: {:.1f}V".format(self._read_battery()))

        else:
            self.ble.send_line("ERR Unknown command: {}".format(verb))
            self.ble.send_line("Commands: RECORD STOP PLAY SAVE LIST DELETE STATUS")

    def _check_button(self):
        """Check button press (GPIO0, active low) with debounce."""
        val = self.button.value()
        now = time.ticks_ms()

        if val == 0 and self._btn_last == 1:
            if time.ticks_diff(now, self._btn_debounce) > 200:
                self._btn_debounce = now
                self._on_button_press()
        self._btn_last = val

    def _on_button_press(self):
        """Handle physical button press - replay last used slot."""
        if self.state == STATE_IDLE:
            result = self.recorder.load_signal(self.last_slot)
            if result:
                name, pulses = result
                self.state = STATE_REPLAYING
                self.led.value(1)

                def progress(current, total):
                    self.display.screen_replaying(self.last_slot, current, total)

                self.recorder.replay(pulses, progress_cb=progress)
                self.led.value(0)
                self.state = STATE_IDLE
            else:
                self.display.screen_error("Slot {} empty".format(self.last_slot))
                time.sleep_ms(1000)
        elif self.state == STATE_RECORDING:
            # Button during recording = stop recording
            self._process_command("STOP")

    def _update_display(self):
        """Periodic display refresh based on current state."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._display_timer) < DISPLAY_UPDATE_MS:
            return
        self._display_timer = now

        if self.state == STATE_IDLE:
            num_signals = len(self.recorder.list_signals())
            voltage = self._read_battery()
            self.display.screen_idle(self.ble.connected, num_signals, voltage)

        elif self.state == STATE_RECORDING:
            pulse_count = self.recorder.get_live_pulse_count()
            elapsed = self.recorder.get_elapsed_ms()
            self.display.screen_recording(pulse_count, elapsed, pulse_count > 0)

            # Blink LED during recording
            if (now // 250) % 2:
                self.led.value(1)
            else:
                self.led.value(0)

    def _check_recording_timeout(self):
        """Auto-stop recording after timeout."""
        if self.state == STATE_RECORDING and self.recorder.is_capture_timeout():
            self._process_command("STOP")

    def run(self):
        """Main event loop."""
        print("GarageDoor433 Ready")

        while True:
            # Process pending BLE command
            if self._pending_cmd:
                cmd = self._pending_cmd
                self._pending_cmd = None
                self._process_command(cmd)

            # Check button
            self._check_button()

            # Check recording timeout
            self._check_recording_timeout()

            # Update display
            self._update_display()

            # Yield to other tasks
            time.sleep_ms(10)


# Entry point
app = App()
app.run()
