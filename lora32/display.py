"""
OLED Display Manager for SSD1306 128x32
Handles all display screens for the Garage Door Signal Recorder.
Uses the lora32 firmware module for hardware initialization.

Layout: 128x32 = 4 rows of 8px text (rows at y=0, 8, 16, 24)
"""

import time


# Text row positions for 128x32 display (8px font height)
ROW0 = 0
ROW1 = 8
ROW2 = 16
ROW3 = 24


class Display:
    def __init__(self, board):
        """Initialize using the lora32.Lora32() board object."""
        self.oled = board.oled
        self.width = self.oled.width
        self.height = self.oled.height
        self._frame = 0  # Animation frame counter

    def clear(self):
        self.oled.fill(0)

    def show(self):
        self.oled.show()

    def _center_text(self, text, y):
        """Draw text centered horizontally."""
        x = max(0, (self.width - len(text) * 8) // 2)
        self.oled.text(text, x, y)

    def _draw_header(self, title):
        """Draw inverted header bar on row 0."""
        self.oled.fill_rect(0, 0, self.width, 9, 1)
        self.oled.text(title, 2, 1, 0)

    def _draw_progress_bar(self, x, y, w, h, progress):
        """Draw a progress bar (progress 0.0 to 1.0)."""
        self.oled.rect(x, y, w, h, 1)
        fill_w = int((w - 2) * max(0, min(1, progress)))
        if fill_w > 0:
            self.oled.fill_rect(x + 1, y + 1, fill_w, h - 2, 1)

    def screen_idle(self, ble_connected=False, num_signals=0, voltage=0.0):
        """Main idle screen."""
        self.clear()
        self._draw_header("GarageDoor 433")

        if ble_connected:
            self.oled.text("BLE:OK", 0, ROW1)
        else:
            self.oled.text("BLE:Adv", 0, ROW1)

        self.oled.text("Sig:{}".format(num_signals), 72, ROW1)

        if voltage > 0:
            self.oled.text("{:.1f}V".format(voltage), 0, ROW2)

        self.oled.text("Ready", 0, ROW3)
        self.show()

    def screen_recording(self, pulse_count=0, elapsed_ms=0, activity=False):
        """Recording in progress screen."""
        self.clear()
        self._draw_header("RECORDING")

        # Animated dots
        self._frame += 1
        dots = "." * ((self._frame % 4) + 1)
        self.oled.text("Listen" + dots, 0, ROW1)

        # Pulse counter + elapsed time
        secs = elapsed_ms // 1000
        self.oled.text("P:{} T:{}s".format(pulse_count, secs), 0, ROW2)

        # Activity indicator bar on row 3
        if activity and pulse_count > 0:
            bar_w = min(pulse_count * 2, self.width - 4)
            self.oled.fill_rect(2, ROW3, bar_w, 7, 1)
        else:
            self.oled.rect(2, ROW3, self.width - 4, 7, 1)

        self.show()

    def screen_captured(self, pulse_count=0, protocol="unknown"):
        """Signal captured successfully screen."""
        self.clear()
        self._draw_header("CAPTURED!")
        self.oled.text("Pulses:{}".format(pulse_count), 0, ROW1)
        self.oled.text(protocol[:16], 0, ROW2)
        self.oled.text("Send SAVE cmd", 0, ROW3)
        self.show()

    def screen_replaying(self, slot=0, current=0, total=0):
        """Transmitting/replaying screen."""
        self.clear()
        self._draw_header("TRANSMITTING")
        self.oled.text("Slot:{} {}/{}".format(slot, current, total), 0, ROW1)

        # Progress bar spanning rows 2-3
        progress = current / total if total > 0 else 0
        self._draw_progress_bar(0, ROW2, self.width, 15, progress)

        self.show()

    def screen_signal_list(self, signals, offset=0):
        """List of saved signals (3 visible at a time)."""
        self.clear()
        self._draw_header("SIGNALS")

        if not signals:
            self._center_text("(empty)", ROW2)
        else:
            y = ROW1
            for slot, name, count, proto in signals[offset:offset + 3]:
                self.oled.text("{}: {} ({})".format(slot, name[:7], count), 0, y)
                y += 8

        self.show()

    def screen_error(self, message):
        """Error/status message screen."""
        self.clear()
        self._draw_header("ERROR")

        # Word wrap (16 chars per line, 3 rows available)
        words = message.split()
        lines = []
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= 16:
                current = current + " " + word if current else word
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        y = ROW1
        for line in lines[:3]:
            self.oled.text(line, 0, y)
            y += 8

        self.show()

    def screen_splash(self):
        """Boot splash screen."""
        self.clear()
        self._center_text("GarageDoor433", ROW0)
        self._center_text("Signal Recorder", ROW1)
        self._center_text("433.92 MHz OOK", ROW2)
        self._center_text("Ready", ROW3)
        self.show()
