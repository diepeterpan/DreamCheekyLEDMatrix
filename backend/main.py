"""
FastAPI Server & REST / WebSocket Endpoints.
Serves WebUI, live streaming of matrix frames, service controls, and script test/promote APIs.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Check if running in mock device test mode
mock_manager = None
if os.environ.get("DCLED_MOCK_DEVICE", "").strip().lower() in ("1", "true", "yes"):
    try:
        from scripts.mock_device import install_mock_usb, MockUSBManager
        mock_manager = install_mock_usb()
    except Exception as e:
        logging.getLogger("dcled.api").warning(f"Could not initialize mock device: {e}")

from backend.config_manager import ConfigManager
from backend.driver import DCLEDDriver
from backend.font import get_font_manager
from backend.script_engine import format_python_code, validate_python_syntax
from backend.service import DCLEDService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("dcled.api")

app = FastAPI(title="DCLED Studio 80s", version="1.0.0")

# Initialize core singletons
config_mgr = ConfigManager()
driver = DCLEDDriver()
service = DCLEDService(config_mgr, driver)

# Start background worker loops
service.start()

# Mount static and frontend assets
BASE_DIR = Path(__file__).resolve().parent.parent
static_dir = BASE_DIR / "static"
frontend_dir = BASE_DIR / "frontend"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

class ServiceStateRequest(BaseModel):
    running: bool

class TestScriptRequest(BaseModel):
    code: str
    font: str = "default"
    spacing: str = "proportional"

class PreviewFramesRequest(BaseModel):
    text: str
    effect: str = "scroll_west"
    font: str = "default"
    spacing: str = "proportional"

class FormatScriptRequest(BaseModel):
    code: str
    indent_style: str = "spaces"  # "spaces" or "tabs"
    indent_size: int = 4

class ValidateScriptRequest(BaseModel):
    code: str

class PromoteRequest(BaseModel):
    code: str
    interval_seconds: int = 30
    effect: str = "scroll_west"
    speed_ms: int = 40
    brightness: int = 2
    font: str = "default"
    spacing: str = "proportional"

class ConfigUpdateRequest(BaseModel):
    interval_seconds: int = 30
    effect: str = "scroll_west"
    speed_ms: int = 40
    brightness: int = 2
    font: str = "default"
    spacing: str = "proportional"

class DevSettingsUpdateRequest(BaseModel):
    effect: str = "scroll_west"
    interval_seconds: int = 30
    speed_ms: int = 40
    brightness: int = 2
    font: str = "default"
    spacing: str = "proportional"
    script_code: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = frontend_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>DCLED 80s Studio: frontend/index.html not found</h1>")

@app.get("/favicon.ico")
async def serve_favicon():
    fav_file = static_dir / "favicon.svg"
    if fav_file.exists():
        return FileResponse(fav_file, media_type="image/svg+xml")
    return HTMLResponse(status_code=404)

@app.get("/api/fonts")
async def get_fonts():
    return {"fonts": get_font_manager().list_fonts(), "current": service.font_name}

@app.get("/api/state")
async def get_state():
    return service.get_full_state()

@app.post("/api/service/state")
async def toggle_service(req: ServiceStateRequest):
    service.set_service_state(req.running)
    return {"status": "ok", "service_running": service.is_running}

@app.post("/api/logs/clear")
async def clear_logs():
    service.clear_logs()
    return {"status": "ok", "cleared": True}

@app.post("/api/script/test")
async def test_script(req: TestScriptRequest):
    result = service.test_script(req.code, font_name=req.font, spacing_mode=req.spacing)
    # Persist the dev script in config under dev_settings
    current_dev = dict(config_mgr.get("dev_settings", {}))
    current_dev["script_code"] = req.code
    current_dev["font"] = req.font
    current_dev["spacing"] = req.spacing
    config_mgr.update({"dev_settings": current_dev})
    return result

@app.post("/api/script/preview_frames")
async def preview_frames(req: PreviewFramesRequest):
    ee = service.effects
    effect = req.effect
    text = req.text
    font = req.font
    spacing = req.spacing

    frames = []
    if effect == "flash":
        frames = list(ee.flash_frames(text, font_name=font, spacing_mode=spacing, blink_count=4))
    elif effect == "scroll_west":
        frames = list(ee.scroll_west_frames(text, font_name=font, spacing_mode=spacing))
    elif effect == "scroll_east":
        frames = list(ee.scroll_east_frames(text, font_name=font, spacing_mode=spacing))
    elif effect == "scroll_north":
        frames = list(ee.scroll_north_frames(text, font_name=font, spacing_mode=spacing))
    elif effect == "scroll_south":
        frames = list(ee.scroll_south_frames(text, font_name=font, spacing_mode=spacing))
    elif effect == "fire":
        frames = [ee.render_fire_step() for _ in range(30)]
    elif effect == "tv_warmup":
        frames = [ee.render_static_warmup(f, 30) for f in range(30)]
    elif effect == "squiggle":
        frames = [ee.render_squiggle_step(s) for s in range(40)]
    elif effect == "clock24":
        frames = [ee.render_clock(mode_24h=True, font_name=font, spacing_mode=spacing)]
    elif effect == "clock12":
        frames = [ee.render_clock(mode_24h=False, font_name=font, spacing_mode=spacing)]
    elif effect == "bcdclock":
        frames = [ee.render_bcd_clock()]
    elif effect == "tach":
        tach_val = config_mgr.get("tach_percentage", 75)
        frames = [ee.render_tach(tach_val)]
    else:
        from backend.effects import render_static_text
        frames = [render_static_text(text, align="center", font_name=font, spacing_mode=spacing)]

    return {"frames": frames, "count": len(frames)}

@app.post("/api/script/validate")
async def validate_script(req: ValidateScriptRequest):
    result = validate_python_syntax(req.code)
    return result

@app.post("/api/script/format")
async def format_script(req: FormatScriptRequest):
    result = format_python_code(req.code, indent_style=req.indent_style, indent_size=req.indent_size)
    return result

@app.post("/api/script/promote")
async def promote_script(req: PromoteRequest):
    service.promote_test_to_live(
        code=req.code,
        interval=req.interval_seconds,
        effect=req.effect,
        speed_ms=req.speed_ms,
        brightness=req.brightness,
        font=req.font,
        spacing=req.spacing
    )
    return {"status": "promoted", "state": service.get_full_state()}

@app.post("/api/config/update")
async def update_settings(req: ConfigUpdateRequest):
    service.interval_seconds = req.interval_seconds
    service.effect_name = req.effect
    service.speed_ms = req.speed_ms
    service.brightness = req.brightness
    service.font_name = req.font
    service.spacing_mode = req.spacing
    driver.set_brightness(req.brightness)
    config_mgr.update({
        "interval_seconds": req.interval_seconds,
        "effect": req.effect,
        "speed_ms": req.speed_ms,
        "brightness": req.brightness,
        "font": req.font,
        "spacing": req.spacing
    })
    return {"status": "ok", "settings": req.dict()}

@app.post("/api/config/dev_settings")
async def update_dev_settings(req: DevSettingsUpdateRequest):
    config_mgr.update({
        "dev_settings": req.dict()
    })
    return {"status": "ok", "dev_settings": req.dict()}

@app.post("/api/service/reconnect")
async def force_reconnect():
    reconnected = driver.check_connection()
    return {"reconnected": reconnected, "usb": driver.get_status()}

# Mock device inspection endpoints (available when running in mock test mode)
@app.get("/api/mock/status")
async def get_mock_status():
    if mock_manager and mock_manager.device:
        return {"mock_enabled": True, "stats": mock_manager.device.get_stats()}
    elif mock_manager:
        return {"mock_enabled": True, "connected": False, "stats": None}
    return {"mock_enabled": False}

@app.post("/api/mock/toggle_connection")
async def toggle_mock_connection(connected: bool = True):
    if not mock_manager:
        return {"error": "Mock manager not active"}
    if connected:
        mock_manager.connect()
    else:
        mock_manager.disconnect()
    driver.check_connection()
    return {"mock_connected": mock_manager.is_connected, "driver_status": driver.get_status()}

# WebSocket for high-frequency live matrix preview (up to 20-30 fps)
@app.websocket("/ws")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Stream live state every 50ms
            state = service.get_full_state()
            await websocket.send_text(json.dumps(state))
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WebSocket client disconnected: {e}")

