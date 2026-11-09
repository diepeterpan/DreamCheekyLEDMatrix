"""
Background Service orchestrating:
1. Script evaluation at configurable intervals
2. Matrix rendering loop (effects, scrolling, static display)
3. Hardware updates & USB keep-alive
4. Auto-reconnection & hotplug monitoring
5. Thread-safe state reporting to WebUI
"""

import logging
import threading
import time
from typing import Dict, Any, List, Optional
from backend.driver import DCLEDDriver, LEDSX, LEDSY
from backend.effects import EffectsEngine, create_blank_matrix, render_static_text
from backend.script_engine import ScriptEngine
from backend.config_manager import ConfigManager

logger = logging.getLogger("dcled.service")

class DCLEDService:
    def __init__(self, config_mgr: ConfigManager, driver: DCLEDDriver):
        self.config_mgr = config_mgr
        self.driver = driver
        self.effects = EffectsEngine()
        self.script_engine = ScriptEngine()

        self.is_running = config_mgr.get("service_running", True)
        self.interval_seconds = config_mgr.get("interval_seconds", 30)
        self.effect_name = config_mgr.get("effect", "scroll_west")
        self.speed_ms = config_mgr.get("speed_ms", 40)
        self.brightness = config_mgr.get("brightness", 2)
        self.font_name = config_mgr.get("font", "default")
        self.spacing_mode = config_mgr.get("spacing", "proportional")
        self.driver.set_brightness(self.brightness)

        # Runtime states
        self.current_live_text = "INITIALIZING..."
        self.current_live_matrix = create_blank_matrix()
        self.last_script_run_time = 0.0
        self.last_script_duration_ms = 0.0
        self.last_script_stdout = ""
        self.last_script_error = ""

        # Test state
        self.test_text = ""
        self.test_matrix = create_blank_matrix()
        self.test_logs = ""
        self.test_duration_ms = 0.0
        self.test_success = True

        self.logs: List[str] = []
        self.lock = threading.RLock()
        self.stop_signal = threading.Event()
        self._add_log("Dream Cheeky Service Initialized.")

        # Threads
        self.render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self.usb_monitor_thread = threading.Thread(target=self._usb_monitor_loop, daemon=True)

    def _add_log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        with self.lock:
            self.logs.append(entry)
            if len(self.logs) > 100:
                self.logs.pop(0)
        logger.info(entry)

    def clear_logs(self):
        """Clears all in-memory live logs."""
        with self.lock:
            self.logs.clear()

    def start(self):
        self.render_thread.start()
        self.usb_monitor_thread.start()

    def set_service_state(self, run: bool):
        with self.lock:
            self.is_running = run
            self.config_mgr.update({"service_running": run})
            state = "RESUMED" if run else "STOPPED"
            if not run:
                # Clear physical display when stopped
                blank = create_blank_matrix()
                self.driver.send_frame(blank)
                self.current_live_matrix = blank
        self._add_log(f"Service state set to: {state}")

    def _usb_monitor_loop(self):
        """Continuously monitors USB device presence and handles auto-reconnects."""
        last_status = self.driver.is_connected
        while not self.stop_signal.is_set():
            connected = self.driver.check_connection()
            if connected != last_status:
                if connected:
                    self._add_log(f"USB Device DETECTED: VID 0x1d34 PID 0x0013. Auto-reconnected!")
                else:
                    self._add_log("USB Device DISCONNECTED. Operating in virtual simulation mode.")
                last_status = connected
            time.sleep(1.0)

    def execute_script_now(self):
        """Runs the active script to update display text."""
        code = self.config_mgr.get("script_code", "")
        success, result_text, stdout_logs, duration, err_details = self.script_engine.run_script(code)

        with self.lock:
            self.last_script_run_time = time.time()
            self.last_script_duration_ms = duration
            self.last_script_stdout = stdout_logs

            if success:
                self.current_live_text = result_text
                self.last_script_error = ""
            else:
                self.last_script_error = stdout_logs
                self.current_live_text = "SCRIPT ERR"

        if success:
            self._add_log(f"Script evaluated: \"{result_text}\" in {duration:.1f}ms")
        else:
            self._add_log(f"Script evaluation failed: {result_text}")

    def test_script(self, code: str, font_name: Optional[str] = None, spacing_mode: Optional[str] = None) -> Dict[str, Any]:
        """Runs user script in test mode without affecting live physical display."""
        f_name = font_name or self.font_name
        s_mode = spacing_mode or self.spacing_mode
        success, result_text, stdout_logs, duration, err_details = self.script_engine.run_script(code)
        rendered_matrix = render_static_text(result_text, align="center", font_name=f_name, spacing_mode=s_mode)

        with self.lock:
            self.test_text = result_text
            self.test_matrix = rendered_matrix
            self.test_logs = stdout_logs
            self.test_duration_ms = duration
            self.test_success = success

        self._add_log(f"Test script evaluated in {duration:.1f}ms. Output: \"{result_text}\"")
        return {
            "success": success,
            "result_text": result_text,
            "stdout": stdout_logs,
            "duration_ms": duration,
            "matrix": rendered_matrix,
            "error_details": err_details
        }

    def promote_test_to_live(self, code: str, interval: int, effect: str, speed_ms: int, brightness: int, font: str = "default", spacing: str = "proportional"):
        """Promotes tested script & settings to live active configuration and immediately pushes to USB device."""
        with self.lock:
            self.interval_seconds = interval
            self.effect_name = effect
            self.speed_ms = speed_ms
            self.brightness = brightness
            self.font_name = font
            self.spacing_mode = spacing
            self.driver.set_brightness(brightness)
            # Update live configuration AND dev_settings
            dev = dict(self.config_mgr.get("dev_settings", {}))
            dev.update({
                "script_code": code,
                "interval_seconds": interval,
                "effect": effect,
                "speed_ms": speed_ms,
                "brightness": brightness,
                "font": font,
                "spacing": spacing
            })
            self.config_mgr.update({
                "script_code": code,
                "interval_seconds": interval,
                "effect": effect,
                "speed_ms": speed_ms,
                "brightness": brightness,
                "font": font,
                "spacing": spacing,
                "dev_settings": dev
            })
        self._add_log("Promoted new script and settings to LIVE!")

        # Re-evaluate live immediately
        self.execute_script_now()

        # Immediately push an initial frame of the evaluated text to the USB hardware without waiting
        initial_frame = render_static_text(self.current_live_text, align="center", font_name=font, spacing_mode=spacing)
        self._push_frame(initial_frame)

    def _render_loop(self):
        """Main rendering pipeline updating 21x7 frames according to effect & speed."""
        step = 0
        while not self.stop_signal.is_set():
            if not self.is_running:
                time.sleep(0.1)
                continue

            # Check if interval elapsed to re-run script
            now = time.time()
            if (now - self.last_script_run_time) >= self.interval_seconds or self.last_script_run_time == 0:
                self.execute_script_now()

            text = self.current_live_text
            effect = self.effect_name
            font_name = self.font_name
            spacing = self.spacing_mode
            delay = max(0.01, self.speed_ms / 1000.0)

            # Route by effect
            if effect == "flash":
                flash_delay = max(0.1, min(1.0, (self.speed_ms * 4) / 1000.0))
                for frame in self.effects.flash_frames(text, font_name=font_name, spacing_mode=spacing, blink_count=2):
                    if not self.is_running or self.effect_name != effect or self.font_name != font_name or self.spacing_mode != spacing:
                        break
                    self._push_frame(frame)
                    time.sleep(flash_delay)

            elif effect == "scroll_west":
                for frame in self.effects.scroll_west_frames(text, font_name=font_name, spacing_mode=spacing):
                    if not self.is_running or self.effect_name != effect or self.font_name != font_name or self.spacing_mode != spacing:
                        break
                    self._push_frame(frame)
                    time.sleep(delay)

            elif effect == "scroll_east":
                for frame in self.effects.scroll_east_frames(text, font_name=font_name, spacing_mode=spacing):
                    if not self.is_running or self.effect_name != effect or self.font_name != font_name or self.spacing_mode != spacing:
                        break
                    self._push_frame(frame)
                    time.sleep(delay)

            elif effect == "scroll_north":
                for frame in self.effects.scroll_north_frames(text, font_name=font_name, spacing_mode=spacing):
                    if not self.is_running or self.effect_name != effect or self.font_name != font_name or self.spacing_mode != spacing:
                        break
                    self._push_frame(frame)
                    time.sleep(delay * 3)

            elif effect == "scroll_south":
                for frame in self.effects.scroll_south_frames(text, font_name=font_name, spacing_mode=spacing):
                    if not self.is_running or self.effect_name != effect or self.font_name != font_name or self.spacing_mode != spacing:
                        break
                    self._push_frame(frame)
                    time.sleep(delay * 3)

            elif effect == "fire":
                frame = self.effects.render_fire_step()
                self._push_frame(frame)
                time.sleep(0.08)

            elif effect == "tv_warmup":
                for f_num in range(30):
                    if not self.is_running or self.effect_name != effect:
                        break
                    frame = self.effects.render_static_warmup(f_num, 30)
                    self._push_frame(frame)
                    time.sleep(0.04)
                time.sleep(0.5)

            elif effect == "squiggle":
                for s in range(50):
                    if not self.is_running or self.effect_name != effect:
                        break
                    frame = self.effects.render_squiggle_step(s)
                    self._push_frame(frame)
                    time.sleep(0.06)

            elif effect == "clock24":
                frame = self.effects.render_clock(mode_24h=True, font_name=font_name, spacing_mode=spacing)
                self._push_frame(frame)
                time.sleep(0.25)

            elif effect == "clock12":
                frame = self.effects.render_clock(mode_24h=False, font_name=font_name, spacing_mode=spacing)
                self._push_frame(frame)
                time.sleep(0.25)

            elif effect == "bcdclock":
                frame = self.effects.render_bcd_clock()
                self._push_frame(frame)
                time.sleep(0.25)

            elif effect == "tach":
                tach_val = self.config_mgr.get("tach_percentage", 75)
                frame = self.effects.render_tach(tach_val)
                self._push_frame(frame)
                time.sleep(0.25)

            else:  # static text
                frame = render_static_text(text, align="center", font_name=font_name, spacing_mode=spacing)
                self._push_frame(frame)
                time.sleep(0.25)

    def _push_frame(self, frame: List[List[int]]):
        with self.lock:
            self.current_live_matrix = frame
        self.driver.send_frame(frame, brightness=self.brightness)

    def get_full_state(self) -> Dict[str, Any]:
        """Provides full telemetry snapshot for WebUI."""
        with self.lock:
            return {
                "service_running": self.is_running,
                "current_text": self.current_live_text,
                "live_matrix": self.current_live_matrix,
                "test_matrix": self.test_matrix,
                "test_text": self.test_text,
                "test_logs": self.test_logs,
                "test_success": self.test_success,
                "test_duration_ms": self.test_duration_ms,
                "interval_seconds": self.interval_seconds,
                "effect": self.effect_name,
                "speed_ms": self.speed_ms,
                "brightness": self.brightness,
                "font": self.font_name,
                "spacing": self.spacing_mode,
                "dev_settings": self.config_mgr.get("dev_settings", {}),
                "script_code": self.config_mgr.get("script_code", ""),
                "last_script_duration_ms": self.last_script_duration_ms,
                "last_script_error": self.last_script_error,
                "logs": list(self.logs),
                "usb": self.driver.get_status()
            }
