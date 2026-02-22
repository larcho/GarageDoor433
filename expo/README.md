# GarageDoor433 — Expo Mobile App

React Native (Expo) companion app for the GarageDoor433 OOK signal recorder & replayer. Connects to the LILYGO T3 LoRa32 board via Bluetooth Low Energy to record, store, and replay 433 MHz signals (garage door remotes, etc.).

## Current Status

**UI: Complete** — All screens built with mock data, ready for BLE integration.

**BLE: Stub** — A mock device service (`services/device-service.ts`) returns realistic data matching the ESP32 JSON API. Swap it for real BLE when ready.

## Screens

### Slots Tab
- Scrollable 2-column grid of saved signal slots
- Each card shows signal name, protocol, and pulse count
- Tap a card to replay the signal
- Floating "+" button opens the record modal
- Empty state when no signals are saved

### Settings Tab
- Connection section with status indicator and connect/disconnect toggle
- Device info: state, battery voltage, saved signal count, firmware version
- iOS settings-style grouped list layout

### Record Modal
Step-based flow:
1. **Idle** — Tap the record button to start capturing
2. **Recording** — Spinner while waiting for signal capture
3. **Captured** — Shows pulse count, protocol, frequency; enter a name and pick a slot (1-5)
4. **Save** — Returns to Slots tab, which auto-refreshes via `useFocusEffect`

## Project Structure

```
expo/
├── app/
│   ├── _layout.tsx            # Root stack navigator (tabs + record modal)
│   ├── record-modal.tsx       # Signal recording flow (presented as modal)
│   └── (tabs)/
│       ├── _layout.tsx        # Tab bar config (Slots + Settings)
│       ├── index.tsx          # Slots screen — signal grid + FAB
│       └── settings.tsx       # Settings screen — connection & device status
├── components/
│   ├── themed-text.tsx        # Theme-aware Text component
│   ├── themed-view.tsx        # Theme-aware View component
│   ├── haptic-tab.tsx         # Tab bar button with haptic feedback
│   └── ui/
│       ├── icon-symbol.ios.tsx # SF Symbols (iOS native)
│       └── icon-symbol.tsx     # Material Icons fallback (Android/web)
├── constants/
│   └── theme.ts               # Colors (light/dark) and font families
├── hooks/
│   ├── use-color-scheme.ts    # Native color scheme hook
│   ├── use-color-scheme.web.ts# Web color scheme hook (SSR-safe)
│   └── use-theme-color.ts     # Resolve themed color values
└── services/
    └── device-service.ts      # Stub BLE service (mock data)
```

## Device Service API

The stub service (`services/device-service.ts`) exports these async functions, matching the ESP32 BLE JSON API:

| Function | Description |
|---|---|
| `getSlots()` | List all saved signal slots |
| `playSlot(slot)` | Replay a saved signal |
| `startRecording()` | Begin OOK signal capture |
| `stopRecording()` | Stop capture, returns pulse count/protocol/frequency |
| `saveSignal(slot, name, recording)` | Save a captured signal to a slot |
| `deleteSlot(slot)` | Delete a saved signal |
| `getStatus()` | Device state, battery, signal count, firmware version |
| `connect()` / `disconnect()` | BLE connection management |
| `isConnected()` | Check connection state (synchronous) |

## Getting Started

This app uses a **development build** (`expo-dev-client`), not Expo Go. A native build is required because the app will use BLE and other native modules not available in the Expo Go sandbox.

### Prerequisites

- Xcode (for iOS) and/or Android Studio (for Android)
- Yarn

### Setup

1. Install dependencies

   ```bash
   yarn install
   ```

2. Build and run on iOS Simulator

   ```bash
   yarn run:ios
   ```

   Or for Android:

   ```bash
   yarn run:android
   ```

   This compiles the native project and launches the dev client. Subsequent launches only need the dev server:

   ```bash
   yarn start
   ```

### Other commands

```bash
yarn lint      # Run ESLint
```

## Next Steps

- [ ] Implement real BLE service using `react-native-ble-plx` (replace `device-service.ts`)
- [ ] Add slot deletion (long-press or swipe)
- [ ] Haptic feedback on signal replay
- [ ] Signal strength / RSSI display during recording
- [ ] Onboarding flow for first-time device pairing
