#!/usr/bin/env python3
"""
Personal Assistant - Comprehensive Test Suite Runner

This script runs all tests for the Personal Assistant services.
It checks service health, API endpoints, and integration scenarios.

Usage:
    python -m tests.run_tests              # Run all tests
    python -m tests.run_tests --health     # Only run health checks
    python -m tests.run_tests --gateway    # Only test gateway
    python -m tests.run_tests --quick      # Quick health checks only
    python -m tests.run_tests --verbose    # Show detailed output
"""
import asyncio
import argparse
import sys
from typing import List
from datetime import datetime

from .utils import TestResult, TestStatus, print_header, print_results_summary
from .test_services_health import test_all_services_health
from .test_gateway_api import run_all_gateway_tests
from .test_memory_api import run_all_memory_tests
from .test_tools_api import run_all_tools_tests
from .test_tts_services import run_all_tts_tests
from .test_stt_service import run_all_stt_tests
from .test_integration import run_all_integration_tests
from .test_functional import run_functional_tests
from .test_full_functional import run_full_functional_tests


async def run_all_tests(
    health_only: bool = False,
    gateway_only: bool = False,
    memory_only: bool = False,
    tools_only: bool = False,
    integration_only: bool = False,
    functional_only: bool = False,
    full_functional: bool = False,
    skip_download: bool = True,
    skip_inference: bool = True,
    use_gpu: bool = True,
    verbose: bool = False
) -> List[TestResult]:
    """Run all tests and return results."""
    all_results: List[TestResult] = []
    
    print_header("PERSONAL ASSISTANT TEST SUITE")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # For full_functional mode, skip initial health checks (we'll start services ourselves)
    if full_functional:
        # Run full functional tests with proper service management
        full_results = await run_full_functional_tests(
            use_gpu=use_gpu,
            skip_inference=skip_inference
        )
        all_results.extend(full_results)
        return all_results
    
    # Run health checks first for other modes
    health_results = await test_all_services_health()
    all_results.extend(health_results)
    
    if health_only:
        return all_results
    
    # Determine which services are healthy for conditional testing
    healthy_services = {
        r.name.split(": ")[1] 
        for r in health_results 
        if r.status == TestStatus.PASSED
    }
    
    # Run individual service tests based on flags
    if gateway_only:
        if "API Gateway" in healthy_services:
            gateway_results = await run_all_gateway_tests(skip_if_unhealthy=True)
            all_results.extend(gateway_results)
        else:
            print("\n⚠️ Gateway is not healthy - skipping gateway tests")
        return all_results
    
    if memory_only:
        if "Memory Service" in healthy_services:
            memory_results = await run_all_memory_tests(skip_if_unhealthy=True)
            all_results.extend(memory_results)
        else:
            print("\n⚠️ Memory Service is not healthy - skipping memory tests")
        return all_results
    
    if tools_only:
        if "Tool Service" in healthy_services:
            tools_results = await run_all_tools_tests(skip_if_unhealthy=True)
            all_results.extend(tools_results)
        else:
            print("\n⚠️ Tool Service is not healthy - skipping tools tests")
        return all_results
    
    if integration_only:
        integration_results = await run_all_integration_tests()
        all_results.extend(integration_results)
        return all_results
    
    if functional_only:
        functional_results = await run_functional_tests(
            skip_download=skip_download,
            skip_inference=skip_inference
        )
        all_results.extend(functional_results)
        return all_results
    
    if full_functional:
        # Run full functional tests with proper service management
        full_results = await run_full_functional_tests(
            use_gpu=use_gpu,
            skip_inference=skip_inference
        )
        all_results.extend(full_results)
        return all_results
    
    # Run all tests if no specific flag is set
    
    # Gateway tests (if healthy)
    if "API Gateway" in healthy_services:
        gateway_results = await run_all_gateway_tests(skip_if_unhealthy=True)
        all_results.extend(gateway_results)
    else:
        print("\n⚠️ Gateway is not healthy - skipping gateway API tests")
    
    # Memory tests (if healthy)
    if "Memory Service" in healthy_services:
        memory_results = await run_all_memory_tests(skip_if_unhealthy=True)
        all_results.extend(memory_results)
    
    # Tools tests (if healthy)  
    if "Tool Service" in healthy_services:
        tools_results = await run_all_tools_tests(skip_if_unhealthy=True)
        all_results.extend(tools_results)
    
    # TTS tests (optional services)
    tts_results = await run_all_tts_tests()
    all_results.extend(tts_results)
    
    # STT tests (optional service)
    stt_results = await run_all_stt_tests()
    all_results.extend(stt_results)
    
    # Integration tests (only if gateway is healthy)
    if "API Gateway" in healthy_services:
        integration_results = await run_all_integration_tests()
        all_results.extend(integration_results)
    
    return all_results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Personal Assistant Comprehensive Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m tests.run_tests              # Run all tests
    python -m tests.run_tests --health     # Only run health checks
    python -m tests.run_tests --gateway    # Only test gateway API
    python -m tests.run_tests --memory     # Only test memory service
    python -m tests.run_tests --tools      # Only test tools service
    python -m tests.run_tests --verbose    # Show detailed output
        """
    )
    
    parser.add_argument("--health", "-H", action="store_true", 
                       help="Only run health checks")
    parser.add_argument("--gateway", "-g", action="store_true",
                       help="Only test gateway API")
    parser.add_argument("--memory", "-m", action="store_true",
                       help="Only test memory service")
    parser.add_argument("--tools", "-t", action="store_true",
                       help="Only test tools service")
    parser.add_argument("--integration", "-i", action="store_true",
                       help="Only run integration tests")
    parser.add_argument("--functional", "-f", action="store_true",
                       help="Run functional tests (model loading, inference, etc.)")
    parser.add_argument("--download", "-d", action="store_true",
                       help="Enable model downloading in functional tests")
    parser.add_argument("--inference", "-I", action="store_true",
                       help="Enable inference tests in functional tests")
    parser.add_argument("--full", "-F", action="store_true",
                       help="Run full functional tests with service management, model loading, inference")
    parser.add_argument("--no-gpu", action="store_true",
                       help="Skip GPU tests (use CPU only)")
    parser.add_argument("--quick", "-q", action="store_true",
                       help="Quick mode - only health checks")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output")
    
    args = parser.parse_args()
    
    # Quick mode is alias for health-only
    if args.quick:
        args.health = True
    
    # Full mode enables full functional tests with service management
    full_functional = args.full
    
    # Determine skip flags
    # --full enables inference automatically
    skip_download = not args.download
    skip_inference = not args.inference and not args.full  # --full enables inference
    use_gpu = not getattr(args, 'no_gpu', False)
    
    # Run tests
    try:
        results = asyncio.run(run_all_tests(
            health_only=args.health,
            gateway_only=args.gateway,
            memory_only=args.memory,
            tools_only=args.tools,
            integration_only=args.integration,
            functional_only=args.functional,
            full_functional=full_functional,
            skip_download=skip_download,
            skip_inference=skip_inference,
            use_gpu=use_gpu,
            verbose=args.verbose
        ))
        
        # Print summary
        summary = print_results_summary(results)
        
        # Exit with appropriate code
        if summary["failed"] > 0:
            print("\n❌ SOME TESTS FAILED")
            sys.exit(1)
        else:
            print("\n✅ ALL TESTS PASSED")
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n\nTest run interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Test runner error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

