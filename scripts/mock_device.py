"""
Mock Dream Cheeky USB LED Matrix Hardware & PyUSB Interceptor.
Emulates the physical USB device (VID: 0x1D34, PID: 0x0013) at the PyUSB / control transfer level.
Validates protocol packets, tracks live received frames, brightness, and supports testing API queries.
"""

import os
import sys
import threading
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger("dcled.mock_device")

VENDOR_ID = 0x1D34
PRODUCT_ID = 0x0013
LEDSX = 21
LEDSY = 7

HID_SET_REPORT = 0x09
REQUEST_TYPE = 0x21


class MockUSBDevice:
    """
    Simulates pyusb's Device object for Dream Cheeky LED Matrix.
    """
    def __init__(self, fail_transfers: bool = False):
        self.idVendor = VENDOR_ID
        self.idProduct = PRODUCT_ID
        self.fail_transfers = fail_transfers
        self.kernel_driver_active = False
        self.transfers_count = 0
        self.last_packets: List[bytes] = []
        self.raw_frame = [[0 for _ in range(LEDSY)] for _ in range(LEDSX)]
        self.brightness = 2
        self.lock = threading.Lock()

    def is_kernel_driver_active(self, interface: int) -> bool:
        return self.kernel_driver_active

    def detach_kernel_driver(self, interface: int):
        self.kernel_driver_active = False

    def set_configuration(self):
        pass

    def ctrl_transfer(
        self,
        bmRequestType: int,
        bRequest: int,
        wValue: int,
        wIndex: int,
        data_or_wLength: bytes,
        timeout: int = 1000
    ) -> int:
        if self.fail_transfers:
            raise IOError("Simulated mock USB hardware transfer failure")

        if bmRequestType != REQUEST_TYPE or bRequest != HID_SET_REPORT:
            raise ValueError(f"Unexpected USB request: req_type={bmRequestType:#x}, req={bRequest:#x}")

        data = bytes(data_or_wLength)
        if len(data) != 8:
            raise ValueError(f"Expected 8 bytes per chunk, got {len(data)}")

        with self.lock:
            self.transfers_count += 1
            self.last_packets.append(data)
            if len(self.last_packets) > 64:
                self.last_packets.pop(0)

            # Decode packet: [brightness, row, d1[0..2], d2[0..2]]
            brightness = data[0]
            row = data[1]
            self.brightness = brightness

            d1 = data[2:5]
            d2 = data[5:8]

            bytep = 2
            bitp = 0
            for col in range(LEDSX):
                # row bit active low
                if row < LEDSY:
                    is_on_r1 = 1 if ((d1[bytep] & (1 << bitp)) == 0) else 0
                    self.raw_frame[col][row] = is_on_r1

                # row + 1 bit active low
                if row + 1 < LEDSY:
                    is_on_r2 = 1 if ((d2[bytep] & (1 << bitp)) == 0) else 0
                    self.raw_frame[col][row + 1] = is_on_r2

                bitp += 1
                if bitp == 8:
                    bitp = 0
                    bytep -= 1

        return len(data)

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            active_leds = sum(sum(col) for col in self.raw_frame)
            return {
                "vendor_id": f"{self.idVendor:#06x}",
                "product_id": f"{self.idProduct:#06x}",
                "brightness": self.brightness,
                "transfers_count": self.transfers_count,
                "active_leds_count": active_leds,
                "frame": [list(col) for col in self.raw_frame],
            }


class MockUSBManager:
    """
    Global manager for mock USB device lifecycle.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.device: Optional[MockUSBDevice] = MockUSBDevice()
        self.is_connected = True

    @classmethod
    def get_instance(cls) -> "MockUSBManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = MockUSBManager()
            return cls._instance

    def disconnect(self):
        self.is_connected = False
        self.device = None

    def connect(self):
        self.is_connected = True
        self.device = MockUSBDevice()

    def find(self, idVendor: int, idProduct: int):
        if self.is_connected and idVendor == VENDOR_ID and idProduct == PRODUCT_ID:
            return self.device
        return None


def install_mock_usb():
    """
    Monkey-patches pyusb core so that `usb.core.find(idVendor=..., idProduct=...)`
    returns the MockUSBDevice instance.
    """
    try:
        import usb.core
    except ImportError:
        # Create dummy module hierarchy if pyusb isn't installed
        import types
        usb_module = types.ModuleType("usb")
        core_module = types.ModuleType("usb.core")
        util_module = types.ModuleType("usb.util")
        usb_module.core = core_module
        usb_module.util = util_module
        sys.modules["usb"] = usb_module
        sys.modules["usb.core"] = core_module
        sys.modules["usb.util"] = util_module
        import usb.core

    mgr = MockUSBManager.get_instance()
    usb.core.find = mgr.find
    logger.info("Mock USB device installed for VID: 0x1d34 PID: 0x0013")
    return mgr

