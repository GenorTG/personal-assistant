#!/usr/bin/env python3
"""
Full Functional Tests with Proper Service Management

These tests:
- Start services as background processes (non-blocking)
- Test actual model loading and inference
- Test GPU/CUDA support
- Clean up services after tests
"""
import asyncio
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .config import SERVICES
from .utils import TestResult, TestStatus, http_request, print_section, print_header
from .service_runner import service_runner


GATEWAY_URL = SERVICES["gateway"].base_url


@dataclass
class TestContext:
    """Shared context for tests."""
    model_id: Optional[str] = None
    model_loaded: bool = False
    conversation_id: Optional[str] = None
    gpu_available: bool = False
    services_started: List[str] = None
    
    def __post_init__(self):
        if self.services_started is None:
            self.services_started = []


# =============================================================================
# SETUP / TEARDOWN
# =============================================================================

async def setup_core_services() -> bool:
    """Start core services needed for testing."""
    print_section("Starting Core Services")
    
    # Start in dependency order: memory -> tools -> gateway
    services_to_start = ["memory", "tools", "gateway"]
    
    for service in services_to_start:
        if not await service_runner.start_service(service, wait_ready=True, timeout=60):
            print(f"❌ Failed to start {service}")
            return False
    
    return True


async def teardown_services():
    """Stop all services started by tests."""
    service_runner.stop_all()


# =============================================================================
# GPU/CUDA TESTS
# =============================================================================

async def test_cuda_availability() -> TestResult:
    """Test if CUDA/GPU is available using nvidia-smi (not gateway's Python).
    
    The gateway doesn't have PyTorch - CUDA is used by the LLM service.
    We check nvidia-smi directly to see if GPU is available.
    """
    import subprocess
    import shutil
    
    start_time = time.time()
    
    # Check nvidia-smi directly (more reliable than checking gateway's Python)
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return TestResult(
            "CUDA Availability",
            TestStatus.WARNING,
            "nvidia-smi not found",
            (time.time() - start_time) * 1000
        )
    
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        elapsed = (time.time() - start_time) * 1000
        
        if result.returncode == 0 and result.stdout.strip():
            gpu_info = result.stdout.strip().split('\n')[0]
            parts = [p.strip() for p in gpu_info.split(',')]
            gpu_name = parts[0] if parts else "Unknown"
            gpu_memory = parts[1] if len(parts) > 1 else "?"
            
            return TestResult(
                "CUDA Availability",
                TestStatus.PASSED,
                f"GPU: {gpu_name} ({gpu_memory})",
                elapsed,
                {"gpu_name": gpu_name, "memory": gpu_memory}
            )
        else:
            return TestResult(
                "CUDA Availability",
                TestStatus.WARNING,
                "nvidia-smi returned no GPU info",
                elapsed
            )
    except subprocess.TimeoutExpired:
        return TestResult("CUDA Availability", TestStatus.WARNING, "nvidia-smi timeout", 5000)
    except Exception as e:
        return TestResult("CUDA Availability", TestStatus.WARNING, f"Error: {e}", 0)


