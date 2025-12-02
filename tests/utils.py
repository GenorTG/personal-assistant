"""Testing utilities."""
import asyncio
import aiohttp
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import time

from .config import REQUEST_TIMEOUT, HEALTH_CHECK_TIMEOUT


class TestStatus(Enum):
    """Test result status."""
    PASSED = "✅ PASSED"
    FAILED = "❌ FAILED"
    SKIPPED = "⏭️ SKIPPED"
    WARNING = "⚠️ WARNING"


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    status: TestStatus
    message: str = ""
    response_time_ms: float = 0
    details: Optional[Dict[str, Any]] = None
    
    def __str__(self) -> str:
        time_str = f" ({self.response_time_ms:.0f}ms)" if self.response_time_ms > 0 else ""
        msg_str = f" - {self.message}" if self.message else ""
        return f"{self.status.value} {self.name}{time_str}{msg_str}"


async def http_request(
    method: str,
    url: str,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = REQUEST_TIMEOUT
) -> Tuple[int, Optional[Dict[str, Any]], float, Optional[str]]:
    """
    Make an HTTP request and return (status_code, response_json, time_ms, error).
    """
    start_time = time.time()
    default_headers = {"Content-Type": "application/json"}
    if headers:
        default_headers.update(headers)
    
    try:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_obj) as session:
            async with session.request(
                method=method,
                url=url,
                json=data if method in ["POST", "PUT", "PATCH"] else None,
                params=data if method == "GET" and data else None,
                headers=default_headers
            ) as response:
                elapsed_ms = (time.time() - start_time) * 1000
                
                try:
                    response_data = await response.json()
                except:
                    response_data = None
                    
                return response.status, response_data, elapsed_ms, None
                
    except asyncio.TimeoutError:
        elapsed_ms = (time.time() - start_time) * 1000
        return 0, None, elapsed_ms, "Request timed out"
    except aiohttp.ClientConnectorError as e:
        elapsed_ms = (time.time() - start_time) * 1000
        return 0, None, elapsed_ms, f"Connection failed: {e}"
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        return 0, None, elapsed_ms, f"Request error: {e}"


async def check_service_health(base_url: str, health_endpoint: str) -> Tuple[bool, str, float]:
    """
    Check if a service is healthy.
    Returns (is_healthy, message, response_time_ms).
    """
    url = f"{base_url}{health_endpoint}"
    status, data, time_ms, error = await http_request("GET", url, timeout=HEALTH_CHECK_TIMEOUT)
    
    if error:
        return False, error, time_ms
    
    if status == 200:
        return True, "Healthy", time_ms
    else:
        return False, f"HTTP {status}", time_ms


def print_header(title: str, char: str = "=") -> None:
    """Print a formatted header."""
    line = char * 60
    print(f"\n{line}")
    print(f" {title}")
    print(f"{line}\n")


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n--- {title} ---\n")


def print_results_summary(results: list[TestResult]) -> Dict[str, int]:
    """Print a summary of test results and return counts."""
    passed = sum(1 for r in results if r.status == TestStatus.PASSED)
    failed = sum(1 for r in results if r.status == TestStatus.FAILED)
    skipped = sum(1 for r in results if r.status == TestStatus.SKIPPED)
    warnings = sum(1 for r in results if r.status == TestStatus.WARNING)
    
    print_header("TEST SUMMARY")
    print(f"  ✅ Passed:   {passed}")
    print(f"  ❌ Failed:   {failed}")
    print(f"  ⚠️ Warnings: {warnings}")
    print(f"  ⏭️ Skipped:  {skipped}")
    print(f"  ━━━━━━━━━━━━")
    print(f"  Total:      {len(results)}")
    
    if failed > 0:
        print("\n❌ FAILED TESTS:")
        for r in results:
            if r.status == TestStatus.FAILED:
                print(f"  • {r.name}: {r.message}")
    
    return {"passed": passed, "failed": failed, "skipped": skipped, "warnings": warnings}

