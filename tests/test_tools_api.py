"""Test Tool Service API endpoints."""
import asyncio
from typing import List

from .config import SERVICES
from .utils import TestResult, TestStatus, http_request, print_section


TOOLS_URL = SERVICES["tools"].base_url


async def test_health() -> TestResult:
    """Test /health endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{TOOLS_URL}/health")
    
    if error:
        return TestResult("Tools: GET /health", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("Tools: GET /health", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("Tools: GET /health", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_list_tools() -> TestResult:
    """Test /api/tools endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{TOOLS_URL}/api/tools")
    
    if error:
        return TestResult("Tools: GET /api/tools", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        count = data.get("count", 0) if isinstance(data, dict) else 0
        return TestResult("Tools: GET /api/tools", TestStatus.PASSED, f"{count} tools", time_ms)
    
    return TestResult("Tools: GET /api/tools", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_list_reminders() -> TestResult:
    """Test /api/reminders endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{TOOLS_URL}/api/reminders")
    
    if error:
        return TestResult("Tools: GET /api/reminders", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("Tools: GET /api/reminders", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("Tools: GET /api/reminders", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def run_all_tools_tests(skip_if_unhealthy: bool = True) -> List[TestResult]:
    """Run all Tool Service tests."""
    print_section("Tool Service API Tests")
    
    results: List[TestResult] = []
    
    # First check health
    health_result = await test_health()
    results.append(health_result)
    print(health_result)
    
    if health_result.status == TestStatus.FAILED and skip_if_unhealthy:
        print("  ⚠️ Tool Service is not healthy - skipping remaining tests")
        return results
    
    # Run other tests
    tests = [
        test_list_tools,
        test_list_reminders,
    ]
    
    for test_func in tests:
        result = await test_func()
        results.append(result)
        print(result)
    
    return results


if __name__ == "__main__":
    asyncio.run(run_all_tools_tests())

