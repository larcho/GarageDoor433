"""
SX1276 OOK Mode Driver for MicroPython
Configures the SX1276 LoRa chip in OOK continuous mode at 433.92MHz
for garage door signal recording and replay.
"""

from machine import Pin, SPI
import time


# SX1276 Register Addresses
REG_FIFO = 0x00
REG_OP_MODE = 0x01
REG_BITRATE_MSB = 0x02
REG_BITRATE_LSB = 0x03
REG_FRF_MSB = 0x06
REG_FRF_MID = 0x07
REG_FRF_LSB = 0x08
REG_PA_CONFIG = 0x09
REG_PA_RAMP = 0x0A
REG_OCP = 0x0B
REG_LNA = 0x0C
REG_RX_CONFIG = 0x0D
REG_RSSI_CONFIG = 0x0E
REG_RSSI_THRESH = 0x10
REG_RSSI_VALUE = 0x11
REG_RX_BW = 0x12
REG_AFC_BW = 0x13
REG_OOK_PEAK = 0x14
REG_OOK_FIX = 0x15
REG_OOK_AVG = 0x16
REG_PREAMBLE_MSB = 0x25
REG_PREAMBLE_LSB = 0x26
REG_SYNC_CONFIG = 0x27
REG_PACKET_CONFIG1 = 0x30
REG_PACKET_CONFIG2 = 0x31
REG_PAYLOAD_LENGTH = 0x32
REG_IRQ_FLAGS1 = 0x3E
REG_IRQ_FLAGS2 = 0x3F
REG_DIO_MAPPING1 = 0x40
REG_DIO_MAPPING2 = 0x41
REG_VERSION = 0x42

# Operating modes (RegOpMode bits)
MODE_SLEEP = 0x00
MODE_STDBY = 0x01
MODE_TX = 0x03
MODE_RX_CONTINUOUS = 0x05

# Modulation: OOK, FSK/OOK register bank
MODULATION_OOK = 0x20  # Bit 5 = OOK
LONG_RANGE_OFF = 0x00  # Bit 7 = 0 for FSK/OOK mode

# 433.92 MHz frequency registers (Frf = freq * 2^19 / 32MHz)
FREQ_433_92_MSB = 0x6C
FREQ_433_92_MID = 0x7A
FREQ_433_92_LSB = 0xE1


