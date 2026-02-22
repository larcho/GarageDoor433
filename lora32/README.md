# GarageDoor433 — OOK Signal Recorder & Replayer

Capture, store, and replay 433.92 MHz OOK radio signals (garage door remotes, etc.) using a LILYGO T3 LoRa32 V1.6.1 board. Controlled via Bluetooth Low Energy from any BLE serial app on your phone.

## Hardware

- **Board:** LILYGO T3 LoRa32 V1.6.1 (ESP32 + SX1276 @ 433 MHz)
- **Display:** SSD1306 OLED 128x32
- **Button:** GPIO0 (BOOT button) — press to quick-replay last used slot
- **Firmware:** MicroPython v1.27.0 (custom LILYGO build with `lora32` module)

## How It Works

1. The SX1276 is configured in **OOK continuous mode** (not LoRa) at 433.92 MHz
2. In RX mode, DIO2 outputs the demodulated OOK bitstream — GPIO interrupts capture edge timestamps
3. A glitch-filtering algorithm reconstructs clean pulse timings from noisy edges
4. Signals are stored as JSON on the ESP32 flash filesystem (up to 5 slots)
5. In TX mode, DIO2 drives the OOK modulator — pulses are replayed with `@micropython.native` timing

## File Structure

| File | Description |
|---|---|
| `main.py` | Application entry point — event loop, state machine, BLE command dispatch, button/display handling |
| `ble_service.py` | BLE GATT server using Nordic UART Service (NUS) — advertises as `GarageDoor433` |
| `sx1276_ook.py` | Low-level SX1276 driver — SPI register access, OOK RX/TX mode, frequency/power control |
| `signal_recorder.py` | Signal capture engine — IRQ-based edge recording, glitch filtering, protocol detection, JSON storage, replay |
| `display.py` | OLED display manager — splash, idle, recording, captured, replaying, and error screens |

### On-device storage

Saved signals live at `/signals/slot_N.json` (N = 1–5). Each file contains:

```json
{"name": "GARAGE", "pulses": [[380, 840], [890, 330], ...], "protocol": "unknown", "pulse_count": 29}
```

## BLE API

Connect to `GarageDoor433` via the Nordic UART Service (NUS). The primary interface is JSON — write a JSON object to the RX characteristic and receive a JSON response via TX notification.

### JSON Requests (write to RX)

```json
{"action": "record"}
{"action": "stop"}
{"action": "play", "slot": 1}
{"action": "save", "slot": 1, "name": "Garage"}
{"action": "delete", "slot": 1}
{"action": "get_slots"}
{"action": "status"}
```

### JSON Responses (notified via TX)

```json
{"status": "ok", "action": "record"}
{"status": "ok", "action": "stop", "pulse_count": 29, "protocol": "PT2262"}
{"status": "ok", "action": "play", "slot": 1}
{"status": "ok", "action": "save", "slot": 1, "name": "Garage"}
{"status": "ok", "action": "delete", "slot": 1}
{"status": "ok", "action": "get_slots", "slots": [
  {"slot": 1, "name": "Garage", "pulse_count": 29, "protocol": "PT2262"}
]}
{"status": "ok", "action": "status", "state": "idle", "ble": true, "battery": 4.12, "signals": 2}
{"status": "error", "action": "play", "message": "Slot empty"}
```

### Typical workflow

```json
{"action": "record"}       // press your remote near the board
{"action": "stop"}         // or wait for 5s auto-timeout
{"action": "save", "slot": 1, "name": "Garage"}
{"action": "play", "slot": 1}   // replay — should open the door
{"action": "get_slots"}         // list all saved signals
```

### Legacy text commands

Plain-text commands are still supported for debugging with nRF Connect or Serial Bluetooth Terminal:

| Command | Description |
|---|---|
| `RECORD` | Start capturing OOK signal (5-second window) |
| `STOP` | Stop recording early and process captured edges |
| `SAVE <slot> [name]` | Save captured signal to slot 1–5 with optional name |
| `PLAY <slot>` | Replay a saved signal (transmits 8 repetitions) |
| `LIST` | List all saved signals |
| `DELETE <slot>` | Delete a saved signal |
| `STATUS` | Show device state, BLE status, battery voltage |

## Setup

### Prerequisites

- Python 3.12+
- The LILYGO T3 LoRa32 board connected via USB

### Install tools

```bash
python3 -m venv venv
source venv/bin/activate
pip install mpremote esptool
```

### Flash firmware (one-time)

```bash
source venv/bin/activate

# Erase flash
esptool.py --port /dev/cu.usbserial-XXXX erase_flash

# Flash MicroPython
esptool.py --port /dev/cu.usbserial-XXXX --baud 460800 write_flash -z 0x1000 \
  LILYGO_TTGO_LORA32-20251209-v1.27.0.bin
```

Replace `/dev/cu.usbserial-XXXX` with your actual serial port (use `ls /dev/cu.usb*` to find it).

### Upload application files

```bash
source venv/bin/activate
mpremote connect /dev/cu.usbserial-XXXX \
  cp sx1276_ook.py signal_recorder.py display.py ble_service.py main.py :
```

### Reset / run

```bash
mpremote connect /dev/cu.usbserial-XXXX reset
```

The board runs `main.py` automatically on boot.

## Updating

After editing any `.py` file, upload just the changed file(s) and reset:

```bash
source venv/bin/activate

# Upload only the modified file
mpremote connect /dev/cu.usbserial-XXXX cp signal_recorder.py :

# Reset to apply
mpremote connect /dev/cu.usbserial-XXXX reset
```

To upload all files at once:

```bash
mpremote connect /dev/cu.usbserial-XXXX \
  cp sx1276_ook.py signal_recorder.py display.py ble_service.py main.py :
mpremote connect /dev/cu.usbserial-XXXX reset
```

## Debugging

Open an interactive REPL on the board:

```bash
mpremote connect /dev/cu.usbserial-XXXX repl
```

Run a quick diagnostic script:

```bash
mpremote connect /dev/cu.usbserial-XXXX exec "
from sx1276_ook import SX1276OOK
radio = SX1276OOK()
radio.init()
print('RSSI:', radio.get_rssi(), 'dBm')
"
```

Read a saved signal:

```bash
mpremote connect /dev/cu.usbserial-XXXX fs cat :/signals/slot_1.json
```
