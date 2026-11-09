#!/usr/bin/env bash
# ==============================================================================
# DCLED Studio - Containerized Test Environment Runner
# ==============================================================================
# Builds and runs both backend and frontend inside a single Docker container.
# Uses a mock Dream Cheeky USB matrix device to allow testing all features
# without physical hardware.
# ==============================================================================

set -e

CONTAINER_NAME="dcled-studio-test"
IMAGE_NAME="dcled-studio:test"
DEFAULT_PORT="8080"
PORT="${PORT:-$DEFAULT_PORT}"

# Change to repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

print_usage() {
    cat << EOF
Usage: ./scripts/start.sh [COMMAND] [OPTIONS]

Commands:
  (no command)     Start the container (checks port & container status interactively)
  --recreate       Force rebuild image and restart container
  --stop           Stop and remove the running test container
  --status         Check the status of the container and port $PORT
  --logs           View/follow logs from the test container
  --test           Start container in mock mode and run integration tests
  --help, -h       Show this help message

Options:
  PORT=<port>      Set custom host port (default: 8080)
                   Example: PORT=9000 ./scripts/start.sh
EOF
}

check_docker() {
    if ! command -v docker &>/dev/null; then
        echo "Error: 'docker' command not found. Please install Docker." >&2
        exit 1
    fi
}

is_container_running() {
    docker ps --format '{{.Names}}' | grep -Eq "^${CONTAINER_NAME}$"
}

container_exists() {
    docker ps -a --format '{{.Names}}' | grep -Eq "^${CONTAINER_NAME}$"
}

stop_container() {
    if container_exists; then
        echo "Stopping and removing container '$CONTAINER_NAME'..."
        docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
        echo "Container '$CONTAINER_NAME' stopped."
    else
        echo "Container '$CONTAINER_NAME' is not running."
    fi
}

# Find what process is listening on the target port
get_port_process_info() {
    local target_port="$1"
    local found=0

    # 1. Check if a Docker container is binding the port
    local docker_containers
    docker_containers="$(docker ps --filter "publish=${target_port}" --format 'Container ID: {{.ID}} | Name: {{.Names}} | Image: {{.Image}} | Status: {{.Status}}' 2>/dev/null || true)"
    if [ -n "$docker_containers" ]; then
        echo "Docker Container(s):"
        echo "$docker_containers"
        found=1
    fi

    # 2. Check host processes via lsof, ss, fuser
    if command -v lsof &>/dev/null; then
        local lsof_out
        lsof_out="$(lsof -i ":${target_port}" -sTCP:LISTEN -P -n 2>/dev/null || true)"
        if [ -n "$lsof_out" ]; then
            echo "Host Process (lsof):"
            echo "$lsof_out"
            found=1
        fi
    fi

    if [ "$found" -eq 0 ] && command -v ss &>/dev/null; then
        local ss_out
        ss_out="$(ss -lntp "sport = :${target_port}" 2>/dev/null || true)"
        if [ -n "$ss_out" ]; then
            echo "Socket Info (ss):"
            echo "$ss_out"
            found=1
        fi
    fi
}

get_port_pids() {
    local target_port="$1"
    if command -v lsof &>/dev/null; then
        lsof -t -i ":${target_port}" -sTCP:LISTEN 2>/dev/null || true
    elif command -v fuser &>/dev/null; then
        fuser "${target_port}/tcp" 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' || true
    fi
}

is_port_in_use() {
    local target_port="$1"
    local pids
    pids="$(get_port_pids "$target_port")"
    if [ -n "$pids" ]; then
        return 0
    fi
    # Fallback to checking socket open via bash or ss
    if (ss -lnt 2>/dev/null | grep -Eq "[:.]${target_port}\b") 2>/dev/null; then
        return 0
    fi
    return 1
}

kill_port_process() {
    local target_port="$1"
    local pids
    pids="$(get_port_pids "$target_port")"

    if [ -n "$pids" ]; then
        echo "Attempting to terminate PID(s): $pids..."
        # Try graceful termination first
        kill $pids 2>/dev/null || true
        sleep 1
        # Force kill if still lingering
        pids="$(get_port_pids "$target_port")"
        if [ -n "$pids" ]; then
            echo "Force killing remaining PID(s): $pids..."
            kill -9 $pids 2>/dev/null || true
            sleep 1
        fi
    fi

    # Also check if another Docker container is binding the port
    local other_container
    other_container="$(docker ps --filter "publish=${target_port}" --format '{{.Names}}' 2>/dev/null || true)"
    if [ -n "$other_container" ]; then
        echo "Found Docker container(s) using port ${target_port}: $other_container"
        echo "Stopping container(s)..."
        echo "$other_container" | xargs -r docker rm -f >/dev/null 2>&1 || true
        sleep 1
    fi
}