class SX1276OOK:
    def __init__(self, sck=5, mosi=27, miso=19, cs=18, rst=23, dio0=26, dio2=32):
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.rst_pin = Pin(rst, Pin.OUT, value=1)
        self.dio0 = Pin(dio0, Pin.IN)
        self.dio2 = Pin(dio2, Pin.IN)

        self.spi = SPI(1, baudrate=5000000, polarity=0, phase=0,
                       sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))

        self._mode = None
        self._buf = bytearray(2)

    def _read_reg(self, addr):
        self.cs.value(0)
        self._buf[0] = addr & 0x7F
        self._buf[1] = 0x00
        self.spi.write_readinto(self._buf, self._buf)
        self.cs.value(1)
        return self._buf[1]

    def _write_reg(self, addr, value):
        self.cs.value(0)
        self._buf[0] = addr | 0x80
        self._buf[1] = value & 0xFF
        self.spi.write(self._buf)
        self.cs.value(1)

    def _set_mode(self, mode):
        reg = LONG_RANGE_OFF | MODULATION_OOK | mode
        self._write_reg(REG_OP_MODE, reg)
        self._mode = mode
        # Wait for mode ready (IRQFlags1 bit 7)
        for _ in range(100):
            if self._read_reg(REG_IRQ_FLAGS1) & 0x80:
                return
            time.sleep_ms(1)

    def reset(self):
        self.rst_pin.value(0)
        time.sleep_ms(10)
        self.rst_pin.value(1)
        time.sleep_ms(10)

    def init(self):
        self.reset()
        time.sleep_ms(20)

        # Verify chip version
        ver = self._read_reg(REG_VERSION)
        if ver != 0x12:
            raise RuntimeError("SX1276 not found (version=0x{:02X})".format(ver))

        # Enter sleep mode to configure
        self._set_mode(MODE_SLEEP)
        time.sleep_ms(10)

        # Set OOK modulation (already set in _set_mode via MODULATION_OOK)
        # Set frequency to 433.92 MHz
        self._write_reg(REG_FRF_MSB, FREQ_433_92_MSB)
        self._write_reg(REG_FRF_MID, FREQ_433_92_MID)
        self._write_reg(REG_FRF_LSB, FREQ_433_92_LSB)

        # Bit rate: 32kbps (FXOSC / bitrate = 32MHz / 32000 = 1000 = 0x03E8)
        # Fast bit rate lets peak detector adapt quickly to track short pulses
        self._write_reg(REG_BITRATE_MSB, 0x03)
        self._write_reg(REG_BITRATE_LSB, 0xE8)

        # PA config: PA_BOOST pin, max power +17dBm
        self._write_reg(REG_PA_CONFIG, 0x8F)

        # OCP: 120mA
        self._write_reg(REG_OCP, 0x2B)

        # LNA: max gain, auto
        self._write_reg(REG_LNA, 0x23)

        # RX BW: ~83kHz (Mant=24, Exp=2 -> 32MHz / (24 * 16) = 83.3kHz)
        # Narrower BW reduces noise for cleaner OOK threshold tracking
        self._write_reg(REG_RX_BW, 0x12)

        # AFC BW: match RX BW
        self._write_reg(REG_AFC_BW, 0x12)

        # OOK peak detector config:
        # Peak mode, step=1.0dB (faster response), decay every 2 chips
        self._write_reg(REG_OOK_PEAK, 0x2C)

        # OOK fixed threshold (for fixed threshold mode - backup)
        self._write_reg(REG_OOK_FIX, 0x50)

        # RSSI threshold for OOK demodulator
        self._write_reg(REG_RSSI_THRESH, 0xA0)

        # Disable sync word
        self._write_reg(REG_SYNC_CONFIG, 0x00)

        # Packet mode: continuous mode (PacketConfig2 bit 6 = 0)
        self._write_reg(REG_PACKET_CONFIG2, 0x00)

        # No preamble
        self._write_reg(REG_PREAMBLE_MSB, 0x00)
        self._write_reg(REG_PREAMBLE_LSB, 0x00)

        # DIO mapping: DIO2 = DATA in continuous mode
        # DIO2 mapping = 01 for Data in continuous mode
        dio2_map = self._read_reg(REG_DIO_MAPPING1)
        dio2_map = (dio2_map & 0xF3) | 0x04  # DIO2 bits [3:2] = 01
        self._write_reg(REG_DIO_MAPPING1, dio2_map)

        # RX config: enable AGC, trigger on RSSI
        self._write_reg(REG_RX_CONFIG, 0x1E)

        self._set_mode(MODE_STDBY)
        return True

    def start_rx(self):
        """Enter continuous RX mode. DIO2 outputs demodulated OOK data."""
        # Ensure DIO2 is input for reading demodulated signal
        self.dio2 = Pin(32, Pin.IN)
        self._set_mode(MODE_RX_CONTINUOUS)

    def start_tx(self):
        """Enter continuous TX mode. DIO2 is used to modulate the carrier."""
        # DIO2 becomes output to drive OOK modulation
        self.dio2 = Pin(32, Pin.OUT, value=0)
        self._set_mode(MODE_TX)

    def stop(self):
        """Return to standby mode."""
        self.dio2 = Pin(32, Pin.IN)
        self._set_mode(MODE_STDBY)

    def sleep(self):
        """Enter sleep mode for low power."""
        self.dio2 = Pin(32, Pin.IN)
        self._set_mode(MODE_SLEEP)

    def get_rssi(self):
        """Read current RSSI value in dBm."""
        return -self._read_reg(REG_RSSI_VALUE) / 2.0

    def set_frequency(self, freq_mhz):
        """Set carrier frequency in MHz."""
        frf = int((freq_mhz * (1 << 19)) / 32.0)
        self._write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
        self._write_reg(REG_FRF_MID, (frf >> 8) & 0xFF)
        self._write_reg(REG_FRF_LSB, frf & 0xFF)

    def set_tx_power(self, level):
        """Set TX power level (2-17 dBm with PA_BOOST)."""
        level = max(2, min(17, level))
        self._write_reg(REG_PA_CONFIG, 0x80 | (level - 2))

    def set_ook_threshold(self, threshold):
        """Set OOK fixed threshold (0-255)."""
        self._write_reg(REG_OOK_FIX, threshold & 0xFF)
