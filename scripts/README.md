# DCLED Studio - Containerized Test Environment & Mock Device

This directory contains scripts and tooling to run, test, and verify the Dream Cheeky LED Matrix Studio in an isolated Docker container with an emulated hardware device.

---

## Features

- **Single Container Testing:** Runs both the FastAPI backend and HTML5 frontend together in one container on port `8080` (no venv needed inside container).
- **Mock Hardware Emulation (`mock_device.py`):** Intercepts PyUSB calls for Vendor ID `0x1D34` and Product ID `0x0013` (Dream Cheeky LED Matrix).
  - Emulates HID `SET_REPORT` control transfers.
  - Decodes 21x7 bit-packed packets and records brightness and frame buffer states.
  - Remains silent during operation unless queried by test harnesses.
- **Port Conflict Detection & Resolution:** Checks if `:8080` (or custom `$PORT`) is in use by another process or Docker container. Prompts to kill the conflicting process/container and retry automatically.
- **Interactive Start Script (`start.sh`):**
  - Detects if the container is already running and provides an interactive prompt to stop, recreate, or view logs.
  - Supports automated testing with `./scripts/start.sh --test`.
- **Automated Integration Tests (`test_endpoints.py`):**
  - Verifies frontend HTML/static asset serving.
  - Tests REST API endpoints, script sandbox execution, and configuration updates.
  - Validates WebSocket telemetry frame streaming (`/ws`).
  - Asserts packet delivery and brightness updates against the mock device.

---

## Quick Start

### 1. Launch the Test Container
From the project root:
```bash
./scripts/start.sh
```
The server will be available at:
- Web UI: **http://localhost:8080**
- WebSocket Live Feed: **ws://localhost:8080/ws**

If a container is already running, `start.sh` will prompt:
```text
Container 'dcled-studio-test' is already running!

Please choose an action:
  1) Stop and recreate container (rebuild image)
  2) Stop container
  3) Show container logs
  4) Exit without making changes
```

### 2. Run Integration Tests
To spin up the container (if not already running) and execute the test suite:
```bash
./scripts/start.sh --test
```

### 3. View Logs
Stream live container logs:
```bash
./scripts/start.sh --logs
```

### 4. Stop the Container
```bash
./scripts/start.sh --stop
```

### 5. Check Status
```bash
./scripts/start.sh --status
```

---

## Configuration & Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `PORT` | `8080` | Host port to expose. Example: `PORT=9000 ./scripts/start.sh` |
| `DCLED_MOCK_DEVICE` | `1` | Set to `1` inside container to enable hardware mock layer. |
| `PYTHONUNBUFFERED` | `1` | Forces unbuffered stdout/stderr output in container logs. |

---

## Mock Device Architecture

The mock device lives in [`scripts/mock_device.py`](./mock_device.py). When `DCLED_MOCK_DEVICE=1` is present in the environment:
1. `backend/main.py` invokes `install_mock_usb()`.
2. PyUSB's `usb.core.find` is intercepted. When requested for VID `0x1D34` and PID `0x0013`, it yields a `MockUSBDevice` instance instead of failing.
3. Frames dispatched by `DCLEDDriver` are decoded and stored in memory.
4. Test suites can query `/api/mock/status` to verify hardware communications or simulate disconnect events via `/api/mock/toggle_connection`.