async def test_system_status() -> TestResult:
    """Test system status including RAM/VRAM usage."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/system/status")
    
    if error:
        return TestResult("System Status", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("System Status", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    # Extract key info
    ram_used = data.get("ram_used_gb", 0) if data else 0
    vram_used = data.get("vram_used_gb", 0) if data else 0
    
    return TestResult(
        "System Status",
        TestStatus.PASSED,
        f"RAM: {ram_used:.1f}GB, VRAM: {vram_used:.1f}GB",
        time_ms
    )


# =============================================================================
# MODEL MANAGEMENT TESTS
# =============================================================================

async def test_list_models(ctx: TestContext) -> TestResult:
    """Test listing available models."""
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/models")
    
    if error:
        return TestResult("List Models", TestStatus.FAILED, error, time_ms)
    
    if status != 200:
        return TestResult("List Models", TestStatus.FAILED, f"HTTP {status}", time_ms)
    
    models = data if isinstance(data, list) else []
    
    if models:
        # Use first model for subsequent tests
        ctx.model_id = models[0].get("id") or models[0].get("name")
        model_names = [m.get("name", m.get("id", "?"))[:30] for m in models[:3]]
        return TestResult(
            "List Models",
            TestStatus.PASSED,
            f"Found {len(models)}: {', '.join(model_names)}",
            time_ms,
            {"models": models}
        )
    
    return TestResult(
        "List Models",
        TestStatus.WARNING,
        "No models found - download one first",
        time_ms
    )


async def test_load_model_cpu(ctx: TestContext) -> TestResult:
    """Test loading model on CPU."""
    if not ctx.model_id:
        return TestResult("Load Model (CPU)", TestStatus.SKIPPED, "No model available")
    
    import urllib.parse
    encoded_id = urllib.parse.quote(ctx.model_id, safe='')
    
    print(f"  ⏳ Loading model on CPU: {ctx.model_id[:50]}...")
    print(f"  ⏳ This may take several minutes for large models...")
    start_time = time.time()
    
    # Load with CPU settings
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/models/{encoded_id}/load",
        data={
            "n_gpu_layers": 0,  # CPU only
            "n_ctx": 2048,
            "n_threads": 4
        },
        timeout=300  # 5 minutes for model loading
    )
    
    elapsed = time.time() - start_time
    
    if error:
        print(f"  ❌ Load request failed: {error}")
        return TestResult("Load Model (CPU)", TestStatus.FAILED, error, elapsed * 1000)
    
    # Print the response for debugging
    print(f"  📡 Load response: HTTP {status}")
    if data:
        print(f"  📡 Response data: {str(data)[:200]}")
    
    if status not in [200, 202]:
        detail = data.get("detail", "") if data else ""
        print(f"  ❌ Load failed: {detail}")
        return TestResult("Load Model (CPU)", TestStatus.FAILED, f"HTTP {status}: {detail}", elapsed * 1000)
    
    print(f"  ✅ Load request accepted, waiting for LLM server...")
    
    # Wait for model to be fully loaded (LLM server startup can take a while)
    print(f"  ⏳ Waiting for LLM server to be ready...")
    last_status = None
    for i in range(180):  # Wait up to 3 minutes for server to be ready
        await asyncio.sleep(1)
        s, d, _, err = await http_request("GET", f"{GATEWAY_URL}/api/llm/status")
        
        # Print status changes for debugging
        current_status = str(d) if d else f"HTTP {s}, err={err}"
        if current_status != last_status:
            print(f"  📡 LLM status: {current_status[:100]}")
            last_status = current_status
        
        # Check if LLM server is running (model is loaded when server responds)
        if s == 200 and d and d.get("running"):
            # Double-check by hitting the LLM server's /v1/models endpoint
            llm_url = d.get("url", "http://127.0.0.1:8001")
            vs, vd, _, verr = await http_request("GET", f"{llm_url}/v1/models", timeout=5)
            if vs == 200:
                total_elapsed = time.time() - start_time
                ctx.model_loaded = True
                print(f"  ✅ LLM server is responding!")
                return TestResult(
                    "Load Model (CPU)",
                    TestStatus.PASSED,
                    f"Loaded in {total_elapsed:.1f}s",
                    total_elapsed * 1000
                )
        if i > 0 and i % 30 == 0:
            print(f"  ⏳ Still waiting... ({i}s elapsed)")
    
    total_elapsed = time.time() - start_time
    print(f"  ❌ Final LLM status: {last_status}")
    return TestResult("Load Model (CPU)", TestStatus.FAILED, f"Model loading timeout after {total_elapsed:.0f}s", total_elapsed * 1000)


async def test_load_model_gpu(ctx: TestContext) -> TestResult:
    """Test loading model on GPU (if available)."""
    if not ctx.model_id:
        return TestResult("Load Model (GPU)", TestStatus.SKIPPED, "No model available")
    
    if not ctx.gpu_available:
        return TestResult("Load Model (GPU)", TestStatus.SKIPPED, "No GPU available")
    
    import urllib.parse
    encoded_id = urllib.parse.quote(ctx.model_id, safe='')
    
    print(f"  ⏳ Loading model on GPU: {ctx.model_id[:50]}...")
    print(f"  ⏳ This may take a minute or two...")
    start_time = time.time()
    
    # Load with GPU settings
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/models/{encoded_id}/load",
        data={
            "n_gpu_layers": -1,  # All layers on GPU
            "n_ctx": 4096,
            "flash_attn": True  # Enable flash attention if available
        },
        timeout=300  # 5 minutes
    )
    
    elapsed = time.time() - start_time
    
    if error:
        print(f"  ❌ Load request failed: {error}")
        return TestResult("Load Model (GPU)", TestStatus.FAILED, error, elapsed * 1000)
    
    # Print the response for debugging
    print(f"  📡 Load response: HTTP {status}")
    if data:
        print(f"  📡 Response data: {str(data)[:200]}")
    
    if status not in [200, 202]:
        detail = data.get("detail", "") if data else ""
        print(f"  ❌ Load failed: {detail}")
        # GPU loading might fail if CUDA not properly configured
        if "cuda" in detail.lower() or "gpu" in detail.lower():
            return TestResult("Load Model (GPU)", TestStatus.WARNING, f"GPU error: {detail}", elapsed * 1000)
        return TestResult("Load Model (GPU)", TestStatus.FAILED, f"HTTP {status}: {detail}", elapsed * 1000)
    
    print(f"  ✅ Load request accepted, waiting for LLM server...")
    
    # Wait for model to be fully loaded (GPU loading is usually faster than CPU)
    print(f"  ⏳ Waiting for LLM server to be ready...")
    last_status = None
    for i in range(120):  # Wait up to 2 minutes
        await asyncio.sleep(1)
        s, d, _, err = await http_request("GET", f"{GATEWAY_URL}/api/llm/status")
        
        # Print status changes for debugging
        current_status = str(d) if d else f"HTTP {s}, err={err}"
        if current_status != last_status:
            print(f"  📡 LLM status: {current_status[:100]}")
            last_status = current_status
        
        # Check if LLM server is running (model is loaded when server responds)
        if s == 200 and d and d.get("running"):
            # Double-check by hitting the LLM server's /v1/models endpoint
            llm_url = d.get("url", "http://127.0.0.1:8001")
            vs, vd, _, verr = await http_request("GET", f"{llm_url}/v1/models", timeout=5)
            if vs == 200:
                total_elapsed = time.time() - start_time
                ctx.model_loaded = True
                print(f"  ✅ LLM server is responding!")
                
                # Get model details to verify GPU loading
                model_data = vd.get("data", []) if vd else []
                gpu_info = ""
                if model_data:
                    model_info = model_data[0]
                    print(f"  📊 Model info: {model_info}")
                
                # Also check /props endpoint for detailed GPU layer info
                ps, pd, _, _ = await http_request("GET", f"{llm_url}/props", timeout=5)
                if ps == 200 and pd:
                    n_gpu_layers = pd.get("n_gpu_layers", "?")
                    total_slots = pd.get("total_slots", "?")
                    print(f"  🎮 GPU Layers: {n_gpu_layers}")
                    print(f"  📦 Total Slots: {total_slots}")
                    gpu_info = f", GPU layers: {n_gpu_layers}"
                
                return TestResult(
                    "Load Model (GPU)",
                    TestStatus.PASSED,
                    f"Loaded on GPU in {total_elapsed:.1f}s{gpu_info}",
                    total_elapsed * 1000
                )
        if i > 0 and i % 30 == 0:
            print(f"  ⏳ Still waiting... ({i}s elapsed)")
    
    total_elapsed = time.time() - start_time
    print(f"  ❌ Final LLM status: {last_status}")
    return TestResult("Load Model (GPU)", TestStatus.FAILED, f"Model loading timeout after {total_elapsed:.0f}s", total_elapsed * 1000)


# =============================================================================
# INFERENCE TESTS
# =============================================================================

async def test_verify_gpu_loading(ctx: TestContext) -> TestResult:
    """Verify model is actually running on GPU by checking llama.cpp server info."""
    if not ctx.model_loaded:
        return TestResult("Verify GPU Loading", TestStatus.SKIPPED, "No model loaded")
    
    if not ctx.gpu_available:
        return TestResult("Verify GPU Loading", TestStatus.SKIPPED, "No GPU available")
    
    # Get LLM server URL
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/llm/status")
    if status != 200 or not data:
        return TestResult("Verify GPU Loading", TestStatus.FAILED, "Cannot get LLM status", time_ms)
    
    llm_url = data.get("url", "http://127.0.0.1:8001")
    
    # Check /props endpoint for GPU layer info
    ps, pd, _, _ = await http_request("GET", f"{llm_url}/props", timeout=5)
    if ps != 200 or not pd:
        return TestResult("Verify GPU Loading", TestStatus.WARNING, "Cannot get /props endpoint", time_ms)
    
    n_gpu_layers = pd.get("n_gpu_layers", 0)
    n_ctx = pd.get("default_generation_settings", {}).get("n_ctx", "?")
    
    print(f"  📊 Server Properties:")
    print(f"     GPU Layers: {n_gpu_layers}")
    print(f"     Context: {n_ctx}")
    
    # Check /health endpoint for slot info
    hs, hd, _, _ = await http_request("GET", f"{llm_url}/health", timeout=5)
    if hs == 200 and hd:
        slots_idle = hd.get("slots_idle", "?")
        slots_processing = hd.get("slots_processing", "?")
        print(f"     Slots: {slots_idle} idle, {slots_processing} processing")
    
    # Verify GPU is being used
    if n_gpu_layers == -1:
        return TestResult(
            "Verify GPU Loading",
            TestStatus.PASSED,
            f"All layers on GPU (n_gpu_layers=-1), ctx={n_ctx}",
            time_ms
        )
    elif n_gpu_layers > 0:
        return TestResult(
            "Verify GPU Loading",
            TestStatus.PASSED,
            f"{n_gpu_layers} layers on GPU, ctx={n_ctx}",
            time_ms
        )
    else:
        return TestResult(
            "Verify GPU Loading",
            TestStatus.WARNING,
            f"Model running on CPU (n_gpu_layers={n_gpu_layers})",
            time_ms
        )


async def test_simple_inference(ctx: TestContext) -> TestResult:
    """Test basic inference."""
    if not ctx.model_loaded:
        return TestResult("Simple Inference", TestStatus.SKIPPED, "No model loaded")
    
    print("  ⏳ Running inference...")
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/chat",
        data={
            "message": "Reply with exactly: TEST_OK",
            "max_tokens": 20,
            "temperature": 0.1
        },
        timeout=120
    )
    
    elapsed = time.time() - start_time
    
    if error:
        return TestResult("Simple Inference", TestStatus.FAILED, error, elapsed * 1000)
    
    if status != 200:
        detail = data.get("detail", "") if data else ""
        return TestResult("Simple Inference", TestStatus.FAILED, f"HTTP {status}: {detail}", elapsed * 1000)
    
    response = data.get("response", "") if data else ""
    ctx.conversation_id = data.get("conversation_id") if data else None
    tokens_per_sec = len(response.split()) / elapsed if elapsed > 0 else 0
    
    return TestResult(
        "Simple Inference",
        TestStatus.PASSED,
        f"Response in {elapsed:.1f}s (~{tokens_per_sec:.1f} tok/s): '{response[:50]}...'",
        elapsed * 1000
    )


async def test_streaming_inference(ctx: TestContext) -> TestResult:
    """Test streaming inference (if supported)."""
    if not ctx.model_loaded:
        return TestResult("Streaming Inference", TestStatus.SKIPPED, "No model loaded")
    
    # TODO: Implement streaming test when streaming endpoint is available
    return TestResult("Streaming Inference", TestStatus.SKIPPED, "Streaming not yet tested")


async def test_sampler_settings(ctx: TestContext) -> TestResult:
    """Test different sampler settings - comprehensive llama.cpp sampler coverage."""
    if not ctx.model_loaded:
        return TestResult("Sampler Settings", TestStatus.SKIPPED, "No model loaded")
    
    start_time = time.time()
    
    # Comprehensive sampler settings tests for llama.cpp
    settings_tests = [
        # Basic temperature/top_p
        {"name": "deterministic", "temperature": 0.0, "top_p": 1.0, "max_tokens": 10},
        {"name": "creative", "temperature": 1.5, "top_p": 0.5, "max_tokens": 10},
        
        # Top-K sampling
        {"name": "top_k=10", "temperature": 0.7, "top_k": 10, "max_tokens": 10},
        {"name": "top_k=100", "temperature": 0.7, "top_k": 100, "max_tokens": 10},
        
        # Min-P sampling (newer, often better than top_p)
        {"name": "min_p=0.05", "temperature": 0.7, "min_p": 0.05, "max_tokens": 10},
        {"name": "min_p=0.1", "temperature": 0.7, "min_p": 0.1, "max_tokens": 10},
        
        # Repeat penalty
        {"name": "repeat_penalty=1.0", "temperature": 0.7, "repeat_penalty": 1.0, "max_tokens": 10},
        {"name": "repeat_penalty=1.2", "temperature": 0.7, "repeat_penalty": 1.2, "max_tokens": 10},
        
        # Presence/Frequency penalties (OpenAI style)
        {"name": "presence_penalty=0.5", "temperature": 0.7, "presence_penalty": 0.5, "max_tokens": 10},
        {"name": "frequency_penalty=0.5", "temperature": 0.7, "frequency_penalty": 0.5, "max_tokens": 10},
        
        # Typical-P sampling
        {"name": "typical_p=0.9", "temperature": 0.7, "typical_p": 0.9, "max_tokens": 10},
        
        # Tail-Free Sampling (TFS)
        {"name": "tfs_z=0.95", "temperature": 0.7, "tfs_z": 0.95, "max_tokens": 10},
        
        # Mirostat (adaptive perplexity)
        {"name": "mirostat_v1", "mirostat_mode": 1, "mirostat_tau": 5.0, "mirostat_eta": 0.1, "max_tokens": 10},
        {"name": "mirostat_v2", "mirostat_mode": 2, "mirostat_tau": 5.0, "mirostat_eta": 0.1, "max_tokens": 10},
        
        # Combined settings
        {"name": "combined", "temperature": 0.8, "top_p": 0.9, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.1, "max_tokens": 10},
    ]
    
    results = []
    failed_settings = []
    
    print(f"  Testing {len(settings_tests)} sampler configurations...")
    
    for settings in settings_tests:
        name = settings.pop("name")
        status, data, _, err = await http_request(
            "POST",
            f"{GATEWAY_URL}/api/chat",
            data={"message": "Say hi", **settings},
            timeout=60
        )
        success = status == 200
        results.append(success)
        if not success:
            failed_settings.append(f"{name}: HTTP {status}")
            print(f"    ❌ {name}: HTTP {status}")
        else:
            print(f"    ✅ {name}")
    
    elapsed = time.time() - start_time
    
    passed = sum(results)
    total = len(results)
    
    if all(results):
        return TestResult(
            "Sampler Settings",
            TestStatus.PASSED,
            f"All {total} sampler configs work",
            elapsed * 1000
        )
    elif passed > total // 2:
        return TestResult(
            "Sampler Settings",
            TestStatus.WARNING,
            f"{passed}/{total} work. Failed: {', '.join(failed_settings[:3])}",
            elapsed * 1000
        )
    else:
        return TestResult(
            "Sampler Settings",
            TestStatus.FAILED,
            f"Only {passed}/{total} work. Failed: {', '.join(failed_settings[:3])}",
            elapsed * 1000
        )


async def test_conversation_context(ctx: TestContext) -> TestResult:
    """Test multi-turn conversation maintains context."""
    if not ctx.model_loaded:
        return TestResult("Conversation Context", TestStatus.SKIPPED, "No model loaded")
    
    # First message
    status1, data1, _, _ = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/chat",
        data={"message": "My name is TestUser. Remember it.", "max_tokens": 50},
        timeout=60
    )
    
    if status1 != 200:
        return TestResult("Conversation Context", TestStatus.FAILED, "First message failed")
    
    conv_id = data1.get("conversation_id") if data1 else None
    
    # Second message asking to recall
    status2, data2, time_ms, _ = await http_request(
        "POST",
        f"{GATEWAY_URL}/api/chat",
        data={
            "message": "What is my name?",
            "conversation_id": conv_id,
            "max_tokens": 30
        },
        timeout=60
    )
    
    if status2 != 200:
        return TestResult("Conversation Context", TestStatus.FAILED, "Second message failed")
    
    response = data2.get("response", "") if data2 else ""
    
    # Check if context was maintained (name mentioned)
    if "testuser" in response.lower() or "test" in response.lower():
        return TestResult(
            "Conversation Context",
            TestStatus.PASSED,
            f"Context maintained: '{response[:50]}'",
            time_ms
        )
    
    return TestResult(
        "Conversation Context",
        TestStatus.WARNING,
        f"Context may not be maintained: '{response[:50]}'",
        time_ms
    )


# =============================================================================
# OPENAI COMPATIBILITY TESTS
# =============================================================================

async def test_openai_chat_completions(ctx: TestContext) -> TestResult:
    """Test OpenAI-compatible chat completions endpoint."""
    if not ctx.model_loaded:
        return TestResult("OpenAI /v1/chat/completions", TestStatus.SKIPPED, "No model loaded")
    
    start_time = time.time()
    
    status, data, time_ms, error = await http_request(
        "POST",
        f"{GATEWAY_URL}/v1/chat/completions",
        data={
            "model": "default",
            "messages": [
                {"role": "user", "content": "Say 'test' only."}
            ],
            "max_tokens": 10,
            "temperature": 0.1
        },
        timeout=60
    )
    
    elapsed = time.time() - start_time
    
    if error:
        return TestResult("OpenAI /v1/chat/completions", TestStatus.FAILED, error, elapsed * 1000)
    
    if status == 503:
        return TestResult("OpenAI /v1/chat/completions", TestStatus.WARNING, "LLM service not running", elapsed * 1000)
    
    if status != 200:
        return TestResult("OpenAI /v1/chat/completions", TestStatus.FAILED, f"HTTP {status}", elapsed * 1000)
    
    # Verify OpenAI response format
    choices = data.get("choices", []) if data else []
    if not choices:
        return TestResult("OpenAI /v1/chat/completions", TestStatus.FAILED, "No choices", elapsed * 1000)
    
    content = choices[0].get("message", {}).get("content", "")
    
    return TestResult(
        "OpenAI /v1/chat/completions",
        TestStatus.PASSED,
        f"OpenAI format OK: '{content[:30]}'",
        elapsed * 1000
    )


# =============================================================================
# CLEANUP TESTS
# =============================================================================

async def test_unload_model(ctx: TestContext) -> TestResult:
    """Test unloading the model."""
    # Note: This would need an unload endpoint
    # For now, just verify we can check status
    status, data, time_ms, error = await http_request("GET", f"{GATEWAY_URL}/api/llm/status")
    
    if status == 200:
        is_running = data.get("running", False) if data else False
        return TestResult(
            "Check Model Status",
            TestStatus.PASSED,
            f"LLM server running: {is_running}",
            time_ms
        )
    
    return TestResult("Check Model Status", TestStatus.WARNING, f"HTTP {status}", time_ms)


# =============================================================================
# MAIN RUNNER
# =============================================================================

async def run_full_functional_tests(
    use_gpu: bool = True,
    skip_inference: bool = False
) -> List[TestResult]:
    """
    Run full functional tests with proper service management.
    
    Args:
        use_gpu: Whether to test GPU loading (if available)
        skip_inference: Skip inference tests (faster)
    """
    print_header("FULL FUNCTIONAL TESTS")
    print("⚠️  These tests start services, load models, and run inference.")
    print("⚠️  They will automatically clean up when done.\n")
    
    all_results: List[TestResult] = []
    ctx = TestContext()
    
    try:
        # Setup
        if not await setup_core_services():
            return [TestResult("Setup", TestStatus.FAILED, "Could not start services")]
        
        # GPU/System Tests
        print_section("System & GPU Tests")
        
        result = await test_cuda_availability()
        all_results.append(result)
        print(result)
        ctx.gpu_available = result.status == TestStatus.PASSED
        
        result = await test_system_status()
        all_results.append(result)
        print(result)
        
        # Model Tests
        print_section("Model Management Tests")
        
        result = await test_list_models(ctx)
        all_results.append(result)
        print(result)
        
        if not skip_inference and ctx.model_id:
            # Try GPU loading first if available and requested
            if use_gpu and ctx.gpu_available:
                result = await test_load_model_gpu(ctx)
                all_results.append(result)
                print(result)
            
            # If GPU loading failed or not available, try CPU
            if not ctx.model_loaded:
                result = await test_load_model_cpu(ctx)
                all_results.append(result)
                print(result)
        
        # Inference Tests
        if not skip_inference and ctx.model_loaded:
            print_section("Inference Tests")
            
            # First verify GPU loading if applicable
            if ctx.gpu_available:
                result = await test_verify_gpu_loading(ctx)
                all_results.append(result)
                print(result)
            
            result = await test_simple_inference(ctx)
            all_results.append(result)
            print(result)
            
            result = await test_sampler_settings(ctx)
            all_results.append(result)
            print(result)
            
            result = await test_conversation_context(ctx)
            all_results.append(result)
            print(result)
            
            result = await test_openai_chat_completions(ctx)
            all_results.append(result)
            print(result)
        elif skip_inference:
            print_section("Inference Tests")
            print("  ⏭️  Inference tests skipped")
            all_results.append(TestResult("Inference Tests", TestStatus.SKIPPED, "Skipped by user"))
        
        # Cleanup verification
        print_section("Cleanup")
        result = await test_unload_model(ctx)
        all_results.append(result)
        print(result)
        
    finally:
        # Always cleanup
        await teardown_services()
    
    return all_results


if __name__ == "__main__":
    import sys
    
    use_gpu = "--no-gpu" not in sys.argv
    skip_inference = "--no-inference" in sys.argv
    
    results = asyncio.run(run_full_functional_tests(
        use_gpu=use_gpu,
        skip_inference=skip_inference
    ))
    
    # Print summary
    from .utils import print_results_summary
    summary = print_results_summary(results)
    
    sys.exit(1 if summary["failed"] > 0 else 0)

