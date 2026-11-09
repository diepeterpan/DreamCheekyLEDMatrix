"""
Dream Cheeky USB LED Matrix Driver (Vendor ID: 0x1d34, Product ID: 0x0013)
Resolution: 21 cols x 7 rows.
Handles USB control transfer, connection state tracking, and auto-reconnection.
"""

import threading
import time
import logging
from typing import List, Optional

logger = logging.getLogger("dcled.driver")

VENDOR_ID = 0x1D34
PRODUCT_ID = 0x0013
LEDSX = 21
LEDSY = 7

# HID Set Report request definition
HID_SET_REPORT = 0x09
REQUEST_TYPE = 0x21  # LIBUSB_RECIPIENT_INTERFACE | LIBUSB_REQUEST_TYPE_CLASS | LIBUSB_ENDPOINT_OUT

class DCLEDDriver:
    def __init__(self, simulation_mode_fallback: bool = True):
        self.simulation_mode_fallback = simulation_mode_fallback
        self.device = None
        self.handle = None
        self.brightness = 2  # 0: Low, 1: Medium, 2: High
        self.is_connected = False
        self.is_simulated = False
        self.lock = threading.Lock()
        self.last_frame = [[0 for _ in range(LEDSY)] for _ in range(LEDSX)]
        self.last_send_time = 0.0
        self.usb_available = False

        try:
            import usb.core
            import usb.util
            self.usb = usb
            self.usb_available = True
        except ImportError:
            logger.warning("PyUSB not installed or libusb backend missing. Operating in simulation mode.")
            self.usb_available = False

        self._try_connect()

    def _try_connect(self) -> bool:
        with self.lock:
            if not self.usb_available:
                self.is_connected = False
                self.is_simulated = True
                return False

            try:
                dev = self.usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
                if dev is None:
                    self.device = None
                    self.is_connected = False
                    self.is_simulated = True
                    return False

                # Found physical hardware
                try:
                    if dev.is_kernel_driver_active(0):
                        dev.detach_kernel_driver(0)
                except Exception:
                    pass

                dev.set_configuration()
                self.device = dev
                self.is_connected = True
                self.is_simulated = False
                logger.info(f"Connected to Dream Cheeky LED Matrix (VID:{VENDOR_ID:#06x} PID:{PRODUCT_ID:#06x})")
                return True
            except Exception as e:
                logger.warning(f"Error accessing USB device: {e}")
                self.device = None
                self.is_connected = False
                self.is_simulated = True
                return False

    def check_connection(self) -> bool:
        """Called by background monitor loop to detect disconnects and reconnects."""
        if not self.usb_available:
            return False

        with self.lock:
            currently_connected = self.is_connected

        if currently_connected:
            # Test device presence
            try:
                dev = self.usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
                if dev is None:
                    with self.lock:
                        self.is_connected = False
                        self.is_simulated = True
                        self.device = None
                    logger.warning("Dream Cheeky USB Matrix disconnected!")
                    return False
                return True
            except Exception:
                with self.lock:
                    self.is_connected = False
                    self.is_simulated = True
                    self.device = None
                logger.warning("Dream Cheeky USB Matrix lost connection.")
                return False
        else:
            # Attempt auto-reconnection
            if self._try_connect():
                logger.info("Dream Cheeky USB Matrix automatically reconnected!")
                # Push the last frame immediately to resume display
                self._send_frame_unlocked(self.last_frame, self.brightness)
                return True
            return False

    def set_brightness(self, brightness: int):
        self.brightness = max(0, min(2, int(brightness)))
        if self.is_connected:
            with self.lock:
                self._send_frame_unlocked(self.last_frame, self.brightness)

    def _send_frame_unlocked(self, matrix_grid: List[List[int]], brightness: int) -> bool:
        """
        Matrix grid is 21x7: matrix_grid[col][row], where col in [0..20], row in [0..6].
        Value 1 = lit, 0 = off.
        Device expects 4 packets of 8 bytes (each packet handles 2 rows: row and row+1).
        """
        # Pack into 4 chunks (each 8 bytes)
        # struct ledpkt: brightness, row, data1[3], data2[3]
        bigpkt = bytearray(32)

        for row in range(0, LEDSY, 2):
            pkt_offset = (row // 2) * 8
            bigpkt[pkt_offset + 0] = brightness
            bigpkt[pkt_offset + 1] = row

            # Active low: 0xFF default (all off)
            d1 = [0xFF, 0xFF, 0xFF]
            d2 = [0xFF, 0xFF, 0xFF]

            bytep = 2
            bitp = 0
            for col in range(LEDSX):
                # row
                if matrix_grid[col][row] == 1:
                    d1[bytep] &= ~(1 << bitp)
                # row + 1 (if within bounds)
                if row + 1 < LEDSY and matrix_grid[col][row + 1] == 1:
                    d2[bytep] &= ~(1 << bitp)

                bitp += 1
                if bitp == 8:
                    bitp = 0
                    bytep -= 1

            bigpkt[pkt_offset + 2 : pkt_offset + 5] = bytes(d1)
            bigpkt[pkt_offset + 5 : pkt_offset + 8] = bytes(d2)

        if self.device and self.is_connected:
            try:
                # 4 separate 8-byte control transfers
                for chunk in range(4):
                    chunk_data = bigpkt[chunk * 8 : (chunk + 1) * 8]
                    self.device.ctrl_transfer(
                        bmRequestType=REQUEST_TYPE,
                        bRequest=HID_SET_REPORT,
                        wValue=0,
                        wIndex=0,
                        data_or_wLength=chunk_data,
                        timeout=1000
                    )
                self.last_send_time = time.time()
                return True
            except Exception as e:
                logger.error(f"USB Transfer failed: {e}. Marking disconnected.")
                self.is_connected = False
                self.is_simulated = True
                self.device = None
                return False
        return True

    def send_frame(self, matrix_grid: List[List[int]], brightness: Optional[int] = None) -> bool:
        """Sends a 21x7 grid to the device (or records in virtual memory)."""
        b = self.brightness if brightness is None else max(0, min(2, int(brightness)))
        with self.lock:
            # Copy last frame
            self.last_frame = [[matrix_grid[x][y] for y in range(LEDSY)] for x in range(LEDSX)]
            return self._send_frame_unlocked(self.last_frame, b)

    def get_status(self) -> dict:
        return {
            "connected": self.is_connected,
            "simulated": self.is_simulated,
            "brightness": self.brightness,
            "vendor_id": f"{VENDOR_ID:#06x}",
            "product_id": f"{PRODUCT_ID:#06x}",
            "last_send_time": self.last_send_time
        }

