"""
BLE GATT Server - Nordic UART Service (NUS)
Provides JSON API and text command interface for iOS app control.
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
    def __init__(self, name="GarageDoor433", on_command=None):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)

        self._name = name
        self._on_command = on_command  # Callback: fn(command_string)
        self._conn_handle = None
        self._connected = False
        self._rx_buffer = ""

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
        time.sleep_ms(100)  # Let BLE stack initialize before advertising
        self._advertise()

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._conn_handle = data[0]
            self._connected = True

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

    def _advertise(self):
        for _ in range(5):
            try:
                self._ble.gap_advertise(100_000, adv_data=self._adv_data,
                                        resp_data=self._resp_data)
                return
            except OSError:
                time.sleep_ms(100)
        print("BLE: advertising failed")

    @property
    def connected(self):
        return self._connected

    def send(self, text):
        """Send text notification to connected client."""
        if not self._connected or self._conn_handle is None:
            return False
        try:
            data = text.encode()
            # Split into chunks if needed (safe default below typical negotiated MTU)
            chunk_size = 128
            for i in range(0, len(data), chunk_size):
                chunk = data[i:i + chunk_size]
                self._ble.gatts_notify(self._conn_handle, self._tx_handle, chunk)
                if i + chunk_size < len(data):
                    time.sleep_ms(20)  # Small delay between chunks
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
