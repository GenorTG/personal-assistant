"""Test STT (Whisper) Service."""
import asyncio
from typing import List

from .config import SERVICES
from .utils import TestResult, TestStatus, http_request, print_section


WHISPER_URL = SERVICES["whisper"].base_url


async def test_health() -> TestResult:
    """Test /health endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{WHISPER_URL}/health")
    
    if error:
        return TestResult("Whisper: GET /health", TestStatus.WARNING, error, time_ms)
    
    if status == 200:
        return TestResult("Whisper: GET /health", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("Whisper: GET /health", TestStatus.WARNING, f"HTTP {status}", time_ms)


async def run_all_stt_tests() -> List[TestResult]:
    """Run all STT service tests."""
    print_section("STT (Whisper) Service Tests")
    
    results: List[TestResult] = []
    
    result = await test_health()
    results.append(result)
    print(result)
    
    return results


if __name__ == "__main__":
    asyncio.run(run_all_stt_tests())

