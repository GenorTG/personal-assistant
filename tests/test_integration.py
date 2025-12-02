"""Integration tests that simulate actual frontend usage patterns.

These tests verify that the services work together correctly,
mimicking real user workflows.
"""
import asyncio
from typing import List, Optional
import uuid

from .config import SERVICES
from .utils import TestResult, TestStatus, http_request, print_section


GATEWAY_URL = SERVICES["gateway"].base_url


async def test_frontend_initial_load() -> List[TestResult]:
    """
    Test the API calls made when frontend loads.
    
    Frontend calls these on initial load:
    1. GET /health
    2. GET /api/settings
    3. GET /api/models
    4. GET /api/conversations
    5. GET /api/llm/status
    6. GET /api/voice/tts/backends
    7. GET /api/services/status
    """
    print_section("Integration: Frontend Initial Load")
    results: List[TestResult] = []
    
    endpoints = [
        ("GET", "/health", "Health check"),
        ("GET", "/api/settings", "Load settings"),
        ("GET", "/api/models", "List models"),
        ("GET", "/api/conversations", "List conversations"),
        ("GET", "/api/llm/status", "LLM status"),
        ("GET", "/api/voice/tts/backends", "TTS backends"),
        ("GET", "/api/services/status", "Services status"),
    ]
    
    for method, endpoint, description in endpoints:
        status, data, time_ms, error = await http_request(method, f"{GATEWAY_URL}{endpoint}")
        
        if error:
            result = TestResult(f"FrontendLoad: {description}", TestStatus.FAILED, error, time_ms)
        elif status == 200:
            result = TestResult(f"FrontendLoad: {description}", TestStatus.PASSED, "OK", time_ms)
        else:
            result = TestResult(f"FrontendLoad: {description}", TestStatus.FAILED, f"HTTP {status}", time_ms)
        
        results.append(result)
        print(result)
    
    return results


