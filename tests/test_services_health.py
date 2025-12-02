"""Test service health endpoints."""
import asyncio
from typing import List

from .config import SERVICES, ServiceConfig
from .utils import TestResult, TestStatus, check_service_health, print_section


async def test_service_health(service_id: str, config: ServiceConfig) -> TestResult:
    """Test a single service's health endpoint."""
    is_healthy, message, time_ms = await check_service_health(
        config.base_url, 
        config.health_endpoint
    )
    
    if is_healthy:
        return TestResult(
            name=f"Health: {config.name}",
            status=TestStatus.PASSED,
            message=message,
            response_time_ms=time_ms
        )
    else:
        # If service is not required, mark as warning instead of failure
        status = TestStatus.FAILED if config.required else TestStatus.WARNING
        return TestResult(
            name=f"Health: {config.name}",
            status=status,
            message=message,
            response_time_ms=time_ms
        )


async def test_all_services_health() -> List[TestResult]:
    """Test health of all services."""
    print_section("Service Health Checks")
    
    results: List[TestResult] = []
    
    # Test all services in parallel
    tasks = [
        test_service_health(service_id, config) 
        for service_id, config in SERVICES.items()
    ]
    results = await asyncio.gather(*tasks)
    
    # Print results
    for result in results:
        print(result)
    
    return results


async def get_service_status() -> dict[str, bool]:
    """Get status of all services (for use by other test modules)."""
    status = {}
    for service_id, config in SERVICES.items():
        is_healthy, _, _ = await check_service_health(
            config.base_url,
            config.health_endpoint
        )
        status[service_id] = is_healthy
    return status


if __name__ == "__main__":
    results = asyncio.run(test_all_services_health())

