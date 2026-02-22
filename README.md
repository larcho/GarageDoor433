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
- SSD1306 OLED display for on-device feedback
- Hardware button for quick-replay

### [`expo/`](expo/) — Mobile App (React Native / Expo)

Companion iOS/Android app that connects to the LoRa32 board over BLE. Provides a touch-friendly interface for managing saved signals and recording new ones.

- **Slots tab** — Grid of saved signals with one-tap replay
- **Settings tab** — Device connection status and info
- **Record modal** — Step-based signal capture flow
- Currently uses a mock BLE service; real BLE integration is next

## Getting Started

### Firmware

See [`lora32/README.md`](lora32/README.md) for hardware requirements, flashing instructions, and the full BLE API reference.

### Mobile App

```bash
cd expo
yarn install
yarn start
```

See [`expo/README.md`](expo/README.md) for screen details, project structure, and the device service API.
