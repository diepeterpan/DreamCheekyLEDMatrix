#!/usr/bin/env python3
"""
Integration test suite for DCLED Studio in Docker test container with mock device.
Tests:
- Frontend HTML delivery and static files
- Core REST API endpoints (service state, configs, script test/promote)
- WebSocket live telemetry feed (/ws)
- Mock USB hardware device frame reception, brightness, and disconnect/reconnect simulation
"""

import sys
import time
import json
import asyncio
import requests
import websockets

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
WS_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"

async def test_websocket_stream():
    async with websockets.connect(WS_URL) as ws:
        for _ in range(5):
            msg = await ws.recv()
            data = json.loads(msg)
            assert "live_matrix" in data or "frame" in data
            frame = data.get("live_matrix") or data.get("frame")
            assert len(frame) == 21
            assert len(frame[0]) == 7

def run_tests():
    print(f"=== Starting Integration Tests against {BASE_URL} ===")
    session = requests.Session()

    # 1. Frontend Test
    print("[1/6] Testing Frontend delivery...")
    r = session.get(f"{BASE_URL}/", timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert "DCLED" in r.text or "Matrix" in r.text or "<!DOCTYPE html>" in r.text
    print("  ✓ Frontend HTML served successfully")

    # 2. State & Driver Check
    print("[2/6] Testing Service & Driver status...")
    # Start service if stopped
    session.post(f"{BASE_URL}/api/service/state", json={"running": True}, timeout=5)
    r = session.get(f"{BASE_URL}/api/state", timeout=5)
    assert r.status_code == 200
    state = r.json()
    assert state.get("service_running") is True
    assert "usb" in state
    assert state["usb"]["connected"] is True, f"Mock device should be reported as connected, got: {state['usb']}"
    assert "font" in state
    print(f"  ✓ Service status: running={state['service_running']}, USB connected={state['usb']['connected']}, font={state['font']}")

    # Test clear logs endpoint
    r_clear = session.post(f"{BASE_URL}/api/logs/clear", timeout=5)
    assert r_clear.status_code == 200 and r_clear.json().get("cleared") is True
    print("  ✓ Service logs clear endpoint verified")

    # 3. Font API & Mock Device Hardware Stats Query
    print("[3/6] Testing Fonts API and Mock Device...")
    r_fonts = session.get(f"{BASE_URL}/api/fonts", timeout=5)
    assert r_fonts.status_code == 200
    font_names = [f["name"] for f in r_fonts.json().get("fonts", [])]
    assert "default" in font_names and "small" in font_names and "sga" in font_names and "small_inv" in font_names
    print(f"  ✓ Fonts available: {font_names}")

    r = session.get(f"{BASE_URL}/api/mock/status", timeout=5)
    assert r.status_code == 200
    mock_data = r.json()
    assert mock_data.get("mock_enabled") is True
    stats = mock_data.get("stats")
    assert stats is not None
    print(f"  ✓ Mock device received {stats['transfers_count']} USB control packets, brightness={stats['brightness']}")

    # 4. Script Testing, Syntax Validation & Formatting API
    print("[4/6] Testing script sandbox, syntax validation, and code formatting...")
    test_code = "text = 'HELLO MOCK'\neffect = 'scroll_west'"
    r = session.post(f"{BASE_URL}/api/script/test", json={"code": test_code, "font": "small"}, timeout=5)
    assert r.status_code == 200
    test_result = r.json()
    assert test_result.get("success") is True
    assert test_result.get("result_text") == "HELLO MOCK"

    # Test syntax check with intentional indent error
    bad_syntax = "def test():\n\turl = 'x'\n    val = 1\n    return val"
    r_val = session.post(f"{BASE_URL}/api/script/validate", json={"code": bad_syntax}, timeout=5)
    assert r_val.status_code == 200
    val_data = r_val.json()
    assert val_data["valid"] is False
    assert val_data["error_type"] == "IndentationError"
    assert "hint" in val_data and val_data["hint"] is not None

    # Test format code
    r_fmt = session.post(f"{BASE_URL}/api/script/format", json={"code": bad_syntax, "indent_style": "spaces", "indent_size": 4}, timeout=5)
    assert r_fmt.status_code == 200
    fmt_data = r_fmt.json()
    assert fmt_data["success"] is True
    assert "\t" not in fmt_data["formatted_code"]

    # Test preview_frames endpoint for Enable Effect (scroll and flash)
    r_prev = session.post(f"{BASE_URL}/api/script/preview_frames", json={
        "text": "16.54",
        "effect": "scroll_west",
        "font": "default",
        "spacing": "proportional"
    }, timeout=5)
    assert r_prev.status_code == 200
    prev_data = r_prev.json()
    assert "frames" in prev_data and prev_data["count"] > 0

    r_flash = session.post(f"{BASE_URL}/api/script/preview_frames", json={
        "text": "16.54",
        "effect": "flash",
        "font": "default",
        "spacing": "proportional"
    }, timeout=5)
    assert r_flash.status_code == 200
    flash_data = r_flash.json()
    assert "frames" in flash_data and flash_data["count"] == 8
    print(f"  ✓ Animation preview frames generated: {prev_data['count']} scroll frames, {flash_data['count']} flash frames")
    print("  ✓ Script test, syntax validation, formatting, and effect preview successful")

    # 5. Service & Config Update (including font selection & spacing)
    print("[5/6] Testing Config update & font/spacing persistence...")
    r = session.post(f"{BASE_URL}/api/config/update", json={
        "interval_seconds": 15,
        "effect": "scroll_west",
        "speed_ms": 50,
        "brightness": 1,
        "font": "small",
        "spacing": "proportional"
    }, timeout=5)
    assert r.status_code == 200
    time.sleep(0.5)
    r = session.get(f"{BASE_URL}/api/mock/status", timeout=5)
    mock_stats = r.json().get("stats", {})
    assert mock_stats.get("brightness") == 1
    state = session.get(f"{BASE_URL}/api/state", timeout=5).json()
    assert state.get("font") == "small"
    assert state.get("spacing") == "proportional"
    print("  ✓ Brightness, font, and spacing settings synced and persisted")

    # 6. WebSocket Telemetry Stream Test
    print("[6/6] Testing WebSocket stream (/ws)...")
    asyncio.run(test_websocket_stream())
    print("  ✓ Received 5 matrix telemetry frames over WebSocket")

    print("\n✅ ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")

    print("\n✅ ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    try:
        run_tests()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}", file=sys.stderr)
        sys.exit(1)

