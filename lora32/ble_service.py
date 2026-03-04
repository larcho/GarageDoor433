"""
BLE GATT Server - Nordic UART Service (NUS)
Provides JSON API and text command interface for iOS app control.
Supports BLE passkey pairing with persistent bonding (PIN only for new devices).
"""

import bluetooth
import json
import struct
import time


# Nordic UART Service UUIDs
NUS_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
RX_UUID = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")  # Write
TX_UUID = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # Notify

# BLE advertising flags
_ADV_TYPE_FLAGS = 0x01
_ADV_TYPE_NAME = 0x09
_ADV_TYPE_UUID128_COMPLETE = 0x07

# IRQ events
_IRQ_CENTRAL_CONNECT = 1
_IRQ_CENTRAL_DISCONNECT = 2
_IRQ_GATTS_WRITE = 3
_IRQ_ENCRYPTION_UPDATE = 28
_IRQ_GET_SECRET = 29
_IRQ_SET_SECRET = 30
_IRQ_PASSKEY_ACTION = 31

# Passkey action types
_PASSKEY_ACTION_DISPLAY = 3

# IO capability: display only — ESP32 shows PIN, phone user types it
_IO_DISPLAY_ONLY = 0

# Bond key storage file on flash
_BONDS_FILE = "/ble_bonds.json"

_FLAG_READ = 0x0002
_FLAG_WRITE = 0x0008
_FLAG_NOTIFY = 0x0010
_FLAG_WRITE_NO_RESPONSE = 0x0004

NUS_SERVICE = (
    NUS_UUID,
    (
        (TX_UUID, _FLAG_READ | _FLAG_NOTIFY),
        (RX_UUID, _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE),
    ),
)


def _build_payload(*fields):
    """Build a BLE advertising/scan response payload from (type, data) pairs."""
    payload = bytearray()
    for ad_type, data in fields:
        payload += struct.pack("BB", len(data) + 1, ad_type)
        payload += data
    return payload