check_and_resolve_port() {
    local target_port="$1"

    # If the process using the port is our own container, handle that separately
    if is_container_running; then
        return 0
    fi

    if is_port_in_use "$target_port"; then
        echo "=========================================================="
        echo "  Port $target_port is currently in use!"
        echo "=========================================================="
        echo "Process details:"
        get_port_process_info "$target_port" || echo "  (Process details unavailable)"
        echo ""
        echo "Options:"
        echo "  1) Kill process/container on port $target_port and continue"
        echo "  2) Exit without making changes"
        echo ""
        read -rp "Enter choice [1-2]: " choice

        case "$choice" in
            1)
                kill_port_process "$target_port"
                if is_port_in_use "$target_port"; then
                    echo "Error: Failed to free port $target_port. You may need sudo permissions to kill root processes." >&2
                    exit 1
                fi
                echo "Port $target_port successfully freed."
                ;;
            2|*)
                echo "Exiting without starting container."
                exit 0
                ;;
        esac
    fi
}

build_image() {
    echo "Building Docker image '$IMAGE_NAME'..."
    docker build -t "$IMAGE_NAME" -f Dockerfile .
}

run_container() {
    echo "Starting test container '$CONTAINER_NAME' on port $PORT (Mock Device enabled)..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        -p "${PORT}:8080" \
        -e DCLED_MOCK_DEVICE=1 \
        -e PYTHONUNBUFFERED=1 \
        -v "$REPO_ROOT/config.json:/app/config.json" \
        "$IMAGE_NAME"

    echo ""
    echo "=========================================================="
    echo "  DCLED Studio is running in Docker test mode!"
    echo "  Web UI: http://localhost:${PORT}"
    echo "  WebSocket Feed: ws://localhost:${PORT}/ws"
    echo "  Mock Device: Active & Silent"
    echo "=========================================================="
    echo "Use './scripts/start.sh --logs' to inspect output."
    echo "Use './scripts/start.sh --test' to run automated verification."
    echo "Use './scripts/start.sh --stop' to terminate."
    echo ""
}

handle_running_container() {
    echo "Container '$CONTAINER_NAME' is already running!"
    echo ""
    echo "Please choose an action:"
    echo "  1) Stop and recreate container (rebuild image)"
    echo "  2) Stop container"
    echo "  3) Show container logs"
    echo "  4) Exit without making changes"
    echo ""
    read -rp "Enter choice [1-4]: " choice

    case "$choice" in
        1)
            stop_container
            check_and_resolve_port "$PORT"
            build_image
            run_container
            ;;
        2)
            stop_container
            ;;
        3)
            exec docker logs -f "$CONTAINER_NAME"
            ;;
        4|*)
            echo "Exiting without changes."
            exit 0
            ;;
    esac
}

wait_for_health() {
    echo "Waiting for service to be healthy at http://localhost:${PORT}..."
    local attempts=0
    local max_attempts=30
    until curl -s -f "http://localhost:${PORT}/api/state" >/dev/null 2>&1; do
        sleep 1
        attempts=$((attempts + 1))
        if [ "$attempts" -ge "$max_attempts" ]; then
            echo "Timed out waiting for DCLED Studio server." >&2
            docker logs "$CONTAINER_NAME"
            exit 1
        fi
    done
    echo "Server is ready."
}

# ----------------- Command Parsing -----------------
check_docker

case "$1" in
    --help|-h)
        print_usage
        exit 0
        ;;
    --status)
        if is_container_running; then
            echo "Container: RUNNING ($CONTAINER_NAME)"
            docker ps --filter "name=$CONTAINER_NAME"
        elif container_exists; then
            echo "Container: STOPPED ($CONTAINER_NAME exists)"
            docker ps -a --filter "name=$CONTAINER_NAME"
        else
            echo "Container: NOT CREATED ($CONTAINER_NAME)"
        fi
        echo ""
        if is_port_in_use "$PORT"; then
            echo "Port $PORT status: IN USE"
            get_port_process_info "$PORT"
        else
            echo "Port $PORT status: FREE"
        fi
        exit 0
        ;;
    --stop)
        stop_container
        exit 0
        ;;
    --logs)
        if container_exists; then
            exec docker logs -f "$CONTAINER_NAME"
        else
            echo "Container '$CONTAINER_NAME' does not exist." >&2
            exit 1
        fi
        ;;
    --recreate)
        stop_container
        check_and_resolve_port "$PORT"
        build_image
        run_container
        exit 0
        ;;
    --test)
        if ! is_container_running; then
            echo "Container is not running. Starting it now..."
            if container_exists; then
                stop_container
            fi
            check_and_resolve_port "$PORT"
            build_image
            run_container
        fi
        wait_for_health
        echo "Running integration tests inside the container..."
        docker exec -it "$CONTAINER_NAME" python scripts/test_endpoints.py "http://localhost:8080"
        exit 0
        ;;
    "")
        if is_container_running; then
            handle_running_container
        else
            if container_exists; then
                stop_container
            fi
            check_and_resolve_port "$PORT"
            build_image
            run_container
        fi
        ;;
    *)
        echo "Unknown option: $1" >&2
        print_usage
        exit 1
        ;;
esac
