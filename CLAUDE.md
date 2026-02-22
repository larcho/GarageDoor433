# GarageDoor433 — Agent Instructions

## Project Layout

- `lora32/` — ESP32 MicroPython firmware (runs on LILYGO T3 LoRa32 V1.6.1)
- `expo/` — React Native mobile app (Expo Router, TypeScript)

---

## LoRa32 Firmware

### Device files (all live in `lora32/`)

| File | Purpose |
|---|---|
| `main.py` | Entry point — event loop, state machine, BLE dispatch, button/display |
| `ble_service.py` | BLE GATT server (Nordic UART Service), advertises as `GarageDoor433` |
| `sx1276_ook.py` | SX1276 radio driver — SPI registers, OOK RX/TX, frequency/power |
| `signal_recorder.py` | Signal capture — IRQ edge recording, glitch filter, JSON storage, replay |
| `display.py` | SSD1306 OLED display manager |

### Serial port

Find the board's serial port:
```bash
ls /dev/cu.usb*
```
Typical pattern: `/dev/cu.usbserial-XXXX`

### Upload files to the board

Uses `mpremote` from the lora32 virtualenv:

```bash
# Activate the virtualenv first
source lora32/venv/bin/activate

# Upload a single changed file
mpremote connect /dev/cu.usbserial-XXXX cp lora32/<file>.py :

# Upload all firmware files
mpremote connect /dev/cu.usbserial-XXXX \
  cp lora32/sx1276_ook.py lora32/signal_recorder.py lora32/display.py lora32/ble_service.py lora32/main.py :

# Reset board to apply changes
mpremote connect /dev/cu.usbserial-XXXX reset
```

Always reset after uploading — the board runs `main.py` on boot.

### Debugging

```bash
# Interactive REPL
mpremote connect /dev/cu.usbserial-XXXX repl

# Read a saved signal
mpremote connect /dev/cu.usbserial-XXXX fs cat :/signals/slot_1.json
```

### BLE JSON API

The device accepts JSON commands over Nordic UART Service. Key actions:
- `{"action": "record"}` / `{"action": "stop"}` — capture a signal
- `{"action": "play", "slot": N}` — replay slot 1-5
- `{"action": "save", "slot": N, "name": "..."}` — save captured signal
- `{"action": "delete", "slot": N}` — delete a slot
- `{"action": "get_slots"}` — list saved signals
- `{"action": "status"}` — device state, battery, signal count

Responses are JSON with `"status": "ok"` or `"status": "error"`.

---

## Expo Mobile App

### Package manager: Yarn

Always use `yarn`, never `npm`. A `yarn.lock` is present.

```bash
cd expo
yarn install       # install deps
yarn start         # dev server
yarn ios           # open in iOS Simulator
yarn android       # open in Android emulator
yarn lint          # ESLint
```

### Routing

Uses Expo Router (file-based routing). Tab screens live in `expo/app/(tabs)/`. Modals are top-level files in `expo/app/`.

### Conventions

- Themed components: `ThemedText`, `ThemedView` (auto light/dark mode)
- Icons: `IconSymbol` — SF Symbols on iOS, Material Icons on Android/web. New icons need a mapping added in `expo/components/ui/icon-symbol.tsx`
- Colors defined in `expo/constants/theme.ts`
- BLE service is stubbed in `expo/services/device-service.ts` — replace with real BLE later

### Type checking

```bash
cd expo && npx tsc --noEmit
```