class BLEService:
    def __init__(self, name="GarageDoor433", on_command=None, on_pin=None):
        self._ble = bluetooth.BLE()

        # Security config must be set before activating BLE
        try:
            self._ble.config(bond=True, mitm=True, io=_IO_DISPLAY_ONLY)
        except Exception as e:
            print("BLE: security config error:", e)

        # Initialise all state before enabling the IRQ
        self._name = name
        self._on_command = on_command
        self._on_pin = on_pin      # callback(pin_str) — show PIN on display
        self._conn_handle = None
        self._connected = False
        self._rx_buffer = ""
        self._bonds = {}
        self._load_bonds()

        self._ble.irq(self._irq)
        self._ble.active(True)

        # Register GATT service
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services(
            (NUS_SERVICE,)
        )

        # Increase MTU for longer messages
        self._ble.gatts_set_buffer(self._rx_handle, 256)
        self._ble.gatts_set_buffer(self._tx_handle, 256)

        # Advertising data: flags + name (must fit in 31 bytes)
        self._adv_data = _build_payload(
            (_ADV_TYPE_FLAGS, b'\x06'),
            (_ADV_TYPE_NAME, name.encode()),
        )
        # Scan response: UUID (sent when phone requests more info)
        self._resp_data = _build_payload(
            (_ADV_TYPE_UUID128_COMPLETE, bytes(NUS_UUID)),
        )
        time.sleep_ms(100)  # Let BLE stack initialise before advertising
        self._advertise()

    # ------------------------------------------------------------------
    # Bond (pairing key) persistence
    # ------------------------------------------------------------------

    def _load_bonds(self):
        """Load bonded device keys from flash."""
        try:
            with open(_BONDS_FILE) as f:
                self._bonds = json.loads(f.read())
        except Exception:
            self._bonds = {}

    def _save_bonds(self):
        """Persist bonded device keys to flash."""
        try:
            with open(_BONDS_FILE, "w") as f:
                f.write(json.dumps(self._bonds))
        except Exception as e:
            print("BLE: bond save error:", e)

    # ------------------------------------------------------------------
    # BLE IRQ handler
    # ------------------------------------------------------------------

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._conn_handle = data[0]
            self._connected = True
            # Initiate pairing; silently re-authenticates for already-bonded devices
            # so the PIN only appears for new/unknown devices.
            try:
                self._ble.gap_pair(self._conn_handle)
            except Exception as e:
                print("BLE: gap_pair error:", e)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn_handle = None
            self._connected = False
            self._rx_buffer = ""
            # Restart advertising
            self._advertise()

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            if attr_handle == self._rx_handle:
                raw = self._ble.gatts_read(self._rx_handle)
                try:
                    text = raw.decode().strip()
                except UnicodeError:
                    return

                # Handle line-by-line (some apps send with newline)
                self._rx_buffer += text
                while "\n" in self._rx_buffer:
                    line, self._rx_buffer = self._rx_buffer.split("\n", 1)
                    line = line.strip()
                    if line and self._on_command:
                        self._on_command(line)

                # Also process if no newline (direct command)
                if self._rx_buffer and "\n" not in self._rx_buffer:
                    cmd = self._rx_buffer.strip()
                    if cmd and self._on_command:
                        self._on_command(cmd)
                    self._rx_buffer = ""

        elif event == _IRQ_PASSKEY_ACTION:
            # Fired when pairing requires user interaction.
            # With IO=display_only this is always DISPLAY — show the PIN.
            conn_handle, action, passkey = data
            if action == _PASSKEY_ACTION_DISPLAY:
                pin_str = "{:06d}".format(passkey)
                print("BLE: pairing PIN =", pin_str)
                if self._on_pin:
                    self._on_pin(pin_str)
                # Acknowledge to the BLE stack that we have displayed the passkey
                try:
                    self._ble.gap_passkey(conn_handle, action, passkey)
                except Exception as e:
                    print("BLE: gap_passkey error:", e)

        elif event == _IRQ_ENCRYPTION_UPDATE:
            conn_handle, encrypted, authenticated, bonded, key_size = data
            print("BLE: enc={} auth={} bonded={}".format(encrypted, authenticated, bonded))

        elif event == _IRQ_SET_SECRET:
            # Store a bond key sent by the BLE security stack.
            sec_type, key, value = data
            k = "{}:{}".format(sec_type, bytes(key).hex())
            if value:
                self._bonds[k] = bytes(value).hex()
            else:
                self._bonds.pop(k, None)
            self._save_bonds()
            return True  # Return value matters for this event

        elif event == _IRQ_GET_SECRET:
            # Retrieve a bond key for the BLE security stack.
            sec_type, index, key = data
            if key is None:
                # Enumerate stored secrets by index for this sec_type
                prefix = "{}:".format(sec_type)
                matches = [v for sk, v in self._bonds.items() if sk.startswith(prefix)]
                if index < len(matches):
                    return bytes.fromhex(matches[index])
                return None
            else:
                k = "{}:{}".format(sec_type, bytes(key).hex())
                v = self._bonds.get(k)
                return bytes.fromhex(v) if v else None

    # ------------------------------------------------------------------
    # Advertising
    # ------------------------------------------------------------------

    def _advertise(self):
        for _ in range(5):
            try:
                self._ble.gap_advertise(100_000, adv_data=self._adv_data,
                                        resp_data=self._resp_data)
                return
            except OSError:
                time.sleep_ms(100)
        print("BLE: advertising failed")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def connected(self):
        return self._connected

    def send(self, text):
        """Send text notification to connected client."""
        if not self._connected or self._conn_handle is None:
            return False
        try:
            data = text.encode()
            chunk_size = 128
            for i in range(0, len(data), chunk_size):
                chunk = data[i:i + chunk_size]
                self._ble.gatts_notify(self._conn_handle, self._tx_handle, chunk)
                if i + chunk_size < len(data):
                    time.sleep_ms(20)
            return True
        except Exception:
            return False

    def send_line(self, text):
        """Send text with newline."""
        return self.send(text + "\n")

    def send_json(self, data):
        """Serialize a dict to JSON and send as a newline-terminated notification."""
        return self.send(json.dumps(data) + "\n")

    def disconnect(self):
        """Disconnect current client."""
        if self._connected and self._conn_handle is not None:
            try:
                self._ble.gap_disconnect(self._conn_handle)
            except Exception:
                pass

    def deinit(self):
        """Shut down BLE."""
        self._ble.active(False)
