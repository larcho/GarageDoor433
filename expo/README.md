# GarageDoor433 — Expo Mobile App

React Native (Expo) companion app for the GarageDoor433 OOK signal recorder & replayer. Connects to the LILYGO T3 LoRa32 board via Bluetooth Low Energy to record, store, and replay 433 MHz signals (garage door remotes, etc.).

## Features

- **Auto-connect** — Searches for the device automatically on every app launch and when returning from the background. No manual connect step required after initial pairing.
- **BLE PIN pairing** — First connection triggers a standard iOS/Android pairing dialog. Enter the 6-digit PIN shown on the device OLED. Subsequent connections are silent (bonded).
- **Slots tab** — List of saved signal slots with one-tap replay
- **Record sheet** — Step-based signal capture flow (record → captured → save)
- **Settings tab** — Connection status, device info, manual connect/disconnect

## Screens

### Slots Tab

- Lists all saved signal slots (up to 5)
- Each row shows signal name, protocol, and pulse count
- Tap a row to replay the signal immediately
- `+` button in the header opens the Record Sheet
- Refreshes automatically when the tab gains focus

### Settings Tab

- **Status row** — shows `Connected` (green), `Disconnected` (red), `Searching…` or `Pairing…` (orange with spinner) based on real-time BLE state
- **Connect / Disconnect** button — disabled while auto-connect is running to prevent races
- **Device section** — state, battery voltage, saved signal count (only shown when connected)
- Connection error alerts include a pairing hint for first-time users

### Record Sheet (bottom sheet)

Step-based flow:

1. **Idle** — Tap "Start Recording" to begin capture
2. **Recording** — Spinner while the device listens (5-second window)
3. **Captured** — Shows pulse count and protocol; enter a name and pick a slot (1–5)
4. **Saving** — Saves to the device; dismisses and refreshes the Slots tab on success

## Project Structure

```
expo/
├── app/
│   ├── _layout.tsx                    # Root layout — wraps app with BleProvider
│   └── (tabs)/
│       ├── _layout.tsx                # Native tab bar (Slots + Settings)
│       ├── (slots)/
│       │   ├── _layout.tsx            # Stack navigator for Slots tab
│       │   └── index.tsx              # Slots screen
│       └── (settings-stack)/
│           ├── _layout.tsx            # Stack navigator for Settings tab
│           └── index.tsx              # Settings screen
├── components/
│   ├── record-sheet.tsx               # Bottom sheet for signal recording
│   ├── themed-text.tsx                # Theme-aware Text component
│   ├── themed-view.tsx                # Theme-aware View component
│   ├── haptic-tab.tsx                 # Tab button with haptic feedback
│   └── ui/
│       ├── icon-symbol.ios.tsx        # SF Symbols (iOS native)
│       └── icon-symbol.tsx            # Material Icons fallback (Android/web)
├── constants/
│   └── theme.ts                       # Colors (light/dark) and font families
├── contexts/
│   └── ble-context.tsx                # BleProvider + useBleState() hook
├── hooks/
│   ├── use-color-scheme.ts            # Native color scheme hook
│   ├── use-color-scheme.web.ts        # Web color scheme hook (SSR-safe)
│   └── use-theme-color.ts             # Resolve themed color values
└── services/
    ├── ble-manager.ts                 # Low-level BLE singleton (scan, connect, NUS read/write)
    └── device-service.ts              # High-level device API (commands, type mapping)
```

## BLE Architecture

### Auto-connect

`BleProvider` (mounted at the root layout) handles the connection lifecycle:

- Calls `autoConnect()` on app launch — scans for up to 5 seconds in the background
- Listens for `AppState` changes and calls `autoConnect()` every time the app returns to the foreground
- `autoConnect()` is a no-op if the device is already connected or scanning

### PIN Pairing

On the first connection to a new device:

1. iOS/Android shows a system-level pairing dialog: *"Enter the code shown on GarageDoor433"*
2. The OLED on the device wakes and displays the 6-digit PIN
3. After the user enters it, the devices are **bonded** — no PIN is required on subsequent connections
4. The device stores bond keys in `/ble_bonds.json` on its flash, surviving reboots

The app shows **"Pairing…"** in the Settings status row while this dialog is active.

### Services

| Module | Role |
|---|---|
| `ble-manager.ts` | Singleton `BLEManager` class — wraps `react-native-ble-plx`, manages scan/connect/notify lifecycle |
| `device-service.ts` | Async functions that send JSON commands and await matching responses |
| `contexts/ble-context.tsx` | React context that exposes `connectionState` and drives auto-connect |

### Device Service API

| Function | Description |
|---|---|
| `connect()` | Manual scan (10 s timeout) and connect |
| `autoConnect()` | Background scan (5 s timeout), silently no-ops if unavailable |
| `disconnect()` | Disconnect and clean up |
| `isConnected()` | Synchronous connection state check |
| `getSlots()` | List all saved signal slots |
| `playSlot(slot)` | Replay a saved signal |
| `startRecording()` | Begin OOK signal capture |
| `stopRecording()` | Stop capture, returns pulse count and protocol |
| `saveSignal(slot, name, recording)` | Save a captured signal to a slot |
| `deleteSlot(slot)` | Delete a saved signal |
| `getStatus()` | Device state, battery voltage, saved signal count |

## Getting Started

This app uses a **development build** (`expo-dev-client`), not Expo Go. A native build is required for BLE support.

### Prerequisites

- Xcode (for iOS) or Android Studio (for Android)
- Yarn

### Setup

1. Install dependencies

   ```bash
   yarn install
   ```

2. Build and run on device or simulator

   ```bash
   yarn run:ios      # iOS
   yarn run:android  # Android
   ```

   This compiles the native project and launches the dev client. Subsequent JS-only changes only need the dev server:

   ```bash
   yarn start
   ```

### Other commands

```bash
yarn lint          # ESLint
npx tsc --noEmit   # TypeScript check
```

## Next Steps

- [x] Implement real BLE service using `react-native-ble-plx`
- [x] BLE PIN pairing with persistent bonding
- [x] Auto-connect on app launch and foreground
- [ ] Slot deletion (swipe-to-delete or long-press)
- [ ] Haptic feedback on signal replay
- [ ] Signal strength / RSSI display during recording
