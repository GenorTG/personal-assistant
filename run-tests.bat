@echo off
REM Personal Assistant Test Suite Runner
REM 
REM Usage:
REM   run-tests.bat              - Run health checks and API tests
REM   run-tests.bat --health     - Only health checks  
REM   run-tests.bat --quick      - Quick health check only
REM   run-tests.bat --gateway    - Only gateway API tests
REM   run-tests.bat --functional - Functional tests (no inference)
REM   run-tests.bat --full       - FULL tests: start services, load model, run inference
REM   run-tests.bat --full --no-gpu  - Full tests using CPU only
REM
REM Full tests will:
REM   - Start services as background processes
REM   - Load an LLM model (GPU if available, else CPU)
REM   - Run actual inference tests
REM   - Clean up automatically when done

echo ============================================================
echo   Personal Assistant - Test Suite
echo ============================================================
echo.

REM Check if aiohttp is installed
python -c "import aiohttp" 2>NUL
if %ERRORLEVEL% NEQ 0 (
    echo Installing test dependencies...
    pip install aiohttp
    echo.
)

REM Run the test suite with any provided arguments
python -m tests.run_tests %*

