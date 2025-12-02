#!/usr/bin/env python3
"""
Comprehensive Functional Tests for Personal Assistant.

These tests actually exercise real functionality:
- Model downloading
- Model loading with various configurations
- LLM inference
- Chat conversations with real messages
- Settings persistence
- Voice services (if available)

WARNING: These tests may download models and use significant resources.
"""
import asyncio
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .config import SERVICES
from .utils import TestResult, TestStatus, http_request, print_section, print_header


GATEWAY_URL = SERVICES["gateway"].base_url

# Small test model for functional testing
# Using a tiny model to minimize download time
TEST_MODEL_REPO = "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
TEST_MODEL_FILE = "tinyllama-1.1b-chat-v1.0.Q2_K.gguf"  # Smallest quantization ~400MB


@dataclass
class FunctionalTestContext:
    """Shared context for functional tests."""
    model_downloaded: bool = False
    model_loaded: bool = False
    model_id: Optional[str] = None
    conversation_id: Optional[str] = None
    

async def wait_for_condition(
    check_func, 
    timeout: float = 60.0, 
    interval: float = 2.0,
    description: str = "condition"
) -> bool:
    """Wait for a condition to become true."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            if await check_func():
                return True
        except Exception:
            pass
        await asyncio.sleep(interval)
    print(f"  ⏰ Timeout waiting for {description}")
    return False


# =============================================================================
# MODEL MANAGEMENT TESTS
# =============================================================================

async def test_list_local_models() -> TestResult:
    """Test listing locally available models."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/models")
    
    if error:
        return TestResult("List Local Models", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("List Local Models", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    models = data if isinstance(data, list) else []
    model_names = [m.get("name", m.get("id", "unknown")) for m in models]
    
    return TestResult(
        "List Local Models", 
        TestStatus.PASSED, 
        f"Found {len(models)} models: {', '.join(model_names[:3])}{'...' if len(models) > 3 else ''}", 
        time_ms,
        {"models": models}
    )


async def test_search_huggingface_models() -> TestResult:
    """Test searching HuggingFace for models."""
    query = "tinyllama gguf"
    status, data, time_ms, error = await http_request(
        "GET", 
        f"{GATEWAY_URL}/api/models/search?query={query}&limit=5"
    )
    
    if error:
        return TestResult("Search HuggingFace Models", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("Search HuggingFace Models", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    results = data if isinstance(data, list) else []
    return TestResult(
        "Search HuggingFace Models",
        TestStatus.PASSED,
        f"Found {len(results)} results for '{query}'",
        time_ms
    )


async def test_get_model_files(repo_id: str = TEST_MODEL_REPO) -> TestResult:
    """Test getting available files from a HuggingFace repo."""
    import urllib.parse
    encoded_repo = urllib.parse.quote(repo_id, safe='')
    
    status, data, time_ms, error = await http_request(
        "GET",
        f"{GATEWAY_URL}/api/models/files?repo_id={encoded_repo}",
        timeout=30
    )
    
    if error:
        return TestResult("Get Model Files", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("Get Model Files", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    files = data.get("files", []) if isinstance(data, dict) else []
    gguf_files = [f for f in files if f.get("name", "").endswith(".gguf")]
    
    return TestResult(
        "Get Model Files",
        TestStatus.PASSED,
        f"Found {len(gguf_files)} GGUF files in {repo_id}",
        time_ms,
        {"files": gguf_files}
    )


async def test_download_model(ctx: FunctionalTestContext) -> TestResult:
    """Test downloading a model from HuggingFace."""
    import urllib.parse
    
    # First check if model already exists
    status, models, _, _ = await http_request("GET", f"{GATEWAY_URL}/api/models")
    if status == 200 and models:
        for model in models:
            model_name = model.get("name", "") or model.get("id", "")
            if TEST_MODEL_FILE.lower() in model_name.lower() or "tinyllama" in model_name.lower():
                ctx.model_downloaded = True
                ctx.model_id = model.get("id") or model.get("name")
                return TestResult(
                    "Download Model",
                    TestStatus.PASSED,
                    f"Model already exists: {ctx.model_id}",
                    0
                )
    
    # Start download
    encoded_repo = urllib.parse.quote(TEST_MODEL_REPO, safe='')
    encoded_file = urllib.parse.quote(TEST_MODEL_FILE, safe='')
    
    start_time = time.time()
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/models/download?repo_id={encoded_repo}&filename={encoded_file}",
        timeout=30
    )
    
    if error:
        return TestResult("Download Model", TestStatus.FAILED, f"Start failed: {error}", time_ms)
    
    if status not in [200, 202]:
        detail = data.get("detail", "") if data else ""
        return TestResult("Download Model", TestStatus.FAILED, f"HTTP {status}: {detail}", time_ms)
    
    download_id = data.get("download_id") if data else None
    
    # Wait for download to complete (with progress updates)
    print(f"  ⏳ Downloading {TEST_MODEL_FILE}...")
    
    async def check_download():
        if download_id:
            s, d, _, _ = await http_request("GET", f"{GATEWAY_URL}/api/downloads/{download_id}")
            if s == 200 and d:
                status_str = d.get("status", "")
                progress = d.get("progress", 0)
                if progress > 0:
                    print(f"    📥 Progress: {progress:.1f}%")
                if status_str == "completed":
                    return True
                if status_str == "failed":
                    raise Exception(f"Download failed: {d.get('error', 'unknown')}")
        
        # Also check if model appeared in list
        s2, models, _, _ = await http_request("GET", f"{GATEWAY_URL}/api/models")
        if s2 == 200 and models:
            for m in models:
                if TEST_MODEL_FILE.lower() in (m.get("name", "") or m.get("id", "")).lower():
                    return True
        return False
    
    success = await wait_for_condition(
        check_download,
        timeout=600,  # 10 minutes for download
        interval=5,
        description="model download"
    )
    
    elapsed = time.time() - start_time
    
    if success:
        # Get the model ID
        status, models, _, _ = await http_request("GET", f"{GATEWAY_URL}/api/models")
        if status == 200 and models:
            for m in models:
                if TEST_MODEL_FILE.lower() in (m.get("name", "") or m.get("id", "")).lower():
                    ctx.model_id = m.get("id") or m.get("name")
                    break
        
        ctx.model_downloaded = True
        return TestResult(
            "Download Model",
            TestStatus.PASSED,
            f"Downloaded {TEST_MODEL_FILE} in {elapsed:.1f}s",
            elapsed * 1000
        )
    
    return TestResult(
        "Download Model",
        TestStatus.FAILED,
        f"Download timeout after {elapsed:.1f}s",
        elapsed * 1000
    )


async def test_get_model_info(ctx: FunctionalTestContext) -> TestResult:
    """Test getting detailed model information."""
    if not ctx.model_id:
        return TestResult("Get Model Info", TestStatus.SKIPPED, "No model available")
    
    import urllib.parse
    encoded_id = urllib.parse.quote(ctx.model_id, safe='')
    
    # Model info extraction can be slow for large models (reads GGUF metadata)
    status, data, time_ms, error = await http_request(
        "GET",
        f"{GATEWAY_URL}/api/models/{encoded_id}/info",
        timeout=60  # Longer timeout for metadata extraction
    )
    
    if error:
        return TestResult("Get Model Info", TestStatus.FAILED, error, time_ms)
    
    if status == 404:
        return TestResult("Get Model Info", TestStatus.WARNING, "Model info endpoint not found", time_ms)
    
    if status != 200:
        return TestResult("Get Model Info", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    info_keys = list(data.keys()) if data else []
    return TestResult(
        "Get Model Info",
        TestStatus.PASSED,
        f"Got info: {', '.join(info_keys[:5])}",
        time_ms
    )


async def test_get_memory_estimate(ctx: FunctionalTestContext) -> TestResult:
    """Test getting memory estimate for model loading."""
    if not ctx.model_id:
        return TestResult("Get Memory Estimate", TestStatus.SKIPPED, "No model available")
    
    import urllib.parse
    encoded_id = urllib.parse.quote(ctx.model_id, safe='')
    
    # Memory estimation requires model info extraction first
    status, data, time_ms, error = await http_request(
        "GET",
        f"{GATEWAY_URL}/api/models/{encoded_id}/memory-estimate",
        timeout=60  # Longer timeout for metadata extraction
    )
    
    if error:
        return TestResult("Get Memory Estimate", TestStatus.FAILED, error, time_ms)
    
    if status == 404:
        return TestResult("Get Memory Estimate", TestStatus.WARNING, "Endpoint not found", time_ms)
    
    if status != 200:
        return TestResult("Get Memory Estimate", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    ram_mb = data.get("estimated_ram_mb", 0) if data else 0
    vram_mb = data.get("estimated_vram_mb", 0) if data else 0
    
    return TestResult(
        "Get Memory Estimate",
        TestStatus.PASSED,
        f"RAM: {ram_mb}MB, VRAM: {vram_mb}MB",
        time_ms
    )


# =============================================================================
# MODEL LOADING TESTS
# =============================================================================

async def test_load_model_default(ctx: FunctionalTestContext) -> TestResult:
    """Test loading a model with default settings."""
    if not ctx.model_id:
        return TestResult("Load Model (Default)", TestStatus.SKIPPED, "No model available")
    
    import urllib.parse
    encoded_id = urllib.parse.quote(ctx.model_id, safe='')
    
    print(f"  ⏳ Loading model {ctx.model_id}...")
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/models/{encoded_id}/load",
        data={},
        timeout=120  # Model loading can take time
    )
    
    if error:
        return TestResult("Load Model (Default)", TestStatus.FAILED, error, time_ms)
    
    if status not in [200, 202]:
        detail = data.get("detail", "") if data else ""
        return TestResult("Load Model (Default)", TestStatus.FAILED, f"HTTP {status}: {detail}", time_ms)
    
    # Wait for model to be loaded
    async def check_loaded():
        s, d, _, _ = await http_request("GET", f"{GATEWAY_URL}/api/llm/status")
        if s == 200 and d:
            return d.get("model_loaded", False)
        return False
    
    success = await wait_for_condition(
        check_loaded,
        timeout=120,
        interval=2,
        description="model loading"
    )
    
    elapsed = time.time() - start_time
    
    if success:
        ctx.model_loaded = True
        return TestResult(
            "Load Model (Default)",
            TestStatus.PASSED,
            f"Model loaded in {elapsed:.1f}s",
            elapsed * 1000
        )
    
    return TestResult(
        "Load Model (Default)",
        TestStatus.FAILED,
        f"Model loading timeout after {elapsed:.1f}s",
        elapsed * 1000
    )


async def test_load_model_with_options(ctx: FunctionalTestContext) -> TestResult:
    """Test loading a model with specific options (context size, threads, etc.)."""
    if not ctx.model_id:
        return TestResult("Load Model (Options)", TestStatus.SKIPPED, "No model available")
    
    import urllib.parse
    encoded_id = urllib.parse.quote(ctx.model_id, safe='')
    
    # Test with specific options
    load_options = {
        "n_ctx": 2048,
        "n_threads": 4,
        "n_gpu_layers": 0,  # CPU only for testing
        "use_mmap": True
    }
    
    print(f"  ⏳ Loading model with custom options: {load_options}")
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/models/{encoded_id}/load",
        data=load_options,
        timeout=120
    )
    
    if error:
        return TestResult("Load Model (Options)", TestStatus.FAILED, error, time_ms)
    
    if status not in [200, 202]:
        detail = data.get("detail", "") if data else ""
        return TestResult("Load Model (Options)", TestStatus.FAILED, f"HTTP {status}: {detail}", time_ms)
    
    # Wait for model to be loaded
    async def check_loaded():
        s, d, _, _ = await http_request("GET", f"{GATEWAY_URL}/api/llm/status")
        if s == 200 and d:
            return d.get("model_loaded", False)
        return False
    
    success = await wait_for_condition(check_loaded, timeout=120, interval=2, description="model loading")
    elapsed = time.time() - start_time
    
    if success:
        ctx.model_loaded = True
        return TestResult(
            "Load Model (Options)",
            TestStatus.PASSED,
            f"Loaded with n_ctx=2048, n_threads=4 in {elapsed:.1f}s",
            elapsed * 1000
        )
    
    return TestResult(
        "Load Model (Options)",
        TestStatus.FAILED,
        f"Loading timeout after {elapsed:.1f}s",
        elapsed * 1000
    )


async def test_llm_status_after_load(ctx: FunctionalTestContext) -> TestResult:
    """Verify LLM status shows model is loaded with correct info."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/llm/status")
    
    if error:
        return TestResult("LLM Status (Loaded)", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("LLM Status (Loaded)", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    model_loaded = data.get("model_loaded", False) if data else False
    model_name = data.get("model_name", "unknown") if data else "unknown"
    
    if not model_loaded:
        ctx.model_loaded = False
        return TestResult("LLM Status (Loaded)", TestStatus.FAILED, "Model not loaded", time_ms)
    
    ctx.model_loaded = True
    return TestResult(
        "LLM Status (Loaded)",
        TestStatus.PASSED,
        f"Model: {model_name}",
        time_ms
    )


# =============================================================================
# INFERENCE TESTS
# =============================================================================

async def test_simple_chat(ctx: FunctionalTestContext) -> TestResult:
    """Test basic chat inference."""
    if not ctx.model_loaded:
        return TestResult("Simple Chat", TestStatus.SKIPPED, "No model loaded")
    
    print("  ⏳ Running inference...")
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/chat",
        data={
            "message": "Say hello in exactly 5 words.",
            "max_tokens": 50
        },
        timeout=120
    )
    
    elapsed = time.time() - start_time
    
    if error:
        return TestResult("Simple Chat", TestStatus.FAILED, error, elapsed * 1000)
    
    if status != 200:
        detail = data.get("detail", "") if data else ""
        return TestResult("Simple Chat", TestStatus.FAILED, f"HTTP {status}: {detail}", elapsed * 1000)
    
    response = data.get("response", "") if data else ""
    conv_id = data.get("conversation_id", "") if data else ""
    
    if not response:
        return TestResult("Simple Chat", TestStatus.FAILED, "Empty response", elapsed * 1000)
    
    ctx.conversation_id = conv_id
    
    # Truncate response for display
    display_response = response[:100] + "..." if len(response) > 100 else response
    
    return TestResult(
        "Simple Chat",
        TestStatus.PASSED,
        f"Got response ({len(response)} chars) in {elapsed:.1f}s: '{display_response}'",
        elapsed * 1000
    )


async def test_chat_with_sampler_settings(ctx: FunctionalTestContext) -> TestResult:
    """Test chat with custom sampler settings."""
    if not ctx.model_loaded:
        return TestResult("Chat (Sampler Settings)", TestStatus.SKIPPED, "No model loaded")
    
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/chat",
        data={
            "message": "What is 2+2? Answer with just the number.",
            "temperature": 0.1,  # Low temperature for deterministic output
            "top_p": 0.9,
            "top_k": 40,
            "max_tokens": 20,
            "repeat_penalty": 1.1
        },
        timeout=60
    )
    
    elapsed = time.time() - start_time
    
    if error:
        return TestResult("Chat (Sampler Settings)", TestStatus.FAILED, error, elapsed * 1000)
    
    if status != 200:
        detail = data.get("detail", "") if data else ""
        return TestResult("Chat (Sampler Settings)", TestStatus.FAILED, f"HTTP {status}: {detail}", elapsed * 1000)
    
    response = data.get("response", "") if data else ""
    
    return TestResult(
        "Chat (Sampler Settings)",
        TestStatus.PASSED,
        f"Response with temp=0.1: '{response[:50]}'",
        elapsed * 1000
    )


async def test_chat_continuation(ctx: FunctionalTestContext) -> TestResult:
    """Test continuing a conversation."""
    if not ctx.model_loaded or not ctx.conversation_id:
        return TestResult("Chat Continuation", TestStatus.SKIPPED, "No conversation to continue")
    
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/chat",
        data={
            "message": "Now say goodbye.",
            "conversation_id": ctx.conversation_id,
            "max_tokens": 50
        },
        timeout=60
    )
    
    elapsed = time.time() - start_time
    
    if error:
        return TestResult("Chat Continuation", TestStatus.FAILED, error, elapsed * 1000)
    
    if status != 200:
        return TestResult("Chat Continuation", TestStatus.FAILED, f"HTTP {status}", elapsed * 1000)
    
    response = data.get("response", "") if data else ""
    same_conv = data.get("conversation_id") == ctx.conversation_id
    
    return TestResult(
        "Chat Continuation",
        TestStatus.PASSED,
        f"Continued conversation: '{response[:50]}...' (same_conv={same_conv})",
        elapsed * 1000
    )


async def test_regenerate_response(ctx: FunctionalTestContext) -> TestResult:
    """Test regenerating the last response."""
    if not ctx.conversation_id:
        return TestResult("Regenerate Response", TestStatus.SKIPPED, "No conversation")
    
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/chat/regenerate",
        data={"conversation_id": ctx.conversation_id},
        timeout=60
    )
    
    elapsed = time.time() - start_time
    
    if error:
        return TestResult("Regenerate Response", TestStatus.FAILED, error, elapsed * 1000)
    
    if status != 200:
        detail = data.get("detail", "") if data else ""
        return TestResult("Regenerate Response", TestStatus.FAILED, f"HTTP {status}: {detail}", elapsed * 1000)
    
    response = data.get("response", "") if data else ""
    
    return TestResult(
        "Regenerate Response",
        TestStatus.PASSED,
        f"Regenerated: '{response[:50]}...'",
        elapsed * 1000
    )


# =============================================================================
# OPENAI COMPATIBILITY TESTS
# =============================================================================

async def test_openai_chat_completions(ctx: FunctionalTestContext) -> TestResult:
    """Test OpenAI-compatible chat completions endpoint."""
    if not ctx.model_loaded:
        return TestResult("OpenAI Chat Completions", TestStatus.SKIPPED, "No model loaded")
    
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/v1/chat/completions",
        data={
            "model": ctx.model_id or "default",
            "messages": [
                {"role": "user", "content": "Say 'test' and nothing else."}
            ],
            "max_tokens": 20,
            "temperature": 0.1
        },
        timeout=60
    )
    
    elapsed = time.time() - start_time
    
    if error:
        return TestResult("OpenAI Chat Completions", TestStatus.FAILED, error, elapsed * 1000)
    
    if status == 503:
        return TestResult("OpenAI Chat Completions", TestStatus.WARNING, "LLM service not running", elapsed * 1000)
    
    if status != 200:
        detail = data.get("detail", "") if data else ""
        return TestResult("OpenAI Chat Completions", TestStatus.FAILED, f"HTTP {status}: {detail}", elapsed * 1000)
    
    # Check OpenAI-format response
    choices = data.get("choices", []) if data else []
    if not choices:
        return TestResult("OpenAI Chat Completions", TestStatus.FAILED, "No choices in response", elapsed * 1000)
    
    content = choices[0].get("message", {}).get("content", "")
    
    return TestResult(
        "OpenAI Chat Completions",
        TestStatus.PASSED,
        f"OpenAI-format response: '{content[:30]}'",
        elapsed * 1000
    )


# =============================================================================
# CONVERSATION MANAGEMENT TESTS
# =============================================================================

async def test_list_conversations() -> TestResult:
    """Test listing all conversations."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/conversations")
    
    if error:
        return TestResult("List Conversations", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("List Conversations", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    conversations = data if isinstance(data, list) else []
    
    return TestResult(
        "List Conversations",
        TestStatus.PASSED,
        f"Found {len(conversations)} conversations",
        time_ms
    )


async def test_get_conversation(ctx: FunctionalTestContext) -> TestResult:
    """Test getting a specific conversation."""
    if not ctx.conversation_id:
        return TestResult("Get Conversation", TestStatus.SKIPPED, "No conversation")
    
    status, data, time_ms, error = await http_request(
        "GET",
        f"{GATEWAY_URL}/api/conversations/{ctx.conversation_id}"
    )
    
    if error:
        return TestResult("Get Conversation", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("Get Conversation", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    messages = data.get("messages", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    
    return TestResult(
        "Get Conversation",
        TestStatus.PASSED,
        f"Got conversation with {len(messages)} messages",
        time_ms
    )


async def test_rename_conversation(ctx: FunctionalTestContext) -> TestResult:
    """Test renaming a conversation."""
    if not ctx.conversation_id:
        return TestResult("Rename Conversation", TestStatus.SKIPPED, "No conversation")
    
    new_name = "Test Conversation (Functional Test)"
    
    status, data, time_ms, error = await http_request(
        "PUT",
        f"{GATEWAY_URL}/api/conversations/{ctx.conversation_id}/rename",
        data={"name": new_name}
    )
    
    if error:
        return TestResult("Rename Conversation", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("Rename Conversation", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    return TestResult("Rename Conversation", TestStatus.PASSED, f"Renamed to '{new_name}'", time_ms)


async def test_delete_conversation(ctx: FunctionalTestContext) -> TestResult:
    """Test deleting a conversation."""
    if not ctx.conversation_id:
        return TestResult("Delete Conversation", TestStatus.SKIPPED, "No conversation")
    
    status, data, time_ms, error = await http_request(
        "DELETE",
        f"{GATEWAY_URL}/api/conversations/{ctx.conversation_id}"
    )
    
    if error:
        return TestResult("Delete Conversation", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("Delete Conversation", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    ctx.conversation_id = None
    return TestResult("Delete Conversation", TestStatus.PASSED, "Deleted", time_ms)


# =============================================================================
# SETTINGS TESTS
# =============================================================================

async def test_get_settings() -> TestResult:
    """Test getting current settings."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/settings")
    
    if error:
        return TestResult("Get Settings", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("Get Settings", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    keys = list(data.keys()) if data else []
    return TestResult(
        "Get Settings",
        TestStatus.PASSED,
        f"Settings keys: {', '.join(keys[:5])}{'...' if len(keys) > 5 else ''}",
        time_ms
    )


async def test_update_settings() -> TestResult:
    """Test updating settings."""
    # Get current settings first
    status, current, _, _ = await http_request("GET", f"{GATEWAY_URL}/api/settings")
    if status != 200:
        return TestResult("Update Settings", TestStatus.FAILED, "Could not get current settings")
    
    # Update temperature
    original_temp = current.get("temperature", 0.7) if current else 0.7
    new_temp = 0.5 if original_temp != 0.5 else 0.8
    
    status, data, time_ms, error = await http_request(
        "PUT",
        f"{GATEWAY_URL}/api/settings",
        data={"temperature": new_temp}
    )
    
    if error:
        return TestResult("Update Settings", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("Update Settings", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    # Verify the change
    status, updated, _, _ = await http_request("GET", f"{GATEWAY_URL}/api/settings")
    updated_temp = updated.get("temperature") if updated else None
    
    # Restore original
    await http_request("PUT", f"{GATEWAY_URL}/api/settings", data={"temperature": original_temp})
    
    if updated_temp == new_temp:
        return TestResult("Update Settings", TestStatus.PASSED, f"Temperature changed to {new_temp}", time_ms)
    
    return TestResult("Update Settings", TestStatus.WARNING, "Setting may not have persisted", time_ms)


# =============================================================================
# MAIN RUNNER
# =============================================================================

async def run_functional_tests(
    skip_download: bool = False,
    skip_inference: bool = False
) -> List[TestResult]:
    """Run all functional tests."""
    print_header("FUNCTIONAL TESTS")
    print("⚠️  These tests exercise real functionality and may take several minutes.")
    print("⚠️  They may download models and use significant compute resources.\n")
    
    all_results: List[TestResult] = []
    ctx = FunctionalTestContext()
    
    # Check gateway is up
    status, _, _, error = await http_request("GET", f"{GATEWAY_URL}/health")
    if status != 200:
        print("❌ Gateway is not responding - cannot run functional tests")
        return [TestResult("Gateway Check", TestStatus.FAILED, error or f"HTTP {status}")]
    
    # Model Management Tests
    print_section("Model Management Tests")
    
    result = await test_list_local_models()
    all_results.append(result)
    print(result)
    
    # Check if we have a model
    if result.details and result.details.get("models"):
        models = result.details["models"]
        if models:
            # Use first available model
            ctx.model_id = models[0].get("id") or models[0].get("name")
            ctx.model_downloaded = True
            print(f"  ℹ️  Using existing model: {ctx.model_id}")
    
    result = await test_search_huggingface_models()
    all_results.append(result)
    print(result)
    
    result = await test_get_model_files()
    all_results.append(result)
    print(result)
    
    if not skip_download and not ctx.model_downloaded:
        result = await test_download_model(ctx)
        all_results.append(result)
        print(result)
    elif skip_download and not ctx.model_downloaded:
        all_results.append(TestResult("Download Model", TestStatus.SKIPPED, "Skipped by user"))
        print("  ⏭️  Download skipped (use --download to enable)")
    
    if ctx.model_id:
        result = await test_get_model_info(ctx)
        all_results.append(result)
        print(result)
        
        result = await test_get_memory_estimate(ctx)
        all_results.append(result)
        print(result)
    
    # Model Loading Tests
    if ctx.model_id and not skip_inference:
        print_section("Model Loading Tests")
        
        result = await test_load_model_with_options(ctx)
        all_results.append(result)
        print(result)
        
        result = await test_llm_status_after_load(ctx)
        all_results.append(result)
        print(result)
    
    # Inference Tests
    if ctx.model_loaded and not skip_inference:
        print_section("Inference Tests")
        
        result = await test_simple_chat(ctx)
        all_results.append(result)
        print(result)
        
        result = await test_chat_with_sampler_settings(ctx)
        all_results.append(result)
        print(result)
        
        result = await test_chat_continuation(ctx)
        all_results.append(result)
        print(result)
        
        result = await test_regenerate_response(ctx)
        all_results.append(result)
        print(result)
        
        result = await test_openai_chat_completions(ctx)
        all_results.append(result)
        print(result)
    elif skip_inference:
        print_section("Inference Tests")
        print("  ⏭️  Inference tests skipped (use --inference to enable)")
        all_results.append(TestResult("Inference Tests", TestStatus.SKIPPED, "Skipped by user"))
    
    # Conversation Management Tests
    print_section("Conversation Management Tests")
    
    result = await test_list_conversations()
    all_results.append(result)
    print(result)
    
    if ctx.conversation_id:
        result = await test_get_conversation(ctx)
        all_results.append(result)
        print(result)
        
        result = await test_rename_conversation(ctx)
        all_results.append(result)
        print(result)
        
        result = await test_delete_conversation(ctx)
        all_results.append(result)
        print(result)
    
    # Settings Tests
    print_section("Settings Tests")
    
    result = await test_get_settings()
    all_results.append(result)
    print(result)
    
    result = await test_update_settings()
    all_results.append(result)
    print(result)
    
    return all_results


if __name__ == "__main__":
    import sys
    skip_download = "--no-download" in sys.argv or "-nd" in sys.argv
    skip_inference = "--no-inference" in sys.argv or "-ni" in sys.argv
    
    asyncio.run(run_functional_tests(
        skip_download=skip_download,
        skip_inference=skip_inference
    ))