async def test_conversation_workflow() -> List[TestResult]:
    """
    Test a typical conversation workflow:
    1. Create a new conversation
    2. Get conversation list (verify it exists)
    3. Delete the conversation
    """
    print_section("Integration: Conversation Workflow")
    results: List[TestResult] = []
    
    created_id: Optional[str] = None
    
    # Step 1: Create a new conversation
    status, data, time_ms, error = await http_request(
        "POST", 
        f"{GATEWAY_URL}/api/conversations/new"
    )
    
    if error:
        result = TestResult("ConversationFlow: Create", TestStatus.FAILED, error, time_ms)
        results.append(result)
        print(result)
        return results  # Can't continue without conversation
    
    if status == 200 and data:
        created_id = data.get("conversation_id")
        result = TestResult("ConversationFlow: Create", TestStatus.PASSED, f"ID: {created_id[:8]}..." if created_id else "Created", time_ms)
    else:
        result = TestResult("ConversationFlow: Create", TestStatus.FAILED, f"HTTP {status}", time_ms)
        results.append(result)
        print(result)
        return results
    
    results.append(result)
    print(result)
    
    # Step 2: List conversations (verify it exists)
    status, data, time_ms, error = await http_request(
        "GET",
        f"{GATEWAY_URL}/api/conversations"
    )
    
    if status == 200:
        conversations = data if isinstance(data, list) else []
        found = any(c.get("conversation_id") == created_id or c.get("id") == created_id for c in conversations)
        if found:
            result = TestResult("ConversationFlow: Verify", TestStatus.PASSED, "Found in list", time_ms)
        else:
            result = TestResult("ConversationFlow: Verify", TestStatus.WARNING, "Not found in list", time_ms)
    else:
        result = TestResult("ConversationFlow: Verify", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    results.append(result)
    print(result)
    
    # Step 3: Delete the conversation
    if created_id:
        status, data, time_ms, error = await http_request(
            "DELETE",
            f"{GATEWAY_URL}/api/conversations/{created_id}"
        )
        
        if status == 200:
            result = TestResult("ConversationFlow: Delete", TestStatus.PASSED, "Deleted", time_ms)
        else:
            result = TestResult("ConversationFlow: Delete", TestStatus.WARNING, f"HTTP {status}", time_ms)
        
        results.append(result)
        print(result)
    
    return results


async def test_model_listing_workflow() -> List[TestResult]:
    """
    Test model management workflow:
    1. List available models
    2. Get all model metadata
    """
    print_section("Integration: Model Listing")
    results: List[TestResult] = []
    
    # List models
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/models")
    
    if error:
        result = TestResult("ModelListing: List", TestStatus.FAILED, error, time_ms)
    elif status == 200:
        count = len(data) if isinstance(data, list) else 0
        result = TestResult("ModelListing: List", TestStatus.PASSED, f"{count} models", time_ms)
    else:
        result = TestResult("ModelListing: List", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    results.append(result)
    print(result)
    
    # Get all metadata
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/models/all-metadata")
    
    if error:
        result = TestResult("ModelListing: Metadata", TestStatus.FAILED, error, time_ms)
    elif status == 200:
        result = TestResult("ModelListing: Metadata", TestStatus.PASSED, "OK", time_ms)
    else:
        result = TestResult("ModelListing: Metadata", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    results.append(result)
    print(result)
    
    return results


async def test_settings_workflow() -> List[TestResult]:
    """
    Test settings workflow:
    1. Get current settings
    2. Get system prompts
    3. Get memory settings
    """
    print_section("Integration: Settings Workflow")
    results: List[TestResult] = []
    
    endpoints = [
        ("/api/settings", "Main settings"),
        ("/api/settings/system-prompts", "System prompts"),
        ("/api/settings/memory", "Memory settings"),
    ]
    
    for endpoint, description in endpoints:
        status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}{endpoint}")
        
        if error:
            result = TestResult(f"Settings: {description}", TestStatus.FAILED, error, time_ms)
        elif status == 200:
            result = TestResult(f"Settings: {description}", TestStatus.PASSED, "OK", time_ms)
        else:
            result = TestResult(f"Settings: {description}", TestStatus.FAILED, f"HTTP {status}", time_ms)
        
        results.append(result)
        print(result)
    
    return results


async def test_voice_workflow() -> List[TestResult]:
    """
    Test voice-related endpoints:
    1. Get TTS backends
    2. Get TTS settings
    3. Get STT settings
    """
    print_section("Integration: Voice Workflow")
    results: List[TestResult] = []
    
    endpoints = [
        ("/api/voice/tts/backends", "TTS backends"),
        ("/api/voice/tts/settings", "TTS settings"),
        ("/api/voice/stt/settings", "STT settings"),
    ]
    
    for endpoint, description in endpoints:
        status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}{endpoint}")
        
        if error:
            result = TestResult(f"Voice: {description}", TestStatus.FAILED, error, time_ms)
        elif status == 200:
            result = TestResult(f"Voice: {description}", TestStatus.PASSED, "OK", time_ms)
        else:
            result = TestResult(f"Voice: {description}", TestStatus.FAILED, f"HTTP {status}", time_ms)
        
        results.append(result)
        print(result)
    
    return results


async def run_all_integration_tests(skip_if_gateway_unhealthy: bool = True) -> List[TestResult]:
    """Run all integration tests."""
    print_section("INTEGRATION TESTS")
    
    # First check if gateway is available
    status, _, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/health")
    
    if error or status != 200:
        print("⚠️ Gateway is not healthy - skipping integration tests")
        return [TestResult("Integration: Gateway Check", TestStatus.FAILED, error or f"HTTP {status}", time_ms)]
    
    all_results: List[TestResult] = []
    
    # Run each workflow
    all_results.extend(await test_frontend_initial_load())
    all_results.extend(await test_conversation_workflow())
    all_results.extend(await test_model_listing_workflow())
    all_results.extend(await test_settings_workflow())
    all_results.extend(await test_voice_workflow())
    
    return all_results


if __name__ == "__main__":
    asyncio.run(run_all_integration_tests())

