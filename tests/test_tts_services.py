"""Test TTS Services (Piper, Kokoro, Chatterbox)."""
import asyncio
from typing import List

from .config import SERVICES
from .utils import TestResult, TestStatus, http_request, print_section


async def test_piper_health() -> TestResult:
    """Test Piper /health endpoint."""
    config = SERVICES["piper"]
    status, data, time_ms, error = await http_request("GET", f"{config.base_url}/health")
    
    if error:
        return TestResult("Piper: GET /health", TestStatus.WARNING, error, time_ms)
    
    if status == 200:
        return TestResult("Piper: GET /health", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("Piper: GET /health", TestStatus.WARNING, f"HTTP {status}", time_ms)


async def test_kokoro_health() -> TestResult:
    """Test Kokoro /health endpoint."""
    config = SERVICES["kokoro"]
    status, data, time_ms, error = await http_request("GET", f"{config.base_url}/health")
    
    if error:
        return TestResult("Kokoro: GET /health", TestStatus.WARNING, error, time_ms)
    
    if status == 200:
        return TestResult("Kokoro: GET /health", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("Kokoro: GET /health", TestStatus.WARNING, f"HTTP {status}", time_ms)


async def test_chatterbox_health() -> TestResult:
    """Test Chatterbox /health endpoint."""
    config = SERVICES["chatterbox"]
    status, data, time_ms, error = await http_request("GET", f"{config.base_url}/health")
    
    if error:
        return TestResult("Chatterbox: GET /health", TestStatus.WARNING, error, time_ms)
    
    if status == 200:
        return TestResult("Chatterbox: GET /health", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("Chatterbox: GET /health", TestStatus.WARNING, f"HTTP {status}", time_ms)


async def run_all_tts_tests() -> List[TestResult]:
    """Run all TTS service tests."""
    print_section("TTS Services Tests")
    
    results: List[TestResult] = []
    
    tests = [
        test_piper_health,
        test_kokoro_health,
        test_chatterbox_health,
    ]
    
    for test_func in tests:
        result = await test_func()
        results.append(result)
        print(result)
    
    return results


if __name__ == "__main__":
    asyncio.run(run_all_tts_tests())

