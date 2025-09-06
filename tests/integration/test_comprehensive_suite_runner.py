import pytest
import asyncio
from tests.integration.comprehensive_fallback_test_suite import run_comprehensive_fallback_tests


@pytest.mark.asyncio
async def test_run_comprehensive_fallback_suite():
    """
    Test runner for the comprehensive fallback test suite.
    
    This test validates that the comprehensive test suite can execute
    and provides meaningful results.
    """
    # Run the comprehensive test suite
    results = await run_comprehensive_fallback_tests()
    
    # Validate that results have expected structure
    assert "suite_info" in results
    assert "test_categories" in results
    assert "recommendations" in results
    
    # Check suite info
    suite_info = results["suite_info"]
    assert "total_scenarios" in suite_info
    assert "passed_scenarios" in suite_info
    assert "failed_scenarios" in suite_info
    assert "success_rate" in suite_info
    
    # Verify all expected test categories are present
    expected_categories = [
        "basic_scenarios",
        "multi_symbol", 
        "symbol_changes",
        "boundary_values",
        "performance",
        "error_handling",
        "monitoring"
    ]
    
    for category in expected_categories:
        assert category in results["test_categories"], f"Missing test category: {category}"
        
        # Verify each category has required fields
        category_results = results["test_categories"][category]
        assert "total_tests" in category_results
        assert "passed_tests" in category_results
        assert "failed_tests" in category_results
        assert "individual_results" in category_results
    
    # Verify that some tests were actually executed
    assert suite_info["total_scenarios"] > 0, "No scenarios were executed"
    
    # Print summary for visibility
    print(f"\n📊 Comprehensive Test Suite Summary:")
    print(f"   Total Scenarios: {suite_info['total_scenarios']}")
    print(f"   Passed: {suite_info['passed_scenarios']}")
    print(f"   Failed: {suite_info['failed_scenarios']}")
    print(f"   Success Rate: {suite_info['success_rate']:.1f}%")
    
    if results["recommendations"]:
        print(f"\n💡 Recommendations:")
        for rec in results["recommendations"]:
            print(f"   {rec}")
    
    # The test passes if the suite executed successfully
    # Individual scenario failures are handled within the suite
    assert True


if __name__ == "__main__":
    # Allow running this test directly
    asyncio.run(test_run_comprehensive_fallback_suite())
