"""
Garage Door 433MHz Signal Recorder - Main Application
LILYGO T3 LoRa32 V1.6.1 (433MHz) + MicroPython

Coordinates BLE commands, signal capture/replay, display updates,
button input, and LED status.
"""

from machine import Pin, ADC
import json
import time
import lora32

from sx1276_ook import SX1276OOK
from signal_recorder import SignalRecorder
from display import Display
from ble_service import BLEService

try:
    from typing import Optional
except ImportError:
    pass  # MicroPython has no typing module; annotations are not evaluated.


# Hardware pins
BUTTON_PIN = 0

# Application states
STATE_IDLE = 0
STATE_RECORDING = 1
STATE_CAPTURED = 2
STATE_REPLAYING = 3
STATE_RECORDING_MULTI = 4

# Display refresh interval
DISPLAY_UPDATE_MS = 200
# Display power management
DISPLAY_SPLASH_MS = 4000   # How long the boot splash stays on
DISPLAY_LINGER_MS = 5000   # How long to keep screen on after activity
DISPLAY_PIN_MS = 60000     # How long to show the BLE pairing PIN


class App:
    def __init__(self) -> None:
        self.state = STATE_IDLE
        self.last_slot = 1  # Last played/saved slot for button replay
        self._pending_cmd = None  # type: Optional[str]  # queued BLE command

        # Initialize BLE FIRST, while the heap is fresh. The NimBLE controller
        # needs a large CONTIGUOUS block of internal RAM at init; if the display,
        # radio and recorder allocate first they fragment that region and the
        # controller init fails ("hci inits failed") at cold boot even though
        # total free RAM is ample.
        print("Initializing BLE...")
        self.ble = BLEService(name="GarageDoor433", on_command=self._handle_command,
                              on_pin=self._on_pin_display)
        print("BLE advertising")

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

        # Display sleep timer — controls when OLED powers off
        self._disp_until = time.ticks_ms() + DISPLAY_SPLASH_MS
        self._display_timer = time.ticks_ms()

    def _read_battery(self) -> float:
        """Read battery voltage via ADC."""
        if self._adc is None:
            return 0.0
        raw = self._adc.read()
        # T3 board has 100k/100k voltage divider, so multiply by 2
        # ADC 12-bit (0-4095), 3.3V reference
        # 1.0528 calibration factor — ESP32 ADC reads ~5% low (verified against multimeter)
        return (raw / 4095.0) * 3.3 * 2 * 1.0528

    def _handle_command(self, cmd: str) -> None:
        """BLE command callback - queue for main loop processing."""
        self._pending_cmd = cmd.strip()

    def _process_command(self, cmd: str) -> None:
        """Route incoming BLE data: try JSON first, fall back to legacy text."""
        # Try JSON parse first
        try:
            req = json.loads(cmd)
            if isinstance(req, dict) and "action" in req:
                self._process_request(req)
                return
        except (ValueError, KeyError):
            pass

        # Legacy text command fallback
        self._process_legacy_command(cmd.upper())

    def _process_request(self, req: dict) -> None:
        """Process a JSON API request and send a JSON response."""
        action = req.get("action", "")

        if action == "record":
            if self.state == STATE_IDLE or self.state == STATE_CAPTURED:
                self.state = STATE_RECORDING
                self.recorder.start_recording()
                self._keep_display()
                self.led.value(1)
                self.ble.send_json({"status": "ok", "action": "record"})
            else:
                self.ble.send_json({"status": "error", "action": "record", "message": "Busy"})

        elif action == "stop":
            if self.state == STATE_RECORDING:
                self.recorder.stop_recording()
                if self.recorder.has_signal():
                    self.state = STATE_CAPTURED
                    proto = self.recorder.detect_protocol()
                    self._keep_display()
                    self.display.screen_captured(self.recorder.pulse_count, proto)
                    self.ble.send_json({
                        "status": "ok", "action": "stop",
                        "pulse_count": self.recorder.pulse_count, "protocol": proto,
                    })
                else:
                    self.state = STATE_IDLE
                    self._keep_display()
                    self.display.screen_error("No signal detected")
                    self.ble.send_json({
                        "status": "error", "action": "stop",
                        "message": "No signal detected",
                    })
                self.led.value(0)
            else:
                self.ble.send_json({"status": "error", "action": "stop", "message": "Not recording"})

        elif action == "record_multi":
            count = req.get("count", 3)
            if self.state == STATE_IDLE or self.state == STATE_CAPTURED:
                self.state = STATE_RECORDING_MULTI
                self.recorder.start_recording_multi(count)
                self._keep_display()
                self.led.value(1)
                self.ble.send_json({"status": "ok", "action": "record_multi"})
            else:
                self.ble.send_json({"status": "error", "action": "record_multi", "message": "Busy"})

        elif action == "play":
            slot = req.get("slot")
            if slot is None:
                self.ble.send_json({"status": "error", "action": "play", "message": "Missing slot"})
                return

            result = self.recorder.load_signal(slot)
            if result is None:
                self.ble.send_json({"status": "error", "action": "play", "message": "Slot empty"})
                self.display.screen_error("Slot {} empty".format(slot))
                return

            name, pulses = result
            self.state = STATE_REPLAYING
            self.last_slot = slot
            self._keep_display()
            self.ble.send_json({"status": "ok", "action": "play", "slot": slot})
            self.led.value(1)

            def progress(current, total):
                self.display.screen_replaying(slot, current, total)

            self.recorder.replay(pulses, progress_cb=progress)
            self.led.value(0)
            self.state = STATE_IDLE

        elif action == "save":
            slot = req.get("slot")
            name = req.get("name", "signal")
            if slot is None:
                self.ble.send_json({"status": "error", "action": "save", "message": "Missing slot"})
                return

            if not self.recorder.has_signal():
                self.ble.send_json({"status": "error", "action": "save", "message": "No signal to save"})
                return

            try:
                if self.recorder.save_signal(slot, name):
                    self.last_slot = slot
                    self.state = STATE_IDLE
                    self.ble.send_json({"status": "ok", "action": "save", "slot": slot, "name": name})
                else:
                    self.ble.send_json({"status": "error", "action": "save", "message": "Save failed (slot 1-5)"})
            except Exception as e:
                self.state = STATE_IDLE
                self.ble.send_json({"status": "error", "action": "save", "message": str(e)})

        elif action == "delete":
            slot = req.get("slot")
            if slot is None:
                self.ble.send_json({"status": "error", "action": "delete", "message": "Missing slot"})
                return
            if self.recorder.delete_signal(slot):
                self.ble.send_json({"status": "ok", "action": "delete", "slot": slot})
            else:
                self.ble.send_json({"status": "error", "action": "delete", "message": "Slot not found"})

        elif action == "get_slots":
            slots = self.recorder.get_all_slots()
            self.ble.send_json({"status": "ok", "action": "get_slots", "slots": slots})

        elif action == "get_signal":
            slot = req.get("slot")
            if slot is None:
                self.ble.send_json({"status": "error", "action": "get_signal", "message": "Missing slot"})
                return
            data = self.recorder.load_signal_full(slot)
            if data is None:
                self.ble.send_json({"status": "error", "action": "get_signal", "message": "Slot empty"})
                return
            self.ble.send_json({
                "status": "ok", "action": "get_signal",
                "slot": slot,
                "name": data.get("name", ""),
                "protocol": data.get("protocol", "unknown"),
                "pulse_count": data.get("pulse_count", 0),
                "pulses": data.get("pulses", []),
            })

        elif action == "status":
            states = {STATE_IDLE: "idle", STATE_RECORDING: "recording",
                      STATE_CAPTURED: "captured", STATE_REPLAYING: "replaying"}
            signals = self.recorder.list_signals()
            self.ble.send_json({
                "status": "ok", "action": "status",
                "state": states.get(self.state, "unknown"),
                "ble": True,
                "battery": round(self._read_battery(), 2),
                "signals": len(signals),
            })

        else:
            self.ble.send_json({"status": "error", "action": action, "message": "Unknown action"})

    def _process_legacy_command(self, cmd: str) -> None:
        """Process a legacy ASCII text command (backward compat for nRF Connect)."""
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

    def _keep_display(self, ms: int = DISPLAY_LINGER_MS) -> None:
        """Wake the OLED and extend its on-time by ms milliseconds."""
        self.display.wake()
        self._disp_until = time.ticks_ms() + ms

    def _on_pin_display(self, pin: str) -> None:
        """BLE callback: show the pairing PIN on the OLED."""
        self._keep_display(DISPLAY_PIN_MS)
        self.display.screen_pin(pin)

    def _check_button(self) -> None:
        """Check button press (GPIO0, active low) with debounce."""
        val = self.button.value()
        now = time.ticks_ms()

        if val == 0 and self._btn_last == 1:
            if time.ticks_diff(now, self._btn_debounce) > 200:
                self._btn_debounce = now
                self._on_button_press()
        self._btn_last = val

    def _on_button_press(self) -> None:
        """Handle physical button press - replay last used slot."""
        if self.state == STATE_IDLE:
            result = self.recorder.load_signal(self.last_slot)
            if result:
                name, pulses = result
                self.state = STATE_REPLAYING
                self._keep_display()
                self.led.value(1)

                def progress(current, total):
                    self.display.screen_replaying(self.last_slot, current, total)

                self.recorder.replay(pulses, progress_cb=progress)
                self.led.value(0)
                self.state = STATE_IDLE
            else:
                self._keep_display()
                self.display.screen_error("Slot {} empty".format(self.last_slot))
                time.sleep_ms(1000)
        elif self.state == STATE_RECORDING:
            # Button during recording = stop recording
            self._process_command("STOP")

    def _update_display(self) -> None:
        """Periodic display refresh and sleep management.

        The OLED is kept on only while _disp_until is in the future.
        It powers off automatically once that timer expires.
        """
        now = time.ticks_ms()

        # Power off when the active timer expires
        if time.ticks_diff(now, self._disp_until) >= 0:
            self.display.sleep()
            return

        if time.ticks_diff(now, self._display_timer) < DISPLAY_UPDATE_MS:
            return
        self._display_timer = now

        if self.state == STATE_RECORDING:
            # Keep extending display timer while actively recording
            self._disp_until = now + DISPLAY_LINGER_MS
            pulse_count = self.recorder.get_live_pulse_count()
            elapsed = self.recorder.get_elapsed_ms()
            self.display.screen_recording(pulse_count, elapsed, pulse_count > 0)
            if (now // 250) % 2:
                self.led.value(1)
            else:
                self.led.value(0)

        elif self.state == STATE_RECORDING_MULTI:
            self._disp_until = now + DISPLAY_LINGER_MS
            captured = self.recorder.get_multi_captured()
            target = self.recorder.get_multi_target()
            self.display.screen_recording_multi(captured, target)
            if (now // 250) % 2:
                self.led.value(1)
            else:
                self.led.value(0)
        # STATE_IDLE / STATE_CAPTURED / STATE_REPLAYING:
        # Display shows the last drawn frame until _disp_until expires.

    def _finish_multi_recording(self) -> None:
        """Finalise multi-press session and send result over BLE."""
        self.recorder.finish_multi_recording()
        self.led.value(0)
        if self.recorder.has_signal():
            self.state = STATE_CAPTURED
            proto = self.recorder.detect_protocol()
            self._keep_display()
            self.display.screen_captured(self.recorder.pulse_count, proto)
            self.ble.send_json({
                "status": "ok", "action": "record_done",
                "pulse_count": self.recorder.pulse_count, "protocol": proto,
            })
        else:
            self.state = STATE_IDLE
            self._keep_display()
            self.display.screen_error("No signal detected")
            self.ble.send_json({
                "status": "error", "action": "record_done",
                "message": "No signal detected",
            })

    def _check_multi_press(self) -> None:
        """Detect completed presses during multi-press recording."""
        if self.state != STATE_RECORDING_MULTI:
            return
        if self.recorder.check_press_complete():
            captured = self.recorder.get_multi_captured()
            target = self.recorder.get_multi_target()
            self.ble.send_json({
                "action": "record_progress",
                "captured": captured,
                "target": target,
            })
            if captured >= target:
                self._finish_multi_recording()

    def _check_recording_timeout(self) -> None:
        """Auto-stop recording after timeout."""
        if self.state == STATE_RECORDING and self.recorder.is_capture_timeout():
            self._process_command("STOP")
        elif self.state == STATE_RECORDING_MULTI:
            from signal_recorder import MULTI_PRESS_TIMEOUT_MS
            elapsed = time.ticks_diff(time.ticks_ms(), self.recorder.capture_start)
            if elapsed > MULTI_PRESS_TIMEOUT_MS:
                self._keep_display()
                self.ble.send_json({
                    "status": "error", "action": "record_done",
                    "message": "Timed out — press remote faster",
                })
                self.recorder.finish_multi_recording()
                self.state = STATE_IDLE
                self.led.value(0)

    def run(self) -> None:
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

            # Check for completed presses in multi-press mode
            self._check_multi_press()

            # Update display
            self._update_display()

            # Yield to other tasks
            time.sleep_ms(10)


# Entry point
app = App()
app.run()
