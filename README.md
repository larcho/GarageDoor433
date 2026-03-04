# GarageDoor433

Capture, store, and replay 433.92 MHz OOK radio signals (garage door remotes, etc.) using a LILYGO T3 LoRa32 board, controlled from a mobile app over Bluetooth Low Energy.

## Architecture

```
┌──────────────┐        BLE (Nordic UART)        ┌──────────────┐
│   Expo App   │ ◄──────────────────────────────► │  LoRa32 MCU  │
│  (iOS/Android)│    JSON commands/responses      │  (ESP32 +    │
│              │                                  │   SX1276)    │
└──────────────┘                                  └──────┬───────┘
                                                         │ OOK 433.92 MHz
                                                         ▼
                                                  ┌──────────────┐
                                                  │ Garage Door  │
                                                  │   Receiver   │
                                                  └──────────────┘
```

## Project Structure

### [`lora32/`](lora32/) — ESP32 Firmware (MicroPython)

The on-device firmware running on the LILYGO T3 LoRa32 V1.6.1. Handles OOK signal capture and replay via the SX1276 radio, stores up to 5 signals on flash, and exposes a BLE GATT server (Nordic UART Service) for remote control.

- SX1276 in OOK continuous mode at 433.92 MHz
- IRQ-based edge recording with glitch filtering
- JSON-based BLE API for record, play, save, delete, and status
- **Authenticated BLE pairing** — 6-digit PIN shown on OLED, bonded phones reconnect silently
- SSD1306 OLED display — powers on only when needed (boot, pairing, recording, transmitting)
- Hardware button for quick-replay of the last used slot

### [`expo/`](expo/) — Mobile App (React Native / Expo)

Companion iOS/Android app that connects to the LoRa32 board over BLE. Provides a touch-friendly interface for managing saved signals and recording new ones.

- **Auto-connect** — finds and connects to the device automatically on every app launch and foreground
- **BLE PIN pairing** — standard OS dialog on first connect; silent reconnect thereafter
- **Slots tab** — list of saved signals with one-tap replay
- **Settings tab** — real-time connection status, device info, manual connect/disconnect
- **Record sheet** — step-based signal capture flow

## Getting Started

### Firmware

See [`lora32/README.md`](lora32/README.md) for hardware requirements, flashing instructions, pairing/bonding details, and the full BLE API reference.

### Mobile App

```bash
cd expo
yarn install
yarn run:ios      # or yarn run:android
```

See [`expo/README.md`](expo/README.md) for screen details, project structure, and the device service API.
