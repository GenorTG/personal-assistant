"""Test Memory Service API endpoints."""
import asyncio
from typing import List

from .config import SERVICES
from .utils import TestResult, TestStatus, http_request, print_section


MEMORY_URL = SERVICES["memory"].base_url


async def test_health() -> TestResult:
    """Test /health endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{MEMORY_URL}/health")
    
    if error:
        return TestResult("Memory: GET /health", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("Memory: GET /health", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("Memory: GET /health", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_list_conversations() -> TestResult:
    """Test /api/conversations endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{MEMORY_URL}/api/conversations")
    
    if error:
        return TestResult("Memory: GET /api/conversations", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        count = len(data) if isinstance(data, list) else 0
        return TestResult("Memory: GET /api/conversations", TestStatus.PASSED, f"{count} conversations", time_ms)
    
    return TestResult("Memory: GET /api/conversations", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_list_system_prompts() -> TestResult:
    """Test /api/settings/system-prompts endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{MEMORY_URL}/api/settings/system-prompts")
    
    if error:
        return TestResult("Memory: GET /api/settings/system-prompts", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        count = len(data) if isinstance(data, list) else 0
        return TestResult("Memory: GET /api/settings/system-prompts", TestStatus.PASSED, f"{count} prompts", time_ms)
    
    return TestResult("Memory: GET /api/settings/system-prompts", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_retrieve_context() -> TestResult:
    """Test /api/memory/retrieve-context endpoint."""
    test_data = {"query": "test query", "top_k": 5}
    status, data, time_ms, error = await http_request(
        "POST", 
        f"{MEMORY_URL}/api/memory/retrieve-context",
        data=test_data
    )
    
    if error:
        return TestResult("Memory: POST /api/memory/retrieve-context", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("Memory: POST /api/memory/retrieve-context", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("Memory: POST /api/memory/retrieve-context", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def run_all_memory_tests(skip_if_unhealthy: bool = True) -> List[TestResult]:
    """Run all Memory Service tests."""
    print_section("Memory Service API Tests")
    
    results: List[TestResult] = []
    
    # First check health
    health_result = await test_health()
    results.append(health_result)
    print(health_result)
    
    if health_result.status == TestStatus.FAILED and skip_if_unhealthy:
        print("  ⚠️ Memory Service is not healthy - skipping remaining tests")
        return results
    
    # Run other tests
    tests = [
        test_list_conversations,
        test_list_system_prompts,
        test_retrieve_context,
    ]
    
    for test_func in tests:
        result = await test_func()
        results.append(result)
        print(result)
    
    return results


if __name__ == "__main__":
    asyncio.run(run_all_memory_tests())

