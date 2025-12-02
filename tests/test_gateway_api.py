"""Test Gateway API endpoints.

These tests cover the main API endpoints used by the frontend.
"""
import asyncio
from typing import List, Optional
import uuid

from .config import SERVICES
from .utils import TestResult, TestStatus, http_request, print_section


GATEWAY_URL = SERVICES["gateway"].base_url


async def test_health() -> TestResult:
    """Test /health endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/health")
    
    if error:
        return TestResult("GET /health", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /health", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /health", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_services_status() -> TestResult:
    """Test /api/services/status endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/services/status")
    
    if error:
        return TestResult("GET /api/services/status", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/services/status", TestStatus.PASSED, "OK", time_ms, data)
    
    return TestResult("GET /api/services/status", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_system_info() -> TestResult:
    """Test /api/system/info endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/system/info")
    
    if error:
        return TestResult("GET /api/system/info", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/system/info", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/system/info", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_system_status() -> TestResult:
    """Test /api/system/status endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/system/status")
    
    if error:
        return TestResult("GET /api/system/status", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/system/status", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/system/status", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_list_models() -> TestResult:
    """Test /api/models endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/models")
    
    if error:
        return TestResult("GET /api/models", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        count = len(data) if isinstance(data, list) else 0
        return TestResult("GET /api/models", TestStatus.PASSED, f"{count} models found", time_ms)
    
    return TestResult("GET /api/models", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_settings() -> TestResult:
    """Test /api/settings endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/settings")
    
    if error:
        return TestResult("GET /api/settings", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/settings", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/settings", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_conversations_list() -> TestResult:
    """Test /api/conversations endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/conversations")
    
    if error:
        return TestResult("GET /api/conversations", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        count = len(data) if isinstance(data, list) else 0
        return TestResult("GET /api/conversations", TestStatus.PASSED, f"{count} conversations", time_ms)
    
    return TestResult("GET /api/conversations", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_llm_status() -> TestResult:
    """Test /api/llm/status endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/llm/status")
    
    if error:
        return TestResult("GET /api/llm/status", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        model_loaded = data.get("model_loaded", False) if data else False
        msg = "Model loaded" if model_loaded else "No model loaded"
        return TestResult("GET /api/llm/status", TestStatus.PASSED, msg, time_ms)
    
    return TestResult("GET /api/llm/status", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_tts_backends() -> TestResult:
    """Test /api/voice/tts/backends endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/voice/tts/backends")
    
    if error:
        return TestResult("GET /api/voice/tts/backends", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/voice/tts/backends", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/voice/tts/backends", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_tts_settings() -> TestResult:
    """Test /api/voice/tts/settings endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/voice/tts/settings")
    
    if error:
        return TestResult("GET /api/voice/tts/settings", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/voice/tts/settings", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/voice/tts/settings", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_stt_settings() -> TestResult:
    """Test /api/voice/stt/settings endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/voice/stt/settings")
    
    if error:
        return TestResult("GET /api/voice/stt/settings", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/voice/stt/settings", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/voice/stt/settings", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_tools_list() -> TestResult:
    """Test /api/tools endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/tools")
    
    if error:
        return TestResult("GET /api/tools", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        count = len(data.get("tools", [])) if isinstance(data, dict) else 0
        return TestResult("GET /api/tools", TestStatus.PASSED, f"{count} tools", time_ms)
    
    return TestResult("GET /api/tools", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_system_prompts_list() -> TestResult:
    """Test /api/settings/system-prompts endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/settings/system-prompts")
    
    if error:
        return TestResult("GET /api/settings/system-prompts", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        count = len(data) if isinstance(data, list) else 0
        return TestResult("GET /api/settings/system-prompts", TestStatus.PASSED, f"{count} prompts", time_ms)
    
    return TestResult("GET /api/settings/system-prompts", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_memory_settings() -> TestResult:
    """Test /api/settings/memory endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/settings/memory")
    
    if error:
        return TestResult("GET /api/settings/memory", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/settings/memory", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/settings/memory", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_downloads_list() -> TestResult:
    """Test /api/downloads endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/downloads")
    
    if error:
        return TestResult("GET /api/downloads", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/downloads", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/downloads", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_files_list() -> TestResult:
    """Test /api/files endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/files")
    
    if error:
        return TestResult("GET /api/files", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        count = len(data) if isinstance(data, list) else 0
        return TestResult("GET /api/files", TestStatus.PASSED, f"{count} files", time_ms)
    
    return TestResult("GET /api/files", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_debug_info() -> TestResult:
    """Test /api/debug/info endpoint."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/debug/info")
    
    if error:
        return TestResult("GET /api/debug/info", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /api/debug/info", TestStatus.PASSED, "OK", time_ms)
    
    return TestResult("GET /api/debug/info", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def test_openai_models_endpoint() -> TestResult:
    """Test /v1/models (OpenAI-compatible) endpoint.
    
    Note: This endpoint proxies to the LLM service. If LLM service
    is not running, it returns 503 which is expected behavior.
    """
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/v1/models")
    
    if error:
        return TestResult("GET /v1/models (OpenAI)", TestStatus.FAILED, error, time_ms)
    
    if status == 200:
        return TestResult("GET /v1/models (OpenAI)", TestStatus.PASSED, "OK", time_ms)
    
    # 503 is expected when LLM service is not running - mark as warning
    if status == 503:
        return TestResult("GET /v1/models (OpenAI)", TestStatus.WARNING, "LLM service not running (expected)", time_ms)
    
    return TestResult("GET /v1/models (OpenAI)", TestStatus.FAILED, f"HTTP {status}", time_ms)


async def run_all_gateway_tests(skip_if_unhealthy: bool = True) -> List[TestResult]:
    """Run all gateway API tests."""
    print_section("Gateway API Tests")
    
    results: List[TestResult] = []
    
    # First check if gateway is healthy
    health_result = await test_health()
    results.append(health_result)
    print(health_result)
    
    if health_result.status == TestStatus.FAILED and skip_if_unhealthy:
        print("  ⚠️ Gateway is not healthy - skipping remaining tests")
        return results
    
    # Define all tests to run
    tests = [
        test_services_status,
        test_system_info,
        test_system_status,
        test_llm_status,
        test_settings,
        test_list_models,
        test_conversations_list,
        test_tts_backends,
        test_tts_settings,
        test_stt_settings,
        test_tools_list,
        test_system_prompts_list,
        test_memory_settings,
        test_downloads_list,
        test_files_list,
        test_debug_info,
        test_openai_models_endpoint,
    ]
    
    # Run tests sequentially to avoid overwhelming the server
    for test_func in tests:
        result = await test_func()
        results.append(result)
        print(result)
    
    return results


if __name__ == "__main__":
    asyncio.run(run_all_gateway_tests())

