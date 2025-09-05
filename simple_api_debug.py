#!/usr/bin/env python3
"""
Simple API Structure Analysis and Debug Check
"""

import sys
from pathlib import Path

def check_api_structure():
    """Check API structure and potential issues"""
    
    print("=== FastAPI App Structure Analysis ===\n")
    
    # API Endpoints found via grep
    endpoints = [
        {"file": "coverage.py", "method": "GET", "path": "/coverage", "function": "get_coverage"},
        {"file": "coverage.py", "method": "GET", "path": "/coverage/export", "function": "export_coverage"},
        {"file": "symbols.py", "method": "GET", "path": "/symbols", "function": "list_symbols"},
        {"file": "router.py", "method": "GET", "path": "/health", "function": "v1_health"},
        {"file": "prices.py", "method": "GET", "path": "/prices", "function": "get_prices"},
        {"file": "prices.py", "method": "DELETE", "path": "/prices/{symbol}", "function": "delete_prices"},
        {"file": "fetch.py", "method": "POST", "path": "/fetch", "function": "create_fetch_job_endpoint"},
        {"file": "fetch.py", "method": "GET", "path": "/fetch/{job_id}", "function": "get_fetch_job_status"},
        {"file": "fetch.py", "method": "GET", "path": "/fetch", "function": "list_fetch_jobs"},
        {"file": "fetch.py", "method": "POST", "path": "/fetch/{job_id}/cancel", "function": "cancel_fetch_job"},
        {"file": "health.py", "method": "GET", "path": "/healthz", "function": "healthz"}
    ]
    
    print("🌐 API Endpoints Discovered:")
    print("=" * 60)
    
    for endpoint in endpoints:
        print(f"{endpoint['method']:6} /v1{endpoint['path']:25} [{endpoint['file']:12}] {endpoint['function']}")
    
    print(f"\nTotal Endpoints: {len(endpoints)}")
    
    # Group by functionality
    print("\n📋 Endpoints by Category:")
    print("=" * 40)
    
    categories = {
        "Health Checks": [],
        "Stock Prices": [],
        "Symbol Management": [],
        "Data Coverage": [],
        "Background Jobs": []
    }
    
    for endpoint in endpoints:
        if "health" in endpoint['path']:
            categories["Health Checks"].append(endpoint)
        elif "prices" in endpoint['path']:
            categories["Stock Prices"].append(endpoint)
        elif "symbols" in endpoint['path']:
            categories["Symbol Management"].append(endpoint)
        elif "coverage" in endpoint['path']:
            categories["Data Coverage"].append(endpoint)
        elif "fetch" in endpoint['path']:
            categories["Background Jobs"].append(endpoint)
    
    for category, eps in categories.items():
        if eps:
            print(f"\n{category}:")
            for ep in eps:
                print(f"  {ep['method']} /v1{ep['path']}")
    
    # Check for common issues
    print("\n🔍 Potential Issues Check:")
    print("=" * 40)
    
    # Check dependencies
    dep_issues = []
    
    # Check if main app imports the v1 router
    main_py = Path("app/main.py")
    if main_py.exists():
        try:
            with open(main_py, 'r') as f:
                main_content = f.read()
            
            if "from app.api.v1.router import router" not in main_content:
                dep_issues.append("❌ v1 router not imported in main.py")
            else:
                print("✅ v1 router properly imported in main.py")
                
            if "app.include_router(router)" not in main_content:
                dep_issues.append("❌ v1 router not included in main FastAPI app")
            else:
                print("✅ v1 router properly included in main app")
                
        except Exception as e:
            dep_issues.append(f"❌ Error reading main.py: {e}")
    else:
        dep_issues.append("❌ main.py not found")
    
    # Check router.py structure
    router_py = Path("app/api/v1/router.py")
    if router_py.exists():
        try:
            with open(router_py, 'r') as f:
                router_content = f.read()
            
            required_imports = [
                "from .coverage import router as coverage_router",
                "from .fetch import router as fetch_router",
                "from .prices import router as prices_router", 
                "from .symbols import router as symbols_router"
            ]
            
            missing_imports = []
            for req_import in required_imports:
                if req_import not in router_content:
                    missing_imports.append(req_import.split()[-1])
            
            if missing_imports:
                dep_issues.append(f"❌ Missing router imports: {', '.join(missing_imports)}")
            else:
                print("✅ All sub-routers properly imported")
                
        except Exception as e:
            dep_issues.append(f"❌ Error reading router.py: {e}")
    
    # Check for async/await consistency
    async_endpoints = []
    for endpoint in endpoints:
        file_path = Path(f"app/api/v1/{endpoint['file']}")
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                func_def = f"async def {endpoint['function']}"
                if func_def in content:
                    async_endpoints.append(endpoint)
            except:
                pass
    
    print(f"✅ Async endpoints: {len(async_endpoints)}/{len(endpoints)}")
    
    if dep_issues:
        print("\n⚠️  Dependency Issues Found:")
        for issue in dep_issues:
            print(f"  {issue}")
    else:
        print("\n✅ No major dependency issues detected")
    
    # Check for error handling
    print("\n🛡️ Error Handling Check:")
    error_patterns = [
        "HTTPException", "try:", "except", "raise"
    ]
    
    files_with_error_handling = []
    for endpoint in endpoints:
        file_path = Path(f"app/api/v1/{endpoint['file']}")
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                has_error_handling = any(pattern in content for pattern in error_patterns)
                if has_error_handling:
                    files_with_error_handling.append(endpoint['file'])
            except:
                pass
    
    unique_files = set(files_with_error_handling)
    total_files = set(ep['file'] for ep in endpoints)
    
    print(f"✅ Files with error handling: {len(unique_files)}/{len(total_files)}")
    
    files_without_errors = total_files - unique_files
    if files_without_errors:
        print(f"⚠️  Files without error handling: {', '.join(files_without_errors)}")

if __name__ == '__main__':
    check_api_structure()
