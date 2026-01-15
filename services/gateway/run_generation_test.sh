#!/bin/bash
# Automated test runner for generation pipeline
# This script can optionally start the gateway, then run the test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATEWAY_DIR="$SCRIPT_DIR"
VENV_PATH="$PROJECT_ROOT/services/.core_venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Generation Pipeline Test Runner ===${NC}"

# Check if gateway is already running
check_gateway() {
    if curl -s -f "http://localhost:8000/health" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Start gateway if not running
if ! check_gateway; then
    echo -e "${YELLOW}Gateway is not running. Starting gateway...${NC}"
    
    # Activate venv
    if [ -d "$VENV_PATH" ]; then
        source "$VENV_PATH/bin/activate"
    else
        echo -e "${RED}Error: Virtual environment not found at $VENV_PATH${NC}"
        echo "Please run the launcher first or install dependencies."
        exit 1
    fi
    
    # Start gateway in background
    cd "$GATEWAY_DIR"
    python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --no-access-log > /tmp/gateway_test.log 2>&1 &
    GATEWAY_PID=$!
    
    echo -e "${YELLOW}Waiting for gateway to start (PID: $GATEWAY_PID)...${NC}"
    
    # Wait for gateway to be ready (max 60 seconds)
    for i in {1..30}; do
        if check_gateway; then
            echo -e "${GREEN}Gateway is ready!${NC}"
            break
        fi
        if [ $i -eq 30 ]; then
            echo -e "${RED}Gateway failed to start after 60 seconds${NC}"
            echo "Check logs: /tmp/gateway_test.log"
            kill $GATEWAY_PID 2>/dev/null || true
            exit 1
        fi
        sleep 2
    done
    
    # Run test
    echo -e "${GREEN}Running generation test...${NC}"
    cd "$GATEWAY_DIR"
    python test_generation.py
    TEST_EXIT_CODE=$?
    
    # Stop gateway
    echo -e "${YELLOW}Stopping gateway (PID: $GATEWAY_PID)...${NC}"
    kill $GATEWAY_PID 2>/dev/null || true
    wait $GATEWAY_PID 2>/dev/null || true
    
    exit $TEST_EXIT_CODE
else
    echo -e "${GREEN}Gateway is already running. Running test...${NC}"
    cd "$GATEWAY_DIR"
    
    # Activate venv if available
    if [ -d "$VENV_PATH" ]; then
        source "$VENV_PATH/bin/activate"
    fi
    
    python test_generation.py
    exit $?
fi


