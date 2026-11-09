# Dream Cheeky USB LED Matrix Studio

<p align="center">
  <img src="docs/dream_cheeky_led_message_board.jpg" alt="Dream Cheeky USB LED Message Board" width="360"/>
</p>

A modern 1980s retro-styled web controller, animation engine, and sandbox environment for the **Dream Cheeky USB LED Message Board** (Model 818 / VID: `0x1D34`, PID: `0x0013`).

---

## 📟 Hardware Specifications

- **Device Name**: Dream Cheeky USB LED Message Board (Model 818)
- **USB Vendor ID (VID)**: `0x1D34`
- **USB Product ID (PID)**: `0x0013`
- **Resolution**: 21 Columns × 7 Rows (147 Bright Red LEDs)
- **Protocol**: USB HID Control Transfers (5 control packets per frame)
- **Documentation**: [Official Developer Manual v1.0 (PDF)](docs/USB_LED_Message_Board_Developer_Manual_v1.0.pdf)

---

## ✨ Features

- **Dual Tab Architecture**:
  - **LIVE**: Dedicated physical hardware monitor, live 21×7 LED telemetry marquee, brightness, font selection, spacing density, and service logs.
  - **DEVELOPMENT**: Python sandbox runtime editor (`requests`, `datetime`, `math`, `json`), syntax checking, 4-space auto-formatter, local disk save/load, and real-time 21×7 matrix preview with interactive effect playback (`ENABLE EFFECT`).
- **Complete Legacy Font Engine**:
  - Extracted from `legacy/dcled-master/`:
    - `default`: 5×7 Standard X11 font
    - `small`: 4×7 Compact font
    - `sga`: Standard Galactic Alphabet
    - `small_inv`: Inverted high-contrast font
  - **Proportional vs Fixed Spacing**: Tight proportional glyph trimming squeezes strings (e.g. `"16.54"`) into the 21-column boundary statically without mandatory horizontal scrolling.
- **Visual Effects**:
  - Scrolling: Left (West), Right (East), Up (North), Down (South).
  - Flashing text with customizable pulse rate.
  - 12h/24h Digital clocks, Binary BCD clock, TV static warmup, fireplace hearth, and load tachometer.
- **Zero-Hardware Virtual Simulator**:
  - Built-in PyUSB mock device silently intercepts hardware transfers when no physical LED board is plugged in, allowing complete containerized local testing and UI preview.

---

## 🚀 Quick Start (Docker)

Start the environment with the included control script:

```bash
# Start standalone test container (includes Mock USB Device simulator)
./scripts/start.sh

# Rebuild container with latest changes and run automated verification suite
./scripts/start.sh --recreate && ./scripts/start.sh --test

# Follow runtime logs
./scripts/start.sh --logs

# Stop container
./scripts/start.sh --stop
```

Open your browser to:
**http://localhost:8080**

---

## 📁 Repository Structure

```
├── backend/                  # FastAPI backend, effects engine, font loader & service daemon
│   ├── driver.py             # PyUSB hardware driver (VID 0x1D34, PID 0x0013)
│   ├── effects.py            # Text renderers, scroll generators & flashing effects
│   ├── font.py               # DLF font parser & glyph proportional trimmer
│   ├── main.py               # REST API & WebSocket telemetry server
│   ├── script_engine.py      # Python AST validator, sandbox runner & code formatter
│   └── service.py            # Background physical USB & matrix render thread
├── docs/                     # Developer manual & hardware assets
│   ├── dream_cheeky_led_message_board.jpg
│   └── USB_LED_Message_Board_Developer_Manual_v1.0.pdf
├── fonts/                    # .dlf font definitions (default, small, sga, small_inv)
├── frontend/                 # index.html UI
├── scripts/                  # start.sh, mock_device.py, test_endpoints.py
├── static/                   # CSS styling, app.js, favicons, product image
└── config.json               # Persisted user & developer configuration
```

